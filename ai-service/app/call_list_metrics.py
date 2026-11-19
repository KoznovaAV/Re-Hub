"""V-02 skeleton: compare a reference call list with an actual call list.

No M-01 ground truth and no production parser are involved yet.  The module
accepts small JSON list exports, so it can be exercised on synthetic fixtures
and later fed by the approved M-01 data without changing the metric shape.

Input item::

    {"external_id": "AAA00001", "period_code": "Y2025",
     "excluded": false, "exclusion_reason": null}

A top-level list or an object with an ``items`` list is accepted.  Duplicate
keys are rejected: without a single key per list precision/recall is ambiguous.
"""

import argparse
import json
from pathlib import Path

LIST_VERSION = "1.0"
METRIC_VERSION = "v0-synthetic"


def load_list(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return payload["items"]
    raise ValueError("list file must be a JSON array or an object with an items array")


def normalize_item(item):
    if not isinstance(item, dict):
        raise ValueError("each list item must be an object")
    external_id = item.get("external_id")
    if not isinstance(external_id, str) or not external_id.strip():
        raise ValueError("external_id must be a non-empty string")
    period_code = item.get("period_code")
    if period_code is not None and (not isinstance(period_code, str)
                                    or not period_code.strip()):
        raise ValueError("period_code must be a non-empty string or null")
    excluded = item.get("excluded", False)
    if type(excluded) is not bool:
        raise ValueError("excluded must be a boolean")
    reason = item.get("exclusion_reason", item.get("reason"))
    if reason is not None and not isinstance(reason, str):
        raise ValueError("exclusion_reason must be a string or null")
    return {
        "external_id": external_id.strip(),
        "period_code": period_code.strip() if period_code else None,
        "excluded": excluded,
        "reason": reason,
    }


def index_items(items, label):
    index = {}
    for raw in items:
        item = normalize_item(raw)
        key = (item["external_id"], item["period_code"])
        if key in index:
            raise ValueError(f"duplicate key in {label}: {key[0]} / {key[1]}")
        index[key] = item
    return index


def key_object(key, reason=None):
    payload = {"external_id": key[0], "period_code": key[1]}
    if reason is not None:
        payload["reason"] = reason
    return payload


def sorted_keys(keys):
    return sorted(keys, key=lambda key: (key[0], key[1] or ""))


def ratio(numerator, denominator):
    return round(numerator / denominator, 6) if denominator else None


def f1_score(precision, recall):
    if precision is None or recall is None:
        return None
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 6)


def compare_lists(reference, actual):
    reference_index = index_items(reference, "reference")
    actual_index = index_items(actual, "actual")

    reference_required = {key for key, item in reference_index.items() if not item["excluded"]}
    reference_excluded = {key for key, item in reference_index.items() if item["excluded"]}
    actual_included = {key for key, item in actual_index.items() if not item["excluded"]}
    actual_excluded = {key for key, item in actual_index.items() if item["excluded"]}

    true_positive = reference_required & actual_included
    extra = actual_included - reference_required
    missing = reference_required - actual_included

    precision = ratio(len(true_positive), len(true_positive) + len(extra))
    recall = ratio(len(true_positive), len(true_positive) + len(missing))

    return {
        "list_version": LIST_VERSION,
        "metric_version": METRIC_VERSION,
        "key_fields": ["external_id", "period_code"],
        "counts": {
            "reference_items": len(reference_index),
            "reference_required": len(reference_required),
            "reference_excluded": len(reference_excluded),
            "actual_items": len(actual_index),
            "actual_included": len(actual_included),
            "actual_excluded": len(actual_excluded),
            "true_positive": len(true_positive),
            "false_positive_extra": len(extra),
            "false_negative_missing": len(missing),
        },
        "precision": precision,
        "recall": recall,
        "f1": f1_score(precision, recall),
        "extra": [key_object(key) for key in sorted_keys(extra)],
        "missing": [key_object(key) for key in sorted_keys(missing)],
        "exceptions": {
            "reference_excluded": [
                key_object(key, reference_index[key]["reason"])
                for key in sorted_keys(reference_excluded)
            ],
            "actual_excluded": [
                key_object(key, actual_index[key]["reason"])
                for key in sorted_keys(actual_excluded)
            ],
            "included_despite_exclusion": [
                key_object(key, reference_index[key]["reason"])
                for key in sorted_keys(actual_included & reference_excluded)
            ],
            "required_but_marked_excluded": [
                key_object(key, actual_index[key]["reason"])
                for key in sorted_keys(actual_excluded & reference_required)
            ],
        },
        "notes": [
            "Synthetic V-02 skeleton; M-01 ground truth is not used yet.",
            "precision = TP / (TP + extra); recall = TP / (TP + missing).",
            "Reference-excluded items do not enter the recall denominator.",
        ],
    }


def compare_files(reference_path, actual_path):
    return compare_lists(load_list(reference_path), load_list(actual_path))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare reference and actual call lists")
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--actual", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args(argv)
    try:
        result = compare_files(args.reference, args.actual)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
