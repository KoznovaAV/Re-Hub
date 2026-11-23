from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook

from app.customer_clients import PROFILE, parse_file, summary


HEADERS = [
    "Уникальны обезличинный идентификатор",
    "Код КЦР",
    "Теги",
    "Не нужно работать",
    "Недействующий",
    "Контакты",
]


class CustomerClientsTest(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.file = Path(temp.name) / "directory.xlsx"
        self.context = {
            "contract_version": "1.0",
            "file_kind": "clients",
            "key_mode": "anonymous",
            "mapping_profile": PROFILE,
        }

    def make_fixture(self, rows, headers=None, sheet_name="Все КЦР", extra_sheet=False):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = sheet_name
        sheet.append([])
        sheet.append(headers or HEADERS)
        for row in rows:
            sheet.append(row)
        if extra_sheet:
            workbook.create_sheet("Лишнее")
        workbook.save(self.file)
        workbook.close()

    def test_parses_flags_tags_and_contacts(self):
        self.make_fixture([
            ["AAA00001", None, "vip;mpp", "да", "нет", "Иванов +7000"],
            ["AAA00002", None, None, "нет", "да", None],
            ["AAA00003", None, "[]", None, None, "Петров"],
        ])
        result = parse_file(self.file, self.context)
        self.assertEqual(summary(result)["parsed_rows"], 3)
        self.assertEqual(result["rows"][0]["data"], {
            "external_id": "AAA00001",
            "contact_details": "Иванов +7000",
            "tags": ["vip", "mpp"],
            "excluded": True,
            "active": True,
        })
        self.assertEqual(result["rows"][1]["data"], {
            "external_id": "AAA00002",
            "excluded": False,
            "active": False,
        })
        self.assertEqual(result["rows"][2]["data"], {
            "external_id": "AAA00003",
            "contact_details": "Петров",
            "tags": [],
        })

    def test_row_errors_for_bad_keys_tags_and_formulas(self):
        self.make_fixture([
            [1234567, None, "vip", "нет", "нет", None],
            ["AAA00001", None, "unknown", "нет", "нет", None],
            ["AAA00002", None, "vip", "=1+1", "нет", None],
            ["AAA00003", "123", "vip", "нет", "нет", None],
            ["AAA00004", "1234567", "vip", "нет", "нет", None],
        ])
        result = parse_file(self.file, self.context)
        self.assertEqual(result["rows"], [])
        self.assertEqual(summary(result)["errors_by_code"], {
            "KEY_MUST_BE_TEXT": 1,
            "UNKNOWN_TAG": 1,
            "FORMULA_OR_ERROR_NOT_ALLOWED": 1,
            "INVALID_KCR_CODE": 1,
            "KCR_NOT_ALLOWED_IN_ANONYMOUS": 1,
        })

    def test_rejects_wrong_sheet_and_unknown_header(self):
        self.make_fixture([["AAA00001", None, None, None, None, None]], sheet_name="Клиенты")
        bad_sheet = parse_file(self.file, self.context)
        self.assertEqual(bad_sheet["errors"][0]["code"], "UNEXPECTED_SHEETS")

        self.make_fixture(
            [["AAA00001", None, None, None, None, None]],
            headers=HEADERS[:-1] + ["Телефон"],
        )
        bad_header = parse_file(self.file, self.context)
        self.assertEqual(bad_header["errors"][0]["code"], "UNKNOWN_HEADER")

    def test_kcr_mode_uses_seven_digit_code(self):
        self.make_fixture([
            [None, "1234567", "newcomer", "нет", "нет", "Смирнов"],
        ])
        result = parse_file(self.file, {**self.context, "key_mode": "kcr"})
        self.assertEqual(result["rows"][0]["data"]["external_id"], "1234567")
        self.assertEqual(result["rows"][0]["data"]["tags"], ["newcomer"])

    def test_name_and_contacts_are_independent(self):
        self.make_fixture([["AAA00001", None, "vip", "нет", "нет", "Контакт +7000", "Компания"]],
                          headers=HEADERS + ["Название"])
        data = parse_file(self.file, self.context)["rows"][0]["data"]
        self.assertEqual(data["name"], "Компания")
        self.assertEqual(data["contact_details"], "Контакт +7000")

    def test_header_alias_cannot_silently_override_key(self):
        self.make_fixture([["AAA00001", None, None, None, None, None, "AAA00002"]],
                          headers=HEADERS + ["Уникальный обезличенный идентификатор"])
        result = parse_file(self.file, self.context)
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["errors"][0]["code"], "DUPLICATE_HEADER")
