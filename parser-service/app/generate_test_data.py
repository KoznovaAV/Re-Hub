"""V-03: generate synthetic clients directory and two snapshots with real workbook shape."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random

from openpyxl import Workbook

from .customer_clients import PROFILE as CLIENTS_PROFILE, SHEET_NAME as CLIENTS_SHEET
from .customer_xlsx import PERIODS as SNAPSHOT_PERIODS, PROFILE as SNAPSHOT_PROFILE

CLIENT_HEADERS = [
    "Уникальны обезличинный идентификатор",
    "Код КЦР",
    "Теги",
    "Не нужно работать",
    "Недействующий",
    "Контакты",
]
TAG_POOL = ["vip", "integrator", "tech_partner", "mpp", "newcomer"]
SCENARIO_IDS = {
    "S-1": "AAA00001",
    "S-2": "AAA00002",
    "S-3": "AAA00003",
    "S-4": "AAA00004",
    "S-5": "AAA00005",
    "S-6a": "AAA00006",
    "S-6b": "AAA00007",
    "S-7": "AAA00008",
    "S-8": "AAA00009",
}


def external_id(index: int) -> str:
    if not 1 <= index <= 99999:
        raise ValueError("client index out of anonymous key range")
    return f"AAA{index:05d}"


def yes_no(value: bool) -> str:
    return "да" if value else "нет"


def format_int(value: int | None, *, spaced: bool) -> int | str | None:
    if value is None:
        return None
    if not spaced or value < 1000:
        return value
    text = f"{value:,}".replace(",", " ")
    return text


def build_clients(count: int, rng: random.Random) -> list[dict]:
    clients = []
    for index in range(1, count + 1):
        key = external_id(index)
        tags = []
        if key == SCENARIO_IDS["S-1"]:
            tags = ["vip"]
        elif key == SCENARIO_IDS["S-3"]:
            tags = ["mpp"]
        elif key == SCENARIO_IDS["S-5"]:
            tags = ["integrator"]
        elif key == SCENARIO_IDS["S-6b"]:
            tags = ["newcomer"]
        elif key == SCENARIO_IDS["S-8"]:
            tags = ["tech_partner"]
        elif index % 17 == 0:
            tags = [rng.choice(TAG_POOL)]
        elif index % 53 == 0:
            tags = ["vip", "integrator"]

        excluded = key in {external_id(10), external_id(11), external_id(12), external_id(26)} or index % 19 == 0
        inactive = key in {external_id(12), external_id(13), external_id(14), external_id(15)} or index % 23 == 0
        contacts = None if index % 11 == 0 else f"Контакт {index}"
        clients.append({
            "external_id": key,
            "tags": tags,
            "excluded": excluded,
            "inactive": inactive,
            "contacts": contacts,
        })
    return clients


def write_clients_xlsx(path: Path, clients: list[dict]) -> None:
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet(CLIENTS_SHEET)
    sheet.append([])
    sheet.append(CLIENT_HEADERS)
    for client in clients:
        sheet.append([
            client["external_id"],
            None,
            ";".join(client["tags"]) if client["tags"] else None,
            yes_no(client["excluded"]),
            yes_no(client["inactive"]),
            client["contacts"],
        ])
    workbook.save(path)


def snapshot_headers(period_code: str) -> list:
    kcr_header = "Код КЦР" if period_code == "Y2025" else "код СЦ"
    return [
        "Уникальны обезличинный идентификатор",
        kcr_header,
        None,
        "документов всего",
        "Всего не отправлено документов",
    ]


def base_observation(index: int, period_code: str, rng: random.Random) -> dict:
    total = 50 + (index * 7 + len(period_code) * 3) % 400
    unsent = (index * 5 + len(period_code) * 2) % (total + 1)
    if rng.random() < 0.08:
        unsent = min(total, unsent + rng.randint(10, 40))
    return {"total": total, "unsent": unsent}


def apply_scenario(key: str, period_code: str, snap: int, obs: dict) -> dict | None:
    """Return observation for snapshot number 1/2, or None to omit the row."""
    if key == SCENARIO_IDS["S-1"] and period_code == "2026Q3":
        return {"total": 100, "unsent": 40} if snap == 1 else {"total": 100, "unsent": 15}
    if key == SCENARIO_IDS["S-2"] and period_code == "2026Q3":
        return {"total": 100, "unsent": 40}
    if key == SCENARIO_IDS["S-3"]:
        if period_code == "2026Q2":
            return {"total": 200, "unsent": 0}
        if period_code == "2026Q3":
            return None if snap == 1 else {"total": 210, "unsent": 12}
    if key == SCENARIO_IDS["S-4"] and period_code == "2026Q3":
        return {"total": 100, "unsent": 40} if snap == 1 else {"total": 100, "unsent": 25}
    if key == SCENARIO_IDS["S-5"] and period_code == "2026Q3":
        return {"total": 100, "unsent": 40} if snap == 1 else {"total": 100, "unsent": 45}
    if key == SCENARIO_IDS["S-6a"] and period_code == "2026Q3":
        return {"total": 200, "unsent": 8}
    if key == SCENARIO_IDS["S-6b"] and period_code == "2026Q3":
        return {"total": 200, "unsent": 8}
    if key == SCENARIO_IDS["S-7"] and period_code == "2026Q3":
        return {"total": 100, "unsent": 30} if snap == 1 else None
    if key == SCENARIO_IDS["S-8"] and period_code == "2026Q3":
        return {"total": 100, "unsent": 40} if snap == 1 else {"total": None, "unsent": 30}
    return obs


def build_snapshot_rows(count: int, snap: int, rng: random.Random) -> dict[str, list[dict]]:
    rows_by_period = {code: [] for code in SNAPSHOT_PERIODS.values()}
    for index in range(1, count + 1):
        key = external_id(index)
        # Keep workbook size realistic: not every client appears on every tab.
        active_periods = list(SNAPSHOT_PERIODS.values())
        if index > 30 and index % 4 == 0:
            active_periods = active_periods[:2]
        elif index > 30 and index % 4 == 1:
            active_periods = active_periods[1:3]
        for period_code in active_periods:
            obs = base_observation(index, period_code, rng)
            shaped = apply_scenario(key, period_code, snap, obs)
            if shaped is None:
                continue
            rows_by_period[period_code].append({
                "external_id": key,
                "total": shaped["total"],
                "unsent": shaped["unsent"],
            })
    return rows_by_period


def write_snapshot_xlsx(path: Path, rows_by_period: dict[str, list[dict]], *, spaced_numbers: bool) -> None:
    workbook = Workbook(write_only=True)
    for title, period_code in SNAPSHOT_PERIODS.items():
        sheet = workbook.create_sheet(title)
        sheet.append([])
        sheet.append(snapshot_headers(period_code))
        for row in rows_by_period[period_code]:
            sheet.append([
                row["external_id"],
                None,
                None,
                format_int(row["total"], spaced=spaced_numbers),
                format_int(row["unsent"], spaced=spaced_numbers),
            ])
    workbook.save(path)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def generate(out_dir: Path, count: int, seed: int) -> dict:
    if count < 30:
        raise ValueError("count must be >= 30 so S-1..S-8 client ids fit")
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    clients = build_clients(count, rng)
    clients_path = out_dir / "clients.xlsx"
    write_clients_xlsx(clients_path, clients)
    clients_context = {
        "contract_version": "1.0",
        "file_kind": "clients",
        "key_mode": "anonymous",
        "mapping_profile": CLIENTS_PROFILE,
    }
    write_json(out_dir / "clients.context.json", clients_context)

    snap1_rows = build_snapshot_rows(count, 1, rng)
    snap2_rows = build_snapshot_rows(count, 2, random.Random(seed + 1))
    snap1_path = out_dir / "snapshot_1.xlsx"
    snap2_path = out_dir / "snapshot_2.xlsx"
    write_snapshot_xlsx(snap1_path, snap1_rows, spaced_numbers=True)
    write_snapshot_xlsx(snap2_path, snap2_rows, spaced_numbers=True)

    period_scope = list(SNAPSHOT_PERIODS.values())
    for name, day in (("snapshot_1", "2026-09-29"), ("snapshot_2", "2026-10-20")):
        write_json(out_dir / f"{name}.context.json", {
            "contract_version": "1.0",
            "file_kind": "snapshot",
            "key_mode": "anonymous",
            "mapping_profile": SNAPSHOT_PROFILE,
            "snapshot_date": day,
            "period_scope": period_scope,
            "coverage": "unknown",
        })

    manifest = {
        "generator": "v03",
        "seed": seed,
        "client_count": count,
        "files": {
            "clients": clients_path.name,
            "snapshot_1": snap1_path.name,
            "snapshot_2": snap2_path.name,
        },
        "scenario_clients": SCENARIO_IDS,
        "snapshot_row_counts": {
            "snapshot_1": {code: len(rows) for code, rows in snap1_rows.items()},
            "snapshot_2": {code: len(rows) for code, rows in snap2_rows.items()},
        },
        "excluded_count": sum(1 for client in clients if client["excluded"]),
        "inactive_count": sum(1 for client in clients if client["inactive"]),
        "notes": [
            "Clients workbook matches customer_kcr_directory_v1.",
            "Snapshots match customer_october_tabs_v1 with two dates for repeat-slice checks.",
            "S-7 is present in snapshot_1 and omitted from snapshot_2 on 2026Q3.",
            "S-8 has total_docs omitted on snapshot_2 for 2026Q3.",
        ],
    }
    write_json(out_dir / "manifest.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate V-03 pilot/load XLSX fixtures")
    parser.add_argument("--out", type=Path, required=True, help="Output directory")
    parser.add_argument(
        "--size",
        type=int,
        choices=(30, 4000),
        default=30,
        help="30 for pilot, 4000 for load",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    manifest = generate(args.out, args.size, args.seed)
    print(json.dumps({
        "out": str(args.out),
        "client_count": manifest["client_count"],
        "snapshot_row_counts": manifest["snapshot_row_counts"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
