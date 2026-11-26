import test from 'node:test';
import assert from 'node:assert/strict';
import { request, actorIDs } from './composables/live-api.js';

test('live API request uses the versioned route and actor headers', async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, json: async () => ({ data: [] }) };
  };
  try {
    const result = await request('/periods', { actor: 'operator-a' });
    assert.deepEqual(result, { data: [] });
    assert.equal(calls[0].url, '/api/v1/periods');
    assert.equal(calls[0].options.headers['X-User-Id'], actorIDs['operator-a']);
    assert.equal(calls[0].options.headers['X-Role'], 'operator');
  } finally {
    globalThis.fetch = original;
  }
});

test('live API request surfaces a backend error message', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: false, status: 403, json: async () => ({ message: 'Нет доступа' }) });
  try {
    await assert.rejects(() => request('/clients'), /Нет доступа/);
  } finally {
    globalThis.fetch = original;
  }
});
