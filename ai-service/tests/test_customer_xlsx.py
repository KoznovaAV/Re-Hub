from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook

from app.customer_xlsx import PERIODS, parse_file, summary


class CustomerSnapshotTest(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.file = Path(temp.name) / "snapshot.xlsx"
        self.context = {
            "contract_version": "1.0", "file_kind": "snapshot", "key_mode": "anonymous",
            "mapping_profile": "customer_october_tabs_v1", "snapshot_date": "2026-10-20",
            "period_scope": list(PERIODS.values()), "coverage": "unknown",
        }

    def make_fixture(self, extra_tab=False, bad_header=False):
        workbook = Workbook()
        workbook.remove(workbook.active)
        for title, period in PERIODS.items():
            tab = workbook.create_sheet(title)
            tab.append([])
            tab.append(["Уникальны обезличинный идентификатор",
                        "Код КЦР" if period == "Y2025" else "код СЦ", None,
                        "неверный заголовок" if bad_header else "документов всего",
                        "Всего не отправлено документов"])
            tab.append(["AAA00001", None, None, "1 245", 2])
            if period == "Y2025":
                tab.append(["AAA00001", None, None, 1245, 2])
                tab.append(["AAA00002", None, None, None, 0])
                tab.append(["AAA00003", None, None, 5, "=1+1"])
                tab.append(["#N/A", None, None, 5, 1])
                tab.append([1234567, None, None, 5, 1])
                tab.append(["AAA00004", None, None, 5, None])
        if extra_tab:
            workbook.create_sheet("Случайное имя")
        workbook.save(self.file)
        workbook.close()

    def test_periods_provenance_and_errors(self):
        self.make_fixture()
        result = parse_file(self.file, self.context)
        self.assertEqual(summary(result), {
            "source_rows": 10, "parsed_rows": 6, "rejected_rows": 4,
            "duplicates_in_parsed_rows": 1,
            "errors_by_code": {"FORMULA_NOT_ALLOWED": 1, "INVALID_EXTERNAL_ID": 2, "INTEGER_REQUIRED": 1},
        })
        self.assertEqual(result["rows"][0], {
            "source": {"sheet": "весь 2025 год", "row": 3},
            "data": {"external_id": "AAA00001", "period_code": "Y2025", "total_docs": 1245, "unsent_docs": 2},
        })
        self.assertIsNone(result["rows"][2]["data"]["total_docs"])
        self.assertEqual(result["errors"][0]["source"]["column"], "E")
        self.assertEqual(result["errors"][0]["key_hint"], {"external_id": "AAA00003", "period_code": "Y2025"})
        self.assertEqual({row["data"]["period_code"] for row in result["rows"]}, set(PERIODS.values()))

    def test_rejects_unknown_tabs_and_headers(self):
        for flags, code in [({"extra_tab": True}, "PERIOD_SCOPE_MISMATCH"), ({"bad_header": True}, "INVALID_HEADER")]:
            with self.subTest(code=code):
                self.make_fixture(**flags)
                result = parse_file(self.file, self.context)
                self.assertEqual(result["rows"], [])
                self.assertEqual(result["errors"][0]["code"], code)

    def test_customer_profile_cannot_switch_to_kcr_keys(self):
        self.make_fixture()
        with self.assertRaises(ValueError):
            parse_file(self.file, {**self.context, "key_mode": "kcr"})
