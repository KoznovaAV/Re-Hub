import importlib.util
import json
import unittest
from pathlib import Path

from app.customer_clients import parse_file as parse_clients
from app.customer_xlsx import parse_file as parse_snapshot

PACK = Path(__file__).resolve().parents[2] / "contracts" / "testing" / "h00" / "s1-s8"


def _build_pack() -> None:
    path = PACK / "build_pilot_pack.py"
    spec = importlib.util.spec_from_file_location("build_h00_s1_s8", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.build()


class H00S1S8PilotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _build_pack()
        cls.expected = json.loads((PACK / "expected.json").read_text(encoding="utf-8"))

    def test_pack_is_reproducible_and_covers_scenarios(self):
        self.assertEqual(self.expected["size"], 30)
        self.assertEqual(self.expected["covers"], [f"S-{n}" for n in range(1, 9)])
        self.assertEqual(len(self.expected["reference_ids"]), 9)
        for scenario, reason in self.expected["reasons"].items():
            self.assertTrue(reason, scenario)
            self.assertIn(scenario, self.expected["scenario_clients"])

        clients = parse_clients(
            PACK / "clients.xlsx",
            json.loads((PACK / "clients.context.json").read_text(encoding="utf-8")),
        )
        self.assertEqual(clients["errors"], [])
        self.assertEqual(len(clients["rows"]), 30)
        client_ids = {row["data"]["external_id"] for row in clients["rows"]}
        self.assertTrue(set(self.expected["reference_ids"]) <= client_ids)

        snap1 = parse_snapshot(
            PACK / "snapshot_1.xlsx",
            json.loads((PACK / "snapshot_1.context.json").read_text(encoding="utf-8")),
        )
        snap2 = parse_snapshot(
            PACK / "snapshot_2.xlsx",
            json.loads((PACK / "snapshot_2.context.json").read_text(encoding="utf-8")),
        )
        self.assertFalse(any(error["scope"] == "file" for error in snap1["errors"]))
        self.assertFalse(any(error["scope"] == "file" for error in snap2["errors"]))

        def q3_ids(result):
            return {
                row["data"]["external_id"]
                for row in result["rows"]
                if row["data"]["period_code"] == "2026Q3"
            }

        missing = self.expected["checks"]["S-7_missing_in_snapshot_2"]
        self.assertIn(missing, q3_ids(snap1))
        self.assertNotIn(missing, q3_ids(snap2))

        s8 = self.expected["checks"]["S-8_null_total_in_snapshot_2"]
        row = next(
            row for row in snap2["rows"]
            if row["data"]["external_id"] == s8 and row["data"]["period_code"] == "2026Q3"
        )
        self.assertIsNone(row["data"]["total_docs"])
        self.assertEqual(row["data"]["unsent_docs"], 30)
