"""Небольшой HTTP-контур для Python-парсера.

Два эндпоинта намеренно оставлены на стандартной библиотеке:

* ``GET /health`` и ``POST /probe`` — существующий smoke-проброс Go/Python.
* ``POST /parse`` — multipart-загрузка (``file`` + JSON ``context``),
  возвращающая ParserResult v1 для ``file_kind=snapshot``.

Парсер клиентов относится к отдельной задаче; пока его нет, эндпоинт
отвечает ``501`` для ``file_kind=clients``, а не делает вид, что разбирает файл.
"""

from email.message import Message
from email.parser import BytesHeaderParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import sys
import tempfile
import traceback

try:  # импорт пакета в тестах и при ``python -m app.main``
    from .customer_xlsx import parse_file
except ImportError:  # прямой запуск ``python main.py`` в контейнере
    from customer_xlsx import parse_file


def _env_int(name, default):
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


MAX_REQUEST_BYTES = _env_int("PARSE_MAX_REQUEST_BYTES", 32 * 1024 * 1024)
MAX_FILE_BYTES = _env_int("PARSE_MAX_FILE_BYTES", 20 * 1024 * 1024)
MAX_CONTEXT_BYTES = _env_int("PARSE_MAX_CONTEXT_BYTES", 64 * 1024)
MAX_ROWS = _env_int("PARSE_MAX_ROWS", 50_000)


def multipart_boundary(content_type):
    message = Message()
    message["Content-Type"] = content_type
    if message.get_content_type() != "multipart/form-data":
        raise ValueError("expected multipart/form-data")
    boundary = message.get_param("boundary")
    if not boundary:
        raise ValueError("multipart boundary is missing")
    try:
        return boundary.encode("latin-1")
    except UnicodeEncodeError:
        raise ValueError("multipart boundary must be ASCII")


def parse_multipart(content_type, body):
    """Вернуть поля формы как ``{name: bytes}`` без сторонних пакетов.

    Ручное разбиение используется вместо ``cgi`` (удалён из новых версий Python)
    и вместо декодирования payload через ``email``, потому что часть XLSX содержит
    двоичные байты, которые должны дойти без изменений.
    """
    boundary = multipart_boundary(content_type)
    delimiter = b"--" + boundary
    fields = {}
    for chunk in body.split(delimiter)[1:]:
        if chunk.startswith(b"--"):
            break
        if chunk.startswith(b"\r\n"):
            chunk = chunk[2:]
        elif chunk.startswith(b"\n"):
            chunk = chunk[1:]
        if chunk.endswith(b"\r\n"):
            chunk = chunk[:-2]
        elif chunk.endswith(b"\n"):
            chunk = chunk[:-1]
        if not chunk:
            continue
        if b"\r\n\r\n" in chunk:
            header_blob, payload = chunk.split(b"\r\n\r\n", 1)
        elif b"\n\n" in chunk:
            header_blob, payload = chunk.split(b"\n\n", 1)
        else:
            raise ValueError("multipart part has no headers")
        headers = BytesHeaderParser().parsebytes(header_blob + b"\r\n\r\n")
        name = headers.get_param("name", header="content-disposition")
        if not name:
            continue
        if name in fields:
            raise ValueError("duplicate multipart field")
        fields[name] = payload
    if not fields:
        raise ValueError("multipart body contains no fields")
    return fields


class FieldTooLarge(ValueError):
    """Текстовое поле multipart превысило транспортный лимит."""


def field_text(fields, name, limit):
    raw = fields.get(name)
    if raw is None:
        raise KeyError(name)
    if len(raw) > limit:
        raise FieldTooLarge(f"{name} is too large")
    try:
        return raw.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ValueError(f"{name} must be UTF-8") from exc


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

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"status": "ok", "service": "python"})
            return
        self.send_json(404, {"error": "not_found"})

    def do_POST(self):
        if self.path == "/probe":
            self.handle_probe()
            return
        if self.path == "/parse":
            self.handle_parse()
            return
        self.send_json(404, {"error": "not_found"})

    def handle_probe(self):
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

    def read_request_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError("Content-Length is required")
        if length > MAX_REQUEST_BYTES:
            raise OverflowError("request body is too large")
        body = self.rfile.read(length)
        if len(body) != length:
            raise ValueError("request body was truncated")
        return body

    def handle_parse(self):
        if self.headers.get_content_type() != "multipart/form-data":
            self.send_json(415, {"error": "expected_multipart"})
            return
        try:
            body = self.read_request_body()
        except OverflowError:
            self.send_json(413, {"error": "request_too_large", "limit_bytes": MAX_REQUEST_BYTES})
            return
        except (ValueError, TimeoutError) as exc:
            self.send_json(400, {"error": "invalid_request", "detail": str(exc)})
            return

        try:
            fields = parse_multipart(self.headers.get("Content-Type", ""), body)
        except ValueError as exc:
            self.send_json(400, {"error": "invalid_multipart", "detail": str(exc)})
            return

        try:
            context_text = field_text(fields, "context", MAX_CONTEXT_BYTES)
        except KeyError:
            self.send_json(400, {"error": "missing_context"})
            return
        except FieldTooLarge as exc:
            self.send_json(413, {"error": "context_too_large", "detail": str(exc)})
            return
        except ValueError as exc:
            self.send_json(400, {"error": "invalid_context", "detail": str(exc)})
            return
        try:
            context = json.loads(context_text)
        except json.JSONDecodeError:
            self.send_json(400, {"error": "invalid_context", "detail": "context must be JSON"})
            return
        if not isinstance(context, dict):
            self.send_json(400, {"error": "invalid_context", "detail": "context must be an object"})
            return

        file_kind = context.get("file_kind")
        if file_kind == "clients":
            self.send_json(501, {"error": "clients_parser_not_implemented"})
            return
        if file_kind != "snapshot":
            self.send_json(400, {"error": "invalid_context", "detail": "unsupported file_kind"})
            return

        file_bytes = fields.get("file")
        if file_bytes is None:
            self.send_json(400, {"error": "missing_file"})
            return
        if not file_bytes:
            self.send_json(400, {"error": "empty_file"})
            return
        if len(file_bytes) > MAX_FILE_BYTES:
            self.send_json(413, {"error": "file_too_large", "limit_bytes": MAX_FILE_BYTES})
            return

        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(prefix="rehub-parse-", suffix=".xlsx",
                                             delete=False) as temporary:
                temporary.write(file_bytes)
                temporary_path = temporary.name
            try:
                result = parse_file(temporary_path, context, max_rows=MAX_ROWS)
            except ValueError as exc:
                self.send_json(400, {"error": "invalid_context", "detail": str(exc)})
                return
            status = 422 if any(error["code"] == "ROW_LIMIT_EXCEEDED"
                                for error in result["errors"]) else 200
            self.send_json(status, result)
        except (OSError, TimeoutError):
            self.send_json(503, {"error": "parser_unavailable"})
        except Exception:
            traceback.print_exc(file=sys.stderr)
            self.send_json(500, {"error": "internal_error"})
        finally:
            if temporary_path:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass


if __name__ == "__main__":
    host = os.environ.get("PYTHON_HOST", "127.0.0.1")
    port = int(os.environ.get("PYTHON_PORT", "8001"))
    with ThreadingHTTPServer((host, port), Handler) as server:
        print(f"Python probe listening on {host}:{port}", flush=True)
        server.serve_forever()
