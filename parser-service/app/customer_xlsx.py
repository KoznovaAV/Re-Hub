"""Адаптер для явно названных вкладок октябрьского среза КЦР.

Парсер — чистая функция: он читает ячейки, проверяет лексическую форму и
возвращает ParserResult v1. Он не пишет в БД, не разрешает дубли ключей
для импорта и не изменяет исходную книгу.

Пары-дубли намеренно остаются в ``rows`` (а также в ``key_hint`` отклонённых
строк). Решение на уровне файла о дублях по T-02 IM-01 принимает доменный
компонент на Go.
"""

import argparse
from collections import Counter, defaultdict
from datetime import date
import json
import math
from pathlib import Path
import re
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError

try:
    from .xlsx_limits import check_archive, WorkbookLimitError
except ImportError:
    from xlsx_limits import check_archive, WorkbookLimitError

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
MAX_INTEGER = 2147483647
DEFAULT_MAX_SCANNED_ROWS = 100_000


def normalized(value):
    return " ".join(value.casefold().split()) if isinstance(value, str) else ""


def cell_raw_value(cell):
    """Вернуть только JSON-примитив, который может попасть в ошибку ParserResult."""
    raw = cell.value
    if type(raw) in (str, int, bool) or type(raw) is float and math.isfinite(raw):
        return raw
    return None


def key_from(cell, pattern):
    """Вернуть корректный текстовый ключ или None (для read-only диагностики)."""
    value = cell.value
    if cell.data_type in {"f", "e"} or not isinstance(value, str):
        return None
    value = value.strip()
    return value if pattern.fullmatch(value) else None


def key_error_from(cell, pattern):
    """Вернуть ``(external_id, error_code)`` для обязательной текстовой колонки ключа."""
    value = cell.value
    if cell.data_type == "f":
        return None, "FORMULA_NOT_ALLOWED"
    if cell.data_type == "e":
        return None, "INVALID_EXTERNAL_ID"
    if value is None or isinstance(value, str) and not value.strip():
        return None, "INVALID_EXTERNAL_ID"
    if not isinstance(value, str):
        # AC-13: числовой ключ Excel не восстанавливается догадкой о ведущих нулях.
        return None, "KEY_MUST_BE_TEXT"
    value = value.strip()
    if not pattern.fullmatch(value):
        return None, "INVALID_EXTERNAL_ID"
    return value, None


def number_from(cell, allow_missing):
    """Нормализовать целочисленную ячейку, не вычисляя формулы и ячейки ошибок."""
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
    return (number, None) if 0 <= number <= MAX_INTEGER else (None, "INTEGER_OUT_OF_RANGE")


def row_is_empty(cells):
    return all(cell.value is None or isinstance(cell.value, str) and not cell.value.strip()
               for cell in cells)


def validate_context(context):
    required = {"contract_version", "file_kind", "key_mode", "mapping_profile",
                "snapshot_date", "period_scope", "coverage"}
    if (not isinstance(context, dict) or not required <= context.keys()
            or context.keys() - required - {"supersedes_snapshot_id"}):
        raise ValueError("Invalid snapshot context fields")
    if (context["contract_version"], context["file_kind"], context["mapping_profile"]) != (
            "1.0", "snapshot", PROFILE):
        raise ValueError("Unsupported contract, file kind or mapping profile")
    if context["key_mode"] != "anonymous" or context["coverage"] not in ("unknown", "full_declared"):
        raise ValueError("Invalid key mode or coverage")
    scope = context["period_scope"]
    if (not isinstance(scope, list) or not scope
            or any(code not in PERIODS.values() for code in scope)
            or len(set(scope)) != len(scope)):
        raise ValueError("Invalid period scope for the selected profile")
    day = context["snapshot_date"]
    if not isinstance(day, str):
        raise ValueError("snapshot_date must be YYYY-MM-DD")
    try:
        is_iso_day = date.fromisoformat(day).isoformat() == day
    except ValueError:
        is_iso_day = False
    if not is_iso_day:
        raise ValueError("snapshot_date must be YYYY-MM-DD")


def parse_file(file_path, context, max_rows=None):
    """Вернуть ParserResult v1. Проверка дублей и запись — за вызывающей стороной.

    ``max_rows`` — необязательный транспортный предохранитель. При превышении
    результат сохраняет уже разобранные строки и добавляет file-ошибку
    ``ROW_LIMIT_EXCEEDED``, чтобы HTTP-слой вернул понятную ошибку и не выдавал
    книгу за полностью разобранную.
    """
    validate_context(context)
    mode = context["key_mode"]
    result = {"contract_version": "1.0", "file_kind": "snapshot", "key_mode": mode,
              "nonempty_row_count": 0, "rows": [], "errors": []}

    def file_error(code, message, source=None):
        result["errors"].append({"scope": "file", "code": code, "message": message,
                                 "source": source, "raw_value": None})
        return result

    try:
        check_archive(file_path)
        book = load_workbook(file_path, read_only=True, data_only=False, keep_links=False)
    except WorkbookLimitError:
        return file_error("XLSX_LIMIT_EXCEEDED", "Workbook archive exceeds parsing limits")
    except (OSError, BadZipFile, InvalidFileException, ValueError, KeyError, ParseError,
            RuntimeError):
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
            column_headers = {**expected_headers,
                              2: "код кцр" if PERIODS[sheet.title] == "Y2025" else "код сц"}
            for column, expected in column_headers.items():
                if len(header) < column or normalized(header[column - 1].value) != expected:
                    source = {"sheet": sheet.title, "row": 2, "column": "ABCDE"[column - 1]}
                    return file_error("INVALID_HEADER", "Unexpected snapshot header", source)
        key_column, key_pattern = 0, ANONYMOUS
        # max_rows ограничивает непустые строки. Физическое сканирование
        # дополнительно защищено лимитом не меньше DEFAULT_MAX_SCANNED_ROWS,
        # чтобы не перебирать миллион пустых строк в повреждённой книге.
        max_scanned_rows = max(max_rows or 0, DEFAULT_MAX_SCANNED_ROWS)
        scanned_rows = 0
        for sheet in book:
            period = PERIODS[sheet.title]
            for index, cells in enumerate(sheet.iter_rows(min_row=3, max_col=5), 3):
                scanned_rows += 1
                if scanned_rows > max_scanned_rows:
                    return file_error(
                        "ROW_LIMIT_EXCEEDED",
                        f"Snapshot scan exceeds {max_scanned_rows} rows",
                    )
                if row_is_empty(cells):
                    continue
                result["nonempty_row_count"] += 1
                if max_rows is not None and result["nonempty_row_count"] > max_rows:
                    return file_error(
                        "ROW_LIMIT_EXCEEDED",
                        f"Snapshot contains more than {max_rows} non-empty rows",
                    )
                source = {"sheet": sheet.title, "row": index}
                external_id, key_error = key_error_from(cells[key_column], key_pattern)
                total, total_error = number_from(cells[3], allow_missing=True)
                unsent, unsent_error = number_from(cells[4], allow_missing=False)
                failures = [
                    (key_column, key_error),
                    (3, total_error),
                    (4, unsent_error),
                ]
                for column, code in failures:
                    if code:
                        result["errors"].append({
                            "scope": "row", "code": code,
                            "message": f"Invalid field at column {'ABCDE'[column]}",
                            "source": {**source, "column": "ABCDE"[column]},
                            "raw_value": cell_raw_value(cells[column]),
                            "key_hint": {"external_id": external_id, "period_code": period},
                        })
                if not any(code for _, code in failures):
                    result["rows"].append({"source": source, "data": {
                        "external_id": external_id, "period_code": period,
                        "total_docs": total, "unsent_docs": unsent}})
        if result["nonempty_row_count"] == 0:
            return file_error("NO_DATA_ROWS", "The snapshot contains no non-empty data rows")
        return result
    except (ParseError, BadZipFile, KeyError, ValueError, RuntimeError):
        result["rows"] = []
        return file_error("INVALID_XLSX", "The XLSX package is malformed")
    finally:
        book.close()


def find_duplicates(result):
    """Вернуть группы дублей ``(external_id, period_code)`` для диагностики.

    Учитываются и принятые строки, и отклонённые строки с читаемым ``key_hint``,
    как требует T-02 IM-01. Функция намеренно не входит в ParserResult v1:
    отклонение всего файла остаётся решением доменного слоя.
    """
    observations = defaultdict(list)
    for row in result["rows"]:
        data = row["data"]
        observations[(data["external_id"], data["period_code"])].append(
            {"source": row["source"], "kind": "row"})
    for error in result["errors"]:
        if error["scope"] != "row":
            continue
        hint = error.get("key_hint") or {}
        if hint.get("external_id") and hint.get("period_code"):
            observations[(hint["external_id"], hint["period_code"])].append(
                {"source": error["source"], "kind": "error"})
    groups = []
    for (external_id, period_code), items in observations.items():
        if len(items) > 1:
            items.sort(key=lambda item: (item["source"]["sheet"], item["source"]["row"]))
            groups.append({"external_id": external_id, "period_code": period_code,
                           "observations": items})
    groups.sort(key=lambda group: (group["period_code"], group["external_id"]))
    return groups


def summary(result):
    parsed_duplicates = Counter((row["data"]["external_id"], row["data"]["period_code"])
                                for row in result["rows"])
    rejected = {(e["source"]["sheet"], e["source"]["row"])
                for e in result["errors"] if e["scope"] == "row"}
    duplicate_groups = find_duplicates(result)
    return {
        "source_rows": result["nonempty_row_count"],
        "parsed_rows": len(result["rows"]),
        "rejected_rows": len(rejected),
        "duplicates_in_parsed_rows": sum(count - 1 for count in parsed_duplicates.values()),
        "duplicate_groups": len(duplicate_groups),
        "duplicate_observations": sum(len(group["observations"]) - 1
                                      for group in duplicate_groups),
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
