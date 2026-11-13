"""Run the intent cases against a local Ollama instance."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
import sys
import time
from urllib.request import urlopen

from .ml_intent import (
    PERIOD_REGISTRY_PATH, PROMPT_PATH, IntentError, ProviderError, QuestionError,
    check_question, load_periods, load_prompt, predict, validate_intent,
)


def provider_metadata(base_url, model):
    metadata = {"ollama_version": None, "model_digest": None}
    errors = []
    endpoints = {"/api/version": "ollama_version", "/api/tags": "model_digest"}
    for endpoint, key in endpoints.items():
        try:
            with urlopen(f"{base_url.rstrip('/')}{endpoint}", timeout=5) as response:
                payload = json.load(response)
            if key == "ollama_version":
                value = payload["version"]
            else:
                tag = model if ":" in model.rsplit("/", 1)[-1] else f"{model}:latest"
                item = next((item for item in payload["models"]
                             if tag in (item.get("name"), item.get("model"))), {})
                value = item.get("digest")
            if not isinstance(value, str) or not value:
                raise ValueError("Missing metadata")
            metadata[key] = value
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            errors.append(f"{endpoint}: {type(exc).__name__}")
    metadata["metadata_errors"] = errors
    return metadata


def summarize(results):
    measured = [result["latency_ms"] for result in results if "error" not in result["actual"]]
    return {
        "passed": sum(result["match"] for result in results),
        "total": len(results),
        "errors": len(results) - len(measured),
        "median_latency_ms": round(median(measured), 2) if measured else None,
    }


def timed_predict(question, *, options):
    start = time.monotonic()
    try:
        actual = predict(question, **options)
    except (IntentError, ProviderError, QuestionError) as exc:
        actual = {"error": str(exc)}
    return actual, round((time.monotonic() - start) * 1000, 2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cases", type=Path, nargs="+")
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--check-fixtures", action="store_true")
    parser.add_argument("--warmup", action="store_true", help="Run one unscored request before measuring")
    parser.add_argument("--require-ollama-version", help="Require this server version before running cases")
    args = parser.parse_args()
    periods = load_periods()
    cases = []
    for path in args.cases:
        with path.open(encoding="utf-8") as source:
            cases.extend(json.loads(line) for line in source if line.strip())
    if not cases or len({case["id"] for case in cases}) != len(cases):
        parser.error("Cases must be non-empty and have unique IDs")
    for case in cases:
        expected = validate_intent(case["expected"], case["question"], periods)
        if check_question(expected, case["question"], periods) != expected:
            parser.error(f"{case['id']}: expected result conflicts with the question")
    if args.check_fixtures:
        print(f"{len(cases)} fixtures valid")
        return 0

    metadata = provider_metadata(args.base_url, args.model)
    if args.require_ollama_version and metadata["ollama_version"] != args.require_ollama_version:
        parser.error(f"Expected Ollama {args.require_ollama_version}; got {metadata['ollama_version'] or 'unknown'}")
    registry_text = PERIOD_REGISTRY_PATH.read_text(encoding="utf-8")
    metadata.update({
        "prompt_file": PROMPT_PATH.name,
        "prompt_sha256": sha256(load_prompt().encode("utf-8")).hexdigest(),
        "period_registry_version": json.loads(registry_text)["version"],
        "period_registry_sha256": sha256(registry_text.encode("utf-8")).hexdigest(),
    })
    options = dict(periods=periods, model=args.model, base_url=args.base_url)
    warmup = None
    if args.warmup:
        actual, elapsed = timed_predict(cases[0]["question"], options=options)
        warmup = {"latency_ms": elapsed, "error": actual.get("error")}

    results = []
    for case in cases:
        actual, elapsed = timed_predict(case["question"], options=options)
        results.append({
            "id": case["id"],
            "category": case["category"],
            "expected": case["expected"],
            "actual": actual,
            "match": actual == case["expected"],
            "latency_ms": elapsed,
        })
    summary = summarize(results)
    categories = sorted({result["category"] for result in results})
    by_category = {category: summarize([r for r in results if r["category"] == category])
                   for category in categories}
    report = {"model": args.model, **summary, "metadata": metadata, "warmup": warmup,
              "by_category": by_category, "cases": results}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(summary["passed"] != summary["total"] or (warmup is not None and warmup["error"] is not None))


if __name__ == "__main__":
    sys.exit(main())
