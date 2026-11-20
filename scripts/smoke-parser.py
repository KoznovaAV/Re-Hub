"""Сквозная проверка Go -> Python /parse -> PostgreSQL на синтетике.

Запуск внутри ai-service: docker compose exec -T ai-service python - < scripts/smoke-parser.py
"""
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path.cwd() / "ai-service"))
from app.generate_test_data import generate
from openpyxl import load_workbook

BASE = os.environ.get("PARSER_SMOKE_BACKEND", "http://backend:8080").rstrip("/")


def request(path, body=None, content_type=None, expected=200):
    headers = {"X-Role": "admin", "X-User-Id": "00000000-0000-0000-0000-000000000001"}
    if content_type:
        headers["Content-Type"] = content_type
    req = Request(BASE + path, data=body, headers=headers)
    try:
        with urlopen(req, timeout=90) as reply:
            status, data = reply.status, json.load(reply)
    except HTTPError as exc:
        status, data = exc.code, json.load(exc)
    assert status == expected, (path, status, data)
    return data


def upload(path, workbook, context):
    # Полный путь и клиентские строки в отчет не выводятся.
    body = (f'--parser-smoke\r\nContent-Disposition: form-data; name="context"\r\n\r\n{context}\r\n'
            '--parser-smoke\r\nContent-Disposition: form-data; name="file"; filename="synthetic.xlsx"\r\n'
            'Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n').encode()
    body += workbook.read_bytes() + b"\r\n--parser-smoke--\r\n"
    return request(path, body, "multipart/form-data; boundary=parser-smoke", 201)["data"]


with TemporaryDirectory() as temp:
    root = Path(temp)
    generate(root, 30, 42)
    # Отдельный префикс не пересекается с ручными демо-наборами AAA.
    for path in root.glob("*.xlsx"):
        book = load_workbook(path)
        for sheet in book:
            for row in sheet.iter_rows(min_row=3):
                if isinstance(row[0].value, str):
                    row[0].value = row[0].value.replace("AAA", "SMK", 1)
        book.save(path)
        book.close()
    ctx = (root / "clients.context.json").read_text()
    result = upload("/api/v1/clients/import", root / "clients.xlsx", ctx)
    assert result["counters"]["rows_ok"] == 30 and result["counters"]["rows_errors"] == 0
    client = request("/api/v1/clients/SMK00001")["data"]
    assert client["contact_details"] == "Контакт 1"
    assert client["name"] != client["contact_details"]
    assert "vip" in client["tags"]
    assert request("/api/v1/clients/SMK00010")["data"]["excluded"] is True
    assert request("/api/v1/clients/SMK00013")["data"]["inactive"] is True
    result = upload("/api/v1/clients/import", root / "clients.xlsx", ctx)
    assert result["counters"]["created"] == 0 and result["counters"]["updated"] == 30
    for name in ["snapshot_1", "snapshot_2"]:
        result = upload("/api/v1/slices", root / f"{name}.xlsx", (root / f"{name}.context.json").read_text())
        assert result["counters"]["rows_errors"] == 0
        assert result["counters"]["rows_ok"] > 0
    # Проверяем независимость названия и контактов, затем отсутствие обновления.
    path = root / "clients.xlsx"
    book = load_workbook(path)
    book.active.cell(2, 7, "Название")
    book.active.cell(3, 7, "Тестовая организация")
    book.save(path)
    book.close()
    upload("/api/v1/clients/import", path, ctx)
    book = load_workbook(path)
    book.active.delete_cols(7)
    book.active.cell(3, 6).value = None
    book.save(path)
    book.close()
    upload("/api/v1/clients/import", path, ctx)
    client = request("/api/v1/clients/SMK00001")["data"]
    assert client["name"] == "Тестовая организация"
    assert client["contact_details"] == "Контакт 1"
    # Повторная загрузка среза не создает новые наблюдения в истории.
    before = request("/api/v1/clients/SMK00001")["history"]
    upload("/api/v1/slices", root / "snapshot_2.xlsx", (root / "snapshot_2.context.json").read_text())
    assert request("/api/v1/clients/SMK00001")["history"] == before
    # Частичная загрузка: дубли, неизвестные ключи и #N/A видны в отчете.
    path = root / "snapshot_2.xlsx"
    book = load_workbook(path)
    sheet = book.worksheets[0]
    sheet.append(["SMK00001", None, None, 10, 2])
    sheet.append(["ZZZ99999", None, None, 10, 2])
    sheet.append(["#N/A", None, None, 10, 2])
    book.save(path)
    book.close()
    result = upload("/api/v1/slices", path, (root / "snapshot_2.context.json").read_text())
    assert result["status"] == "partial"
    assert {e["code"] for e in result["errors"]} == {"DUPLICATE_KEY", "CLIENT_UNKNOWN", "INVALID_EXTERNAL_ID"}
    assert result["counters"]["rows_errors"] == 3
    print("Parser smoke OK: contacts, flags, 30 clients, two snapshots, repeated imports")
