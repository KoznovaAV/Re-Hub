# Re:Hub — Контур MVP

Re:Hub помогает администратору и оператору КЦР контролировать передачу оригиналов документов. Целевой сценарий: администратор загружает срез, сравнивает динамику по периодам и формирует список на обзвон. Оператор фиксирует результат звонка и видит историю клиента.

## Что доступно в спринте 2

| Функция | Состояние | Как посмотреть |
|---|---|---|
| Интерфейс, Go API и Python | Реализованы точки входа и `/health` | Запуск через Compose, затем проверка ниже |
| Обмен Go ↔ Python | Контрольный JSON-запрос с фиксированным идентификатором | Кнопка «Проверить связь» или `make smoke` |
| Импорт XLSX, PostgreSQL, права и сценарии обзвона | В бэклоге прототипа | [Доска проекта](https://github.com/users/KoznovaAV/projects/5) |
| ML-помощник | В бэклоге прототипа | [Контроль ответов](https://github.com/KoznovaAV/Re-Hub/issues/61) · [подключение сервиса](https://github.com/KoznovaAV/Re-Hub/issues/67) |

## Как это работает

Браузер запрашивает `/api/probe` у сервера интерфейса, который передаёт запрос в Go. Go отправляет в Python `POST /probe` с JSON `{"schema_version":1,"request_id":"skeleton"}` и проверяет, что Python вернул ту же версию и идентификатор со статусом `ok`. При недоступности Python маршрут проверки возвращает 503, а `/health` Go остаётся доступным.

## Архитектура и структура

Целевой паттерн — модульный монолит Go для доменных правил и записи в PostgreSQL. Python выделен для парсинга и ML и взаимодействует с Go по JSON/HTTP. На этапе скелета используется один контрольный запрос. Это позволяет проверить границу компонентов до подключения базы, парсера и модели.

| Путь | Назначение |
|---|---|
| [`backend/cmd/api/main.go`](backend/cmd/api/main.go) | Go API и клиент Python |
| [`backend/contracts/openapi.yaml`](backend/contracts/openapi.yaml) | Маршруты Go, ответы и ошибки скелета |
| [`ai-service/app/main.py`](ai-service/app/main.py) | Python endpoint для проверки JSON |
| [`frontend/src/`](frontend/src/) | Страница проверки связи и прокси к Go |
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

Откройте http://127.0.0.1:3000/ и нажмите «Проверить связь». Ожидаемая строка smoke-проверки: `OK: интерфейс и Go доступны, JSON Go → Python: 10/10.` В PowerShell проверку можно запустить так:

```powershell
Get-Content -Raw scripts/smoke.mjs | docker compose exec -T frontend node --input-type=module -
```

При установленном Make команды из корня — `make up`, `make smoke` и `make down`.

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

## Ограничения проверки

Smoke измеряет доступность и корректность контрольного ответа. Замеры производительности, проверка импорта и проверка качества ML ведутся отдельно.

Прогон на Linux amd64 с Go 1.25.12, Python 3.12.14 и Node.js 24.22.1 выполнен прямым запуском процессов. Все три маршрута `/health` вернули 200. Smoke получил 10 из 10 ожидаемых JSON-ответов до остановки Python и ещё 10 из 10 после перезапуска. Во время остановки Go вернул 200 на `/health` и 503 на запрос связи. Python вернул 400 на запрос с неверным типом версии схемы. Конфигурация Compose проверена статически. Прогон контейнеров и проверка на Node.js 22 остаются открытыми.

## Документы проекта

- [Скелет приложения — T-09](https://github.com/KoznovaAV/Re-Hub/issues/60)
- [Контракт Go/Python — T-26](https://github.com/KoznovaAV/Re-Hub/issues/54)
- [Правила импорта и периодов — T-02](https://github.com/KoznovaAV/Re-Hub/issues/48)
- [Сравнение маршрутизаторов — H-02](https://github.com/KoznovaAV/Re-Hub/issues/70)
