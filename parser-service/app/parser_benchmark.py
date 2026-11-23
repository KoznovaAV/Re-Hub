"""Замер парсера в отдельных процессах; отчет содержит только агрегаты."""
import argparse
import cProfile
import pstats
import math
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
    parsed_at = time.perf_counter()
    from .contract import validate_result
    validate_result(result)
    elapsed = time.perf_counter() - started
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {"elapsed_seconds": round(elapsed, 6), "parse_seconds":round(parsed_at-started,6), "schema_seconds":round(time.perf_counter()-parsed_at,6),
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
    # Profiling is a separate run and never included in the timing distribution.
    profile=cProfile.Profile();profile.runcall(measure,workbook,context)
    stats=pstats.Stats(profile)
    top=sorted(stats.stats.items(),key=lambda item:item[1][3],reverse=True)[:12]
    profile_rows=[{"function":Path(k[0]).name+":"+str(k[1])+":"+k[2],"calls":v[1],"self_seconds":round(v[2],6),"cumulative_seconds":round(v[3],6)} for k,v in top]
    times=sorted(r["elapsed_seconds"] for r in runs)
    return {"python": platform.python_version(), "platform": platform.platform(),
            "openpyxl": importlib.metadata.version("openpyxl"),
            "input_sha256": hashlib.sha256(Path(workbook).read_bytes()).hexdigest(),
            "context_sha256": hashlib.sha256(Path(context).read_bytes()).hexdigest(),
            "repeat": repeat, "runs": runs, "p95_seconds":times[math.ceil(.95*len(times))-1], "p95_method":"nearest-rank", "profile_separate_run":profile_rows,
            "stage_median_seconds":{k:statistics.median(r[k] for r in runs) for k in ("parse_seconds","schema_seconds")},
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
    if not 1 <= args.repeat <= 200:
        parser.error("repeat must be between 1 and 200")
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
