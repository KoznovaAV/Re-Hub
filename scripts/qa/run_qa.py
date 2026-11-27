"""E2E QA сценарии Q-01, Q-02 и Q-04 для Re:Hub.

Запуск в Compose (так делает CI):

    docker compose exec -T parser-service python - < scripts/qa/run_qa.py

Скрипт использует синтетические XLSX из parser-service, создаёт данные с
уникальными префиксами QAA/QBA/QCA и проверяет реальный Go API + PostgreSQL.
Он не заменяет ручной чек-лист Q-01, но автоматизирует проверяемые шаги.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen

try:
    ROOT = Path(__file__).resolve().parents[2]
except (NameError, IndexError, OSError):  # запуск через ``python -`` внутри контейнера
    ROOT = Path.cwd()
for candidate in (ROOT, ROOT / "parser-service", Path.cwd(), Path.cwd() / "parser-service"):
    if candidate.exists():
        sys.path.insert(0, str(candidate))

from openpyxl import load_workbook

from app.generate_test_data import generate


BASE = os.environ.get("QA_BACKEND", "http://backend:8080").rstrip("/")
ADMIN = "00000000-0000-0000-0000-000000000001"
OPERATOR_1 = "00000000-0000-0000-0000-000000000002"
OPERATOR_2 = "00000000-0000-0000-0000-000000000003"
PERIOD = "2026Q3"
TODAY = date.today()
FUTURE = (TODAY + timedelta(days=7)).isoformat()
PAST = (TODAY - timedelta(days=1)).isoformat()


def expect(condition, message):
    if not condition:
        raise AssertionError(message)


class Api:
    def __init__(self, role="admin", user=ADMIN):
        self.role = role
        self.user = user

    def call(self, method, path, body=None, content_type=None, expected=200):
        headers = {"X-Role": self.role, "X-User-Id": self.user}
        if body is not None:
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
                content_type = content_type or "application/json"
            elif isinstance(body, str):
                body = body.encode("utf-8")
            if content_type:
                headers["Content-Type"] = content_type
        request = Request(BASE + path, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=90) as reply:
                status, raw = reply.status, reply.read()
        except HTTPError as exc:
            status, raw = exc.code, exc.read()
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw.decode("utf-8", errors="replace")}
        allowed = expected if isinstance(expected, (tuple, list, set)) else (expected,)
        expect(status in allowed, f"{method} {path}: {status} {payload}; expected {sorted(allowed)}")
        return status, payload


def read_text(path):
    return Path(path).read_text(encoding="utf-8")


def rewrite_ids(root: Path, prefix: str):
    for path in root.glob("*.xlsx"):
        book = load_workbook(path)
        for sheet in book:
            for row in sheet.iter_rows(min_row=3):
                if isinstance(row[0].value, str):
                    row[0].value = row[0].value.replace("AAA", prefix, 1)
        book.save(path)
        book.close()


def upload(api: Api, endpoint: str, workbook: Path, context: str,
           accept_partial: bool = False, expected=201):
    boundary = "qa-" + uuid.uuid4().hex
    parts = [
        (f"--{boundary}\r\n"
         'Content-Disposition: form-data; name="context"\r\n\r\n'
         f"{context}\r\n").encode("utf-8"),
        (f"--{boundary}\r\n"
         f'Content-Disposition: form-data; name="file"; filename="{workbook.name}"\r\n'
         "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n").encode("utf-8"),
        workbook.read_bytes(),
        b"\r\n",
    ]
    if accept_partial:
        parts.append((f"--{boundary}\r\n"
                      'Content-Disposition: form-data; name="accept_partial"\r\n\r\n'
                      "true\r\n").encode("utf-8"))
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return api.call("POST", endpoint, b"".join(parts),
                    content_type=f"multipart/form-data; boundary={boundary}",
                    expected=expected)


def prepare(prefix: str, count: int = 30):
    temp = TemporaryDirectory()
    root = Path(temp.name)
    generate(root, count, 42)
    rewrite_ids(root, prefix)
    return temp, root


def import_clients(api: Api, root: Path, expected=201):
    return upload(api, "/api/v1/clients/import", root / "clients.xlsx",
                  read_text(root / "clients.context.json"), expected=expected)


def import_snapshot(api: Api, root: Path, name: str, expected=201, accept_partial=False):
    return upload(api, "/api/v1/slices", root / f"{name}.xlsx",
                  read_text(root / f"{name}.context.json"),
                  accept_partial=accept_partial, expected=expected)


def first_client(api: Api, period=PERIOD):
    _, result = api.call("GET", f"/api/v1/call-list?period={period}")
    expect(result.get("data"), "call list is empty")
    return result["data"][0]["external_id"]


def q01(admin: Api, operator: Api, second_operator: Api):
    temp, root = prepare("QAA")
    try:
        _, clients = import_clients(admin, root)
        counters = clients["data"]["counters"]
        expect(counters["rows_ok"] == 30 and counters["rows_errors"] == 0,
               f"clients import counters: {counters}")
        operator_status, _ = import_clients(operator, root, expected=403)
        expect(operator_status == 403, "operator must not import clients")

        _, snapshot = import_snapshot(admin, root, "snapshot_1")
        expect(snapshot["data"]["counters"]["rows_ok"] > 0,
               f"snapshot import counters: {snapshot['data']['counters']}")
        import_snapshot(operator, root, "snapshot_1", expected=403)

        _, call_list = admin.call("GET", f"/api/v1/call-list?period={PERIOD}")
        expect(call_list["data"], "administrator call list is empty")
        operator.call("GET", f"/api/v1/call-list?period={PERIOD}", expected=403)

        code = next((item["external_id"] for item in call_list["data"]
                     if item["external_id"].startswith("QAA")), None)
        expect(code, "QAA client is missing from the call list")
        operator.call("GET", f"/api/v1/clients/{code}", expected=403)
        admin.call("GET", f"/api/v1/clients/{code}")
        _, pooled = admin.call("POST", "/api/v1/pool",
                               {"ids": [code], "period": PERIOD})
        expect(pooled.get("changed", 0) >= 1, f"pool was not changed: {pooled}")
        operator.call("GET", f"/api/v1/clients/{code}")

        operator.call("POST", f"/api/v1/clients/{code}/take", expected=200)
        second_operator.call("POST", f"/api/v1/clients/{code}/take", expected=409)
        admin.call("POST", f"/api/v1/clients/{code}/take", expected=403)

        promise = {"event_type": "call", "result": "Обещание",
                   "promise_label": "Через неделю", "period_code": PERIOD,
                   "promised_at": FUTURE, "event_date": TODAY.isoformat()}
        operator.call("POST", f"/api/v1/clients/{code}/events", promise, expected=201)
        callback = {"event_type": "call", "result": "Перенос",
                    "period_code": PERIOD, "callback_on": FUTURE,
                    "event_date": TODAY.isoformat()}
        operator.call("POST", f"/api/v1/clients/{code}/events", callback, expected=201)
        operator.call("POST", f"/api/v1/clients/{code}/events",
                      {"event_type": "call", "result": "Недозвон",
                       "period_code": PERIOD, "event_date": TODAY.isoformat()},
                      expected=201)
        operator.call("POST", f"/api/v1/clients/{code}/actions",
                      {"kind": "claim", "number": "QA-1", "date": TODAY.isoformat(),
                       "status": "Направлена"}, expected=403)
        admin.call("POST", f"/api/v1/clients/{code}/actions",
                   {"kind": "claim", "number": "QA-1", "date": TODAY.isoformat(),
                    "status": "Направлена"}, expected=201)

        _, card = admin.call("GET", f"/api/v1/clients/{code}")
        expect(card.get("data", {}).get("external_id") == code, "client card changed")
        expect(card.get("history") is not None and card.get("events") is not None
               and card.get("actions") is not None, "client card lacks history/events/actions")
        results = {item.get("result") for item in card["events"] if item.get("event_type") == "call"}
        expect({"Обещание", "Перенос", "Недозвон"} <= results,
               f"call results lost: {results}")
        expect(any(item.get("promised_at") for item in card["events"]),
               "promise date is not stored")
        expect(any(item.get("callback_on") for item in card["events"]),
               "callback date is not stored")
        return {"client": code, "call_results": sorted(results)}
    finally:
        temp.cleanup()


def error_csv(errors):
    rows = [["Лист", "Строка", "Колонка", "ID", "Период", "Код", "Причина", "Значение"]]
    for error in errors:
        rows.append([error.get("sheet"), error.get("row"), error.get("column"),
                     error.get("external_id"), error.get("period_code"),
                     error.get("code"), error.get("message"), error.get("raw_value")])
    buffer = io.StringIO()
    csv.writer(buffer, delimiter=";", lineterminator="\r\n").writerows(rows)
    return buffer.getvalue()


def q02(admin: Api):
    temp, root = prepare("QBA")
    try:
        import_clients(admin, root)
        path = root / "snapshot_2.xlsx"
        book = load_workbook(path)
        sheet = book.worksheets[0]
        sheet.append(["QBA00001", None, None, 10, 2])
        sheet.append(["ZZZ99999", None, None, 10, 2])
        sheet.append(["#N/A", None, None, 10, 2])
        sheet.cell(4, 4, 1)
        sheet.cell(4, 5, 2)
        book.save(path)
        book.close()

        context = read_text(root / "snapshot_2.context.json")
        _, preview = upload(admin, "/api/v1/slices?preview=true", path, context, expected=200)
        codes = {item["code"] for item in preview["errors"]}
        expected_codes = {"DUPLICATE_KEY", "CLIENT_UNKNOWN", "INVALID_EXTERNAL_ID", "UNSENT_GT_TOTAL"}
        expect(expected_codes <= codes, f"preview codes: {sorted(codes)}")
        expect(preview["counters"]["accepted"] > 0, "preview accepted no valid rows")
        expect(all(item.get("message") and item.get("code") for item in preview["errors"]),
               "preview errors are not ready for CSV")
        csv_text = error_csv(preview["errors"])
        expect("DUPLICATE_KEY" in csv_text and "Лист;Строка" in csv_text,
               "error CSV does not contain codes/header")

        upload(admin, "/api/v1/slices", path, context, expected=422)
        _, partial = upload(admin, "/api/v1/slices", path, context,
                            accept_partial=True, expected=201)
        data = partial["data"]
        expect(data["status"] == "partial", f"status: {data['status']}")
        expect(data["counters"]["rows_ok"] == preview["counters"]["accepted"],
               "partial import accepted a different row set")
        expect(data["counters"]["rows_errors"] > 0, "partial import hid errors")
        expect({item["code"] for item in data["errors"]} >= expected_codes,
               "partial import lost error details")

        valid_code = preview["rows"][0]["externalId"]
        _, card = admin.call("GET", f"/api/v1/clients/{valid_code}")
        history = card.get("history", [])
        expect(history, f"valid row was not preserved for {valid_code}")

        _, repeated = upload(admin, "/api/v1/slices", path, context,
                             accept_partial=True, expected=201)
        expect(repeated["data"]["counters"]["rows_ok"] == data["counters"]["rows_ok"],
               "repeated import changed accepted rows")
        _, repeated_card = admin.call("GET", f"/api/v1/clients/{valid_code}")
        expect(len(repeated_card.get("history", [])) == len(history),
               "repeated import duplicated history")

        _, clients_again = import_clients(admin, root)
        counters = clients_again["data"]["counters"]
        expect(counters["created"] == 0 and counters["updated"] == 30,
               f"repeated clients import: {counters}")
        return {"preview_errors": sorted(codes), "accepted": data["counters"]["rows_ok"],
                "csv_rows": len(preview["errors"]) + 1}
    finally:
        temp.cleanup()


def q04(admin: Api, operator: Api):
    temp, root = prepare("QCA")
    try:
        import_clients(admin, root)
        import_snapshot(admin, root, "snapshot_1")

        admin.call("GET", "/api/v1/call-list?period=UNKNOWN", expected=422)
        for query in ("min_unsent=-1", "min_share=NaN", "contacted=maybe"):
            admin.call("GET", f"/api/v1/call-list?period={PERIOD}&{query}", expected=422)
        operator.call("GET", f"/api/v1/call-list?period={PERIOD}", expected=403)

        _, call_list = admin.call(
            "GET", f"/api/v1/call-list?period={PERIOD}&min_unsent=0&min_share=0&contacted=no")
        expect(call_list["data"], "filtered call list is empty")
        for client in call_list["data"]:
            expect(client["latest"]["period_code"] == PERIOD,
                   f"wrong period in call list: {client['external_id']}")
            expect(not client["excluded"] and not client["inactive"],
                   f"excluded client in call list: {client['external_id']}")
            expect(client["latest"]["not_sent_docs"] >= 0,
                   f"invalid unsent value: {client['external_id']}")

        _, clients = admin.call(
            "GET", f"/api/v1/clients?period={PERIOD}&excluded=false&inactive=false")
        expect(clients["data"], "clients filter returned no rows")
        expect(all(not item["excluded"] and not item["inactive"] for item in clients["data"]),
               "clients filter returned excluded/inactive rows")

        code = next((item["external_id"] for item in call_list["data"]
                     if item["external_id"].startswith("QCA")), None)
        expect(code, "QCA client is missing from the call list")
        _, pooled = admin.call("POST", "/api/v1/pool", {"ids": [code], "period": PERIOD})
        expect(pooled.get("changed", 0) >= 1, f"pool was not changed: {pooled}")
        operator.call("POST", f"/api/v1/clients/{code}/take", expected=200)
        events = [
            {"event_type": "call", "result": "Недозвон", "period_code": PERIOD,
             "event_date": TODAY.isoformat()},
            {"event_type": "call", "result": "Перенос", "period_code": PERIOD,
             "callback_on": FUTURE, "event_date": TODAY.isoformat()},
            {"event_type": "call", "result": "Обещание", "period_code": PERIOD,
             "promised_at": FUTURE, "event_date": TODAY.isoformat()},
        ]
        for event in events:
            operator.call("POST", f"/api/v1/clients/{code}/events", event, expected=201)
        operator.call("POST", f"/api/v1/clients/{code}/events",
                      {"event_type": "call", "result": "Перенос", "period_code": PERIOD,
                       "callback_on": PAST, "event_date": TODAY.isoformat()}, expected=422)
        operator.call("POST", f"/api/v1/clients/{code}/events",
                      {"event_type": "call", "result": "Обещание", "period_code": PERIOD,
                       "promised_at": PAST, "event_date": TODAY.isoformat()}, expected=422)

        _, card = admin.call("GET", f"/api/v1/clients/{code}")
        call_events = [item for item in card["events"]
                       if item.get("event_type") == "call" and item.get("result")]
        expect({"Недозвон", "Перенос", "Обещание"} <= {item["result"] for item in call_events},
               "call statuses were not stored")
        expect(any(item.get("callback_on") for item in call_events), "callback is missing")
        expect(any(item.get("promised_at") for item in call_events), "promise is missing")

        _, after_call = admin.call(
            "GET", f"/api/v1/call-list?period={PERIOD}&min_unsent=0&min_share=0&contacted=no")
        expect(code not in {item["external_id"] for item in after_call["data"]},
               "contacted=no did not exclude the called client")
        admin.call("GET", "/api/v1/today", expected=200)
        return {"client": code, "call_list": len(call_list["data"]),
                "clients": len(clients["data"])}
    finally:
        temp.cleanup()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    admin = Api()
    operator = Api("operator", OPERATOR_1)
    second_operator = Api("operator", OPERATOR_2)
    tasks = [("Q-01", lambda: q01(admin, operator, second_operator)),
             ("Q-02", lambda: q02(admin)),
             ("Q-04", lambda: q04(admin, operator))]
    report = {"backend": BASE, "period": PERIOD, "tasks": []}
    failed = False
    for name, run in tasks:
        try:
            details = run()
            report["tasks"].append({"task": name, "status": "passed", "details": details})
            print(f"PASS {name}: {details}")
        except Exception as exc:
            failed = True
            report["tasks"].append({"task": name, "status": "failed", "error": str(exc)})
            print(f"FAIL {name}: {exc}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
