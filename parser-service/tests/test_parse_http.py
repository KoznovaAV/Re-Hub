"""Настоящий HTTP /parse: оба профиля, контракт и ошибки входных файлов."""
import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from app.main import Handler
from app.generate_test_data import generate


class QuietHandler(Handler):
    def log_message(self, *args):
        pass


class ParseHTTPTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        generate(cls.root, 30, 42)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def request(self, body, content_type="multipart/form-data; boundary=rehub-test"):
        conn = HTTPConnection(*self.server.server_address, timeout=10)
        try:
            conn.request("POST", "/parse", body, {"Content-Type": content_type})
            reply = conn.getresponse()
            return reply.status, json.loads(reply.read())
        finally:
            conn.close()

    def upload(self, name="clients", context=None, data=None, filename=None,
               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"):
        context = context if context is not None else (self.root / f"{name}.context.json").read_text()
        data = data if data is not None else (self.root / f"{name}.xlsx").read_bytes()
        filename = filename or f"{name}.xlsx"
        body = (f'--rehub-test\r\nContent-Disposition: form-data; name="context"\r\n\r\n{context}\r\n'
                f'--rehub-test\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                f'Content-Type: {mime}\r\n\r\n').encode() + data + b"\r\n--rehub-test--\r\n"
        return self.request(body)

    def test_clients_and_snapshots_return_common_contract(self):
        fields = {"contract_version", "file_kind", "key_mode", "nonempty_row_count", "rows", "errors"}
        for name in ("clients", "snapshot_1", "snapshot_2"):
            with self.subTest(name=name):
                status, result = self.upload(name)
                self.assertEqual(status, 200)
                self.assertEqual(set(result), fields)
                self.assertEqual(result["errors"], [])
                self.assertTrue(result["rows"])
                if name == "clients":
                    row = result["rows"][0]["data"]
                    self.assertIn("contact_details", row)
                    self.assertNotIn("name", row)

    def test_transport_and_context_errors(self):
        self.assertEqual(self.request(b"{}", "application/json")[0], 415)
        self.assertEqual(self.request(b"--rehub-test--\r\n")[0], 400)
        for context in ("{", "[]", '{"file_kind":"unknown"}'):
            with self.subTest(context=context):
                self.assertEqual(self.upload(context=context)[0], 422)
        self.assertEqual(self.upload(filename="clients.csv")[0], 422)
        with patch("app.main.MAX_PARSE_BYTES", 64):
            self.assertEqual(self.upload()[0], 413)

    def test_file_mime_and_missing_boundary(self):
        self.assertEqual(self.upload(mime="text/html")[0], 415)
        self.assertEqual(self.upload(mime="application/octet-stream")[0], 200)
        self.assertEqual(self.request(b"broken", "multipart/form-data")[0], 400)

    def test_duplicate_file_part_is_rejected(self):
        context = (self.root / "clients.context.json").read_text()
        data = (self.root / "clients.xlsx").read_bytes()
        file_part = (f'--rehub-test\r\nContent-Disposition: form-data; name="file"; filename="clients.xlsx"\r\n'
                     'Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n').encode()
        body = (f'--rehub-test\r\nContent-Disposition: form-data; name="context"\r\n\r\n{context}\r\n').encode()
        body += file_part + data + b"\r\n" + file_part + data + b"\r\n--rehub-test--\r\n"
        status, result = self.request(body)
        self.assertEqual(status, 400)
        self.assertEqual(result["error"], "duplicate_file")

    def test_corrupt_and_expanded_archive_limits(self):
        status, result = self.upload(data=b"not a workbook")
        self.assertEqual(status, 200)
        self.assertEqual(result["errors"][0]["code"], "INVALID_XLSX")
        with patch("xlsx_limits.MAX_EXPANDED_BYTES", 10):
            status, result = self.upload()
            self.assertEqual(status, 200)
            self.assertEqual(result["errors"][0]["code"], "XLSX_LIMIT_EXCEEDED")
        with patch("xlsx_limits.MAX_ENTRY_BYTES", 10):
            status, result = self.upload()
            self.assertEqual(status, 200)
            self.assertEqual(result["errors"][0]["code"], "XLSX_LIMIT_EXCEEDED")
        self.assertEqual(self.upload()[0], 200)

    def test_temp_cleanup_after_success_failure_and_unknown_kind(self):
        from tempfile import NamedTemporaryFile
        paths = []

        def create(*args, **kwargs):
            result = NamedTemporaryFile(*args, **kwargs)
            paths.append(Path(result.name))
            return result

        with patch("app.main.NamedTemporaryFile", side_effect=create):
            self.assertEqual(self.upload()[0], 200)
            self.assertEqual(self.upload(context='{"file_kind":"unknown"}')[0], 422)
            with patch("customer_clients.parse_file", side_effect=RuntimeError("test")):
                self.assertEqual(self.upload()[0], 500)
            self.assertEqual(self.upload()[0], 200)
        self.assertEqual(len(paths), 4)
        self.assertTrue(all(not path.exists() for path in paths))

    def test_bad_parser_contract_is_rejected_and_service_recovers(self):
        with patch("customer_clients.parse_file", return_value={"unexpected": 1}):
            self.assertEqual(self.upload()[0], 502)
        self.assertEqual(self.upload()[0], 200)

    def test_zip_entry_limit_and_recovery(self):
        with patch("xlsx_limits.MAX_ZIP_ENTRIES", 1):
            status, result = self.upload()
            self.assertEqual(status, 200)
            self.assertEqual(result["errors"][0]["code"], "XLSX_LIMIT_EXCEEDED")
        self.assertEqual(self.upload()[0], 200)

    def test_incomplete_upload(self):
        conn = HTTPConnection(*self.server.server_address, timeout=6)
        try:
            conn.putrequest("POST", "/parse")
            conn.putheader("Content-Type", "multipart/form-data; boundary=x")
            conn.putheader("Content-Length", "100")
            conn.endheaders()
            conn.send(b"partial")
            import socket
            conn.sock.shutdown(socket.SHUT_WR)
            response = conn.getresponse()
            self.assertEqual(response.status, 400)
            self.assertEqual(json.loads(response.read())["error"], "incomplete_upload")
        finally:
            conn.close()
        self.assertEqual(self.upload()[0], 200)

    def test_too_many_multipart_parts(self):
        with patch("app.main.MAX_MULTIPART_PARTS", 1):
            self.assertEqual(self.upload()[0], 400)

    def test_deeply_nested_context_is_rejected(self):
        context = "[" * 10000 + "]" * 10000
        self.assertEqual(self.upload(context=context)[0], 422)

    def test_context_size_limit_is_rejected(self):
        with patch("app.main.MAX_CONTEXT_BYTES", 10):
            status, result = self.upload()
            self.assertEqual(status, 413)
            self.assertEqual(result["error"], "context_too_large")

    def test_row_limit_returns_file_error(self):
        with patch("app.main.MAX_ROWS", 1):
            status, result = self.upload("snapshot_1")
            self.assertEqual(status, 200)
            self.assertEqual(result["errors"][-1]["code"], "ROW_LIMIT_EXCEEDED")
