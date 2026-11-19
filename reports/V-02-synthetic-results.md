# V-02 — синтетический замер сравнения списков

**Дата:** 2026-11-19. **Статус:** каркас на синтетике; M-01 и реальный эталон
не используются.

Скрипт: [`ai-service/app/call_list_metrics.py`](../ai-service/app/call_list_metrics.py).
Машиночитаемый результат:
[`V-02-synthetic-results.json`](V-02-synthetic-results.json).

## Что сравнивается

Ключ списка — `(external_id, period_code)`. Эталонные элементы с
`excluded=true` не входят в знаменатель recall; фактические исключения
показываются отдельно. Дубли ключей в одном списке отклоняются, чтобы метрика
была однозначной.

## Синтетический прогон

Исходные файлы:
[`reference.json`](../ai-service/tests/fixtures/v02/reference.json) и
[`actual.json`](../ai-service/tests/fixtures/v02/actual.json).

| Метрика | Значение |
|---|---:|
| Эталонных элементов | 5 (4 обязательных, 1 исключённый) |
| Фактических элементов | 5 (4 в обзвоне, 1 исключён) |
| True positive | 2 |
| Лишние | 2 |
| Пропуски | 2 |
| Precision | 0,5 |
| Recall | 0,5 |
| F1 | 0,5 |

Исключения: один обязательный клиент фактически помечен исключённым, один
исключённый эталонный клиент попал в обзвон. Оба случая вынесены в
`exceptions`, а не спрятаны внутри precision/recall.

## Воспроизведение

```powershell
cd ai-service
py -3 -m app.call_list_metrics `
  --reference tests/fixtures/v02/reference.json `
  --actual tests/fixtures/v02/actual.json `
  --output ../reports/V-02-synthetic-results.json
```

Когда появится M-01 и парсер клиентов, форма входа и метрик сохраняется:
меняются только источники файлов.
