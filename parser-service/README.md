# parser-service — разбор XLSX и проверка ParserResult

Сервис принимает справочник клиентов и срезы КЦР, возвращает `ParserResult` v1
по контракту [`contracts/parser-result.schema.json`](../contracts/parser-result.schema.json).
Python проверяет структуру книги и ячеек; дубли, клиент, период и числовые
ограничения проверяет Go.

## Установка и тесты

```powershell
py -3 -m pip install -r parser-service/requirements-import.txt
cd parser-service
py -3 -m unittest discover -s tests -v
```

## `POST /parse`

Запуск:

```powershell
py -3 app/main.py
```

Запрос — `multipart/form-data`:

| Поле | Содержимое |
|---|---|
| `file` | XLSX-файл (`clients` или `snapshot`) |
| `context` | JSON-контекст загрузки |

Для `file_kind=snapshot` парсер возвращает строки среза, для
`file_kind=clients` — справочник клиентов. Ответ — `ParserResult` v1.

## Ограничения и безопасность

- `xlsx_limits.check_archive` проверяет zip до `openpyxl`: число файлов,
  распакованный размер, размер одного файла и подозрительную степень сжатия.
- Лимиты HTTP: тело запроса 25 МиБ, context 64 КиБ, 20 частей multipart,
  50 000 непустых строк и 100 000 просмотренных строк.
- Число одновременных запросов ограничено 8.
- `defusedxml` блокирует XML-бомбы и внешние сущности при разборе XLSX.
- Временный XLSX удаляется после разбора.
- `POST /parse` не содержит аутентификации и rate limit. Сервис должен быть
  доступен только внутри закрытого контура или за Go-API.

## Фикстуры и V-02

Golden-фикстуры среза лежат в `tests/fixtures/snapshot/`. Пересборка:

```powershell
py -3 parser-service/tests/fixtures/snapshot/build_cases.py
```

Каркас V-02:

```powershell
cd parser-service
py -3 -m app.call_list_metrics `
  --reference tests/fixtures/v02/reference.json `
  --actual tests/fixtures/v02/actual.json
```

Замер производительности и RSS выполняет `app/parser_benchmark.py`; результаты
и ограничения описаны в `reports/p-tasks/performance.md`.
