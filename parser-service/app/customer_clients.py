"""Adapter for the customer KCR directory workbook (file_kind=clients)."""

import argparse
from collections import Counter
from datetime import date, datetime
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

PROFILE = "customer_kcr_directory_v1"
SHEET_NAME = "Все КЦР"
HEADER_ROW = 2
DATA_START = 3
ANONYMOUS = re.compile(r"[A-Z]{3}[0-9]{5}")
KCR = re.compile(r"[0-9]{7}")
ALLOWED_TAGS = {"vip", "integrator", "tech_partner", "mpp", "newcomer"}
TRUE_VALUES = {"да", "yes", "true", "1", "x", "+"}
FALSE_VALUES = {"нет", "no", "false", "0", "-"}

# Explicit header → logical field. No fuzzy matching.
HEADER_FIELDS = {
    "уникальны обезличинный идентификатор": "anonymous_id",
    "уникальный обезличенный идентификатор": "anonymous_id",
    "код кцр": "kcr_code",
    "теги": "tags",
    "не нужно работать": "excluded",
    "недействующий": "inactive",
    # Сохраняем контактную строку целиком, не выдавая ее за название клиента.
    "контакты": "contact_details",
    "название": "name",
}


def normalized(value):
    return " ".join(value.casefold().split()) if isinstance(value, str) else ""


def column_letter(index):
    letter = ""
    number = index + 1
    while number:
        number, rem = divmod(number - 1, 26)
        letter = chr(65 + rem) + letter
    return letter


def raw_primitive(value):
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return None


def validate_context(context):
    required = {"contract_version", "file_kind", "key_mode", "mapping_profile"}
    if not isinstance(context, dict) or not required <= context.keys():
        raise ValueError("Invalid clients context fields")
    if context.keys() - required:
        raise ValueError("Clients context must not include snapshot fields")
    if (context["contract_version"], context["file_kind"], context["mapping_profile"]) != (
        "1.0",
        "clients",
        PROFILE,
    ):
        raise ValueError("Unsupported contract, file kind or mapping profile")
    if context["key_mode"] not in ("anonymous", "kcr"):
        raise ValueError("Invalid key mode")


def text_from(cell, *, as_key=False):
    if cell.data_type in {"f", "e"}:
        return None, "FORMULA_OR_ERROR_NOT_ALLOWED"
    value = cell.value
    if value is None:
        return None, None
    if isinstance(value, str):
        text = value.strip()
        return (text, None) if text else (None, None)
    if isinstance(value, bool):
        return None, "TEXT_REQUIRED"
    if type(value) in (int, float) and math.isfinite(value):
        return None, "KEY_MUST_BE_TEXT" if as_key else "TEXT_REQUIRED"
    return None, "TEXT_REQUIRED"


def bool_from(cell):
    if cell.data_type in {"f", "e"}:
        return None, "FORMULA_OR_ERROR_NOT_ALLOWED"
    value = cell.value
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, None
    if isinstance(value, bool):
        return value, None
    if type(value) in (int, float) and math.isfinite(value) and value in (0, 1):
        return bool(int(value)), None
    if isinstance(value, str):
        token = normalized(value)
        if token in TRUE_VALUES:
            return True, None
        if token in FALSE_VALUES:
            return False, None
    return None, "INVALID_BOOLEAN"


def tags_from(cell):
    if cell.data_type in {"f", "e"}:
        return None, "FORMULA_OR_ERROR_NOT_ALLOWED"
    value = cell.value
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, None
    if isinstance(value, str) and value.strip() == "[]":
        return [], None
    if not isinstance(value, str):
        return None, "INVALID_TAGS"
    parts = [part.strip().casefold() for part in value.split(";") if part.strip()]
    if not parts:
        return None, None
    if len(parts) != len(set(parts)):
        return None, "DUPLICATE_TAG"
    if any(part not in ALLOWED_TAGS for part in parts):
        return None, "UNKNOWN_TAG"
    return parts, None


def parse_file(file_path, context):
    """Return ParserResult v1 for the KCR directory. Caller owns duplicates and writes."""
    validate_context(context)
    mode = context["key_mode"]
    result = {
        "contract_version": "1.0",
        "file_kind": "clients",
        "key_mode": mode,
        "nonempty_row_count": 0,
        "rows": [],
        "errors": [],
    }

    def file_error(code, message, source=None, raw_value=None):
        result["errors"].append({
            "scope": "file",
            "code": code,
            "message": message,
            "source": source,
            "raw_value": raw_value,
        })
        return result

    def row_error(code, message, source, raw_value, external_id=None):
        result["errors"].append({
            "scope": "row",
            "code": code,
            "message": message,
            "source": source,
            "raw_value": raw_primitive(raw_value),
            "key_hint": {"external_id": external_id, "period_code": None},
        })

    try:
        check_archive(file_path)
        book = load_workbook(file_path, read_only=True, data_only=False, keep_links=False)
    except WorkbookLimitError:
        return file_error("XLSX_LIMIT_EXCEEDED", "Workbook archive exceeds parsing limits")
    except (OSError, BadZipFile, InvalidFileException, ValueError, KeyError, ParseError):
        return file_error("INVALID_XLSX", "The XLSX package could not be opened")

    try:
        if book.sheetnames != [SHEET_NAME]:
            return file_error(
                "UNEXPECTED_SHEETS",
                f"Expected a single sheet named {SHEET_NAME!r}",
                {"sheet": book.sheetnames[0] if book.sheetnames else SHEET_NAME, "row": 1, "column": None},
            )
        sheet = book.active
        header_cells = next(sheet.iter_rows(min_row=HEADER_ROW, max_row=HEADER_ROW), ())
        if not header_cells:
            return file_error("INVALID_HEADER", "Header row is missing",
                              {"sheet": SHEET_NAME, "row": HEADER_ROW, "column": None})

        columns = {}
        seen_headers = set()
        for cell in header_cells:
            title = normalized(cell.value)
            if not title:
                continue
            if title in seen_headers:
                return file_error(
                    "DUPLICATE_HEADER",
                    "Duplicate header in the directory sheet",
                    {"sheet": SHEET_NAME, "row": HEADER_ROW, "column": column_letter(cell.column - 1)},
                    cell.value,
                )
            seen_headers.add(title)
            field = HEADER_FIELDS.get(title)
            if field is None:
                return file_error(
                    "UNKNOWN_HEADER",
                    "Directory header is not in the explicit mapping",
                    {"sheet": SHEET_NAME, "row": HEADER_ROW, "column": column_letter(cell.column - 1)},
                    cell.value,
                )
            if field in columns:
                return file_error("DUPLICATE_HEADER", "Two headers map to the same field",
                                  {"sheet": SHEET_NAME, "row": HEADER_ROW, "column": column_letter(cell.column - 1)})
            columns[field] = cell.column - 1

        required = {"anonymous_id", "kcr_code"} if mode == "anonymous" else {"kcr_code"}
        # Always require the T-01 flag/contact columns when present in the profile.
        required |= {"tags", "excluded", "inactive", "contact_details"}
        missing = sorted(required - columns.keys())
        if missing:
            return file_error(
                "MISSING_HEADER",
                "Required directory columns are missing: " + ", ".join(missing),
                {"sheet": SHEET_NAME, "row": HEADER_ROW, "column": None},
            )

        max_col = max(columns.values()) + 1
        for index, cells in enumerate(sheet.iter_rows(min_row=DATA_START, max_col=max_col), DATA_START):
            if all(cell.value is None for cell in cells):
                continue
            result["nonempty_row_count"] += 1
            source_base = {"sheet": SHEET_NAME, "row": index}
            failures = []
            values = {}

            def take(field, reader):
                column = columns[field]
                cell = cells[column]
                value, error = reader(cell)
                if error:
                    failures.append((column, error, cell.value))
                else:
                    values[field] = value

            take("tags", tags_from)
            take("excluded", bool_from)
            take("inactive", bool_from)
            take("contact_details", text_from)
            if "name" in columns:
                take("name", text_from)

            anonymous_id = None
            kcr_code = None
            if "anonymous_id" in columns:
                column = columns["anonymous_id"]
                anonymous_id, error = text_from(cells[column], as_key=True)
                if error:
                    failures.append((column, error, cells[column].value))
                    anonymous_id = None
                elif mode == "anonymous" and (anonymous_id is None or not ANONYMOUS.fullmatch(anonymous_id)):
                    failures.append((column, "INVALID_EXTERNAL_ID", cells[column].value))
                    anonymous_id = None
                elif anonymous_id is not None and not ANONYMOUS.fullmatch(anonymous_id):
                    failures.append((column, "INVALID_EXTERNAL_ID", cells[column].value))
                    anonymous_id = None

            if "kcr_code" in columns:
                column = columns["kcr_code"]
                kcr_code, error = text_from(cells[column], as_key=True)
                if error:
                    failures.append((column, error, cells[column].value))
                    kcr_code = None
                elif kcr_code is not None and not KCR.fullmatch(kcr_code):
                    failures.append((column, "INVALID_KCR_CODE", cells[column].value))
                    kcr_code = None

            if mode == "anonymous":
                external_id = anonymous_id
                if kcr_code is not None:
                    # Keep anonymized key; do not silently prefer a filled KCR column.
                    failures.append((
                        columns["kcr_code"],
                        "KCR_NOT_ALLOWED_IN_ANONYMOUS",
                        cells[columns["kcr_code"]].value,
                    ))
            else:
                external_id = kcr_code
                if anonymous_id is not None and kcr_code is not None:
                    failures.append((
                        columns.get("anonymous_id", columns["kcr_code"]),
                        "CONFLICTING_KEY_COLUMNS",
                        cells[columns.get("anonymous_id", 0)].value,
                    ))
                elif external_id is None and not any(col == columns["kcr_code"] for col, _, _ in failures):
                    failures.append((columns["kcr_code"], "INVALID_EXTERNAL_ID", cells[columns["kcr_code"]].value))

            if failures:
                for column, code, raw in failures:
                    row_error(
                        code,
                        f"Invalid field at column {column_letter(column)}",
                        {**source_base, "column": column_letter(column)},
                        raw,
                        external_id,
                    )
                continue

            data = {"external_id": external_id}
            for field in ("name", "contact_details"):
                if values.get(field) is not None:
                    data[field] = values[field]
            if values.get("tags") is not None:
                data["tags"] = values["tags"]
            if values.get("excluded") is not None:
                data["excluded"] = values["excluded"]
            if values.get("inactive") is not None:
                data["active"] = not values["inactive"]
            result["rows"].append({"source": source_base, "data": data})
        return result
    except (ParseError, BadZipFile, KeyError, ValueError):
        result["rows"] = []
        return file_error("INVALID_XLSX", "The XLSX package is malformed")
    finally:
        book.close()


def summary(result):
    duplicates = Counter(row["data"]["external_id"] for row in result["rows"])
    rejected = {(e["source"]["sheet"], e["source"]["row"]) for e in result["errors"] if e["scope"] == "row"}
    flagged = sum(
        1
        for row in result["rows"]
        if row["data"].get("excluded")
        or row["data"].get("active") is False
        or row["data"].get("tags")
        or row["data"].get("contact_details")
    )
    return {
        "source_rows": result["nonempty_row_count"],
        "parsed_rows": len(result["rows"]),
        "rejected_rows": len(rejected),
        "duplicates_in_parsed_rows": sum(count - 1 for count in duplicates.values()),
        "rows_with_flags_or_contacts": flagged,
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
