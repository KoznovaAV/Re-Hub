"""Общие ограничения XLSX до разбора XML и выделения памяти openpyxl."""
from zipfile import BadZipFile, LargeZipFile, ZipFile
import stat

MAX_ZIP_ENTRIES = 512
MAX_EXPANDED_BYTES = 200 * 1024 * 1024
MAX_ENTRY_BYTES = 50 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200


class WorkbookLimitError(ValueError):
    pass


def check_archive(path):
    """Проверить zip-контейнер до передачи файла в openpyxl."""
    try:
        with ZipFile(path) as archive:
            entries = archive.infolist()
            if any(item.flag_bits & 1 or stat.S_ISLNK(item.external_attr >> 16)
                   for item in entries):
                raise WorkbookLimitError("Encrypted or symlink entries are not supported")
            if (len(entries) > MAX_ZIP_ENTRIES
                    or sum(item.file_size for item in entries) > MAX_EXPANDED_BYTES):
                raise WorkbookLimitError("Workbook archive exceeds parsing limits")
            for item in entries:
                if item.file_size < 0:
                    raise BadZipFile("Workbook archive contains an invalid entry")
                if item.file_size > MAX_ENTRY_BYTES:
                    raise WorkbookLimitError("Workbook archive exceeds parsing limits")
                if (item.compress_size > 0
                        and item.file_size > 5 * 1024 * 1024
                        and item.file_size / item.compress_size > MAX_COMPRESSION_RATIO):
                    raise WorkbookLimitError("Workbook archive looks like a decompression bomb")
    except LargeZipFile as exc:
        raise WorkbookLimitError("Workbook archive exceeds parsing limits") from exc
