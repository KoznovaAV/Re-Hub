"""Build the T-04 clients workbook and golden ParserResult from clients_seed.json."""

from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent
SEED = ROOT / "clients_seed.json"
XLSX = ROOT / "clients.xlsx"
EXPECTED = ROOT / "clients.expected.json"
CONTEXT = ROOT / "clients.context.json"

HEADERS = [
    "Уникальны обезличинный идентификатор",
    "Код КЦР",
    "Теги",
    "Не нужно работать",
    "Недействующий",
    "Контакты",
]


def yes_no(value: bool) -> str:
    return "да" if value else "нет"


def tags_cell(tags: list[str]) -> str | None:
    if not tags:
        return None
    return ";".join(tags)


def expected_data(client: dict) -> dict:
    data = {"external_id": client["external_id"]}
    if client.get("contacts"):
        data["name"] = client["contacts"]
    if client.get("tags"):
        data["tags"] = list(client["tags"])
    data["excluded"] = bool(client["excluded"])
    data["active"] = not bool(client["inactive"])
    return data


def build() -> None:
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    clients = seed["clients"]
    assert len(clients) == 30, "T-04 client fixture must contain 30 clients"

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = seed["sheet"]
    sheet.append([])
    sheet.append(HEADERS)
    for client in clients:
        sheet.append([
            client["external_id"],
            None,
            tags_cell(client.get("tags") or []),
            yes_no(client["excluded"]),
            yes_no(client["inactive"]),
            client.get("contacts"),
        ])
    workbook.save(XLSX)
    workbook.close()

    context = {
        "contract_version": "1.0",
        "file_kind": "clients",
        "key_mode": seed["key_mode"],
        "mapping_profile": seed["profile"],
    }
    CONTEXT.write_text(json.dumps(context, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rows = []
    for index, client in enumerate(clients, start=3):
        rows.append({
            "source": {"sheet": seed["sheet"], "row": index},
            "data": expected_data(client),
            "scenarios": client.get("scenarios") or [],
        })
    expected = {
        "contract_version": "1.0",
        "file_kind": "clients",
        "key_mode": seed["key_mode"],
        "nonempty_row_count": 30,
        "rows": [{"source": row["source"], "data": row["data"]} for row in rows],
        "errors": [],
        "meta": {
            "client_count": 30,
            "excluded_count": sum(1 for client in clients if client["excluded"]),
            "inactive_count": sum(1 for client in clients if client["inactive"]),
            "scenario_clients": {
                scenario: [row["data"]["external_id"] for row in rows if scenario in row["scenarios"]]
                for scenario in [f"S-{n}" for n in range(1, 9)]
            },
        },
    }
    EXPECTED.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {XLSX.name}, {CONTEXT.name}, {EXPECTED.name}")


if __name__ == "__main__":
    build()
