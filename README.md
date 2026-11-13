# Re:Hub — Контур MVP

Re:Hub помогает администратору и оператору КЦР контролировать передачу оригиналов документов. Целевой сценарий: администратор загружает срез, сравнивает динамику по периодам и формирует список на обзвон. Оператор фиксирует результат звонка и видит историю клиента.

## Что доступно в спринте 2

| Функция | Состояние | Как посмотреть |
|---|---|---|
| Интерфейс, Go API и Python | Реализованы точки входа и `/health` | Запуск через Compose, затем проверка ниже |
| Обмен Go ↔ Python | Контрольный JSON-запрос с фиксированным идентификатором | `make smoke` |
| Импорт XLSX, PostgreSQL, права и сценарии обзвона | В бэклоге прототипа | [Доска проекта](https://github.com/users/KoznovaAV/projects/5) |
| ML-помощник | Демо на синтетических данных | [Контроль ответов](https://github.com/KoznovaAV/Re-Hub/issues/61) · [подключение сервиса](https://github.com/KoznovaAV/Re-Hub/issues/67) |

## Как это работает

Браузер запрашивает `/api/probe` у сервера интерфейса, который передаёт запрос в Go. Go отправляет в Python `POST /probe` с JSON `{"schema_version":1,"request_id":"skeleton"}` и проверяет, что Python вернул ту же версию и идентификатор со статусом `ok`. При недоступности Python маршрут проверки возвращает 503, а `/health` Go остаётся доступным.

## Архитектура и структура

Целевой паттерн — модульный монолит Go для доменных правил и записи в PostgreSQL. Python выделен для парсинга и ML и взаимодействует с Go по JSON/HTTP. На этапе скелета используется один контрольный запрос. Это позволяет проверить границу компонентов до подключения базы, парсера и модели.

| Путь | Назначение |
|---|---|
| [`backend/cmd/api/main.go`](backend/cmd/api/main.go) | Go API и клиент Python |
| [`backend/contracts/openapi.yaml`](backend/contracts/openapi.yaml) | Маршруты Go, ответы и ошибки скелета |
| [`ai-service/app/main.py`](ai-service/app/main.py) | Python endpoint для проверки JSON |
| [`frontend/src/`](frontend/src/) | Экраны прототипа и прокси к Go |
| [`docker-compose.yml`](docker-compose.yml) | Сборка, сеть и проверки доступности трёх компонентов |
| [`scripts/smoke.mjs`](scripts/smoke.mjs) | Проверка страницы, Go API и 10 JSON-запросов |

## Как запустить

Нужны Git и Docker с Compose v2, поддерживающим `up --wait`. Compose собирает образы с Go 1.25, Python 3.12 и Node.js 22. Скелет использует стандартные библиотеки. При первой сборке Docker скачивает базовые образы.

```bash
git clone https://github.com/KoznovaAV/Re-Hub.git
cd Re-Hub
docker compose up --build -d --wait
docker compose ps
docker compose exec -T frontend node --input-type=module - < scripts/smoke.mjs
```

Откройте http://127.0.0.1:3000/. Ожидаемая строка smoke-проверки: `OK: интерфейс и Go доступны, JSON Go → Python: 10/10.` В PowerShell проверку можно запустить так:

```powershell
Get-Content -Raw scripts/smoke.mjs | docker compose exec -T frontend node --input-type=module -
```

При установленном Make команды из корня — `make up`, `make smoke` и `make down`. Команда `make smoke-recovery` проверяет отказ Python, запускает его снова и повторяет smoke.

### Демо интерфейса с помощником

Обычный запуск открывает главную, список клиентов, карточки, рабочую очередь, историю и экран импорта. Сценарии этих экранов выполняются на демо-данных в браузере и сбрасываются при перезагрузке. Экран импорта имитирует разбор XLSX и подтверждение.

На Windows с запущенным Ollama и скачанной моделью `qwen3:4b` можно подключить помощника к тому же интерфейсу:

```powershell
$env:WEB_PORT = "3002"
$env:AI_DEMO_PORT = "8082"
docker compose -f docker-compose.yml -f docker-compose.ai-demo.yml up --build -d --wait
Start-Process "http://127.0.0.1:3002/"
py -3 -X utf8 scripts/smoke-ai-query.py --url http://127.0.0.1:3002/api/ai/query
```

Откройте «Тест помощника» в боковом меню. Запросы проходят через Node, Go и Python к Ollama. Помощник использует отдельный набор синтетических клиентов для тестового оператора. Смена роли и изменения в основных экранах на ответы помощника не влияют.

### Проверка отказа и восстановления

```bash
docker compose stop ai-service
docker compose exec -T -e SMOKE_PYTHON_DOWN=1 frontend node --input-type=module - < scripts/smoke.mjs
docker compose up -d --wait ai-service
make smoke
```

При остановке Python ожидаются ответ Go `/health` с кодом 200 и `/api/probe` с кодом 503. После запуска Python smoke снова ожидает 10 успешных ответов.

### Запуск без Docker

В трёх терминалах из корня репозитория:

```bash
python3 ai-service/app/main.py
(cd backend && go run ./cmd/api)
node frontend/src/server.mjs
```

После запуска: `node scripts/smoke.mjs`. Остановите процессы через Ctrl+C. Для Compose используйте `docker compose down`. Логи сервисов доступны через `docker compose logs --tail=50`.

## Настройки, данные и доступы

По умолчанию Compose открывает только интерфейс на `127.0.0.1:3000`. Если порт занят, укажите `WEB_PORT=3001` в окружении или в локальном `.env`. Go и Python доступны внутри сети Compose.

Ключи, база данных, модель и файлы заказчика для запуска не нужны. Контрольный запрос содержит только версию схемы и тестовый идентификатор. Расходы ограничены загрузкой образов и локальными ресурсами. Для проверки доступен локальный запуск.

## Проверка и выбор маршрутизатора

Smoke измеряет доступность и корректность контрольного ответа. Для проверки границы Go → Python, включая неверные ответы, запустите `cd backend && go test ./...`.

Выбор роутера описан в [отчёте H-02](reports/H-02-conclusion.md). В [плане](docs/experiments/H-02-plan.md) зафиксированы критерии, в [результатах](backend/benchmarks/results.json) — все раунды. Импорт XLSX, база данных и ML требуют отдельных проверок.

## Документы проекта

Начните с [индекса документов](docs/README.md) и [свидетельств спринта](reports/sprint-evidence.md). Прототип для проверки списка обзвона и карточки клиента доступен на `http://127.0.0.1:3000/pilot` после запуска. Проверка октябрьского XLSX выполняется отдельно через [локальный адаптер](docs/data/customer-october-xlsx.md).

- [Скелет приложения — T-09](https://github.com/KoznovaAV/Re-Hub/issues/60)
- [Контракт Go/Python — T-26](https://github.com/KoznovaAV/Re-Hub/issues/54)
- [Правила импорта и периодов — T-02](https://github.com/KoznovaAV/Re-Hub/issues/48)
- [Сравнение маршрутизаторов — H-02](https://github.com/KoznovaAV/Re-Hub/issues/70)
