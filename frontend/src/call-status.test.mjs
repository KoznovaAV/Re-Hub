import test from 'node:test';
import assert from 'node:assert/strict';
import { callSummary } from './composables/call-list.mjs';

const MISSED = 'Недозвон';
const TRANSFER = 'Перенос';
const CALLED = 'Дозвон';
const NOT_CALLED = 'Не звонили';

test('call status keeps counts, missed attempts and callback separately', () => {
  const client = { events: [
    { type: 'call', period: '2026Q3', result: MISSED, date: '2026-11-01' },
    { type: 'call', period: '2026Q3', result: MISSED, date: '2026-11-02' },
    { type: 'call', period: '2026Q3', result: TRANSFER, callbackOn: '2026-11-20', date: '2026-11-10' },
  ] };
  const summary = callSummary(client, '2026Q3');
  assert.equal(summary.count, 3);
  assert.equal(summary.missed, 2);
  assert.equal(summary.status, TRANSFER);
  assert.equal(summary.callbackOn, '2026-11-20');
});

test('calls from another period are not reported as this period calls', () => {
  const client = { events: [{ type: 'call', period: '2026Q2', result: CALLED, date: '2026-07-01' }] };
  const summary = callSummary(client, '2026Q3');
  assert.equal(summary.count, 0);
  assert.equal(summary.status, NOT_CALLED);
});
