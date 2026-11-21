import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL(".", import.meta.url));
const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8080";
const routes = { "/api/health": "/health", "/api/probe": "/api/probe" };
const staticPrefixes = ["/main.js", "/App.js", "/components/", "/views/", "/composables/", "/mock/", "/styles/", "/vendor/"];
const mime = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
};

function json(response, status, body) {
  response.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store" });
  response.end(JSON.stringify(body));
}

function staticPath(pathname) {
  const path = resolve(root, `.${pathname}`);
  const prefix = root.endsWith("\\") || root.endsWith("/") ? root : `${root}/`;
  return path.startsWith(prefix) ? path : null;
}

async function sendFile(response, path) {
  try {
    const body = await readFile(path);
    response.writeHead(200, {
      "Content-Type": mime[extname(path)] ?? "application/octet-stream",
      "Cache-Control": "no-store",
    });
    response.end(body);
  } catch {
    json(response, 404, { error: "not_found" });
  }
}

createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", "http://localhost");
  const pathname = url.pathname;

  if (request.method === "GET" && pathname === "/health") {
    return json(response, 200, { status: "ok", service: "frontend" });
  }

  if (request.method === "GET" && pathname === "/") {
    return sendFile(response, resolve(root, "index.html"));
  }

  if (request.method === "GET" && pathname === "/pilot") {
    return sendFile(response, resolve(root, "pilot.html"));
  }

  if (request.method === "GET" && pathname === "/pilot-data.mjs") {
    return sendFile(response, resolve(root, "pilot-data.mjs"));
  }

  if (request.method === "GET" && staticPrefixes.some((prefix) => pathname.startsWith(prefix))) {
    const path = staticPath(pathname);
    if (!path) return json(response, 403, { error: "forbidden" });
    return sendFile(response, path);
  }

  if (pathname.startsWith("/api/")) {
    if (request.method !== "GET") {
      response.setHeader("Allow", "GET");
      return json(response, 405, { error: "method_not_allowed" });
    }
    if (!Object.hasOwn(routes, pathname)) return json(response, 404, { error: "not_found" });
    try {
      const upstream = await fetch(new URL(routes[pathname], backend), {
        signal: AbortSignal.timeout(3500),
        redirect: "error",
      });
      json(response, upstream.status, await upstream.json());
    } catch {
      json(response, 502, { error: "backend_unavailable" });
    }
    return;
  }

  json(response, 404, { error: "not_found" });
}).listen(Number(process.env.PORT ?? 3000), process.env.WEB_HOST ?? "127.0.0.1");
