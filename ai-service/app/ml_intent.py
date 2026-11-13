"""Translate a Russian request into a validated read-only Re:Hub intent."""

from functools import lru_cache
import json
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class IntentError(ValueError):
    """The provider response does not satisfy the intent contract."""


class ProviderError(RuntimeError):
    """Ollama could not return a usable response."""


class QuestionError(ValueError):
    """The question is missing or exceeds the input limit."""


class UnresolvedReference(IntentError):
    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason


ROOT = Path(__file__).resolve().parents[2]
PROMPT_PATH = ROOT / "docs" / "ml" / "intent-prompt-v1.txt"
PERIOD_REGISTRY_PATH = ROOT / "contracts" / "periods.v1.json"
MAX_QUESTION_CHARS = 2_000
MAX_MIN_UNSENT = 1_000_000
GREETING_ONLY = re.compile(
    r"(?:привет|здравствуй(?:те)?|доброе\s+утро|добрый\s+(?:день|вечер))[\s.!?,…]*",
    re.IGNORECASE,
)
REASONS = {
    "clarify": {"missing_period", "missing_client", "ambiguous_deadline", "missing_question"},
    "refused": {"write_request", "raw_sql", "access_override", "hidden_instructions"},
    "unsupported": {"document_content", "unsupported_filter"},
}
PARAMETERS = {
    "list_debtors": {"period", "min_unsent"},
    "get_client_debt": {"period", "client_ref"},
    "get_client_promise": {"period", "client_ref"},
    **{intent: frozenset({"reason"}) for intent in REASONS},
}
FIELDS = {"intent", "period", "client_ref", "min_unsent", "reason"}
WHOLE_YEAR = re.compile(r"\bвесь\s+((?:19|20)\d{2})(?!\w)", re.IGNORECASE)
PERCENT = re.compile(r"%|\bпроцент\w*\b", re.IGNORECASE)
CLIENT_PLACEHOLDERS = {"этот клиент", "этого клиента", "этой компании", "эта компания", "эта контора", "этой конторы"}
CLIENT_PLACEHOLDER = re.compile(r"\b(?:" + "|".join(CLIENT_PLACEHOLDERS) + r")\b", re.IGNORECASE)
CLIENT_REFERENCE = re.compile(
    r"""«([^»]+)»|"([^"]+)"|'([^']+)'|\b(?:КЦР|ИНН)\s*[:№]?\s*(\d+)\b|\b([A-Z][A-Z0-9]*-\d+|[A-Z]{3}[0-9]{5})\b""",
    re.IGNORECASE,
)
ANONYMOUS_CODE = re.compile(r"[A-Za-z]{3}[0-9]{5}")
PREFIXED_KCR_CODE = re.compile(r"КЦР\s*[:№]?\s*([0-9]{7})", re.IGNORECASE)
COUNT_REQUEST = re.compile(r"\b(?:сколько|скок|число|количество)\b", re.IGNORECASE)
LIST_REQUEST = re.compile(r"\b(?:список|перечень|должник\w*|должнк\w*|всех|кто|у кого|клиентов)\b", re.IGNORECASE)
UNSUPPORTED_LIST = re.compile(
    r"\b(?:vip|перезвон\w*|в\s+работе|не\s+менял\w*|"
    r"повторн\w*\s+(?:по)?звон\w*|позвон\w*\s+повторно)\b", re.IGNORECASE,
)
SQL_REQUEST = re.compile(
    r"\b(?:запрос\s+(?:на|в)\s+sql|sql[-\s]+запрос\w*|(?:выполни|напиши|скинь|покажи|дай)\s+(?:сырой\s+)?sql)\b",
    re.IGNORECASE,
)
CROSS_OPERATOR_REQUEST = re.compile(
    r"(?<!не )\b(?:покажи|открой|выгрузи|выдай) (?:мне )?(?:чужих клиент\w*|"
    r"(?:клиент\w*|карточк\w*) другого оператора|"
    r"(?:список (?:всех )?)?клиент\w*[^.!?]{0,80}к котор\w* у меня нет доступа|"
    r"список (?:всех )?клиентов, включая тех, к кому у меня нет доступа)\b", re.IGNORECASE,
)
WRITE_REQUEST = re.compile(
    r"(?<!не )\b(?:удали|измени|закрой|назначь|переведи|поставь)\s+"
    r"(?:(?:предыдущ\w*|нов\w*|все|весь|всю)\s+)?(?:истори\w*|запис\w*|статус\w*|долг\w*|клиент\w*|"
    r"ответственн\w*|оператор\w*|ноль|0)\b|"
    r"(?<!не )\bназначь\s+(?:[A-Z][A-Z0-9]*-\d+|[A-Z]{3}[0-9]{5}|[0-9]{7})\s+на\s+меня\b",
    re.IGNORECASE,
)
HIDDEN_REQUEST = re.compile(
    r"(?<!не )\b(?:покажи|выведи|раскрой|скопируй|напечатай|выдай|дай)\s+"
    r"(?:(?:сюда|свой)\s+)?(?:системн\w*\s+промпт\w*|внутренн\w*\s+инструкци\w*|ключ\s+api)\b",
    re.IGNORECASE,
)
DOCUMENT_REQUEST = re.compile(
    r"\b(?:что|ч[её])\s+(?:(?:там|сказано|написано)\s+)*в\s+(?:письме|договоре|файле)\b|"
    r"\b(?:цитат\w*|содержимое|текст)\s+(?:из\s+)?(?:письма|договора|файла)\b", re.IGNORECASE,
)
PERIOD_CODE = re.compile(r"\b(?:Y\d{4}|\d{4}Q[1-4](?:_\d{4}Q[1-4])?)\b", re.IGNORECASE)
QUARTER_NAMES = {
    "1": 1, "i": 1, "перв": 1,
    "2": 2, "ii": 2, "втор": 2,
    "3": 3, "iii": 3, "трет": 3,
    "4": 4, "iv": 4, "четв": 4,
}
QUARTER_TOKEN = r"[1-4]|iv|iii|ii|i|перв\w*|втор\w*|трет\w*|четв\w*"
QUARTER_TEXT = rf"({QUARTER_TOKEN})\s*(?:квартал\w*|кв\.?)\s*(\d{{4}})"
QUARTER_RANGE = re.compile(
    rf"\b{QUARTER_TEXT}\s+по\s+{QUARTER_TEXT}|\b([1-4])\s*[-–—]\s*{QUARTER_TEXT}",
    re.IGNORECASE,
)
QUARTER_PERIOD = re.compile(rf"\b{QUARTER_TEXT}", re.IGNORECASE)
ANNUAL_PERIOD = re.compile(r"\b(?:за\s+)?(\d{4})\s+год\w*\b", re.IGNORECASE)
QUARTER_MONTHS = {"январь-март": 1, "апрель-июнь": 2, "июль-сентябрь": 3, "октябрь-декабрь": 4}
MONTH_RANGE = re.compile(
    r"\b(январь|апрель|июль|октябрь)\s*[-–—]\s*(март|июнь|сентябрь|декабрь)\s+(\d{4})\b",
    re.IGNORECASE,
)
PERIOD_CONTEXT = re.compile(r"(?:[.!?(]\s*в|\bне путать с)\s*$", re.IGNORECASE)
PROMISE_MENTION = re.compile(
    r"\b(?:обещ\w*|согласова\w*|договорил\w*|договор[её]нност\w*|назва(?:л|ла|ли))\b",
    re.IGNORECASE,
)


def load_periods():
    registry = json.loads(PERIOD_REGISTRY_PATH.read_text(encoding="utf-8"))
    return {item["code"]: item["label"] for item in registry["periods"]}


@lru_cache(maxsize=1)
def load_prompt():
    return PROMPT_PATH.read_text(encoding="utf-8")


def output_schema(periods, *, allow_docs=False):
    value_schemas = {
        "period": {"enum": list(periods)},
        "client_ref": {"type": "string", "minLength": 1, "maxLength": 120},
        "min_unsent": {"type": "integer", "minimum": 1, "maximum": MAX_MIN_UNSENT},
    }
    variants = []
    for intent, parameters in PARAMETERS.items():
        properties = {"intent": {"const": intent}}
        properties.update({name: {"type": "null"} for name in sorted(FIELDS - {"intent"})})
        for name in parameters - {"reason"}:
            properties[name] = value_schemas[name]
        if "reason" in parameters:
            properties["reason"] = {"enum": sorted(REASONS[intent])}
        variants.append({
            "type": "object",
            "additionalProperties": False,
            "required": list(properties),
            "properties": properties,
        })
    if allow_docs:
        properties = {field: {"type": "null"} for field in sorted(FIELDS)}
        properties["intent"] = {"const": "search_docs"}
        variants.append({
            "type": "object", "additionalProperties": False,
            "required": list(properties), "properties": properties,
        })
    return {"oneOf": variants}


def validate_intent(payload, question, periods):
    if not isinstance(payload, dict) or set(payload) != FIELDS:
        raise IntentError("Unexpected intent fields")
    intent = payload["intent"]
    if not isinstance(intent, str) or intent not in PARAMETERS:
        raise IntentError("Unknown intent")
    supplied = {name for name in FIELDS - {"intent"} if payload[name] is not None}
    if supplied != PARAMETERS[intent]:
        raise IntentError("Parameters do not match the intent")
    if intent in REASONS:
        reason = payload["reason"]
        if not isinstance(reason, str) or reason not in REASONS[intent]:
            raise IntentError("Invalid reason")
        return payload
    period = payload["period"]
    if not isinstance(period, str):
        raise IntentError("Expected a period code")
    if period not in periods and PERIOD_CODE.fullmatch(period):
        raise UnresolvedReference("missing_period", "Period outside registry")
    if period not in periods:
        raise IntentError("Unknown period")
    if intent == "list_debtors":
        minimum = payload["min_unsent"]
        if type(minimum) is not int or not 1 <= minimum <= MAX_MIN_UNSENT:
            raise IntentError(f"Expected a document count from 1 to {MAX_MIN_UNSENT}")
    else:
        client = payload["client_ref"]
        if not isinstance(client, str) or not client.strip() or len(client) > 120:
            raise IntentError("Expected a client reference")
        if client.casefold() not in question.casefold():
            raise UnresolvedReference("missing_client", "Client reference does not occur in the question")
    return payload


def no_action(intent, reason):
    return dict.fromkeys(FIELDS) | {"intent": intent, "reason": reason}


def quarter_code(number, year):
    return f"{year}Q{QUARTER_NAMES[number.casefold()[:4]]}"


def explicit_periods(question):
    mentions = []

    def remember(match, code):
        prefix = question[:match.start()]
        mentions.append((code, PERIOD_CONTEXT.search(prefix) is not None))

    # Заменяем уже разобранные периоды пробелами той же длины, чтобы сохранить позиции в вопросе.
    for match in PERIOD_CODE.finditer(question):
        remember(match, match[0].upper())
    text = PERIOD_CODE.sub(lambda match: " " * len(match[0]), question)
    for match in QUARTER_RANGE.finditer(text):
        first, start, last, end, same_year_first, same_year_last, year = match.groups()
        if year:
            first, start, last, end = same_year_first, year, same_year_last, year
        remember(match, f"{quarter_code(first, start)}_{quarter_code(last, end)}")
    text = QUARTER_RANGE.sub(lambda match: " " * len(match[0]), text)
    for match in QUARTER_PERIOD.finditer(text):
        remember(match, quarter_code(match[1], match[2]))
    text = QUARTER_PERIOD.sub(lambda match: " " * len(match[0]), text)
    for pattern in (WHOLE_YEAR, ANNUAL_PERIOD):
        for match in pattern.finditer(text):
            remember(match, f"Y{match[1]}")
    return {code for code, contextual in mentions if not contextual} or {code for code, _ in mentions}


def check_question(result, question, periods):
    intent = result["intent"]
    period = result["period"]
    if SQL_REQUEST.search(question):
        return no_action("refused", "raw_sql")
    normalized = " ".join(question.split())
    for pattern, reason in ((CROSS_OPERATOR_REQUEST, "access_override"),
                            (WRITE_REQUEST, "write_request"), (HIDDEN_REQUEST, "hidden_instructions")):
        if pattern.search(normalized):
            return no_action("refused", reason)
    if intent == "search_docs":
        return result
    if intent != "refused":
        if DOCUMENT_REQUEST.search(question):
            return no_action("unsupported", "document_content")
        if PERCENT.search(question) or UNSUPPORTED_LIST.search(question):
            return no_action("unsupported", "unsupported_filter")
    if intent == "list_debtors":
        # Если отбросить указание на клиента, запрос по одному клиенту может стать общим списком.
        references = {
            value.strip() for match in CLIENT_REFERENCE.findall(question) for value in match if value.strip()
        }
        if not references and CLIENT_PLACEHOLDER.search(" ".join(question.split())):
            return no_action("clarify", "missing_client")
        if references:
            if len(references) != 1 or not COUNT_REQUEST.search(question):
                return no_action("unsupported", "unsupported_filter")
            result = result | {
                "intent": "get_client_debt", "client_ref": references.pop(), "min_unsent": None,
            }
            result = validate_intent(result, question, periods)
        elif not LIST_REQUEST.search(question):
            return no_action("clarify", "missing_client")
    client = result["client_ref"]
    if client is not None:
        client = client.strip()
        if " ".join(client.casefold().split()) in CLIENT_PLACEHOLDERS:
            return no_action("clarify", "missing_client")
        kcr = PREFIXED_KCR_CODE.fullmatch(client)
        if kcr:
            client = kcr[1]
        elif ANONYMOUS_CODE.fullmatch(client):
            client = client.upper()
        result = result | {"client_ref": client}
    if intent == "get_client_promise" and not PROMISE_MENTION.search(question):
        return no_action("clarify", "ambiguous_deadline")
    if period is None:
        return result
    mentioned = explicit_periods(question)
    # В справочнике могут быть полный год и отдельный интервал за тот же год.
    full_year = WHOLE_YEAR.search(question)
    if full_year and len(mentioned) == 1:
        annual_period = f"Y{full_year[1]}"
        if annual_period in mentioned and annual_period in periods:
            return result | {"period": annual_period}
    if mentioned == {period}:
        return result
    return no_action("clarify", "missing_period")


def ollama_chat(*, messages, schema, model, base_url, timeout, max_tokens=256):
    body = {
        "model": model,
        "stream": False,
        "think": False,
        "format": schema,
        "options": {"temperature": 0, "seed": 42, "num_predict": max_tokens},
        "messages": messages,
    }
    request = Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw_response = response.read()
    except HTTPError as exc:
        raise ProviderError(f"Ollama returned HTTP {exc.code}") from exc
    except OSError as exc:
        raise ProviderError("Ollama request failed") from exc
    try:
        return json.loads(json.loads(raw_response)["message"]["content"])
    except (ValueError, KeyError, TypeError) as exc:
        raise ProviderError("Ollama returned an invalid response") from exc


def normalize_month_range(match):
    quarter = QUARTER_MONTHS.get(f"{match[1]}-{match[2]}".casefold())
    return f"{match[3]}Q{quarter}" if quarter else match[0]


def predict(question, *, periods, model, base_url, timeout=30, allow_docs=False):
    if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION_CHARS:
        raise QuestionError(f"Expected a non-empty question up to {MAX_QUESTION_CHARS} characters")
    if GREETING_ONLY.fullmatch(question.strip()):
        return no_action("clarify", "missing_question")
    question = MONTH_RANGE.sub(normalize_month_range, question)
    prompt = load_prompt()
    if allow_docs:
        prompt += (
            "\nsearch_docs: вопрос о правилах проекта, импорте, формате, полях, статусах "
            "или значении периода/среза. Все остальные поля null. "
            "Для фактов о клиенте используй действия get или list. "
            "Письма и договоры клиентов сюда не относятся. "
            "Период отчёта не требуется для вопроса о правилах.\n"
        )
    period_text = "\n".join(f"{code} = {label}" for code, label in periods.items())
    payload = ollama_chat(
        messages=[
            {"role": "system", "content": f"{prompt}\nПериоды:\n{period_text}"},
            {"role": "user", "content": question},
        ],
        schema=output_schema(periods, allow_docs=allow_docs),
        model=model, base_url=base_url, timeout=timeout,
    )
    if allow_docs and payload == no_action("search_docs", None):
        return check_question(payload, question, periods)
    try:
        result = validate_intent(payload, question, periods)
    except UnresolvedReference as exc:
        result = no_action("clarify", exc.reason)
    return check_question(result, question, periods)
