import { readFile } from "node:fs/promises";
import { createServer } from "node:http";

const html = await readFile(new URL("./index.html", import.meta.url));
const pilot = await readFile(new URL("./pilot.html", import.meta.url));
const pilotData = await readFile(new URL("./pilot-data.mjs", import.meta.url));
const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8080";
const aiDemo = process.env.REHUB_AI_DEMO === "1";
const aiPage = aiDemo && await readFile(new URL("./ai-demo.html", import.meta.url));
const routes = { "/api/health": "/health", "/api/probe": "/api/probe" };

function json(response, status, body) {
  response.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store" });
  response.end(JSON.stringify(body));
}

createServer(async (request, response) => {
  if (aiDemo && request.url === "/api/ai/query" && request.method === "POST") {
    if (request.headers["content-type"]?.split(";")[0].trim().toLowerCase() !== "application/json") {
      return json(response, 415, { error: "expected_json" });
    }
    try {
      const chunks = [];
      let size = 0;
      for await (const chunk of request.iterator({ destroyOnReturn: false })) {
        size += chunk.length;
        if (size > 32768) {
          request.resume();
          return json(response, 413, { error: "body_too_large" });
        }
        chunks.push(chunk);
      }
      const upstream = await fetch(new URL("/ai/query", backend), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: Buffer.concat(chunks),
        signal: AbortSignal.timeout(36_000),
        redirect: "error",
      });
      return json(response, upstream.status, await upstream.json());
    } catch {
      return json(response, 502, { error: "backend_unavailable" });
    }
  }
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
  if (aiDemo && request.url === "/ai-demo") {
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    return response.end(aiPage);
  }
  if (request.url === "/pilot" || request.url === "/pilot-data.mjs") {
    const page = request.url === "/pilot";
    response.writeHead(200, { "Content-Type": page ? "text/html; charset=utf-8" : "text/javascript; charset=utf-8" });
    return response.end(page ? pilot : pilotData);
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
