"""Resolve validated intents against the synthetic integration fixture."""

from functools import lru_cache
import json
import os
import re

from ml_intent import (
    MAX_MIN_UNSENT, MAX_QUESTION_CHARS, QUARTER_TEXT, ROOT, check_question, explicit_periods,
    load_periods, no_action, predict, validate_intent,
)


# Codespaces может выполнять модель на CPU. Внешние прокси ждут дольше.
DEMO_OLLAMA_TIMEOUT = 90


@lru_cache(maxsize=1)
def fixture():
    path = ROOT / "contracts" / "eval" / "synthetic-client-data-v1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("synthetic") is not True:
        raise ValueError("Expected synthetic fixture")
    return data


# Короткий путь только для однозначных формулировок. Остальные разбирает модель.
CLIENT_CODE = r"(?P<client>[a-z]{3}[0-9]{5}|[0-9]{7})"
REPORT_PERIOD = rf"(?:[0-9]{{4}}Q[1-4]|{QUARTER_TEXT})"
DIRECT_QUERIES = tuple((intent, re.compile(pattern, re.IGNORECASE)) for intent, pattern in (
    ("get_client_debt",
     rf"сколько оригиналов (?:жд[её]м от|не передано по КЦР) {CLIENT_CODE} за {REPORT_PERIOD}"),
    ("get_client_debt",
     rf"за {REPORT_PERIOD} сколько не сдал клиент {CLIENT_CODE}"),
    ("get_client_debt",
     rf"по коду КЦР {CLIENT_CODE}, сколько оригиналов не передано за {REPORT_PERIOD}"),
    ("get_client_promise",
     rf"к какому числу клиент с кодом КЦР {CLIENT_CODE} обещал передать оригиналы за {REPORT_PERIOD}"),
    ("list_debtors",
     rf"кто не передал минимум (?P<minimum>[0-9]{{1,7}}) оригиналов за {REPORT_PERIOD}"),
))


def direct_intent(question, periods):
    if not isinstance(question, str) or len(question) > MAX_QUESTION_CHARS:
        return None
    normalized = " ".join(question.strip().rstrip("?! .").split())
    for intent, pattern in DIRECT_QUERIES:
        match = pattern.fullmatch(normalized)
        if not match:
            continue
        mentioned = explicit_periods(normalized)
        if len(mentioned) != 1 or not mentioned <= periods.keys():
            return no_action("clarify", "missing_period")
        fields = match.groupdict()
        minimum = int(fields["minimum"]) if "minimum" in fields else None
        if minimum is not None and not 1 <= minimum <= MAX_MIN_UNSENT:
            return None
        result = {
            "intent": intent, "period": mentioned.pop(), "client_ref": fields.get("client"),
            "min_unsent": minimum, "reason": None,
        }
        return check_question(validate_intent(result, question, periods), question, periods)
    return None


def answer(question, client_external_id):
    periods = load_periods()
    intent = direct_intent(question, periods)
    if intent is None:
        intent = predict(
            question, periods=periods,
            model=os.environ.get("OLLAMA_MODEL", "qwen3:4b"),
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            timeout=DEMO_OLLAMA_TIMEOUT,
        )
    return resolve(intent, fixture(), client_external_id)


def response(status, answer, rows=(), *, reason=None):
    return {
        "status": status, "reason": reason, "answer": answer,
        "data": list(rows), "sources": list(dict.fromkeys(row["source_id"] for row in rows)),
    }


def resolve(intent, data, client_external_id):
    action = intent["intent"]
    if action in ("clarify", "unsupported", "refused"):
        messages = {
            "clarify": "Уточните клиента или отчётный период.",
            "unsupported": "Этот запрос пока не поддерживается.",
            "refused": "Этот запрос отклонён.",
        }
        message = messages[action]
        if intent["reason"] == "missing_question":
            message = (
                "Привет! Задайте вопрос по документам. "
                "Если вопрос об одном клиенте, укажите его код или название и отчётный период."
            )
        return response(action, message, reason=intent["reason"])

    # В демо оператор фиксирован. Код клиента из запроса только сужает его выборку.
    allowed = {
        client["external_id"]: client["name"] for client in data["clients"]
        if client["operator_id"] == "test-op-a"
        and (not client_external_id or client["external_id"] == client_external_id)
    }
    period = intent["period"]
    if action == "list_debtors":
        rows = sorted(
            (row for row in data["snapshots"] if row["external_id"] in allowed
             and row["period_code"] == period and row["unsent_docs"] >= intent["min_unsent"]),
            key=lambda row: row["external_id"],
        )
        return response("ok", f"Найдено клиентов: {len(rows)}.", rows)

    reference = intent["client_ref"].casefold()
    matches = [key for key, name in allowed.items() if reference in (key.casefold(), name.casefold())]
    # Один ответ для неизвестного и чужого клиента скрывает само наличие записи.
    if not matches:
        return response("unavailable", "Доступная запись клиента не найдена.")
    if len(matches) != 1:
        return response("clarify", "Уточните код клиента.", reason="missing_client")
    key = matches[0]
    if action == "get_client_promise":
        records, field, label = data["promises"], "promised_on", "Обещанный срок"
    else:
        records, field, label = data["snapshots"], "unsent_docs", "Не передано оригиналов"
    row = next((row for row in records if row["external_id"] == key and row["period_code"] == period), None)
    # Отсутствующая строка отличается от существующей строки с нулевым долгом.
    if row is None:
        return response("no_data", "За выбранный период запись отсутствует.")
    return response("ok", f"{label}: {row[field]}.", (row,))
