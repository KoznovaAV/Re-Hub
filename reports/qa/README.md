# QA-отчёты Q-01…Q-04

| Задача | Материал | Автопроверка |
|---|---|---|
| Q-01 | [Чек-лист администратора и оператора](Q-01-admin-operator.md) | `scripts/qa/run_qa.py::q01` |
| Q-02 | [E2E импорта и CSV](Q-02-import-e2e.md) | `scripts/qa/run_qa.py::q02`, `frontend/src/import-errors.test.mjs` |
| Q-03 | [Протокол M-05](../h00/Q-03-M-05-protocol.md) | `scripts/tests/test_q03_protocol.py` |
| Q-04 | [Регрессия периода, call-list, фильтров и звонков](Q-04-regression.md) | `scripts/qa/run_qa.py::q04`, `frontend/src/qa-regression.test.mjs` |

## Ограничения

Q-01, Q-02 и Q-04 выполняются на синтетических XLSX в закрытом контуре. Q-03
нельзя закрыть автоматически: нужны два реальных администратора и независимый
эксперт для эталона. Синтетические и автоматизированные прогоны не подменяют
пользовательский пилот.
