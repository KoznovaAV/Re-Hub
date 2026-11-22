import csv,json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from app.data_quality import report
from app.generate_test_data import generate
class DataQualityTest(unittest.TestCase):
    def test_one_command_artifacts_and_private_rows(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp);generate(p,30,42)
            result=report(p/'snapshot_1.xlsx',p/'clients.xlsx',p/'snapshot_1.context.json',p/'out',True)
            self.assertEqual(result['unknown_ids'],0)
            self.assertFalse(result['historical_claim']['verified'])
            self.assertTrue(result['input_sha256']['snapshot'])
            for name in ['data-quality.csv','data-quality.md','data-quality.json','unknown-private.csv']:
                self.assertTrue((p/'out'/name).is_file())
            self.assertNotIn('AAA00001',(p/'out/data-quality.csv').read_text())
