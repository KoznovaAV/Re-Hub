import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from parser_ml.core import parse_file

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures', 'import')
TEST_XLSX = os.path.join(FIXTURES_DIR, 'sample_data.xlsx')

def test_parser_runs_without_crash():
    context = {"snapshot_date": "2026-10-31"}
    result = parse_file(TEST_XLSX, context)
    
    assert "rows" in result
    assert "errors" in result
    # Проверяем, что нет фатальных ошибок файла (вкладки правильные)
    file_errors = [e for e in result["errors"] if e["scope"] == "file"]
    assert len(file_errors) == 0, f"Файл заблокирован: {file_errors}"

def test_validation_errors():
    context = {"snapshot_date": "2026-10-31"}
    result = parse_file(TEST_XLSX, context)
    errors = result["errors"]
    
    assert len(errors) > 0, "Парсер должен был найти ошибки"
    
    # Проверяем, что ошибка в колонке D найдена (формула/неверный формат)
    d_errors = [e for e in errors if e["source"].get("column") == "D"]
    assert len(d_errors) > 0, "Не найдена ошибка в колонке D"
    
    # Проверяем, что ошибка пустого обязательного поля в колонке E найдена
    missing_errors = [e for e in errors if e["code"] == "REQUIRED_FIELD_MISSING"]
    assert len(missing_errors) > 0, "Не найдена ошибка пустого поля"