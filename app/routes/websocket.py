"""WebSocket session orchestration."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.models import SessionState
from app.services.processor import process_control_message, process_frame, safe_send_json

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    state = SessionState()
    frame_ready = asyncio.Event()

    async def processor_loop() -> None:
        while True:
            try:
                await frame_ready.wait()
                frame_ready.clear()
                if not state.latest_frame or state.is_processing:
                    continue
                frame = state.latest_frame
                state.latest_frame = None
                state.is_processing = True
                try:
                    await process_frame(frame, state, websocket)
                finally:
                    state.is_processing = False
                    if state.latest_frame:
                        frame_ready.set()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logging.exception("Frame processor failed: %s", exc)
                state.is_processing = False

    task = asyncio.create_task(processor_loop())
    await safe_send_json(websocket, {"type": "status", "status": "connected", "mode": state.mode})

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if "bytes" in message:
                payload = message["bytes"]
                state.frames_received += 1
                if state.is_processing:
                    state.frames_skipped += 1
                state.latest_frame = payload
                frame_ready.set()
            elif "text" in message:
                await _handle_text(message["text"], state, websocket)
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def _handle_text(raw_text: str, state: SessionState, websocket: WebSocket) -> None:
    try:
        data: Dict[str, Any] = json.loads(raw_text)
    except json.JSONDecodeError:
        await safe_send_json(websocket, {"type": "error", "message": "Invalid control message."})
        return
    await process_control_message(data, state, websocket)

