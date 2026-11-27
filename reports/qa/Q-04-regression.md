# Q-04 — регрессия периода, списка обзвона, фильтров и статуса звонка

**Задача:** Q-04, SHOULD, A-10/A-14. **Статус:** набор добавлен в CI и
регулярный прогон.

## Что проверяется

- период обязателен; неизвестный период и неверные фильтры дают `422`;
- список обзвона доступен только администратору;
- фильтры `min_unsent`, `min_share`, `contacted=no` не пропускают неподходящие
  строки;
- исключённые и неактивные клиенты не попадают в список;
- звонки сохраняют результат `Недозвон`/`Перенос`/`Обещание`, callback и
  обещанную дату;
- после звонка клиент исключается из `contacted=no`;
- фронтенд-функции периода, `callSummary`, `eligibleForCall` и CSV устойчивы
  к регрессиям.

## Где запускается

- `scripts/qa/run_qa.py::q04` — E2E через Go API/PostgreSQL в CI Compose.
- `frontend/src/qa-regression.test.mjs` — Node-тесты в CI (`npm test`).
- существующие Go-тесты `backend/internal/api/call_list_integration_test.go` и
  `backend/internal/store/workflow_test.go` — в CI job `Go tests`.

## Ручной/регулярный прогон

```powershell
docker compose exec -T parser-service python - < scripts/qa/run_qa.py
cd frontend
npm ci
npm test
cd ..\backend
go test -p 1 ./...
```

## Результаты

Набор добавлен в CI; после push результаты доступны в check `Compose smoke` и
`ci`. До фактического прогона дефекты не объявляются найденными или
отсутствующими.
