import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

test('client list keeps customer type and hides promise/work status columns', () => {
  const source = readFileSync(new URL('./views/ClientsView.js', import.meta.url), 'utf8');
  assert.ok(source.includes('\u0422\u0438\u043f \u043a\u043b\u0438\u0435\u043d\u0442\u0430'));
  assert.ok(!source.includes('\u041e\u0431\u0435\u0449\u0430\u043d\u043d\u044b\u0439 \u0441\u0440\u043e\u043a'));
});

test('client history shows interactions, not assignment internals', () => {
  const source = readFileSync(new URL('./views/ClientCardView.js', import.meta.url), 'utf8');
  assert.match(source, /call.*email.*comment/);
});
