from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from openpyxl import Workbook

from app import customer_xlsx, xlsx_limits
from app.customer_xlsx import PERIODS, find_duplicates, parse_file, summary


class ExcelError(str):
    """Маркер, который записывается как настоящая ячейка ошибки Excel (``#N/A``)."""


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

    def add_row(self, tab, values):
        tab.append(list(values))
        row = tab.max_row
        for column, value in enumerate(values, 1):
            if isinstance(value, ExcelError):
                cell = tab.cell(row=row, column=column)
                cell.value = str(value)
                cell.data_type = "e"

    def make_fixture(self, rows_by_period=None, periods=None, extra_tab=False,
                     bad_header=False, with_headers=True):
        rows_by_period = rows_by_period or {}
        periods = periods or list(PERIODS)
        workbook = Workbook()
        workbook.remove(workbook.active)
        for title in periods:
            period = PERIODS[title]
            tab = workbook.create_sheet(title)
            tab.append([])
            if with_headers:
                tab.append(["Уникальны обезличинный идентификатор",
                            "Код КЦР" if period == "Y2025" else "код СЦ", None,
                            "неверный заголовок" if bad_header else "документов всего",
                            "Всего не отправлено документов"])
            else:
                tab.append([None, None, None, None, None])
            for values in rows_by_period.get(title, []):
                self.add_row(tab, values)
        if extra_tab:
            workbook.create_sheet("Случайное имя")
        workbook.save(self.file)
        workbook.close()

    def default_rows(self):
        rows = {title: [["AAA00001", None, None, "1 245", 2]] for title in PERIODS}
        rows["весь 2025 год"] = [
            ["AAA00001", None, None, "1 245", 2],
            ["AAA00001", None, None, 1245, 2],
            ["AAA00002", None, None, None, 0],
            ["AAA00003", None, None, 5, "=1+1"],
            [ExcelError("#N/A"), None, None, 5, 1],
            [1234567, None, None, 5, 1],
            ["AAA00004", None, None, 5, None],
        ]
        return rows

    def test_periods_provenance_and_errors(self):
        self.make_fixture(rows_by_period=self.default_rows())
        result = parse_file(self.file, self.context)
        self.assertEqual(summary(result), {
            "source_rows": 10, "parsed_rows": 6, "rejected_rows": 4,
            "duplicates_in_parsed_rows": 1,
            "duplicate_groups": 1,
            "duplicate_observations": 1,
            "errors_by_code": {
                "FORMULA_NOT_ALLOWED": 1, "EXCEL_CELL_ERROR": 1,
                "KEY_MUST_BE_TEXT": 1, "INTEGER_REQUIRED": 1,
            },
        })
        self.assertEqual(result["rows"][0], {
            "source": {"sheet": "весь 2025 год", "row": 3},
            "data": {"external_id": "AAA00001", "period_code": "Y2025",
                     "total_docs": 1245, "unsent_docs": 2},
        })
        self.assertIsNone(result["rows"][2]["data"]["total_docs"])
        self.assertEqual(result["errors"][0]["source"], {
            "sheet": "весь 2025 год", "row": 6, "column": "E"})
        self.assertEqual(result["errors"][0]["key_hint"],
                         {"external_id": "AAA00003", "period_code": "Y2025"})
        self.assertEqual({row["data"]["period_code"] for row in result["rows"]},
                         set(PERIODS.values()))

    def test_duplicate_pairs_are_retained_and_diagnosed(self):
        self.make_fixture(periods=["весь 2025 год", "1 кв 2026"], rows_by_period={
            "весь 2025 год": [
                ["AAA00001", None, None, 10, 1],
                ["AAA00001", None, None, 10, 1],
                ["AAA00001", None, None, 9, None],
            ],
            "1 кв 2026": [["AAA00001", None, None, 5, 0]],
        })
        self.context["period_scope"] = ["Y2025", "2026Q1"]
        result = parse_file(self.file, self.context)

        self.assertEqual(len(result["rows"]), 3)
        self.assertEqual(len(result["errors"]), 1)
        groups = find_duplicates(result)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["external_id"], "AAA00001")
        self.assertEqual(groups[0]["period_code"], "Y2025")
        self.assertEqual([(item["source"]["row"], item["kind"])
                          for item in groups[0]["observations"]],
                         [(3, "row"), (4, "row"), (5, "error")])
        self.assertEqual(summary(result)["duplicate_observations"], 2)
        # Тот же external_id в другом периоде — обычная строка истории, а не дубль.
        self.assertEqual(sum(1 for row in result["rows"]
                             if row["data"]["period_code"] == "2026Q1"), 1)

    def test_numbers_with_separators_and_error_codes(self):
        self.make_fixture(periods=["весь 2025 год"], rows_by_period={
            "весь 2025 год": [
                ["AAA00001", None, None, "1 245", 2],
                ["AAA00002", None, None, "1\u00a0234", 0],
                ["AAA00003", None, None, "1\u202f234", 1],
                ["AAA00004", None, None, 1245.0, 0],
                ["AAA00005", None, None, "1 24", 0],
                ["AAA00006", None, None, "12,5", 0],
                ["AAA00007", None, None, -1, 0],
                ["AAA00008", None, None, True, 0],
                ["AAA00009", None, None, 2147483648, 0],
                ["AAA00010", None, None, "=1+1", 0],
                ["AAA00011", None, None, 1, ExcelError("#N/A")],
            ],
        })
        self.context["period_scope"] = ["Y2025"]
        result = parse_file(self.file, self.context)

        self.assertEqual([row["data"]["total_docs"] for row in result["rows"]],
                         [1245, 1234, 1234, 1245])
        self.assertEqual(summary(result)["errors_by_code"], {
            "INVALID_INTEGER": 3, "INTEGER_OUT_OF_RANGE": 2,
            "FORMULA_NOT_ALLOWED": 1, "EXCEL_CELL_ERROR": 1,
        })
        by_row = {error["source"]["row"]: error for error in result["errors"]}
        self.assertEqual(by_row[7]["code"], "INVALID_INTEGER")
        self.assertEqual(by_row[7]["raw_value"], "1 24")
        self.assertEqual(by_row[13]["raw_value"], "#N/A")
        self.assertEqual(by_row[13]["key_hint"],
                         {"external_id": "AAA00011", "period_code": "Y2025"})

    def test_key_errors_have_precise_codes(self):
        self.make_fixture(periods=["весь 2025 год"], rows_by_period={
            "весь 2025 год": [
                [1234567, None, None, 5, 1],
                [ExcelError("#N/A"), None, None, 5, 1],
                ["=A1", None, None, 5, 1],
                [None, None, None, 5, 1],
            ],
        })
        self.context["period_scope"] = ["Y2025"]
        result = parse_file(self.file, self.context)
        self.assertEqual([error["code"] for error in result["errors"]], [
            "KEY_MUST_BE_TEXT", "EXCEL_CELL_ERROR", "FORMULA_NOT_ALLOWED",
            "INVALID_EXTERNAL_ID",
        ])
        self.assertTrue(all(error["source"]["column"] == "A" for error in result["errors"]))
        self.assertTrue(all(error["key_hint"]["external_id"] is None
                            for error in result["errors"]))

    def test_missing_total_is_a_valid_null(self):
        self.make_fixture(periods=["весь 2025 год"], rows_by_period={
            "весь 2025 год": [["AAA00001", None, None, None, 0]],
        })
        self.context["period_scope"] = ["Y2025"]
        result = parse_file(self.file, self.context)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["rows"][0]["data"], {
            "external_id": "AAA00001", "period_code": "Y2025",
            "total_docs": None, "unsent_docs": 0,
        })

    def test_empty_and_whitespace_rows_are_skipped(self):
        self.make_fixture(periods=["весь 2025 год"], rows_by_period={
            "весь 2025 год": [
                ["   ", None, None, None, None],
                ["AAA00001", None, None, 3, 1],
            ],
        })
        self.context["period_scope"] = ["Y2025"]
        result = parse_file(self.file, self.context)
        self.assertEqual(result["nonempty_row_count"], 1)
        self.assertEqual(len(result["rows"]), 1)

    def test_workbook_without_data_rows_is_rejected(self):
        self.make_fixture(periods=["весь 2025 год"])
        self.context["period_scope"] = ["Y2025"]
        result = parse_file(self.file, self.context)
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["errors"][0]["code"], "NO_DATA_ROWS")

    def test_row_limit_returns_file_error_with_partial_rows(self):
        self.make_fixture(periods=["весь 2025 год"], rows_by_period={
            "весь 2025 год": [
                ["AAA00001", None, None, 1, 0],
                ["AAA00002", None, None, 2, 0],
                ["AAA00003", None, None, 3, 0],
            ],
        })
        self.context["period_scope"] = ["Y2025"]
        result = parse_file(self.file, self.context, max_rows=2)
        self.assertEqual(len(result["rows"]), 2)
        self.assertEqual(result["errors"][-1]["code"], "ROW_LIMIT_EXCEEDED")
        self.assertEqual(result["errors"][-1]["scope"], "file")

    def test_rejects_unknown_tabs_and_headers(self):
        for flags, code in [({"extra_tab": True}, "PERIOD_SCOPE_MISMATCH"),
                            ({"bad_header": True}, "INVALID_HEADER")]:
            with self.subTest(code=code):
                self.make_fixture(rows_by_period=self.default_rows(), **flags)
                result = parse_file(self.file, self.context)
                self.assertEqual(result["rows"], [])
                self.assertEqual(result["errors"][0]["code"], code)

    def test_invalid_workbook_is_a_file_error(self):
        self.file.write_bytes(b"not an xlsx")
        result = parse_file(self.file, self.context)
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["errors"][0]["code"], "INVALID_XLSX")

    def test_zip_archive_size_limit_is_a_file_error(self):
        original = xlsx_limits.MAX_EXPANDED_BYTES
        xlsx_limits.MAX_EXPANDED_BYTES = 1024
        try:
            with ZipFile(self.file, "w") as archive:
                archive.writestr("xl/workbook.xml", b"0" * 4096)
            result = parse_file(self.file, self.context)
        finally:
            xlsx_limits.MAX_EXPANDED_BYTES = original
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["errors"][0]["code"], "XLSX_LIMIT_EXCEEDED")

    def test_defusedxml_is_active(self):
        import openpyxl
        self.assertTrue(openpyxl.DEFUSEDXML)

    def test_scanned_row_limit_stops_pathological_empty_rows(self):
        original = customer_xlsx.DEFAULT_MAX_SCANNED_ROWS
        customer_xlsx.DEFAULT_MAX_SCANNED_ROWS = 2
        try:
            self.make_fixture(periods=["весь 2025 год"], rows_by_period={
                "весь 2025 год": [[None, None, None, None, None]] * 5,
            })
            self.context["period_scope"] = ["Y2025"]
            result = parse_file(self.file, self.context)
        finally:
            customer_xlsx.DEFAULT_MAX_SCANNED_ROWS = original
        self.assertEqual(result["errors"][-1]["code"], "ROW_LIMIT_EXCEEDED")

    def test_customer_profile_cannot_switch_to_kcr_keys(self):
        self.make_fixture(rows_by_period=self.default_rows())
        with self.assertRaises(ValueError):
            parse_file(self.file, {**self.context, "key_mode": "kcr"})

    def test_context_validation(self):
        self.make_fixture(rows_by_period=self.default_rows())
        invalid = [
            {**self.context, "snapshot_date": "20.10.2026"},
            {**self.context, "snapshot_date": 20261020},
            {**self.context, "period_scope": ["2026Q1", "2026Q1"]},
            {**self.context, "period_scope": ["2026Q4"]},
            {**self.context, "unexpected": True},
            {key: value for key, value in self.context.items() if key != "coverage"},
        ]
        for context in invalid:
            with self.subTest(context=context):
                with self.assertRaises(ValueError):
                    parse_file(self.file, context)
