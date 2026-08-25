from __future__ import annotations

import hmac
import json
import mimetypes
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .analytics import analyze_question, metric_catalogue, quality_summary
from .database import connect
from .openapi import action_schema
from .query import ask


STATIC_ROOT = Path(__file__).resolve().with_name("static")
MAX_REQUEST_BYTES = 16_384


def serve(database_path: str | Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    database = str(Path(database_path).resolve())
    api_key = os.environ.get("TELECOM_API_KEY", "").strip()
    public_base_url = os.environ.get(
        "TELECOM_PUBLIC_BASE_URL", "https://YOUR-APPROVED-AFRICAN-HOST.example"
    ).strip()
    if host not in {"127.0.0.1", "localhost", "::1"} and not api_key:
        raise RuntimeError("TELECOM_API_KEY is required when binding beyond localhost.")

    class Handler(BaseHTTPRequestHandler):
        server_version = "TelecomAI/1.0"

        def _security_headers(self) -> None:
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
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
            self.send_header(
                "Content-Type",
                f"{content_type}; charset=utf-8" if content_type.startswith("text/") else content_type,
            )
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=300" if cache else "no-store")
            self._security_headers()
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self, path: str) -> bool:
            public_paths = {"/health", "/api/health", "/api/v1/health", "/openapi.json", "/api/v1/openapi.json"}
            protected = path.startswith("/api/") or path in {"/ask", "/stats"}
            if path in public_paths or not protected:
                return True
            if not api_key:
                return True
            supplied = self.headers.get("X-API-Key", "")
            authorization = self.headers.get("Authorization", "")
            if authorization.lower().startswith("bearer "):
                supplied = authorization[7:].strip()
            if hmac.compare_digest(supplied, api_key):
                return True
            self._json(
                HTTPStatus.UNAUTHORIZED,
                {"error": "unauthorized", "message": "A valid API credential is required."},
            )
            return False

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
                        row[0]
                        for row in connection.execute(
                            "SELECT DISTINCT operator FROM observations ORDER BY operator"
                        )
                    ],
                    "period": {
                        "first": connection.execute("SELECT MIN(period) FROM observations").fetchone()[0],
                        "last": connection.execute("SELECT MAX(period) FROM observations").fetchone()[0],
                    },
                }

        def _health(self) -> dict:
            return {
                "status": "ok",
                "service": "adinkra-omega-telecom-analytics",
                "authentication_enforced": bool(api_key),
                "local_processing": True,
                "external_transfer": "only_when_called_through_an_external_action",
                "residency_verified": False,
                "human_authority": "required_for_consequential_decisions",
            }

        def _read_question(self) -> str:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > MAX_REQUEST_BYTES:
                    raise ValueError("request_too_large")
                payload = json.loads(self.rfile.read(length) or b"{}")
                question = payload.get("question")
                if not isinstance(question, str) or not question.strip():
                    raise ValueError("question_required")
                return question.strip()
            except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
                raise ValueError(str(error)) from error

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            if not self._authorized(path):
                return
            if path == "/":
                self._static("index.html", cache=False)
                return
            if path == "/privacy":
                self._static("privacy.html", cache=False)
                return
            if path.startswith("/static/"):
                self._static(path.removeprefix("/static/"))
                return
            if path in {"/openapi.json", "/api/v1/openapi.json"}:
                self._json(HTTPStatus.OK, action_schema(public_base_url))
                return
            if path in {"/health", "/api/health", "/api/v1/health"}:
                self._json(HTTPStatus.OK, self._health())
                return
            if path in {"/stats", "/api/stats"}:
                self._json(HTTPStatus.OK, self._stats())
                return
            if path == "/api/v1/metrics":
                try:
                    limit = int(parse_qs(parsed.query).get("limit", ["200"])[0])
                except ValueError:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_limit"})
                    return
                with connect(database, readonly=True) as connection:
                    self._json(HTTPStatus.OK, metric_catalogue(connection, limit))
                return
            if path == "/api/v1/quality":
                with connect(database, readonly=True) as connection:
                    self._json(HTTPStatus.OK, quality_summary(connection))
                return
            if path in {"/ask", "/api/ask"}:
                question = parse_qs(parsed.query).get("q", [""])[0]
                with connect(database) as connection:
                    self._json(HTTPStatus.OK, ask(connection, question))
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if not self._authorized(path):
                return
            if path not in {"/ask", "/api/ask", "/api/analysis", "/api/v1/analysis/query"}:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            try:
                question = self._read_question()
            except ValueError as error:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "invalid_request", "message": str(error) or "A question is required."},
                )
                return
            with connect(database) as connection:
                response = (
                    analyze_question(connection, question)
                    if path in {"/api/analysis", "/api/v1/analysis/query"}
                    else ask(connection, question)
                )
                if path == "/api/v1/analysis/query":
                    response.pop("chart_svg", None)
                self._json(HTTPStatus.OK, response)

        def log_message(self, format: str, *args: object) -> None:
            return

    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Telecom AI listening on http://{host}:{port}")
    print(f"GPT Action schema: http://{host}:{port}/openapi.json")
    print("Local-development server only; press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
