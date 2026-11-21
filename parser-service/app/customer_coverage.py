"""Measure unique-ID coverage of the supplied snapshot against its directory."""

import argparse
from collections import Counter
import json
from pathlib import Path

from openpyxl import load_workbook

from .customer_xlsx import ANONYMOUS, key_from, parse_file


def coverage(snapshot, directory, context):
    parsed = parse_file(snapshot, context)
    if any(error["scope"] == "file" for error in parsed["errors"]):
        raise ValueError("The snapshot did not pass format validation")
    book = load_workbook(directory, read_only=True, data_only=False, keep_links=False)
    try:
        if book.sheetnames != ["Все КЦР"]:
            raise ValueError("Unexpected directory sheets")
        clients = {key for (cell,) in book.active.iter_rows(min_row=3, max_col=1)
                   if (key := key_from(cell, ANONYMOUS))}
    finally:
        book.close()
    periods = {}
    unknown = []
    for row in parsed["rows"]:
        key, period = row["data"]["external_id"], row["data"]["period_code"]
        periods.setdefault(period, set()).add(key)
        if key not in clients:
            unknown.append(row)
    keys = set().union(*periods.values())
    missing = keys - clients
    return {
        "directory_ids": len(clients), "snapshot_ids": len(keys), "matched_ids": len(keys & clients),
        "unknown_ids": len(missing), "unknown_percent": round(100 * len(missing) / len(keys), 2) if keys else None,
        "unknown_rows_by_period": dict(Counter(row["data"]["period_code"] for row in unknown)),
        "unique_ids_by_period": {period: len(ids) for period, ids in periods.items()},
    }, unknown


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("directory", type=Path)
    parser.add_argument("context", type=Path)
    parser.add_argument("--private-unknown-output", type=Path, help="Optional new local JSON file with source rows")
    args = parser.parse_args()
    result, unknown = coverage(args.snapshot, args.directory, json.loads(args.context.read_text(encoding="utf-8")))
    if args.private_unknown_output:
        with args.private_unknown_output.open("x", encoding="utf-8") as output:
            json.dump(unknown, output, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
