"""Repeatable A-14 smoke: upload clients and two snapshots through the real HTTP API.

Generate data first (parser-service):
  python -m app.generate_test_data --out /tmp/h00 --size 4000
Then, with Compose running:
  python scripts/tests/import_load.py --base http://127.0.0.1:8080 \
    --clients /tmp/h00/clients.xlsx --clients-context /tmp/h00/clients.context.json \
    --snapshot /tmp/h00/snapshot_1.xlsx:/tmp/h00/snapshot_1.context.json \
    --snapshot /tmp/h00/snapshot_2.xlsx:/tmp/h00/snapshot_2.context.json
"""
import argparse
import json
import os
import time
import urllib.error
import urllib.request
import uuid


def multipart(fields, file_path):
    boundary = "----rehub-load-" + uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n").encode("utf-8"))
    payload = open(file_path, "rb").read()
    parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{os.path.basename(file_path)}\"\r\nContent-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n").encode("ascii"))
    parts.append(payload)
    parts.append(f"\r\n--{boundary}--\r\n".encode("ascii"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def upload(base, endpoint, file_path, context_path, headers):
    context = open(context_path, encoding="utf-8").read()
    body, content_type = multipart({"context": context}, file_path)
    request = urllib.request.Request(base.rstrip("/") + endpoint, data=body, method="POST", headers={**headers, "Content-Type": content_type})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.load(response)
            status = response.status
    except urllib.error.HTTPError as error:
        payload = {"error": error.read().decode("utf-8", "replace")}
        status = error.code
    return {"file": os.path.basename(file_path), "seconds": round(time.perf_counter() - started, 3), "status": status, "response": payload}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8080")
    parser.add_argument("--clients", required=True)
    parser.add_argument("--clients-context", required=True)
    parser.add_argument("--snapshot", action="append", default=[], help="XLSX:CONTEXT; may be repeated")
    args = parser.parse_args()
    headers = {"X-Role": "admin", "X-User-Id": "00000000-0000-0000-0000-000000000001"}
    results = [upload(args.base, "/api/v1/clients/import", args.clients, args.clients_context, headers)]
    for pair in args.snapshot:
        file_path, context_path = pair.rsplit(":", 1)
        results.append(upload(args.base, "/api/v1/slices", file_path, context_path, headers))
    print(json.dumps({"base": args.base, "uploads": results}, ensure_ascii=False, indent=2))
    if any(item["status"] not in (200, 201) for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
