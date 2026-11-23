from pathlib import Path
from tempfile import TemporaryDirectory
import stat
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from app import xlsx_limits


class XlsxLimitsTest(unittest.TestCase):
    def test_encrypted_entry_is_rejected(self):
        class Entry:
            flag_bits = 1
            external_attr = 0
            file_size = 0

        class Archive:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def infolist(self):
                return [Entry()]

        with patch.object(xlsx_limits, "ZipFile", return_value=Archive()):
            with self.assertRaises(xlsx_limits.WorkbookLimitError):
                xlsx_limits.check_archive("ignored.xlsx")

    def test_symlink_entry_is_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "link.xlsx"
            info = ZipInfo("link")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            with ZipFile(path, "w") as archive:
                archive.writestr(info, b"target")
            with self.assertRaises(xlsx_limits.WorkbookLimitError):
                xlsx_limits.check_archive(path)

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
