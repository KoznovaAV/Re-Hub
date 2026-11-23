from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from app import xlsx_limits


class XlsxLimitsTest(unittest.TestCase):
    def test_entry_count_limit(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "many.xlsx"
            with ZipFile(path, "w") as archive:
                archive.writestr("a.xml", b"a")
                archive.writestr("b.xml", b"b")
            with patch.object(xlsx_limits, "MAX_ZIP_ENTRIES", 1):
                with self.assertRaises(xlsx_limits.WorkbookLimitError):
                    xlsx_limits.check_archive(path)

    def test_entry_size_limit(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "entry.xlsx"
            with ZipFile(path, "w") as archive:
                archive.writestr("a.xml", b"ab")
            with patch.object(xlsx_limits, "MAX_ENTRY_BYTES", 1):
                with self.assertRaises(xlsx_limits.WorkbookLimitError):
                    xlsx_limits.check_archive(path)

    def test_compression_ratio_limit(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ratio.xlsx"
            with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("a.xml", b"0" * (6 * 1024 * 1024))
            with patch.object(xlsx_limits, "MAX_COMPRESSION_RATIO", 10):
                with self.assertRaises(xlsx_limits.WorkbookLimitError):
                    xlsx_limits.check_archive(path)


if __name__ == "__main__":
    unittest.main()
