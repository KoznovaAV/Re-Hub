"""Общие ограничения XLSX до разбора XML и выделения памяти openpyxl."""
from zipfile import ZipFile
import stat

MAX_ZIP_ENTRIES = 512
MAX_EXPANDED_BYTES = 200 * 1024 * 1024


class WorkbookLimitError(ValueError):
    pass


def check_archive(path):
    with ZipFile(path) as archive:
        entries = archive.infolist()
        if any(item.flag_bits & 1 or stat.S_ISLNK(item.external_attr >> 16) for item in entries):
            raise WorkbookLimitError("Encrypted or symlink entries are not supported")
        if len(entries) > MAX_ZIP_ENTRIES or sum(item.file_size for item in entries) > MAX_EXPANDED_BYTES:
            raise WorkbookLimitError("Workbook archive exceeds parsing limits")
