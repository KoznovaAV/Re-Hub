import http.client
import json
from pathlib import Path
import threading
import unittest
from http.server import ThreadingHTTPServer

from app import main

FIXTURES = Path(__file__).parent / "fixtures" / "snapshot"
BOUNDARY = "----rehub-test-boundary-7f90a7"


def multipart(fields):
    chunks = []
    for name, value, filename in fields:
        if isinstance(value, str):
            value = value.encode("utf-8")
        disposition = f'form-data; name="{name}"'
        if filename:
            disposition += f'; filename="{filename}"'
        chunks.append(f"--{BOUNDARY}\r\n".encode("utf-8"))
        chunks.append(f"Content-Disposition: {disposition}\r\n".encode("utf-8"))
        if filename:
            chunks.append(b"Content-Type: application/octet-stream\r\n")
        chunks.append(b"\r\n")
        chunks.append(value)
        chunks.append(b"\r\n")
    chunks.append(f"--{BOUNDARY}--\r\n".encode("utf-8"))
    return b"".join(chunks)


class QuietHandler(main.Handler):
    def log_message(self, format, *args):
        pass


class ParseEndpointTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def post(self, path, body, content_type):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request("POST", path, body=body, headers={
                "Content-Type": content_type, "Content-Length": str(len(body))})
            response = connection.getresponse()
            payload = response.read()
            return response.status, response.getheader("Content-Type"), payload
        finally:
            connection.close()

    def post_parse(self, fields):
        body = multipart(fields)
        return self.post("/parse", body,
                         f"multipart/form-data; boundary={BOUNDARY}")

    def snapshot_fields(self, name="normal"):
        workbook = FIXTURES / f"{name}.xlsx"
        context = (FIXTURES / f"{name}.context.json").read_text(encoding="utf-8")
        return [
            ("file", workbook.read_bytes(), workbook.name),
            ("context", context, None),
        ]

    def assert_json(self, status, content_type, payload):
        self.assertTrue(content_type.startswith("application/json"), content_type)
        return json.loads(payload.decode("utf-8"))

    def test_snapshot_returns_golden_contract_result(self):
        status, content_type, payload = self.post_parse(self.snapshot_fields())
        result = self.assert_json(status, content_type, payload)
        expected = json.loads((FIXTURES / "normal.expected.json").read_text(encoding="utf-8"))
        self.assertEqual(status, 200)
        self.assertEqual(set(result), {"contract_version", "file_kind", "key_mode",
                                       "nonempty_row_count", "rows", "errors"})
        self.assertEqual(result, expected)

    def test_clients_parser_is_explicitly_not_implemented(self):
        context = json.dumps({
            "contract_version": "1.0", "file_kind": "clients", "key_mode": "anonymous",
            "mapping_profile": "canonical_xlsx_v1",
        })
        status, content_type, payload = self.post_parse([
            ("file", b"anything", "clients.xlsx"), ("context", context, None)])
        self.assertEqual(status, 501)
        self.assertEqual(self.assert_json(status, content_type, payload),
                         {"error": "clients_parser_not_implemented"})

    def test_invalid_context_is_a_client_error(self):
        status, content_type, payload = self.post_parse([
            ("file", b"anything", "snapshot.xlsx"), ("context", "{not json", None)])
        self.assertEqual(status, 400)
        self.assertEqual(self.assert_json(status, content_type, payload)["error"],
                         "invalid_context")

    def test_non_utf8_context_is_a_client_error(self):
        status, content_type, payload = self.post_parse([
            ("file", b"anything", "snapshot.xlsx"), ("context", b"\xff\xfe", None)])
        self.assertEqual(status, 400)
        self.assertEqual(self.assert_json(status, content_type, payload)["error"],
                         "invalid_context")

    def test_non_multipart_request_is_rejected(self):
        body = b'{"file_path":"snapshot.xlsx"}'
        status, content_type, payload = self.post("/parse", body, "application/json")
        self.assertEqual(status, 415)
        self.assertEqual(self.assert_json(status, content_type, payload)["error"],
                         "expected_multipart")

    def test_missing_file_is_a_client_error(self):
        context = (FIXTURES / "normal.context.json").read_text(encoding="utf-8")
        status, content_type, payload = self.post_parse([("context", context, None)])
        self.assertEqual(status, 400)
        self.assertEqual(self.assert_json(status, content_type, payload)["error"],
                         "missing_file")

    def test_invalid_xlsx_is_returned_as_parser_result(self):
        context = (FIXTURES / "normal.context.json").read_text(encoding="utf-8")
        status, content_type, payload = self.post_parse([
            ("file", b"not an xlsx", "snapshot.xlsx"), ("context", context, None)])
        result = self.assert_json(status, content_type, payload)
        self.assertEqual(status, 200)
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["errors"][0]["code"], "INVALID_XLSX")

    def test_file_size_limit_is_a_readable_413(self):
        original = main.MAX_FILE_BYTES
        main.MAX_FILE_BYTES = 1024
        try:
            status, content_type, payload = self.post_parse(self.snapshot_fields())
        finally:
            main.MAX_FILE_BYTES = original
        self.assertEqual(status, 413)
        self.assertEqual(self.assert_json(status, content_type, payload)["error"],
                         "file_too_large")

    def test_row_limit_is_a_readable_422_with_parser_result(self):
        original = main.MAX_ROWS
        main.MAX_ROWS = 2
        try:
            status, content_type, payload = self.post_parse(self.snapshot_fields())
        finally:
            main.MAX_ROWS = original
        result = self.assert_json(status, content_type, payload)
        self.assertEqual(status, 422)
        self.assertEqual(result["errors"][-1]["code"], "ROW_LIMIT_EXCEEDED")
        self.assertEqual(len(result["rows"]), 2)

    def test_context_size_limit_is_a_readable_413(self):
        original = main.MAX_CONTEXT_BYTES
        main.MAX_CONTEXT_BYTES = 10
        try:
            status, content_type, payload = self.post_parse(self.snapshot_fields())
        finally:
            main.MAX_CONTEXT_BYTES = original
        self.assertEqual(status, 413)
        self.assertEqual(self.assert_json(status, content_type, payload)["error"],
                         "context_too_large")
