"""Build T-10 negative snapshot fixtures with expected ParserResult error codes."""

from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent
PERIODS = {
    "весь 2025 год": "Y2025",
    "1 кв 2026": "2026Q1",
    "2 кв 2026": "2026Q2",
    "3 кв 2026": "2026Q3",
}


def headers(period_code: str) -> list:
    return [
        "Уникальны обезличинный идентификатор",
        "Код КЦР" if period_code == "Y2025" else "код СЦ",
        None,
        "документов всего",
        "Всего не отправлено документов",
    ]


def write_snapshot(path: Path, rows_by_period: dict[str, list[list]]) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, period_code in PERIODS.items():
        sheet = workbook.create_sheet(title)
        sheet.append([])
        sheet.append(headers(period_code))
        for row in rows_by_period.get(period_code, []):
            sheet.append(row)
    workbook.save(path)
    workbook.close()


def build() -> None:
    # One workbook that exercises parser-level negatives on 2026Q3 (+ sparse other tabs).
    rows = {
        "Y2025": [["NEG00001", None, None, 10, 1]],
        "2026Q1": [["NEG00001", None, None, 10, 1]],
        "2026Q2": [["NEG00001", None, None, 10, 1]],
        "2026Q3": [
            ["NEG00001", None, None, 100, 40],  # valid
            ["NEG00001", None, None, 100, 41],  # duplicate key (parser keeps both; Go marks DUPLICATE)
            ["#N/A", None, None, 10, 2],  # INVALID_EXTERNAL_ID
            ["BADCODE", None, None, 10, 2],  # unknown/invalid code
            ["NEG00002", None, None, None, 5],  # missing total -> null total_docs, still valid parse
            ["NEG00003", None, None, 10, None],  # INTEGER_REQUIRED on unsent
        ],
    }
    write_snapshot(ROOT / "snapshot-negatives.xlsx", rows)

    # Pair for "client disappeared": present in snap1, absent in snap2 on 2026Q3.
    snap1 = {
        "Y2025": [["NEG00010", None, None, 20, 2]],
        "2026Q1": [["NEG00010", None, None, 20, 2]],
        "2026Q2": [["NEG00010", None, None, 20, 2]],
        "2026Q3": [["NEG00010", None, None, 100, 30], ["NEG00011", None, None, 50, 5]],
    }
    snap2 = {
        "Y2025": [["NEG00010", None, None, 20, 2]],
        "2026Q1": [["NEG00010", None, None, 20, 2]],
        "2026Q2": [["NEG00010", None, None, 20, 2]],
        "2026Q3": [["NEG00011", None, None, 50, 5]],  # NEG00010 disappeared
    }
    write_snapshot(ROOT / "snapshot-before-missing-client.xlsx", snap1)
    write_snapshot(ROOT / "snapshot-after-missing-client.xlsx", snap2)

    context = {
        "contract_version": "1.0",
        "file_kind": "snapshot",
        "key_mode": "anonymous",
        "mapping_profile": "customer_october_tabs_v1",
        "snapshot_date": "2026-10-20",
        "period_scope": list(PERIODS.values()),
        "coverage": "unknown",
    }
    (ROOT / "snapshot.context.json").write_text(json.dumps(context, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    expected = {
        "snapshot-negatives.xlsx": {
            "parser_error_codes": ["INVALID_EXTERNAL_ID", "INVALID_EXTERNAL_ID", "INTEGER_REQUIRED"],
            "parsed_external_ids": ["NEG00001", "NEG00001", "NEG00002"],
            "missing_total_external_id": "NEG00002",
            "duplicate_external_id": "NEG00001",
            "notes": {
                "duplicate": "Parser keeps both duplicate rows; Go domain emits DUPLICATE_KEY",
                "unknown_code": "BADCODE -> INVALID_EXTERNAL_ID",
                "na": "#N/A -> INVALID_EXTERNAL_ID",
                "missing_total": "empty Всего -> total_docs null in rows",
            },
        },
        "missing-client-pair": {
            "before_ids_2026Q3": ["NEG00010", "NEG00011"],
            "after_ids_2026Q3": ["NEG00011"],
            "disappeared": ["NEG00010"],
        },
    }
    (ROOT / "expected.json").write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote negative fixtures into {ROOT}")


if __name__ == "__main__":
    build()
