# Профиль октябрьского XLSX

`customer_october_tabs_v1` читает заголовок со строки 2 и данные со строки 3. Период задаётся точным именем вкладки.

| Вкладка | period_code | Строк |
|---|---|---:|
| весь 2025 год | Y2025 | 3 419 |
| 1 кв 2026 | 2026Q1 | 2 928 |
| 2 кв 2026 | 2026Q2 | 3 021 |
| 3 кв 2026 | 2026Q3 | 3 404 |

Ключ обезличенного набора находится в столбце A. Столбец B называется «Код КЦР» на первой вкладке и «код СЦ» на трёх остальных, поэтому профиль работает только в режиме `anonymous`. D и E содержат всего и не отправлено. Дату среза задаёт контекст. Неизвестная вкладка, другой заголовок или расхождение со scope блокируют файл.

Парсер сохраняет исходные вкладку, строку и колонку, отклоняет формулы в числах и оставляет дубли для проверки в Go. Для ошибок с читаемым ID выдаёт `key_hint`. Проверка покрытия справочником отделена от парсинга. Реальный импорт по коду КЦР и транзакционная запись относятся к другим задачам.

```sh
python -m pip install -r ai-service/requirements-import.txt
python ai-service/app/customer_xlsx.py /path/to/snapshot.xlsx contracts/examples/customer-october-context.json --summary
cd ai-service
python -m unittest discover -s tests -v
python -m app.customer_period_check /path/to/snapshot.xlsx ../contracts/examples/customer-october-context.json
python -m app.customer_coverage /path/to/snapshot.xlsx /path/to/directory.xlsx ../contracts/examples/customer-october-context.json
```

Сырые файлы, результаты с клиентскими строками и отчёты с ID хранятся внутри проекта. Для сверки из репозитория доступны синтетическая фикстура и агрегаты.
