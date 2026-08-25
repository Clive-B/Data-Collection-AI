from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .database import connect
from .query import ask


def serve(database_path: str | Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    database = str(Path(database_path).resolve())

    class Handler(BaseHTTPRequestHandler):
        server_version = "TelecomAI/0.1"

        def _json(self, status: HTTPStatus, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._json(HTTPStatus.OK, {"status": "ok", "data_transfer": "none"})
                return
            if parsed.path == "/ask":
                question = parse_qs(parsed.query).get("q", [""])[0]
                with connect(database) as connection:
                    self._json(HTTPStatus.OK, ask(connection, question))
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/ask":
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 16_384:
                    raise ValueError("request_too_large")
                payload = json.loads(self.rfile.read(length) or b"{}")
                question = str(payload.get("question", ""))
            except (ValueError, json.JSONDecodeError):
                self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
                return
            with connect(database) as connection:
                self._json(HTTPStatus.OK, ask(connection, question))

        def log_message(self, format: str, *args: object) -> None:
            return

    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Telecom AI listening on http://{host}:{port}")
    print("Local-development server only; press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

