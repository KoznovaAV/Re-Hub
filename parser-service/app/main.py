import json
import os
from email.errors import MessageError
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import NamedTemporaryFile
import threading


def _env_int(name, default):
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


MAX_PARSE_BYTES = 25 * 1024 * 1024
MAX_CONTEXT_BYTES = _env_int("PARSE_MAX_CONTEXT_BYTES", 64 * 1024)
MAX_MULTIPART_PARTS = _env_int("PARSE_MAX_MULTIPART_PARTS", 20)
MAX_ROWS = _env_int("PARSE_MAX_ROWS", 50_000)
MAX_CONCURRENT_REQUESTS = _env_int("PARSE_MAX_CONCURRENCY", 8)


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """HTTP-сервер с ограничением числа одновременно обрабатываемых запросов."""

    daemon_threads = True

    def __init__(self, *args, **kwargs):
        self._request_slots = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        self._request_slots.acquire()
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._request_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        self.timeout = 15
        super().setup()

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_parse(self):
        if self.headers.get_content_type() != "multipart/form-data":
            self.send_json(415, {"error": "expected_multipart"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= MAX_PARSE_BYTES:
            self.send_json(413, {"error": "file_too_large"})
            return

        try:
            raw = self.rfile.read(length)
        except TimeoutError:
            self.send_json(400, {"error": "incomplete_upload"})
            return
        if len(raw) != length:
            self.send_json(400, {"error": "incomplete_upload"})
            return

        try:
            message = BytesParser(policy=email_policy).parsebytes(
                b"Content-Type: " + self.headers.get("Content-Type", "").encode("latin-1")
                + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw
            )
        except (ValueError, TypeError, MessageError):
            self.send_json(400, {"error": "invalid_multipart"})
            return

        file_data = None
        file_name = ""
        context_text = None
        part_count = 0
        for part in message.iter_parts():
            part_count += 1
            if part_count > MAX_MULTIPART_PARTS:
                self.send_json(400, {"error": "invalid_multipart"})
                return
            name = part.get_param("name", header="content-disposition")
            payload = part.get_payload(decode=True)
            if name == "file" and payload is not None:
                file_name = part.get_filename() or ""
                file_data = payload
            elif name == "context" and payload is not None:
                if len(payload) > MAX_CONTEXT_BYTES:
                    self.send_json(413, {"error": "context_too_large"})
                    return
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
        except (TypeError, ValueError, RecursionError):
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
                result = parse_file(temp_name, context)
            elif kind == "snapshot":
                from customer_xlsx import parse_file
                result = parse_file(temp_name, context, max_rows=MAX_ROWS)
            else:
                self.send_json(422, {"error": "unsupported_file_kind"})
                return
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
        if self.path != "/probe":
            self.send_json(404, {"error": "not_found"})
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json(415, {"error": "expected_json"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError
            payload = json.loads(self.rfile.read(length))
        except (ValueError, TimeoutError):
            self.send_json(400, {"error": "invalid_json"})
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
    with BoundedThreadingHTTPServer((host, port), Handler) as server:
        print(f"Python probe listening on {host}:{port}", flush=True)
        server.serve_forever()
