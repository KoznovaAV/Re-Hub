# ai-service — Python-парсер среза

Сервис читает XLSX-срез КЦР и отдаёт `ParserResult` v1 по контракту
[`contracts/parser-result.schema.json`](../contracts/parser-result.schema.json).
Этот модуль не ходит в БД, не создаёт клиентов, не считает историю и не
подтверждает импорт: доменная проверка и commit остаются на стороне Go.

Текущая область ответственности — срез (`file_kind=snapshot`). Парсер файла
клиентов (`file_kind=clients`, T-01) ещё не реализован: `POST /parse` отвечает
`501` и не пытается угадывать формат.

## Установка и тесты

```powershell
py -3 -m pip install -r ai-service/requirements-import.txt
cd ai-service
py -3 -m unittest discover -s tests -v
```

Тесты проверяют golden-фикстуры, HTTP-контур, лимиты, дубли, формулы,
`#N/A`, числа с пробелами и отсутствие `total_docs`.

## `POST /parse`

Запуск сервиса:

```powershell
py -3 ai-service/app/main.py
```

Запрос — `multipart/form-data` с двумя частями:

| Поле | Содержимое |
|---|---|
| `file` | XLSX-файл среза |
| `context` | JSON-контекст `ImportContext` (текстом или файлом) |

Пример с `curl`:

```bash
curl -X POST http://127.0.0.1:8001/parse \
  -F "file=@snapshot.xlsx" \
  -F "context=@contracts/examples/customer-october-context.json;type=application/json"
```

Или контекст текстом:

```bash
curl -X POST http://127.0.0.1:8001/parse \
  -F "file=@snapshot.xlsx" \
  -F 'context={"contract_version":"1.0","file_kind":"snapshot","key_mode":"anonymous","mapping_profile":"customer_october_tabs_v1","snapshot_date":"2026-10-20","period_scope":["Y2025","2026Q1","2026Q2","2026Q3"],"coverage":"unknown"}'
```

Успешный разбор среза возвращает `200` и строго `ParserResult` v1. Ошибки
формата файла (`INVALID_XLSX`, `PERIOD_SCOPE_MISMATCH`, `INVALID_HEADER`,
`NO_DATA_ROWS`) тоже приходят внутри `ParserResult` с `errors[].scope=file`:
это данные для доменного компонента, а не 500.

Понятные транспортные ошибки:

| Статус | Когда |
|---:|---|
| `400` | нет `context`/`file`, битый JSON, неподдерживаемый контекст |
| `413` | слишком большой запрос, файл или context |
| `415` | запрос не `multipart/form-data` |
| `422` | превышен лимит строк; тело — `ParserResult` с `ROW_LIMIT_EXCEEDED` |
| `501` | `file_kind=clients` (парсер появится в T-01) |

Лимиты по умолчанию: запрос 32 МиБ, файл 20 МиБ, context 64 КиБ,
50 000 непустых строк. Их можно изменить переменными окружения
`PARSE_MAX_REQUEST_BYTES`, `PARSE_MAX_FILE_BYTES`, `PARSE_MAX_CONTEXT_BYTES`,
`PARSE_MAX_ROWS`.

Пример smoke на срез:

```powershell
curl.exe -s -X POST http://127.0.0.1:8001/parse `
  -F "file=@ai-service/tests/fixtures/snapshot/normal.xlsx" `
  -F "context=@ai-service/tests/fixtures/snapshot/normal.context.json;type=application/json"
```

## Прямой вызов парсера

```powershell
py -3 ai-service/app/customer_xlsx.py `
  ai-service/tests/fixtures/snapshot/normal.xlsx `
  ai-service/tests/fixtures/snapshot/normal.context.json --summary
```

Дубли не удаляются и не превращаются в row-ошибку: обе строки остаются в
`rows`, а `find_duplicates(result)` и `summary(result)` показывают группы и
позиции, включая `key_hint` отклонённых строк. Решение «отклонить весь файл»
по T-02 IM-01 принимает Go.

## Фикстуры и golden JSON

`ai-service/tests/fixtures/snapshot/` содержит четыре кейса:

| Кейс | Что проверяет |
|---|---|
| `normal` | обычный срез на четырёх вкладках |
| `duplicates` | точный дубль, дубль с другим числом и дубль через `key_hint` |
| `cell-errors` | `#N/A`, формулы, `1 234`, `1 24`, числовой ключ |
| `repeat-missing-total` | повторный парсинг и `total_docs=null` |

Для каждого кейса рядом лежат `*.context.json` и `*.expected.json`.
Ожидаемый JSON написан вручную в `build_cases.py`, а не снят с проверяемого
парсера. Пересобрать бинарные фикстуры:

```powershell
py -3 ai-service/tests/fixtures/snapshot/build_cases.py
```

## T-05 — замер полного среза

```powershell
py -3 ai-service/benchmarks/measure_snapshot_parse.py --iterations 3
```

Без `--input` скрипт собирает синтетический XLSX с публичными агрегатами
12 772 строки / 4 205 ID. Для реального файла:

```powershell
py -3 ai-service/benchmarks/measure_snapshot_parse.py `
  --input path/to/snapshot.xlsx `
  --context contracts/examples/customer-october-context.json
```

Результат по умолчанию — `ai-service/benchmarks/results.json`; краткая выжимка
— в [`reports/T-05-parser-benchmark.md`](../reports/T-05-parser-benchmark.md).

## V-02 — каркас сравнения списков

```powershell
cd ai-service
py -3 -m app.call_list_metrics `
  --reference tests/fixtures/v02/reference.json `
  --actual tests/fixtures/v02/actual.json `
  --output ../reports/V-02-synthetic-results.json
```

Скрипт считает precision/recall/F1, лишние и пропущенные ключи
`(external_id, period_code)` и исключения. M-01 и реальный эталон не
используются: это синтетический каркас, который позже подключается к готовым
данным без изменения формы метрик.
