"""T-05: замер парсера среза на полном объёме.

По умолчанию скрипт генерирует синтетическую книгу с четырьмя вкладками и
публичными агрегатами октябрьского среза (12 772 непустые строки и 4 205
уникальных обезличенных ID), потому что файл заказчика не хранится в
репозитории. Реальный файл можно замерить без изменения кода:

    py -3 ai-service/benchmarks/measure_snapshot_parse.py \
        --input /path/to/snapshot.xlsx \
        --context contracts/examples/customer-october-context.json

Отчёт намеренно разделяет wall-clock время, пик tracemalloc и пик процесса ОС,
если платформа его предоставляет.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time
import tracemalloc

from openpyxl import Workbook

AI_SERVICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_SERVICE))

from app.customer_xlsx import PERIODS, find_duplicates, parse_file, summary  # noqa: E402


PERIOD_ROWS = {
    "весь 2025 год": 3419,
    "1 кв 2026": 2928,
    "2 кв 2026": 3021,
    "3 кв 2026": 3404,
}
TOTAL_ROWS = sum(PERIOD_ROWS.values())
UNIQUE_IDS = 4205
HEADER_FOR_PERIOD = {
    "весь 2025 год": "Код КЦР",
    "1 кв 2026": "код СЦ",
    "2 кв 2026": "код СЦ",
    "3 кв 2026": "код СЦ",
}


def synthetic_context():
    return {
        "contract_version": "1.0",
        "file_kind": "snapshot",
        "key_mode": "anonymous",
        "mapping_profile": "customer_october_tabs_v1",
        "snapshot_date": "2026-10-20",
        "period_scope": list(PERIODS.values()),
        "coverage": "unknown",
    }


def build_synthetic(path):
    ids = [f"AAA{index:05d}" for index in range(1, UNIQUE_IDS + 1)]
    workbook = Workbook()
    workbook.remove(workbook.active)
    cursor = 0
    for title, row_count in PERIOD_ROWS.items():
        sheet = workbook.create_sheet(title)
        sheet.append([])
        sheet.append(["Уникальны обезличинный идентификатор",
                      HEADER_FOR_PERIOD[title], None, "документов всего",
                      "Всего не отправлено документов"])
        for offset in range(row_count):
            total = 1000 + offset % 900
            total_value = (f"{total:,}".replace(",", " ")
                           if offset % 7 == 0 else total)
            sheet.append([ids[(cursor + offset) % UNIQUE_IDS], None, None,
                          total_value, offset % 23])
        cursor += row_count
    workbook.save(path)
    workbook.close()


def peak_rss_bytes():
    """Вернуть пик рабочего набора ОС / max RSS, если платформа его предоставляет."""
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            kernel32 = ctypes.windll.kernel32
            psapi = ctypes.windll.psapi
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            process = ctypes.c_void_p(kernel32.GetCurrentProcess())
            ok = psapi.GetProcessMemoryInfo(
                process, ctypes.byref(counters), counters.cb)
            return int(counters.PeakWorkingSetSize) if ok else None
        import resource
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    except Exception:
        return None


def result_facts(result):
    rows = result["rows"]
    unique_ids = {row["data"]["external_id"] for row in rows}
    return {
        **summary(result),
        "unique_ids": len(unique_ids),
        "rows_by_period": dict(Counter(row["data"]["period_code"] for row in rows)),
        "duplicate_groups": len(find_duplicates(result)),
        "file_error_codes": [error["code"] for error in result["errors"]
                             if error["scope"] == "file"],
    }


def measure(path, context, iterations):
    warmup = parse_file(path, context)
    if warmup["errors"]:
        raise SystemExit(f"Warm-up parse failed: {warmup['errors'][0]}")

    timings = []
    result = warmup
    for _ in range(iterations):
        started = time.perf_counter()
        result = parse_file(path, context)
        timings.append(time.perf_counter() - started)

    tracemalloc.start()
    try:
        parse_file(path, context)
        _, traced_peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    facts = result_facts(result)
    median = statistics.median(timings)
    return {
        "timing_seconds": {
            "runs": [round(value, 6) for value in timings],
            "median": round(median, 6),
            "min": round(min(timings), 6),
            "max": round(max(timings), 6),
            "rows_per_second": round(facts["parsed_rows"] / median) if median else None,
        },
        "memory": {
            "tracemalloc_peak_bytes": traced_peak,
            "tracemalloc_peak_mib": round(traced_peak / 1024 / 1024, 2),
            "process_peak_rss_bytes": peak_rss_bytes(),
        },
        "result": facts,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure snapshot parser time and memory")
    parser.add_argument("--input", type=Path, help="Real snapshot XLSX (optional)")
    parser.add_argument("--context", type=Path, help="Context JSON for --input")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parent / "results.json")
    args = parser.parse_args(argv)
    if args.iterations < 1:
        parser.error("--iterations must be at least 1")
    if args.input and not args.context:
        parser.error("--context is required with --input")

    temporary = None
    try:
        if args.input:
            workbook_path = args.input
            context = json.loads(args.context.read_text(encoding="utf-8"))
            mode = "real"
        else:
            temporary = tempfile.NamedTemporaryFile(
                prefix="rehub-benchmark-", suffix=".xlsx", delete=False)
            temporary.close()
            workbook_path = Path(temporary.name)
            build_synthetic(workbook_path)
            context = synthetic_context()
            mode = "synthetic"

        measured = measure(workbook_path, context, args.iterations)
        facts = measured["result"]
        if mode == "synthetic" and (
                facts["source_rows"] != TOTAL_ROWS
                or facts["unique_ids"] != UNIQUE_IDS
                or facts["errors_by_code"]):
            raise SystemExit(f"Synthetic workload differs from its declaration: {facts}")

        report = {
            "task": "T-05",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "mode": mode,
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "machine": platform.machine(),
                "processor": platform.processor(),
            },
            "input": {
                "file": str(workbook_path) if mode == "real" else "synthetic",
                "bytes": workbook_path.stat().st_size,
                "rows": facts["source_rows"],
                "parsed_rows": facts["parsed_rows"],
                "unique_ids": facts["unique_ids"],
                "period_rows": facts["rows_by_period"],
                "declared_dimensions": {
                    "rows": TOTAL_ROWS, "unique_ids": UNIQUE_IDS,
                } if mode == "synthetic" else None,
            },
            "settings": {"iterations": args.iterations},
            **measured,
            "notes": [
                "Synthetic mode uses the public aggregate dimensions because the customer XLSX is not in the repository.",
                "tracemalloc_peak is Python-traced peak; process_peak_rss is the OS peak when available.",
                "Re-run with --input and --context to replace the synthetic measurement with the real snapshot.",
            ],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        if temporary:
            try:
                os.unlink(temporary.name)
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
