"""M-05: проверить журнал H-00 двух администраторов и собрать протокол."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]


def _evaluator():
    path = ROOT / "scripts" / "evaluate-h00.py"
    spec = importlib.util.spec_from_file_location("evaluate_h00", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_protocol(payload):
    kind = payload.get("data_kind", "measured")
    if kind != "measured":
        raise ValueError("M-05 требует реальный журнал data_kind=measured")
    result = _evaluator().evaluate(payload)
    if result["human_participants"] != 2:
        raise ValueError("M-05 требует двух разных участников")
    runs = sorted(result["runs"], key=lambda item: (item["participant"], item["tool"]))
    return {
        "protocol": "M-05",
        "status": "filled",
        "participants": sorted({item["participant"] for item in runs}),
        "result": result,
        "runs": [
            {
                "participant": item["participant"],
                "tool": item["tool"],
                "group": item["group"],
                "seconds": item["seconds"],
                "ids": item["ids"],
                "precision": item["precision"],
                "recall": item["recall"],
                "excluded_errors": item["excluded_errors"],
            }
            for item in runs
        ],
    }


def render(protocol):
    result = protocol["result"]
    lines = [
        "# M-05 — протокол пилота H-00",
        "",
        "**Статус:** заполнен по реальному журналу двух администраторов.",
        "",
        "**Участники:** " + ", ".join(protocol["participants"]),
        "",
        "| Участник | Инструмент | Набор | Время, с | Precision | Recall | Исключённых | ID |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for item in protocol["runs"]:
        lines.append(
            f"| {item['participant']} | {item['tool']} | {item['group']} | "
            f"{item['seconds']:.3f} | {item['precision']:.3f} | {item['recall']:.3f} | "
            f"{item['excluded_errors']} | {', '.join(item['ids'])} |"
        )
    lines.extend([
        "",
        f"**Медиана Excel:** {result['median_seconds']['excel']:.3f} с",
        f"**Медиана Re:Hub:** {result['median_seconds']['rehub']:.3f} с",
        f"**Ускорение:** {result['speedup']:.2f}×",
        f"**Качество пройдено:** {'да' if result['quality_passed'] else 'нет'}",
        f"**Критерии H-00:** {'достигнуты' if result['criteria_met'] else 'не достигнуты'}",
        f"**Вывод:** {result['conclusion']}",
        f"**human_participants:** {result['human_participants']}",
        "",
    ])
    return "\n".join(lines)


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("measurements", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--json", action="store_true", help="Print protocol JSON")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.measurements.read_text(encoding="utf-8"))
        protocol = build_protocol(payload)
        text = json.dumps(protocol, ensure_ascii=False, indent=2) if args.json else render(protocol)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Протокол не собран: {exc}\n")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
