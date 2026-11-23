"""T-01: reproducible H-00 pilot pack — 30 clients, two snapshots, S-1..S-8 reasons."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
sys.path.insert(0, str(REPO / "parser-service"))

from app.generate_test_data import SCENARIO_IDS, generate  # noqa: E402

REASONS = {
    "S-1": "Долг уменьшился между срезами на 2026Q3",
    "S-2": "Долг не изменился после звонка на 2026Q3",
    "S-3": "Долг появился повторно на 2026Q3",
    "S-4": "Срок истёк, долг уменьшился частично на 2026Q3",
    "S-5": "Клиент уже в работе и снова попал под фильтр на 2026Q3",
    "S-6a": "Обычный клиент с небольшим долгом на 2026Q3",
    "S-6b": "Новичок с небольшим долгом на 2026Q3",
    "S-7": "Клиент пропал из второго среза на 2026Q3",
    "S-8": "Повторный срез без поля «Всего» на 2026Q3",
}


def build() -> None:
    manifest = generate(ROOT, count=30, seed=42)
    expected = {
        "size": 30,
        "seed": 42,
        "synthetic": True,
        "covers": [f"S-{n}" for n in range(1, 9)],
        "scenario_clients": SCENARIO_IDS,
        "reasons": REASONS,
        "reference_ids": list(SCENARIO_IDS.values()),
        "files": manifest["files"],
        "checks": {
            "S-7_missing_in_snapshot_2": SCENARIO_IDS["S-7"],
            "S-8_null_total_in_snapshot_2": SCENARIO_IDS["S-8"],
            "S-6_pair": [SCENARIO_IDS["S-6a"], SCENARIO_IDS["S-6b"]],
        },
    }
    (ROOT / "expected.json").write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(ROOT), "clients": 30, "scenarios": list(SCENARIO_IDS)}, ensure_ascii=False))


if __name__ == "__main__":
    build()
