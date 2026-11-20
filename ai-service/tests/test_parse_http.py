"""Настоящий HTTP /parse: оба профиля, контракт и ошибки входных файлов."""
import io
import json
import sys
import threading
import unittest
from contextlib import contextmanager
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from openpyxl import Workbook

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

    def upload(self, name="clients", context=None, data=None, filename=None):
        context = context if context is not None else (self.root / f"{name}.context.json").read_text()
        data = data if data is not None else (self.root / f"{name}.xlsx").read_bytes()
        filename = filename or f"{name}.xlsx"
        body = (f'--rehub-test\r\nContent-Disposition: form-data; name="context"\r\n\r\n{context}\r\n'
                f'--rehub-test\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                'Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n').encode() + data + b"\r\n--rehub-test--\r\n"
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

    def test_corrupt_and_expanded_archive_limits(self):
        status, result = self.upload(data=b"not a workbook")
        self.assertEqual(status, 200)
        self.assertEqual(result["errors"][0]["code"], "INVALID_XLSX")
        with patch("xlsx_limits.MAX_EXPANDED_BYTES", 10):
            status, result = self.upload()
            self.assertEqual(status, 200)
            self.assertEqual(result["errors"][0]["code"], "XLSX_LIMIT_EXCEEDED")
