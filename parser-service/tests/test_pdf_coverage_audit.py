import unittest
from app.pdf_coverage_audit import compare_sets
class PDFCoverageAuditTest(unittest.TestCase):
    def test_extractor_loss_explains_only_matching_unknowns(self):
        native={'AAA00001','AAA00002','AAA00003'}
        snapshot={'AAA00001','AAA00002','AAA00004'}
        evidence=compare_sets(native,snapshot,{'full':native,'lossy':{'AAA00001'}})
        self.assertTrue(evidence['full']['equals_native'])
        self.assertEqual(evidence['full']['unknown_ids'],1)
        self.assertEqual(evidence['lossy']['missing_native_ids'],2)
        self.assertEqual(evidence['lossy']['lost_matching_ids'],1)
        self.assertEqual(evidence['lossy']['unknown_ids']-evidence['full']['unknown_ids'],1)
        self.assertFalse(evidence['lossy']['equals_native'])
