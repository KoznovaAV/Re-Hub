# P-01–P-08: результаты

Рабочая ветка: fix/review-roles-and-workflow. Изменения не объединены с main.

| Задача | Реализация и проверка |
|---|---|
| P-01 | Лимит запроса 25 МиБ, MIME вложения XLSX/octet-stream, расширение и реальная структура ZIP; 512 записей/200 МиБ распакованного размера; отказ для шифрования/ссылок; временные файлы удаляются после успеха и ошибок. HTTP-тесты проверяют коды и следующий успешный запрос. |
| P-02 | Draft 2020-12 валидация ParserResult по contracts/parser-result.schema.json перед HTTP-ответом. Оба парсера и вложенные мутации проверяются в CI. Go отклоняет неизвестные поля конверта/строк и несовпадающий контекст. |
| P-03 | Общая доменная проверка Go используется предпросмотром и транзакционной записью. Дубли отклоняются целиком; проверяются клиент, период/scope, числа и unsent ≤ total. Отсутствующий total берётся только из более раннего среза той же пары клиент/период; сохраняются значение и ссылка на источник. Валидные строки частичного импорта сохраняются. Тесты выполняются с PostgreSQL. |
| P-04 | Технический аудит завершён: XLSX сверяется по полному множеству ID с pypdf и PyMuPDF; проверено влияние Poppler на результат. Историческое 1572 не воспроизводится и исключено из выводов. Подробные расчёты и хеши: data-quality.md/json/csv. Оставшиеся 243 неизвестных ID требуют делового объяснения поставщика; это не незавершённая разработка отчёта. |
| P-05 | По 40 отдельных процессов для 4000 синтетических клиентов и 12768 валидных строк исходного среза. Есть p95 nearest-rank, время разбора/схемы, пик RSS и отдельный cProfile. См. performance.md. |
| P-06 | Python CI запускает HTTP, контракт, оба парсера, качество данных и негативные случаи. Go CI с PostgreSQL проверяет доменные правила. |
| P-07 | В Compose, CI и зависимостях нет AI runtime; регрессионный тест не допускает его случайного возврата. backend/parser_ml — старый детерминированный XLSX-парсер, не модель. |
| P-08 | scripts/evaluate-h00.py считает precision, recall, включение исключённых и пропущенных кандидатов, сохраняет причины в диагностике. Смоделированные данные никогда не подтверждают реальный пилот. |

## Повторение

```bash
python -m pip install -r parser-service/requirements-import.txt
(cd parser-service && python -m unittest discover -s tests -v)
python -m unittest discover -s scripts/tests -v
(cd backend && TEST_DATABASE_URL='postgres://…' go test -p 1 ./...)
(cd parser-service && python -m app.data_quality /path/to/snapshot.xlsx /path/to/directory.xlsx ../contracts/examples/customer-october-context.json --out /tmp/quality)
(cd parser-service && python -m app.generate_test_data --out /tmp/p05 --size 4000 --seed 42)
(cd parser-service && python -m app.parser_benchmark /tmp/p05/clients.xlsx /tmp/p05/clients.context.json --repeat 40 --out /tmp/clients-benchmark.json)
(cd parser-service && python -m app.parser_benchmark /path/to/snapshot.xlsx ../contracts/examples/customer-october-context.json --repeat 40 --out /tmp/snapshot-benchmark.json)
python scripts/evaluate-h00.py contracts/testing/h00/simulated/pilot.json
```

Исходные файлы заказчика и строки с их ID не добавляются в репозиторий. В отчётах опубликованы агрегаты и хеши. Пользовательский замер ускорения с двумя администраторами остаётся задачей Q-03; технические тесты и вымышленные времена его не подменяют.

Фактически выполнены локально: 25 тестов парсера/контракта/HTTP/качества, 10 тестов оценщика и отключения AI, 26 тестов фронтенда, Go-тесты с отдельной PostgreSQL (без кэша), go vet и сквозной smoke реального XLSX через Go/Python/БД. Docker-сборка в этом окружении не запускалась: Docker CLI отсутствует; её выполняет workflow CI.

## Дополнение: пользовательские замеры и P-04

Сбор интервалов и ответов реализован на `/study`. [Инструкция](../../docs/scenarios/user-measurements.md), [автоматизированный прогон](../h00/browser-workflow-method.md). Для P-04 доступна независимая проверка PDF:

```bash
python3 -m pip install -r parser-service/requirements-audit.txt
# Также нужен системный pdftotext (Poppler).
PYTHONPATH=parser-service python3 -m app.data_quality /path/to/snapshot.xlsx /path/to/directory.xlsx contracts/examples/customer-october-context.json --pdf-directory /path/to/directory.pdf --out /tmp/quality
```

Вывод о 1572 не заменён вымышленной причиной: неподтверждённая цифра исключается, альтернативный результат извлечения воспроизводится отдельно. Техническая задача P-04 закрывается отчётом; H-10 остаётся отрицательным результатом проверки покрытия.

Предыдущий коммит f16ea727 успешно прошёл GitHub CI: Python, Go/PostgreSQL, frontend, security, Compose smoke и сборки трёх Docker-образов (workflow run 45033217590). Проверки текущего дополнения выполняются отдельно.

Дополнительно устранена гонка завершения HTTP-запроса: временная книга удаляется до отправки ответа парсера, что проверяется тестом без ожиданий.
