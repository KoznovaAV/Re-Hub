import importlib.util
import json
import unittest
from pathlib import Path

from app.customer_xlsx import parse_file

ROOT = Path(__file__).resolve().parent / "fixtures" / "negative"


def _build_fixtures() -> None:
    path = ROOT / "build_negative_fixtures.py"
    spec = importlib.util.spec_from_file_location("build_negative_fixtures", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.build()


class NegativeFixturesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _build_fixtures()
        cls.context = json.loads((ROOT / "snapshot.context.json").read_text(encoding="utf-8"))
        cls.expected = json.loads((ROOT / "expected.json").read_text(encoding="utf-8"))

    def test_parser_negatives_duplicate_na_unknown_missing_total(self):
        result = parse_file(ROOT / "snapshot-negatives.xlsx", self.context)
        expect = self.expected["snapshot-negatives.xlsx"]
        codes = [error["code"] for error in result["errors"] if error["scope"] == "row"]
        self.assertEqual(codes, expect["parser_error_codes"])
        for error in result["errors"]:
            if error["scope"] != "row":
                continue
            self.assertIn("source", error)
            self.assertIn("row", error["source"])
            self.assertIn("column", error["source"])
            self.assertTrue(error["code"])
            self.assertTrue(error["message"])
            self.assertIn("raw_value", error)

        parsed_ids = [row["data"]["external_id"] for row in result["rows"] if row["data"]["period_code"] == "2026Q3"]
        self.assertEqual(parsed_ids, expect["parsed_external_ids"])
        missing_total = next(
            row for row in result["rows"]
            if row["data"]["external_id"] == expect["missing_total_external_id"] and row["data"]["period_code"] == "2026Q3"
        )
        self.assertIsNone(missing_total["data"]["total_docs"])
        duplicate_count = sum(1 for row in result["rows"] if row["data"]["external_id"] == expect["duplicate_external_id"] and row["data"]["period_code"] == "2026Q3")
        self.assertEqual(duplicate_count, 2)

    def test_client_disappeared_between_snapshots(self):
        before = parse_file(ROOT / "snapshot-before-missing-client.xlsx", {
            **self.context, "snapshot_date": "2026-09-29",
        })
        after = parse_file(ROOT / "snapshot-after-missing-client.xlsx", self.context)
        expect = self.expected["missing-client-pair"]

        def ids(result):
            return sorted(
                row["data"]["external_id"]
                for row in result["rows"]
                if row["data"]["period_code"] == "2026Q3"
            )

        self.assertEqual(ids(before), sorted(expect["before_ids_2026Q3"]))
        self.assertEqual(ids(after), sorted(expect["after_ids_2026Q3"]))
        self.assertEqual(sorted(set(ids(before)) - set(ids(after))), sorted(expect["disappeared"]))
