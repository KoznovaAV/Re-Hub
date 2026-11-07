import assert from "node:assert/strict";
import { test } from "node:test";
import { callList, sample } from "./pilot-data.mjs";

test("two separate sets of 30 clients; period observations stay separate", () => {
  const a = sample("A");
  const b = sample("B");
  assert.equal(a.length, 30);
  assert.equal(b.length, 30);
  assert.equal(new Set([...a, ...b].map(row => row.client)).size, 60);
  assert.deepEqual(a[0].periods.map(row => row.observed), [true, false]);
});

test("exclusion, missing observation and previous calls are respected", () => {
  const fixture = (client, unsent, observed, contacted, excluded = false) => ({
    client, excluded, periods: [{period:"2026Q3", unsent, observed, contacted}],
  });
  const rows = [fixture("match", 8, true, false), fixture("low", 7, true, false),
    fixture("no observation", 9, false, false), fixture("called", 9, true, true),
    fixture("excluded", 9, true, false, true)];
  assert.deepEqual(callList(rows, "2026Q3", 8).map(row => row.client), ["match"]);
});
