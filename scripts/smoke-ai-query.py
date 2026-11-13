"""Check the local Go AI endpoint with synthetic data."""

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8080/ai/query")
    args = parser.parse_args()
    cases_path = Path(__file__).resolve().parents[1] / "contracts/eval/intent-synthetic-v1.jsonl"
    checks = {
        "SYN-01": ("unsent_docs", ["test-slice-2026-10-20"]),
        "SYN-02": (None, []),
        "SYN-06": (None, []),
        "SYN-09": ("promised_on", ["test-call-19"]),
    }
    for case in map(json.loads, cases_path.read_text(encoding="utf-8").splitlines()):
        if case["id"] not in checks:
            continue
        field, sources = checks[case["id"]]
        expected = case["expected_read"]
        request = Request(args.url, data=json.dumps({"query": case["question"]}).encode("utf-8"),
                          headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=36) as reply:
            result = json.load(reply)
        rows = result["data"]
        value = rows[0][field] if field and len(rows) == 1 else None
        if (result["status"], value, result["sources"], len(rows)) != (
            expected["status"], expected["value"], sources, int(field is not None)
        ):
            raise SystemExit(f"{case['id']} failed: {json.dumps(result)}")
        print(f"{case['id']} OK")


if __name__ == "__main__":
    main()
