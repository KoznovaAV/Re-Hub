# Re:Hub — Контур MVP

Re:Hub помогает администратору и оператору КЦР контролировать передачу оригиналов документов. Целевой сценарий: администратор загружает срез, сравнивает динамику по периодам и формирует список на обзвон. Оператор фиксирует результат звонка и видит историю клиента.

## Что доступно в прототипе

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

## Как запустить через Docker

Для локальной работы нужны Git и запущенный Docker Desktop (Windows/macOS) или Docker Engine с плагином Compose v2 (Linux). Проверить, что Docker запущен и Compose доступен, можно командами `docker info` и `docker compose version`. Для запуска нужны Compose v2 с поддержкой `up --wait` и доступ к реестру образов при первой сборке.

### Первый запуск

```bash
git clone --branch main https://github.com/KoznovaAV/Re-Hub.git
cd Re-Hub
docker compose up --build -d --wait
docker compose ps
```

Compose собирает фронтенд, Go API и Python-сервис. Откройте [главную](http://127.0.0.1:3000/). В обычном режиме доступны главная, клиенты, карточки, рабочая очередь, история и экран импорта. Действия выполняются на демо-данных в памяти браузера, включая имитацию импорта Excel. После перезагрузки страницы изменения сбрасываются. Базовому запуску не нужны Ollama, PostgreSQL, ключи или файлы заказчика.

### Проверка запуска

PowerShell:

```powershell
Get-Content -Raw scripts/smoke.mjs | docker compose exec -T frontend node --input-type=module -
```

Bash:

```bash
docker compose exec -T frontend node --input-type=module - < scripts/smoke.mjs
```

Ожидаемый результат - 10 из 10 успешных JSON-запросов через Go и Python. При установленном Make можно использовать `make up`, `make smoke` и `make down`.

### Обновление и остановка

В рабочей копии с чистой веткой `main`:

```bash
git switch main
git pull --ff-only origin main
docker compose up --build -d --wait
```

Чтобы остановить контейнеры, выполните `docker compose down`. Если сервис не запустился, посмотрите `docker compose ps -a` и `docker compose logs --tail=80`. Если порт 3000 занят, добавьте `WEB_PORT=3001` в локальный `.env` в корне репозитория, повторите запуск и откройте [порт 3001](http://127.0.0.1:3001/).

### Демо интерфейса с помощником

На Windows запустите Ollama и один раз скачайте модель командой `ollama pull qwen3:4b`. Затем из корня репозитория выполните в PowerShell:

```powershell
$env:WEB_PORT = "3002"
$env:AI_DEMO_PORT = "8082"
docker compose -f docker-compose.yml -f docker-compose.ai-demo.yml up --build -d --wait
Start-Process "http://127.0.0.1:3002/"
```

Откройте «Тест помощника» в боковом меню. Запросы проходят через Node, Go и Python к Ollama. Помощник использует отдельный набор синтетических клиентов для тестового оператора. Qwen разбирает вопросы о долге, списках и обещанных сроках. Для вопросов о правилах импорта и полях помощник ищет подтверждённые цитаты в Markdown-документах проекта. Тексты писем, PDF и договоров клиентов в этот набор не входят. Смена роли и изменения в основных экранах на ответы помощника не влияют.

Для smoke-проверки помощника установите Python 3 и выполните:

```powershell
py -3 -X utf8 scripts/smoke-ai-query.py --url http://127.0.0.1:3002/api/ai/query
```

Чтобы остановить демо, выполните `docker compose -f docker-compose.yml -f docker-compose.ai-demo.yml down`.

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

В режиме помощника Compose дополнительно публикует Go API на локальном порту `AI_DEMO_PORT` (по умолчанию 8080). Python остаётся доступен внутри сети Compose.

## Проверка и выбор маршрутизатора

Smoke измеряет доступность и корректность контрольного ответа. Для проверки границы Go → Python, включая неверные ответы, запустите `cd backend && go test ./...`.

Выбор роутера описан в [отчёте H-02](reports/H-02-conclusion.md). В [плане](docs/experiments/H-02-plan.md) зафиксированы критерии, в [результатах](backend/benchmarks/results.json) — все раунды. Импорт XLSX, база данных и ML требуют отдельных проверок.

## Документы проекта

Начните с [индекса документов](docs/README.md) и [свидетельств спринта](reports/sprint-evidence.md). Прототип для проверки списка обзвона и карточки клиента доступен на `http://127.0.0.1:3000/pilot` после запуска. Проверка октябрьского XLSX выполняется отдельно через [локальный адаптер](docs/data/customer-october-xlsx.md).

- [Скелет приложения — T-09](https://github.com/KoznovaAV/Re-Hub/issues/60)
- [Контракт Go/Python — T-26](https://github.com/KoznovaAV/Re-Hub/issues/54)
- [Правила импорта и периодов — T-02](https://github.com/KoznovaAV/Re-Hub/issues/48)
- [Сравнение маршрутизаторов — H-02](https://github.com/KoznovaAV/Re-Hub/issues/70)
