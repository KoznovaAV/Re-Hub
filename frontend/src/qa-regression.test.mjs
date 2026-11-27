import {test} from 'node:test';
import assert from 'node:assert/strict';
import {callSummary, eligibleForCall, csvCell} from './composables/call-list.mjs';
import {sample, callList} from './pilot-data.mjs';

test('Q-04 period and call status are explicit', () => {
  const client = {
    id: 'qa', active: true, stage: 'В работе',
    history: [{period: '2026Q2', unsent: 10, total: 100}],
    events: [
      {type: 'call', period: '2026Q2', result: 'Недозвон', date: '2026-11-01'},
      {type: 'call', period: '2026Q3', result: 'Перенос', callbackOn: '2026-12-01', date: '2026-11-02'},
    ],
  };
  assert.equal(callSummary(client, '2026Q2').missed, 1);
  assert.equal(callSummary(client, '2026Q2').status, 'Недозвон');
  assert.equal(callSummary(client, '2026Q3').status, 'Перенос');
  assert.equal(callSummary(client, '2026Q3').callbackOn, '2026-12-01');
  assert.equal(callSummary(client, '2025').status, 'Не звонили');
});

test('Q-04 call list applies period, exclusions and threshold', () => {
  const rows = sample('A');
  const selected = callList(rows, '2026Q3', 8);
  assert.ok(selected.length > 0);
  for (const row of selected) {
    const observation = row.periods.find((item) => item.period === '2026Q3');
    assert.equal(row.excluded, false);
    assert.equal(observation.observed, true);
    assert.ok(observation.unsent >= 8);
    assert.equal(observation.contacted, false);
  }
  const otherPeriod = callList(rows, '2026Q2', 8);
  assert.notDeepEqual(otherPeriod.map((row) => row.client), selected.map((row) => row.client));
});

test('Q-04 filters exclude missing observations and zero debt', () => {
  const base = {id: 'qa', active: true, stage: 'В работе', excluded: false, inactive: false,
    history: [{period: '2026Q3', unsent: 10, total: 100, observed: true}], events: []};
  assert.equal(eligibleForCall(base, '2026Q3'), true);
  assert.equal(eligibleForCall(base, '2026Q2'), false);
  assert.equal(eligibleForCall({...base, excluded: true}, '2026Q3'), false);
  assert.equal(eligibleForCall({...base, inactive: true}, '2026Q3'), false);
  assert.equal(eligibleForCall({...base, stage: 'Закрыт'}, '2026Q3'), false);
  assert.equal(eligibleForCall({...base, history: [{period: '2026Q3', unsent: 0, total: 100}]}, '2026Q3'), false);
});

test('Q-04 regression keeps CSV exports safe', () => {
  assert.equal(csvCell('=1+1'), '"\'=1+1"');
  assert.equal(csvCell('A"B'), '"A""B"');
});
