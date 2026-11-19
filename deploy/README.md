# CI/CD и откат

## Что происходит

1. Pull request в `main` → workflow **CI**: Python, Go, frontend, Compose smoke, security scan, сборка образов без push.
2. Merge в `main` → CI публикует образы в GHCR с тегами `sha-<short>`, `main`, `latest`.
3. После успешного CI на `main` workflow **Deploy** пытается выложить `sha-<short>` на staging. Если секреты не заданы — шаг пропускается, пайплайн остаётся зелёным.
4. Production — только вручную: **Deploy → Run workflow**, environment `production`, тег `sha-…` или `v…`. В GitHub Environment можно включить required reviewers.
5. Тег `v*` дополнительно создаёт GitHub Release.

## Образы

- `ghcr.io/<owner>/rehub-backend:<tag>`
- `ghcr.io/<owner>/rehub-ai-service:<tag>`
- `ghcr.io/<owner>/rehub-frontend:<tag>`

Для отката используйте `sha-<short>` конкретного проверенного коммита. GHCR технически позволяет перезаписать тег; защита неизменяемости этим workflow не настраивается.

## Секреты и окружения

В branch protection для `main` включите required check `ci` и запрет прямых push.

Создайте GitHub Environments `staging` и `production`. В каждом задайте секреты. Preflight привязан к выбранному Environment и читает его секреты. Ручной запуск с неполной конфигурацией завершается ошибкой; автоматический staging пропускается с уведомлением.

| Secret | Назначение |
|---|---|
| `DEPLOY_HOST` | IP или DNS сервера |
| `DEPLOY_USER` | SSH-пользователь |
| `DEPLOY_SSH_KEY` | приватный SSH-ключ |
| `DEPLOY_PORT` | SSH-порт, необязательно |
| `DEPLOY_PATH` | каталог деплоя на сервере |
| `GHCR_READ_TOKEN` | PAT с `read:packages` для private-образов |
| `GHCR_USER` | пользователь GHCR, необязательно |

`DEPLOY_PATH` должен существовать. В нём один раз создайте `.env` из `deploy/.env.example` и заполните пароль БД.

## Сервер

- Docker Engine + Compose v2.
- Порты наружу не нужны: frontend слушает `127.0.0.1:${WEB_PORT}`; TLS/reverse proxy — отдельно.
- Первый деплой: `Deploy` с environment `staging` и тегом `latest`.
- `remote-deploy.sh` по умолчанию делает `pg_dump` в `backups/` перед сменой образов и хранит 7 дней. Отключается `BACKUP_BEFORE_DEPLOY=0`.

## Откат

### Приложение

1. **Actions → Rollback → Run workflow**.
2. Выберите environment и known-good тег `sha-…`.
3. Скрипт `remote-rollback.sh` поднимет прежние образы и проверит `/health`.

При неудачном деплое `remote-deploy.sh` пытается вернуть последний рабочий тег из `.previous_image_tag` и завершает job с ошибкой. Этот файл обновляется только после успешного запуска и всех health-проверок. Ошибка самого отката явно выводится в лог. Deploy и Rollback одного окружения выполняются последовательно.

### Код и пайплайн

- Изменения пайплайна — отдельный PR. Откат: `git revert <merge-commit>` и merge обратно.
- Удаление секретов `DEPLOY_*` полностью отключает CD, не ломая CI.
- Откат использует сохраненные образы: не удаляйте теги и digest рабочих версий из GHCR.

### База данных

Backend применяет встроенные миграции при старте. Перед деплоем создаётся `pg_dump` в `backups/` (7 дней). Восстановление БД автоматически не выполняется: используйте `psql`/restore из backup. Не добавляйте destructive-миграции без проверки backup.

## Локальная проверка

```bash
docker compose config --quiet
docker compose up --build -d --wait
make smoke
```

Production-конфиг:

```bash
cd deploy
cp .env.example .env
docker compose -f docker-compose.prod.yml config --quiet
```

## Границы проверки

CI проверяет Python, Go с PostgreSQL, frontend, фикстуры, запуск Compose и восстановление Python. Только после Compose smoke публикуются образы. Проверки не запускают настоящую Qwen и не подтверждают качество ее ответов: для этого нужен отдельный `scripts/smoke-ai-query.py` на стенде с Ollama.

Основной Vue-интерфейс пока использует `frontend/src/mock/api.js`. Добавленный Go API с PostgreSQL не означает, что интерфейс уже переведен на него. `/health` проверяет доступность сервисов, но не готовность модели Ollama. Перед показом помощника проверьте `/ai-demo` через frontend.

Production-конфиг включает демонстрационные маршруты и не содержит полноценной аутентификации. Используйте закрытый тестовый стенд. Секреты сервера, правила защиты main и reviewers окружения настраиваются отдельно в GitHub; наличие YAML не подтверждает их настройку.
