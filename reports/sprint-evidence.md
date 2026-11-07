# Свидетельства спринта

| Гипотеза | Проверено | Следующий шаг |
|---|---|---|
| H-01 | 40/40 на 10 клиентах; профиль XLSX воспроизводит результат на всей книге. [Отчёт](H-01-period-mapping.md) | Использовать явные вкладки и проверять дубли в Go. |
| H-02 | Контрольный обмен, восстановление и сравнение маршрутизаторов. [Отчёт](H-02-conclusion.md) | Оставить net/http. |
| H-05 | Не применимо к текущему источнику. Исходный XLSX найден. [Решение](H-01-period-mapping.md) | Использовать XLSX. |
| H-10 | Порог 5% не пройден. Расхождения сосредоточены в III квартале. [Отчёт](H-10-coverage.md) | Поставщик уточняет состав и причину в #69. |
| H-00 | Прототип и два синтетических набора готовы. [Протокол](../docs/scenarios/pilot.md) | Замер с двумя администраторами и реальный эталон #51. |
| H-06 | Сценарии карточки и проверка фильтров на фикстурах. [Отчёт](ui-scenarios.md) | Замер с 2–3 операторами. |
| H-03 | 20 + 3 контрольных кейса на эталоне чтения. [Отчёт](ml-evaluation.md) | Проверить модель через рабочий API и сравнить с фильтрами. |

## Статусы задач по свидетельствам

| Состояние | Карточки |
|---|---|
| Завершён измеримый результат | [#68 H-01](https://github.com/KoznovaAV/Re-Hub/issues/68), [#70 H-02](https://github.com/KoznovaAV/Re-Hub/issues/70) |
| Есть артефакт для проверки | [#48 правила](https://github.com/KoznovaAV/Re-Hub/issues/48), [#53 документы](https://github.com/KoznovaAV/Re-Hub/issues/53), [#54 контракт](https://github.com/KoznovaAV/Re-Hub/issues/54), [#59 макет](https://github.com/KoznovaAV/Re-Hub/issues/59), [#71 адаптер](https://github.com/KoznovaAV/Re-Hub/issues/71) |
| Есть результат и ещё нужна работа | [#55 доска](https://github.com/KoznovaAV/Re-Hub/issues/55), [#57 парсер](https://github.com/KoznovaAV/Re-Hub/issues/57), [#60 скелет](https://github.com/KoznovaAV/Re-Hub/issues/60), [#61 эталон](https://github.com/KoznovaAV/Re-Hub/issues/61) |
| Готовы входы, можно начать подготовку | [#49 спорные правила](https://github.com/KoznovaAV/Re-Hub/issues/49), [#50 фикстуры](https://github.com/KoznovaAV/Re-Hub/issues/50), [#52 сценарии](https://github.com/KoznovaAV/Re-Hub/issues/52), [#58 вызов парсера](https://github.com/KoznovaAV/Re-Hub/issues/58) |
| Ожидает внешнего ответа | [#69 справочник](https://github.com/KoznovaAV/Re-Hub/issues/69) |

Остальные задачи сохраняют свои зависимости. Карточки, закрытые как заменённые, не входят в список выполненной разработки.
