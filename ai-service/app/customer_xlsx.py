"""Adapter for the explicitly named tabs in the October customer snapshot."""

import argparse
from collections import Counter
from datetime import date
import json
import math
from pathlib import Path
import re
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

PERIODS = {
    "весь 2025 год": "Y2025",
    "1 кв 2026": "2026Q1",
    "2 кв 2026": "2026Q2",
    "3 кв 2026": "2026Q3",
}
PROFILE = "customer_october_tabs_v1"
ANONYMOUS = re.compile(r"[A-Z]{3}[0-9]{5}")
NUMBER = re.compile(r"(?:[0-9]+|[0-9]{1,3}(?:[ \u00a0\u202f][0-9]{3})+)")


def normalized(value):
    return " ".join(value.casefold().split()) if isinstance(value, str) else ""


def key_from(cell, pattern):
    value = cell.value
    if cell.data_type in {"f", "e"} or not isinstance(value, str):
        return None
    return value.strip() if pattern.fullmatch(value.strip()) else None


def number_from(cell, allow_missing):
    value = cell.value
    if cell.data_type == "f":
        return None, "FORMULA_NOT_ALLOWED"
    if cell.data_type == "e":
        return None, "EXCEL_CELL_ERROR"
    if value is None or isinstance(value, str) and not value.strip():
        return None, None if allow_missing else "INTEGER_REQUIRED"
    if type(value) in (int, float) and math.isfinite(value) and int(value) == value:
        number = int(value)
    elif isinstance(value, str) and NUMBER.fullmatch(value.strip()):
        try:
            number = int(re.sub(r"[ \u00a0\u202f]", "", value.strip()))
        except ValueError:
            return None, "INVALID_INTEGER"
    else:
        return None, "INVALID_INTEGER"
    return (number, None) if 0 <= number <= 2147483647 else (None, "INTEGER_OUT_OF_RANGE")


def validate_context(context):
    required = {"contract_version", "file_kind", "key_mode", "mapping_profile", "snapshot_date", "period_scope", "coverage"}
    if not isinstance(context, dict) or not required <= context.keys() or context.keys() - required - {"supersedes_snapshot_id"}:
        raise ValueError("Invalid snapshot context fields")
    if (context["contract_version"], context["file_kind"], context["mapping_profile"]) != ("1.0", "snapshot", PROFILE):
        raise ValueError("Unsupported contract, file kind or mapping profile")
    if context["key_mode"] != "anonymous" or context["coverage"] not in ("unknown", "full_declared"):
        raise ValueError("Invalid key mode or coverage")
    scope = context["period_scope"]
    if not isinstance(scope, list) or not scope or any(code not in PERIODS.values() for code in scope) or len(set(scope)) != len(scope):
        raise ValueError("Invalid period scope for the selected profile")
    day = context["snapshot_date"]
    if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
        raise ValueError("snapshot_date must be YYYY-MM-DD")


def parse_file(file_path, context):
    """Return ParserResult v1. The caller owns duplicate checks and any write."""
    validate_context(context)
    mode = context["key_mode"]
    result = {"contract_version": "1.0", "file_kind": "snapshot", "key_mode": mode,
              "nonempty_row_count": 0, "rows": [], "errors": []}

    def file_error(code, message, source=None):
        result["errors"].append({"scope": "file", "code": code, "message": message,
                                 "source": source, "raw_value": None})
        return result

    try:
        book = load_workbook(file_path, read_only=True, data_only=False, keep_links=False)
    except (OSError, BadZipFile, InvalidFileException, ValueError, KeyError):
        return file_error("INVALID_XLSX", "The XLSX package could not be opened")
    try:
        actual = [PERIODS.get(sheet) for sheet in book.sheetnames]
        if None in actual or set(actual) != set(context["period_scope"]):
            return file_error("PERIOD_SCOPE_MISMATCH", "Tabs must match the explicit period scope")
        expected_headers = {
            1: "уникальны обезличинный идентификатор",
            4: "документов всего",
            5: "всего не отправлено документов",
        }
        for sheet in book:
            header = next(sheet.iter_rows(min_row=2, max_row=2, max_col=5), ())
            column_headers = {**expected_headers, 2: "код кцр" if PERIODS[sheet.title] == "Y2025" else "код сц"}
            for column, expected in column_headers.items():
                if len(header) < column or normalized(header[column - 1].value) != expected:
                    source = {"sheet": sheet.title, "row": 2, "column": "ABCDE"[column - 1]}
                    return file_error("INVALID_HEADER", "Unexpected snapshot header", source)
        key_column, key_pattern = 0, ANONYMOUS
        for sheet in book:
            period = PERIODS[sheet.title]
            for index, cells in enumerate(sheet.iter_rows(min_row=3, max_col=5), 3):
                if all(cell.value is None for cell in cells):
                    continue
                result["nonempty_row_count"] += 1
                source = {"sheet": sheet.title, "row": index}
                external_id = key_from(cells[key_column], key_pattern)
                total, total_error = number_from(cells[3], allow_missing=True)
                unsent, unsent_error = number_from(cells[4], allow_missing=False)
                failures = [
                    (key_column, None if external_id else "INVALID_EXTERNAL_ID"),
                    (3, total_error), (4, unsent_error),
                ]
                for column, code in failures:
                    if code:
                        raw = cells[column].value
                        result["errors"].append({
                            "scope": "row", "code": code, "message": f"Invalid field at column {'ABCDE'[column]}",
                            "source": {**source, "column": "ABCDE"[column]},
                            "raw_value": raw if type(raw) in (str, int, bool) or type(raw) is float and math.isfinite(raw) else None,
                            "key_hint": {"external_id": external_id, "period_code": period},
                        })
                if not any(code for _, code in failures):
                    result["rows"].append({"source": source, "data": {"external_id": external_id,
                        "period_code": period, "total_docs": total, "unsent_docs": unsent}})
        return result
    finally:
        book.close()


def summary(result):
    duplicates = Counter((row["data"]["external_id"], row["data"]["period_code"]) for row in result["rows"])
    rejected = {(e["source"]["sheet"], e["source"]["row"]) for e in result["errors"] if e["scope"] == "row"}
    return {
        "source_rows": result["nonempty_row_count"], "parsed_rows": len(result["rows"]),
        "rejected_rows": len(rejected),
        "duplicates_in_parsed_rows": sum(count - 1 for count in duplicates.values()),
        "errors_by_code": dict(Counter(error["code"] for error in result["errors"])),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("context", type=Path)
    parser.add_argument("--summary", action="store_true", help="Print aggregate counts only")
    args = parser.parse_args()
    data = parse_file(args.workbook, json.loads(args.context.read_text(encoding="utf-8")))
    print(json.dumps(summary(data) if args.summary else data, ensure_ascii=False, indent=2))
    raise SystemExit(any(error["scope"] == "file" for error in data["errors"]))
