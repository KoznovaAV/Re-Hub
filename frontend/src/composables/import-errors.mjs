import {csvCell} from "./call-list.mjs";

export const ERROR_CSV_HEADER = [
  "Лист", "Строка", "Колонка", "ID", "Период", "Код", "Причина", "Значение",
];

export function buildErrorsCsv(errors) {
  const rows = [
    ERROR_CSV_HEADER,
    ...errors.map((error) => [
      error.sheet,
      error.row,
      error.column,
      error.external_id,
      error.period_code,
      error.code,
      error.message,
      error.value ?? error.raw_value,
    ]),
  ];
  return rows.map((row) => row.map(csvCell).join(";")).join("\r\n");
}
