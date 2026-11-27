import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "h00" / "m05_protocol.py"
spec = importlib.util.spec_from_file_location("m05_protocol", MODULE_PATH)
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)


class M05ProtocolTest(unittest.TestCase):
    def data(self):
        gold = {
            group: {
                "all_ids": [f"{group}{index}" for index in range(15)],
                "expected": [f"{group}0"],
                "excluded": [f"{group}1"],
                "approved_by": "expert",
            }
            for group in ("A", "B")
        }
        runs = [
            {"participant": "P-1", "tool": "excel", "group": "A", "seconds": 100, "ids": ["A0"]},
            {"participant": "P-1", "tool": "rehub", "group": "B", "seconds": 40, "ids": ["B0"]},
            {"participant": "P-2", "tool": "rehub", "group": "A", "seconds": 40, "ids": ["A0"]},
            {"participant": "P-2", "tool": "excel", "group": "B", "seconds": 100, "ids": ["B0"]},
        ]
        return {"data_kind": "measured", "gold": gold, "runs": runs}

    def test_two_administrators_fill_protocol(self):
        result = protocol.build_protocol(self.data())
        self.assertEqual(result["status"], "filled")
        self.assertEqual(result["participants"], ["P-1", "P-2"])
        self.assertEqual(len(result["runs"]), 4)
        text = protocol.render(result)
        self.assertIn("P-1", text)
        self.assertIn("P-2", text)
        self.assertIn("Ускорение", text)
        self.assertIn("100.000", text)

    def test_simulated_data_cannot_fill_m05(self):
        payload = self.data()
        payload["data_kind"] = "simulated"
        with self.assertRaises(ValueError):
            protocol.build_protocol(payload)

    def test_single_participant_is_rejected(self):
        payload = self.data()
        payload["runs"] = payload["runs"][:2]
        with self.assertRaises(ValueError):
            protocol.build_protocol(payload)

    def test_missing_expert_is_rejected(self):
        payload = self.data()
        payload["gold"]["A"]["approved_by"] = ""
        with self.assertRaises(ValueError):
            protocol.build_protocol(payload)
