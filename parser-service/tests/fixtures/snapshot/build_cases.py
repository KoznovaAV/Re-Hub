"""Собрать закоммиченные фикстуры среза и независимый golden JSON.

Запуск из корня репозитория:

    py -3 parser-service/tests/fixtures/snapshot/build_cases.py

Ожидаемые объекты ParserResult ниже написаны вручную. Они не генерируются
вызовом проверяемого парсера, поэтому регрессия парсера не может молча
переписать собственные ожидания.
"""

import json
from pathlib import Path
import sys

from openpyxl import Workbook

PARSER_SERVICE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PARSER_SERVICE))

from app.customer_xlsx import PERIODS, parse_file  # noqa: E402


HERE = Path(__file__).resolve().parent
PERIOD_HEADER = {
    "весь 2025 год": "Код КЦР",
    "1 кв 2026": "код СЦ",
    "2 кв 2026": "код СЦ",
    "3 кв 2026": "код СЦ",
}


class ErrorCell(str):
    """Значение, записываемое как настоящая ячейка ошибки Excel, например ``#N/A``."""


def context(period_scope, snapshot_date):
    return {
        "contract_version": "1.0",
        "file_kind": "snapshot",
        "key_mode": "anonymous",
        "mapping_profile": "customer_october_tabs_v1",
        "snapshot_date": snapshot_date,
        "period_scope": period_scope,
        "coverage": "unknown",
    }


def source_row(sheet, row):
    return {"sheet": sheet, "row": row}


def data(external_id, period_code, total_docs, unsent_docs):
    return {"external_id": external_id, "period_code": period_code,
            "total_docs": total_docs, "unsent_docs": unsent_docs}


def row_error(sheet, row, column, code, raw_value, external_id, period_code):
    return {
        "scope": "row",
        "code": code,
        "message": f"Invalid field at column {column}",
        "source": {"sheet": sheet, "row": row, "column": column},
        "raw_value": raw_value,
        "key_hint": {"external_id": external_id, "period_code": period_code},
    }


CASES = {
    "normal": {
        "context": context(["Y2025", "2026Q1", "2026Q2", "2026Q3"], "2026-10-20"),
        "rows": {
            "весь 2025 год": [
                ["AAA00001", None, None, "1 245", 2],
                ["AAA00002", None, None, 0, 0],
            ],
            "1 кв 2026": [
                ["AAA00001", None, None, 100, 40],
                ["AAA00002", None, None, 50, 5],
            ],
            "2 кв 2026": [["AAA00002", None, None, 7, 0]],
            "3 кв 2026": [["AAA00003", None, None, 12, 12]],
        },
        "expected": {
            "contract_version": "1.0",
            "file_kind": "snapshot",
            "key_mode": "anonymous",
            "nonempty_row_count": 6,
            "rows": [
                {"source": source_row("весь 2025 год", 3),
                 "data": data("AAA00001", "Y2025", 1245, 2)},
                {"source": source_row("весь 2025 год", 4),
                 "data": data("AAA00002", "Y2025", 0, 0)},
                {"source": source_row("1 кв 2026", 3),
                 "data": data("AAA00001", "2026Q1", 100, 40)},
                {"source": source_row("1 кв 2026", 4),
                 "data": data("AAA00002", "2026Q1", 50, 5)},
                {"source": source_row("2 кв 2026", 3),
                 "data": data("AAA00002", "2026Q2", 7, 0)},
                {"source": source_row("3 кв 2026", 3),
                 "data": data("AAA00003", "2026Q3", 12, 12)},
            ],
            "errors": [],
        },
    },
    "duplicates": {
        "context": context(["Y2025", "2026Q1"], "2026-10-20"),
        "rows": {
            "весь 2025 год": [
                ["AAA00001", None, None, 10, 1],
                ["AAA00001", None, None, 10, 1],
                ["AAA00001", None, None, 11, 1],
                ["AAA00001", None, None, 9, None],
            ],
            "1 кв 2026": [["AAA00001", None, None, 5, 0]],
        },
        "expected": {
            "contract_version": "1.0",
            "file_kind": "snapshot",
            "key_mode": "anonymous",
            "nonempty_row_count": 5,
            "rows": [
                {"source": source_row("весь 2025 год", 3),
                 "data": data("AAA00001", "Y2025", 10, 1)},
                {"source": source_row("весь 2025 год", 4),
                 "data": data("AAA00001", "Y2025", 10, 1)},
                {"source": source_row("весь 2025 год", 5),
                 "data": data("AAA00001", "Y2025", 11, 1)},
                {"source": source_row("1 кв 2026", 3),
                 "data": data("AAA00001", "2026Q1", 5, 0)},
            ],
            "errors": [
                row_error("весь 2025 год", 6, "E", "INTEGER_REQUIRED", None,
                          "AAA00001", "Y2025"),
            ],
        },
    },
    "cell-errors": {
        "context": context(["Y2025", "2026Q1"], "2026-10-20"),
        "rows": {
            "весь 2025 год": [
                ["AAA00001", None, None, "1 234", 2],
                ["AAA00002", None, None, "=1+1", 1],
                ["AAA00003", None, None, 5, ErrorCell("#N/A")],
                ["AAA00004", None, None, "1 24", 1],
                [1234567, None, None, 5, 1],
                [ErrorCell("#N/A"), None, None, 5, 1],
            ],
            "1 кв 2026": [
                ["AAA00005", None, None, None, 0],
                ["AAA00006", None, None, 5, "=A1"],
            ],
        },
        "expected": {
            "contract_version": "1.0",
            "file_kind": "snapshot",
            "key_mode": "anonymous",
            "nonempty_row_count": 8,
            "rows": [
                {"source": source_row("весь 2025 год", 3),
                 "data": data("AAA00001", "Y2025", 1234, 2)},
                {"source": source_row("1 кв 2026", 3),
                 "data": data("AAA00005", "2026Q1", None, 0)},
            ],
            "errors": [
                row_error("весь 2025 год", 4, "D", "FORMULA_NOT_ALLOWED", "=1+1",
                          "AAA00002", "Y2025"),
                row_error("весь 2025 год", 5, "E", "EXCEL_CELL_ERROR", "#N/A",
                          "AAA00003", "Y2025"),
                row_error("весь 2025 год", 6, "D", "INVALID_INTEGER", "1 24",
                          "AAA00004", "Y2025"),
                row_error("весь 2025 год", 7, "A", "KEY_MUST_BE_TEXT", 1234567,
                          None, "Y2025"),
                row_error("весь 2025 год", 8, "A", "INVALID_EXTERNAL_ID", "#N/A",
                          None, "Y2025"),
                row_error("1 кв 2026", 4, "E", "FORMULA_NOT_ALLOWED", "=A1",
                          "AAA00006", "2026Q1"),
            ],
        },
    },
    "repeat-missing-total": {
        "context": context(["Y2025", "2026Q1"], "2026-11-20"),
        "rows": {
            "весь 2025 год": [["AAA00001", None, None, None, 3]],
            "1 кв 2026": [["AAA00002", None, None, None, 0]],
        },
        "expected": {
            "contract_version": "1.0",
            "file_kind": "snapshot",
            "key_mode": "anonymous",
            "nonempty_row_count": 2,
            "rows": [
                {"source": source_row("весь 2025 год", 3),
                 "data": data("AAA00001", "Y2025", None, 3)},
                {"source": source_row("1 кв 2026", 3),
                 "data": data("AAA00002", "2026Q1", None, 0)},
            ],
            "errors": [],
        },
    },
}


def write_workbook(path, rows_by_period):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, rows in rows_by_period.items():
        tab = workbook.create_sheet(title)
        tab.append([])
        tab.append(["Уникальны обезличинный идентификатор",
                    PERIOD_HEADER[title], None, "документов всего",
                    "Всего не отправлено документов"])
        for values in rows:
            tab.append(list(values))
            row_number = tab.max_row
            for column, value in enumerate(values, 1):
                if isinstance(value, ErrorCell):
                    cell = tab.cell(row=row_number, column=column)
                    cell.value = str(value)
                    cell.data_type = "e"
    workbook.save(path)
    workbook.close()


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def main():
    for name, case in CASES.items():
        write_workbook(HERE / f"{name}.xlsx", case["rows"])
        write_json(HERE / f"{name}.context.json", case["context"])
        write_json(HERE / f"{name}.expected.json", case["expected"])
        print(f"wrote {name}")


if __name__ == "__main__":
    main()
