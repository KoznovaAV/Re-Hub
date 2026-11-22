# Go API

Основной запуск выполняется из корня через `docker compose up --build -d --wait`. Backend ждёт PostgreSQL, применяет миграции и обращается к Python по `PYTHON_SERVICE_URL`. Без `DATABASE_URL` бизнес-маршруты возвращают 503, данные в память не подставляются.

```bash
go vet ./...
go test -p 1 ./...
```

Для интеграционных тестов нужна отдельная тестовая PostgreSQL в `TEST_DATABASE_URL`. Без неё тесты БД пропускаются; такой локальный результат не заменяет CI с PostgreSQL. Тесты очищают рабочие таблицы, поэтому использовать для них эксплуатационную БД нельзя.

[OpenAPI](contracts/openapi.yaml), [схема компонентов](../docs/architecture/components.md), [границы ролей](../docs/scenarios/roles-and-statuses.md), [проверка готовности](../reports/prototype-readiness.md).
