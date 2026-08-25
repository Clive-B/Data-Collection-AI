from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .database import connect
from .query import ask


STATIC_ROOT = Path(__file__).resolve().with_name("static")


def serve(database_path: str | Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    database = str(Path(database_path).resolve())

    class Handler(BaseHTTPRequestHandler):
        server_version = "TelecomAI/0.1"

        def _security_headers(self) -> None:
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
            )

        def _json(self, status: HTTPStatus, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self._security_headers()
            self.end_headers()
            self.wfile.write(body)

        def _static(self, relative_path: str, *, cache: bool = True) -> None:
            try:
                target = (STATIC_ROOT / relative_path).resolve()
                target.relative_to(STATIC_ROOT)
                body = target.read_bytes()
            except (ValueError, OSError):
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith("text/") else content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=300" if cache else "no-store")
            self._security_headers()
            self.end_headers()
            self.wfile.write(body)

        def _stats(self) -> dict:
            with connect(database, readonly=True) as connection:
                return {
                    "workbooks": connection.execute("SELECT COUNT(*) FROM source_workbooks").fetchone()[0],
                    "metrics": connection.execute("SELECT COUNT(*) FROM metrics").fetchone()[0],
                    "observations": connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0],
                    "numeric_observations": connection.execute(
                        "SELECT COUNT(*) FROM observations WHERE value_status = 'numeric'"
                    ).fetchone()[0],
                    "quality_issues": connection.execute("SELECT COUNT(*) FROM quality_issues").fetchone()[0],
                    "operators": [
                        row[0] for row in connection.execute("SELECT DISTINCT operator FROM observations ORDER BY operator")
                    ],
                    "period": {
                        "first": connection.execute("SELECT MIN(period) FROM observations").fetchone()[0],
                        "last": connection.execute("SELECT MAX(period) FROM observations").fetchone()[0],
                    },
                }

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._static("index.html", cache=False)
                return
            if parsed.path.startswith("/static/"):
                self._static(parsed.path.removeprefix("/static/"))
                return
            if parsed.path in {"/health", "/api/health"}:
                self._json(HTTPStatus.OK, {"status": "ok", "data_transfer": "none"})
                return
            if parsed.path in {"/stats", "/api/stats"}:
                self._json(HTTPStatus.OK, self._stats())
                return
            if parsed.path in {"/ask", "/api/ask"}:
                question = parse_qs(parsed.query).get("q", [""])[0]
                with connect(database) as connection:
                    self._json(HTTPStatus.OK, ask(connection, question))
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path not in {"/ask", "/api/ask"}:
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
