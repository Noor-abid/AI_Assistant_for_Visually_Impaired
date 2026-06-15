"""No-network local runner for development.

The production app uses FastAPI/Uvicorn. This lightweight runner uses only the
Python standard library so the interface and WebSocket contract can still be
verified in constrained environments where dependencies cannot be installed.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import mimetypes
import socketserver
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional, Tuple

from app.models import SessionState
from app.services.processor import process_control_message, process_frame, safe_send_json

ROOT = Path(__file__).resolve().parent
STATIC_ROOT = ROOT / "static"
TEMPLATE_ROOT = ROOT / "templates"
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class LocalWebSocket:
    def __init__(self, handler: BaseHTTPRequestHandler):
        self.handler = handler

    async def send_json(self, data):
        payload = json.dumps(data, separators=(",", ":")).encode("utf-8")
        self._send_frame(payload, opcode=0x1)

    def _send_frame(self, payload: bytes, opcode: int) -> None:
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(length)
        elif length < 65536:
            header.extend([126, (length >> 8) & 0xFF, length & 0xFF])
        else:
            header.append(127)
            header.extend(length.to_bytes(8, "big"))
        self.handler.wfile.write(bytes(header) + payload)
        self.handler.wfile.flush()


class Handler(BaseHTTPRequestHandler):
    server_version = "AssistiveVisionDev/0.1"

    def do_GET(self) -> None:
        if self.path == "/ws" and self.headers.get("Upgrade", "").lower() == "websocket":
            self._handle_websocket()
            return
        if self.path in {"/", "/index.html"}:
            self._send_file(TEMPLATE_ROOT / "index.html", "text/html; charset=utf-8")
            return
        if self.path.startswith("/static/"):
            requested = (ROOT / self.path.lstrip("/")).resolve()
            if STATIC_ROOT.resolve() not in requested.parents and requested != STATIC_ROOT.resolve():
                self.send_error(403)
                return
            self._send_file(requested)
            return
        self.send_error(404)

    def log_message(self, fmt: str, *args) -> None:
        print("%s - %s" % (self.address_string(), fmt % args))

    def _send_file(self, path: Path, content_type: Optional[str] = None) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return
        body = path.read_bytes()
        ctype = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _handle_websocket(self) -> None:
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self.send_error(400)
            return
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode("ascii")).digest()).decode("ascii")
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()

        state = SessionState()
        ws = LocalWebSocket(self)
        asyncio.run(safe_send_json(ws, {"type": "status", "status": "connected", "mode": state.mode}))

        while True:
            frame = self._read_frame()
            if frame is None:
                break
            opcode, payload = frame
            if opcode == 0x8:
                break
            if opcode == 0x9:
                ws._send_frame(payload, opcode=0xA)
                continue
            if opcode == 0x1:
                try:
                    data = json.loads(payload.decode("utf-8"))
                except json.JSONDecodeError:
                    asyncio.run(safe_send_json(ws, {"type": "error", "message": "Invalid control message."}))
                    continue
                asyncio.run(process_control_message(data, state, ws))
            elif opcode == 0x2:
                state.frames_received += 1
                asyncio.run(process_frame(payload, state, ws))

    def _read_exact(self, count: int) -> Optional[bytes]:
        try:
            data = self.rfile.read(count)
        except OSError:
            return None
        if len(data) != count:
            return None
        return data

    def _read_frame(self) -> Optional[Tuple[int, bytes]]:
        header = self._read_exact(2)
        if not header:
            return None
        first, second = header
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            raw = self._read_exact(2)
            if raw is None:
                return None
            length = int.from_bytes(raw, "big")
        elif length == 127:
            raw = self._read_exact(8)
            if raw is None:
                return None
            length = int.from_bytes(raw, "big")
        mask = self._read_exact(4) if masked else b""
        payload = self._read_exact(length)
        if payload is None:
            return None
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        return opcode, payload


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def main() -> None:
    host = "127.0.0.1"
    port = 5000
    with ReusableThreadingHTTPServer((host, port), Handler) as server:
        print(f"Serving local fallback at http://{host}:{port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
