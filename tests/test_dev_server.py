import base64
import hashlib
import os
import socket
import threading
import time
import unittest
import urllib.request

from dev_server import GUID, Handler, ReusableThreadingHTTPServer


class DevServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ReusableThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_serves_app_shell_and_static_js(self):
        for path in ["/", "/static/js/main.js"]:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=3) as response:
                body = response.read()
            self.assertEqual(response.status, 200)
            self.assertGreater(len(body), 100)

    def test_websocket_upgrade(self):
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        expected = base64.b64encode(hashlib.sha1((key + GUID).encode("ascii")).digest()).decode("ascii")
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=3)
        try:
            request = (
                "GET /ws HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{self.port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            )
            sock.sendall(request.encode("ascii"))
            response = sock.recv(1024).decode("latin1")
        finally:
            sock.close()
        self.assertIn("101 Switching Protocols", response)
        self.assertIn(expected, response)


if __name__ == "__main__":
    unittest.main()

