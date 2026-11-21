import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.customer_clients import parse_file as parse_clients
from app.customer_xlsx import parse_file as parse_snapshot
from app.generate_test_data import generate


class GenerateTestDataTest(unittest.TestCase):
    def test_pilot_pack_parses(self):
        with TemporaryDirectory() as temp:
            out = Path(temp)
            manifest = generate(out, count=30, seed=42)
            self.assertEqual(manifest["client_count"], 30)

            clients = parse_clients(out / "clients.xlsx", json.loads((out / "clients.context.json").read_text(encoding="utf-8")))
            self.assertEqual(clients["errors"], [])
            self.assertEqual(len(clients["rows"]), 30)

            for name in ("snapshot_1", "snapshot_2"):
                parsed = parse_snapshot(
                    out / f"{name}.xlsx",
                    json.loads((out / f"{name}.context.json").read_text(encoding="utf-8")),
                )
                self.assertFalse(any(error["scope"] == "file" for error in parsed["errors"]), parsed["errors"][:3])
                self.assertGreater(len(parsed["rows"]), 0)

            by_id = {row["data"]["external_id"]: row["data"] for row in clients["rows"]}
            self.assertTrue(by_id["AAA00010"]["excluded"])
            self.assertEqual(by_id["AAA00007"]["tags"], ["newcomer"])

            snap1 = parse_snapshot(
                out / "snapshot_1.xlsx",
                json.loads((out / "snapshot_1.context.json").read_text(encoding="utf-8")),
            )
            snap2 = parse_snapshot(
                out / "snapshot_2.xlsx",
                json.loads((out / "snapshot_2.context.json").read_text(encoding="utf-8")),
            )
            s7_snap1 = [
                row for row in snap1["rows"]
                if row["data"]["external_id"] == "AAA00008" and row["data"]["period_code"] == "2026Q3"
            ]
            s7_snap2 = [
                row for row in snap2["rows"]
                if row["data"]["external_id"] == "AAA00008" and row["data"]["period_code"] == "2026Q3"
            ]
            self.assertEqual(len(s7_snap1), 1)
            self.assertEqual(s7_snap2, [])

            s8 = [
                row for row in snap2["rows"]
                if row["data"]["external_id"] == "AAA00009" and row["data"]["period_code"] == "2026Q3"
            ]
            self.assertEqual(len(s8), 1)
            self.assertIsNone(s8[0]["data"]["total_docs"])
            self.assertEqual(s8[0]["data"]["unsent_docs"], 30)
