import json
from pathlib import Path
import unittest

from app.customer_xlsx import find_duplicates, parse_file, summary

FIXTURES = Path(__file__).parent / "fixtures" / "snapshot"


class SnapshotGoldenFixtureTest(unittest.TestCase):
    def cases(self):
        for workbook in sorted(FIXTURES.glob("*.xlsx")):
            context = json.loads(
                workbook.with_suffix(".context.json").read_text(encoding="utf-8"))
            expected = json.loads(
                workbook.with_suffix(".expected.json").read_text(encoding="utf-8"))
            yield workbook, context, expected

    def test_golden_parser_results(self):
        seen = 0
        for workbook, context, expected in self.cases():
            with self.subTest(case=workbook.stem):
                result = parse_file(workbook, context)
                self.assertEqual(result, expected)
                seen += 1
        self.assertGreaterEqual(seen, 4)

    def test_repeating_the_same_parse_is_deterministic(self):
        for workbook, context, expected in self.cases():
            with self.subTest(case=workbook.stem):
                first = parse_file(workbook, context)
                second = parse_file(workbook, context)
                self.assertEqual(first, expected)
                self.assertEqual(second, expected)

    def test_duplicate_case_keeps_rows_and_reports_positions(self):
        workbook = FIXTURES / "duplicates.xlsx"
        context = json.loads(
            workbook.with_suffix(".context.json").read_text(encoding="utf-8"))
        result = parse_file(workbook, context)
        groups = find_duplicates(result)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["period_code"], "Y2025")
        self.assertEqual(len(groups[0]["observations"]), 4)
        self.assertEqual(summary(result)["duplicate_observations"], 3)

    def test_missing_total_case_is_a_null_not_an_error(self):
        workbook = FIXTURES / "repeat-missing-total.xlsx"
        context = json.loads(
            workbook.with_suffix(".context.json").read_text(encoding="utf-8"))
        result = parse_file(workbook, context)
        self.assertEqual(result["errors"], [])
        self.assertEqual([row["data"]["total_docs"] for row in result["rows"]],
                         [None, None])
