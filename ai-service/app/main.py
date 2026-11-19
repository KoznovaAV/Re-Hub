import json
import os
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import NamedTemporaryFile


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        self.timeout = 3
        super().setup()

    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_query(self, payload):
        # Обычный образ для /probe не содержит модулей демо.
        from ai_query import answer
        from ml_intent import InvalidProviderResponse, IntentError, ProviderError, ProviderTimeout, QuestionError

        if (not isinstance(payload, dict) or set(payload) - {"query", "client_external_id"}
                or not isinstance(payload.get("client_external_id", ""), str)):
            self.send_json(422, {"error": "invalid_query"})
            return
        try:
            result = answer(payload.get("query"), payload.get("client_external_id"))
        except QuestionError:
            self.send_json(422, {"error": "invalid_query"})
        except (IntentError, ProviderError) as exc:
            # В логи идут типы ошибок, без вопроса и сырого ответа модели.
            cause = type(exc.__cause__).__name__ if exc.__cause__ else "none"
            self.log_error("AI query failed: %s: %s (cause: %s)", type(exc).__name__, exc, cause)
            if isinstance(exc, ProviderTimeout):
                self.send_json(504, {"error": "ollama_timeout"})
            elif isinstance(exc, (IntentError, InvalidProviderResponse)):
                self.send_json(502, {"error": "ollama_invalid_response"})
            else:
                self.send_json(502, {"error": "ollama_unavailable"})
        else:
            self.send_json(200, result)

    def handle_parse(self):
        if self.headers.get_content_type() != "multipart/form-data":
            self.send_json(415, {"error": "expected_multipart"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= 25 * 1024 * 1024:
            self.send_json(413, {"error": "file_too_large"})
            return

        raw = self.rfile.read(length)
        message = BytesParser(policy=email_policy).parsebytes(
            b"Content-Type: " + self.headers.get("Content-Type", "").encode("latin-1")
            + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw
        )
        file_data = None
        file_name = ""
        context_text = None
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            payload = part.get_payload(decode=True)
            if name == "file" and payload is not None:
                file_name = part.get_filename() or ""
                file_data = payload
            elif name == "context" and payload is not None:
                context_text = payload.decode("utf-8", errors="replace")
        if file_data is None or context_text is None:
            self.send_json(400, {"error": "file_and_context_required"})
            return

        suffix = Path(file_name).suffix.lower()
        if suffix != ".xlsx":
            self.send_json(422, {"error": "xlsx_required"})
            return

        try:
            context = json.loads(context_text)
        except (TypeError, ValueError):
            self.send_json(422, {"error": "invalid_context"})
            return
        if not isinstance(context, dict):
            self.send_json(422, {"error": "invalid_context"})
            return

        kind = context.get("file_kind")
        temp_name = None
        try:
            with NamedTemporaryFile(delete=False, suffix=".xlsx") as temp:
                temp.write(file_data)
                temp_name = temp.name
            if kind == "clients":
                from customer_clients import parse_file
            elif kind == "snapshot":
                from customer_xlsx import parse_file
            else:
                self.send_json(422, {"error": "unsupported_file_kind"})
                return
            result = parse_file(temp_name, context)
            self.send_json(200, result)
        except ValueError as exc:
            self.send_json(422, {"error": "invalid_context", "message": str(exc)})
        finally:
            if temp_name:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"status": "ok", "service": "python"})
            return
        self.send_json(404, {"error": "not_found"})

    def do_POST(self):
        if self.path == "/parse":
            self.handle_parse()
            return
        is_query = self.path == "/ai/query" and os.environ.get("REHUB_AI_DEMO") == "1"
        if self.path != "/probe" and not is_query:
            self.send_json(404, {"error": "not_found"})
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json(415, {"error": "expected_json"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= (32768 if is_query else 4096):
                raise ValueError
            payload = json.loads(self.rfile.read(length))
        except (ValueError, TimeoutError):
            self.send_json(400, {"error": "invalid_json"})
            return
        if is_query:
            self.handle_query(payload)
            return
        if (
            not isinstance(payload, dict)
            or set(payload) != {"schema_version", "request_id"}
            or type(payload["schema_version"]) is not int
            or payload["schema_version"] != 1
            or not isinstance(payload["request_id"], str)
            or not payload["request_id"].strip()
        ):
            self.send_json(400, {"error": "invalid_probe"})
            return
        self.send_json(200, {**payload, "status": "ok"})


if __name__ == "__main__":
    host = os.environ.get("PYTHON_HOST", "127.0.0.1")
    port = int(os.environ.get("PYTHON_PORT", "8001"))
    with ThreadingHTTPServer((host, port), Handler) as server:
        print(f"Python probe listening on {host}:{port}", flush=True)
        server.serve_forever()
