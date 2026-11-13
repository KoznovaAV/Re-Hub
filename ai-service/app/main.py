import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


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
        from ai_query import answer
        from ml_intent import IntentError, ProviderError, QuestionError

        if (not isinstance(payload, dict) or set(payload) - {"query", "client_external_id"}
                or not isinstance(payload.get("client_external_id", ""), str)):
            self.send_json(422, {"error": "invalid_query"})
            return
        try:
            result = answer(payload.get("query"), payload.get("client_external_id"))
        except QuestionError:
            self.send_json(422, {"error": "invalid_query"})
        except (IntentError, ProviderError):
            self.send_json(502, {"error": "model_unavailable_or_invalid"})
        else:
            self.send_json(200, result)

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"status": "ok", "service": "python"})
            return
        self.send_json(404, {"error": "not_found"})

    def do_POST(self):
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
