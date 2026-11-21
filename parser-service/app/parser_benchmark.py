"""Замер парсера в отдельных процессах; отчет содержит только агрегаты."""
import argparse
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
import statistics
import subprocess
import sys
import time


def measure(workbook, context):
    # Linux/macOS: ru_maxrss измеряет пик RSS всего процесса, а не только Python heap.
    import resource
    from .customer_clients import parse_file as parse_clients, summary as clients_summary
    from .customer_xlsx import parse_file as parse_snapshot, summary as snapshot_summary
    ctx = json.loads(Path(context).read_text(encoding="utf-8"))
    parse, summarize = (parse_clients, clients_summary) if ctx["file_kind"] == "clients" else (parse_snapshot, snapshot_summary)
    started = time.perf_counter()
    result = parse(workbook, ctx)
    elapsed = time.perf_counter() - started
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {"elapsed_seconds": round(elapsed, 6),
            "peak_rss_mib": round(peak / (1024 * 1024 if sys.platform == "darwin" else 1024), 3),
            "summary": summarize(result),
            "unique_clients": len({r["data"]["external_id"] for r in result["rows"]}),
            "file_errors": sum(e["scope"] == "file" for e in result["errors"])}


def benchmark(workbook, context, repeat):
    runs = []
    for _ in range(repeat):
        reply = subprocess.run([sys.executable, "-m", "app.parser_benchmark", str(workbook),
                                str(context), "--worker"], check=True, capture_output=True, text=True)
        runs.append(json.loads(reply.stdout))
    return {"python": platform.python_version(), "platform": platform.platform(),
            "openpyxl": importlib.metadata.version("openpyxl"),
            "input_sha256": hashlib.sha256(Path(workbook).read_bytes()).hexdigest(),
            "context_sha256": hashlib.sha256(Path(context).read_bytes()).hexdigest(),
            "repeat": repeat, "runs": runs,
            "median_seconds": statistics.median(r["elapsed_seconds"] for r in runs),
            "maximum_peak_rss_mib": max(r["peak_rss_mib"] for r in runs)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("context", type=Path)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.repeat <= 20:
        parser.error("repeat must be between 1 and 20")
    report = measure(args.workbook, args.context) if args.worker else benchmark(args.workbook, args.context, args.repeat)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    runs = [report] if args.worker else report["runs"]
    return int(any(r["file_errors"] for r in runs))


if __name__ == "__main__":
    raise SystemExit(main())
