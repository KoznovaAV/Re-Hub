"""Reproduce the independent sheet/row check for ten four-period clients."""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import posixpath
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from .customer_xlsx import parse_file

NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
# Ground truth recorded separately from the adapter's mapping.
EXPECTED = {"весь 2025 год": "Y2025", "1 кв 2026": "2026Q1", "2 кв 2026": "2026Q2", "3 кв 2026": "2026Q3"}


def verify(path, context):
    parsed = parse_file(path, context)
    observations = defaultdict(set)
    for row in parsed["rows"]:
        observations[row["data"]["external_id"]].add(row["data"]["period_code"])
    sample = set(sorted(key for key, periods in observations.items() if periods == set(EXPECTED.values()))[:10])
    if len(sample) != 10:
        raise ValueError("Fewer than ten clients with observations in all four periods")
    expected = Counter()
    with ZipFile(path) as archive:
        relations = {r.get("Id"): r.get("Target") for r in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
        strings = ["".join(c.itertext()) for c in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        for sheet in workbook.findall(".//x:sheet", NS):
            target = relations[sheet.get(REL_ID)]
            part = target.lstrip("/") if target.startswith("/") else posixpath.join("xl", target)
            for cell in ET.fromstring(archive.read(part)).findall(".//x:c", NS):
                coordinate = cell.get("r", "")
                if re.fullmatch(r"A\d+", coordinate) and cell.get("t") == "s":
                    key = strings[int(cell.find("x:v", NS).text)]
                    if key in sample:
                        expected[(key, EXPECTED[sheet.get("name")], int(coordinate[1:]))] += 1
    observed = Counter((row["data"]["external_id"], row["data"]["period_code"], row["source"]["row"])
                       for row in parsed["rows"] if row["data"]["external_id"] in sample)
    if expected != observed:
        raise ValueError("Coordinates or assigned periods differ from workbook XML")
    return {"clients": len(sample), "source_rows": sum(expected.values()), "matched_rows": sum(observed.values())}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("context", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.snapshot, json.loads(args.context.read_text(encoding="utf-8"))), indent=2))
