import assert from "node:assert/strict";

const base = process.env.SMOKE_URL ?? "http://127.0.0.1:3000";
const expectUnavailable = process.argv.includes("--python-down") || process.env.SMOKE_PYTHON_DOWN === "1";

async function get(path, expectedStatus = 200) {
  const response = await fetch(new URL(path, base), { signal: AbortSignal.timeout(5000) });
  assert.equal(response.status, expectedStatus, path);
  return response;
}

assert.match(await (await get("/")).text(), /Re:Hub/);
assert.deepEqual(await (await get("/health")).json(), { status: "ok", service: "frontend" });
assert.deepEqual(await (await get("/api/health")).json(), { status: "ok", service: "backend" });

if (expectUnavailable) {
  assert.deepEqual(await (await get("/api/probe", 503)).json(), { error: "python_unavailable" });
  console.log("OK: Go доступен, отказ Python обработан.");
} else {
  for (let i = 0; i < 10; i += 1) {
    assert.deepEqual(await (await get("/api/probe")).json(), {
      schema_version: 1,
      request_id: "skeleton",
      status: "ok",
    });
  }
  console.log("OK: интерфейс и Go доступны, JSON Go → Python: 10/10.");
}
