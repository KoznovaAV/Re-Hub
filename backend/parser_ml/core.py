import re
import math
from datetime import datetime
from zipfile import BadZipFile
from typing import Dict, Any, Tuple, Optional

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
CURRENT_YEAR = datetime.now().year
MIN_YEAR = CURRENT_YEAR - 10  # Разрешаем данные за последние 10 лет
MAX_YEAR = CURRENT_YEAR + 2   # Разрешаем планы на 2 года вперед


def get_period_code(sheet_name: str) -> Optional[str]:
    clean_name = sheet_name.strip()
    
    # Проверка на "весь YYYY год"
    match_year = re.match(r'^весь\s+(\d{4})\s+год$', clean_name, re.IGNORECASE)
    if match_year:
        year = int(match_year.group(1))
        if MIN_YEAR <= year <= MAX_YEAR:
            return f"Y{year}"
        return None

    # Проверка на "X кв YYYY"
    match_q = re.match(r'^([1-4])\s+кв\s+(\d{4})$', clean_name, re.IGNORECASE)
    if match_q:
        quarter = int(match_q.group(1))
        year = int(match_q.group(2))
        if quarter in (1, 2, 3, 4) and MIN_YEAR <= year <= MAX_YEAR:
            return f"{year}Q{quarter}"
            
    return None


def _clean_string(cell: Any) -> Tuple[Optional[str], Optional[str]]:
    if cell.data_type in {"f", "e"}:
        return None, "FORMULA_OR_ERROR_NOT_ALLOWED"
    val = cell.value
    if val is None:
        return None, None
    s = str(val).strip()
    return (s, None) if s else (None, None)


def _clean_number(cell: Any, allow_missing: bool) -> Tuple[Optional[float], Optional[str]]:
    if cell.data_type == "f":
        return None, "FORMULA_NOT_ALLOWED"
    if cell.data_type == "e":
        return None, "EXCEL_CELL_ERROR"
        
    val = cell.value
    if val is None or (isinstance(val, str) and not val.strip()):
        return None, (None if allow_missing else "REQUIRED_FIELD_MISSING")
        
    if type(val) in (int, float) and math.isfinite(val):
        return float(val), None
        
    if isinstance(val, str):
        # Убираем пробелы тысяч и меняем запятую на точку
        s = val.strip().replace(" ", "").replace("\u00A0", "").replace(",", ".")
        try:
            return float(s), None
        except ValueError:
            return None, "INVALID_NUMBER"
            
    return None, "INVALID_NUMBER"


def parse_file(file_path: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    result = {
        "contract_version": "1.0",
        "rows": [],
        "errors": []
    }

    def file_error(code: str, message: str, source: Optional[dict] = None) -> Dict[str, Any]:
        result["errors"].append({
            "scope": "file", "code": code, "message": message, "source": source
        })
        return result

    # Загрузка файла
    try:
        book = load_workbook(file_path, read_only=True, data_only=False, keep_links=False)
    except (OSError, BadZipFile, InvalidFileException, ValueError, KeyError):
        return file_error("INVALID_XLSX", "The XLSX package could not be opened")

    try:
        # Проверка вкладок
        sheet_to_period = {}
        for sheet in book.sheetnames:
            code = get_period_code(sheet)
            if not code:
                return file_error("UNKNOWN_TAB", f"Unknown tab: '{sheet}'", {"sheet": sheet})
            sheet_to_period[sheet] = code

        # Чтение данных
        for sheet in book:
            period = sheet_to_period[sheet.title]
            
            for row_idx, cells in enumerate(sheet.iter_rows(min_row=3, max_col=5), start=3):
                if all(cell.value is None for cell in cells):
                    continue
                    
                source = {"sheet": sheet.title, "row": row_idx}
                row_failures = []
                
                # Читаем колонки: A(0), B(1), D(3), E(4). Колонку C(2) игнорируем.
                raw_id, id_err = _clean_string(cells[0])
                raw_kcr, kcr_err = _clean_string(cells[1])
                total, total_err = _clean_number(cells[3], allow_missing=True)
                unsent, unsent_err = _clean_number(cells[4], allow_missing=False)
                
                key_hint = raw_id or "unknown"
                
                if id_err or not raw_id:
                    row_failures.append(("A", id_err or "ID_EMPTY", cells[0].value))
                if kcr_err or not raw_kcr:
                    row_failures.append(("B", kcr_err or "KCR_EMPTY", cells[1].value))
                if total_err:
                    row_failures.append(("D", total_err, cells[3].value))
                if unsent_err:
                    row_failures.append(("E", unsent_err, cells[4].value))

                if row_failures:
                    for col, code, raw_val in row_failures:
                        result["errors"].append({
                            "scope": "row",
                            "code": code,
                            "message": f"Invalid field at column {col}",
                            "source": {**source, "column": col},
                            "raw_value": raw_val if isinstance(raw_val, (str, int, float, bool)) else None,
                            "key_hint": key_hint
                        })
                else:
                    parsed_data = {
                        "sheet": sheet.title,
                        "period_code": period,
                        "date": context.get("snapshot_date") if context else None,
                        "id": raw_id,
                        "kcr": raw_kcr,
                        "total": total,
                        "unsent": unsent
                    }
                    result["rows"].append({"source": source, "data": parsed_data})
                    
        return result
        
    finally:
        book.close()