import {test} from 'node:test';
import assert from 'node:assert/strict';
import {buildErrorsCsv, ERROR_CSV_HEADER} from './composables/import-errors.mjs';

test('error CSV has a stable header and one row per rejected source row', () => {
  const csv = buildErrorsCsv([
    {sheet: '1 кв 2026', row: 4, column: 'A', external_id: 'AAA00002',
     period_code: '2026Q1', code: 'INVALID_EXTERNAL_ID', message: 'bad key', raw_value: '#N/A'},
    {sheet: 'все 2025', row: 7, column: 'D', external_id: null,
     period_code: 'Y2025', code: 'UNSENT_GT_TOTAL', message: 'unsent > total'},
  ]);
  const lines = csv.split('\r\n');
  assert.equal(lines.length, 3);
  assert.equal(lines[0], ERROR_CSV_HEADER.map((cell) => `"${cell}"`).join(';'));
  assert.match(lines[1], /"INVALID_EXTERNAL_ID"/);
  assert.match(lines[1], /"#N\/A"/);
  assert.match(lines[2], /"UNSENT_GT_TOTAL"/);
});

test('error CSV escapes formulas and quotes instead of executing them', () => {
  const csv = buildErrorsCsv([
    {sheet: '=1+1', row: 2, column: 'A', external_id: 'A"B',
     period_code: 'Y2025', code: 'INVALID_EXTERNAL_ID', message: 'm', raw_value: '=cmd'},
  ]);
  assert.match(csv, /"'=1\+1"/);
  assert.match(csv, /"A""B"/);
  assert.match(csv, /"'=cmd"/);
});

test('empty error list still produces a downloadable header', () => {
  assert.equal(buildErrorsCsv([]), ERROR_CSV_HEADER.map((cell) => `"${cell}"`).join(';'));
});
