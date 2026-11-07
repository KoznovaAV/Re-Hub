import { readFile } from "node:fs/promises";
import { createServer } from "node:http";

const html = await readFile(new URL("./index.html", import.meta.url));
const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8080";
const routes = { "/api/health": "/health", "/api/probe": "/api/probe" };

function json(response, status, body) {
  response.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store" });
  response.end(JSON.stringify(body));
}

createServer(async (request, response) => {
  if (request.method !== "GET") {
    response.setHeader("Allow", "GET");
    return json(response, 405, { error: "method_not_allowed" });
  }
  if (request.url === "/health") {
    return json(response, 200, { status: "ok", service: "frontend" });
  }
  if (request.url === "/") {
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    return response.end(html);
  }
  if (!Object.hasOwn(routes, request.url)) {
    return json(response, 404, { error: "not_found" });
  }
  try {
    const upstream = await fetch(new URL(routes[request.url], backend), {
      signal: AbortSignal.timeout(3500),
      redirect: "error",
    });
    json(response, upstream.status, await upstream.json());
  } catch {
    json(response, 502, { error: "backend_unavailable" });
  }
}).listen(Number(process.env.PORT ?? 3000), process.env.WEB_HOST ?? "127.0.0.1");
