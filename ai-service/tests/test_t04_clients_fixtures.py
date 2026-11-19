import json
import unittest
from pathlib import Path

from app.customer_clients import parse_file, summary

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "t04"


class T04ClientsFixturesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed = json.loads((FIXTURES / "clients_seed.json").read_text(encoding="utf-8"))
        cls.context = json.loads((FIXTURES / "clients.context.json").read_text(encoding="utf-8"))
        cls.expected = json.loads((FIXTURES / "clients.expected.json").read_text(encoding="utf-8"))
        cls.workbook = FIXTURES / "clients.xlsx"

    def test_seed_covers_thirty_clients_and_eight_scenarios(self):
        clients = self.seed["clients"]
        self.assertEqual(len(clients), 30)
        covered = {scenario for client in clients for scenario in client.get("scenarios") or []}
        self.assertEqual(covered, {f"S-{n}" for n in range(1, 9)})
        self.assertGreaterEqual(sum(1 for client in clients if client["excluded"]), 3)
        self.assertGreaterEqual(sum(1 for client in clients if client["inactive"]), 3)

    def test_parser_matches_golden_result(self):
        result = parse_file(self.workbook, self.context)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["nonempty_row_count"], 30)
        self.assertEqual(len(result["rows"]), 30)
        self.assertEqual(
            [{"source": row["source"], "data": row["data"]} for row in result["rows"]],
            self.expected["rows"],
        )
        counts = summary(result)
        self.assertEqual(counts["parsed_rows"], 30)
        self.assertEqual(counts["rejected_rows"], 0)
        self.assertEqual(counts["duplicates_in_parsed_rows"], 0)

    def test_excluded_and_inactive_flags_present(self):
        result = parse_file(self.workbook, self.context)
        by_id = {row["data"]["external_id"]: row["data"] for row in result["rows"]}
        self.assertTrue(by_id["AAA00010"]["excluded"])
        self.assertTrue(by_id["AAA00013"]["active"] is False)
        self.assertEqual(by_id["AAA00016"]["tags"], ["vip", "integrator"])
        self.assertEqual(by_id["AAA00007"]["tags"], ["newcomer"])
        self.assertEqual(
            self.expected["meta"]["scenario_clients"]["S-6"],
            ["AAA00006", "AAA00007"],
        )
