import json
from pathlib import Path
import tempfile
import unittest

from app.call_list_metrics import compare_files, compare_lists, load_list

FIXTURES = Path(__file__).parent / "fixtures" / "v02"


def item(external_id, period_code="Y2025", excluded=False, reason=None):
    payload = {"external_id": external_id, "period_code": period_code, "excluded": excluded}
    if reason is not None:
        payload["exclusion_reason"] = reason
    return payload


class CallListMetricsTest(unittest.TestCase):
    def test_synthetic_fixture_metrics(self):
        result = compare_files(FIXTURES / "reference.json", FIXTURES / "actual.json")
        self.assertEqual(result["counts"], {
            "reference_items": 5,
            "reference_required": 4,
            "reference_excluded": 1,
            "actual_items": 5,
            "actual_included": 4,
            "actual_excluded": 1,
            "true_positive": 2,
            "false_positive_extra": 2,
            "false_negative_missing": 2,
        })
        self.assertEqual(result["precision"], 0.5)
        self.assertEqual(result["recall"], 0.5)
        self.assertEqual(result["f1"], 0.5)
        self.assertEqual(result["extra"], [
            {"external_id": "AAA00004", "period_code": "2026Q1"},
            {"external_id": "AAA00006", "period_code": "2026Q3"},
        ])
        self.assertEqual(result["missing"], [
            {"external_id": "AAA00002", "period_code": "Y2025"},
            {"external_id": "AAA00005", "period_code": "2026Q2"},
        ])
        exceptions = result["exceptions"]
        self.assertEqual(len(exceptions["reference_excluded"]), 1)
        self.assertEqual(exceptions["reference_excluded"][0]["reason"],
                         "synthetic exclusion")
        self.assertEqual(exceptions["included_despite_exclusion"], [
            {"external_id": "AAA00004", "period_code": "2026Q1",
             "reason": "synthetic exclusion"},
        ])
        self.assertEqual(exceptions["required_but_marked_excluded"], [
            {"external_id": "AAA00005", "period_code": "2026Q2",
             "reason": "operator marked as exception"},
        ])

    def test_period_code_is_part_of_the_key(self):
        result = compare_lists(
            [item("AAA00001", "Y2025")],
            [item("AAA00001", "2026Q1")],
        )
        self.assertEqual(result["counts"]["true_positive"], 0)
        self.assertEqual(result["counts"]["false_positive_extra"], 1)
        self.assertEqual(result["counts"]["false_negative_missing"], 1)

    def test_reference_exclusions_do_not_lower_recall(self):
        result = compare_lists(
            [item("AAA00001", excluded=True, reason="test")],
            [item("AAA00002")],
        )
        self.assertEqual(result["counts"]["reference_required"], 0)
        self.assertEqual(result["counts"]["reference_excluded"], 1)
        self.assertIsNone(result["recall"])
        self.assertEqual(result["precision"], 0.0)

    def test_both_empty_lists_have_undefined_metrics(self):
        result = compare_lists([], [])
        self.assertIsNone(result["precision"])
        self.assertIsNone(result["recall"])
        self.assertIsNone(result["f1"])

    def test_duplicate_keys_are_rejected(self):
        with self.assertRaises(ValueError):
            compare_lists([item("AAA00001"), item("AAA00001")], [])

    def test_top_level_array_and_items_object_are_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "list.json"
            path.write_text(json.dumps([item("AAA00001")]), encoding="utf-8")
            self.assertEqual(len(load_list(path)), 1)
            path.write_text(json.dumps({"items": [item("AAA00002")]}), encoding="utf-8")
            self.assertEqual(load_list(path)[0]["external_id"], "AAA00002")

    def test_invalid_item_is_rejected(self):
        with self.assertRaises(ValueError):
            compare_lists([{"external_id": ""}], [])
        with self.assertRaises(ValueError):
            compare_lists([{"external_id": "AAA00001", "excluded": "no"}], [])
