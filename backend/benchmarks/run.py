import argparse
import http.client
import json
import math
import os
import platform
from pathlib import Path
import statistics
import subprocess
import tempfile
import time


ROUTERS = ("net/http", "chi", "gin")
MODES = ("route", "probe")
EXPECTED = {"schema_version": 1, "request_id": "skeleton", "status": "ok"}
HERE = Path(__file__).resolve().parent


def stop_server(server):
    server.kill()
    if server.returncode is not None:
        return None
    if platform.system() == "Linux":
        _, status, usage = os.wait4(server.pid, 0)
        server.returncode = os.waitstatus_to_exitcode(status)
        return usage.ru_maxrss or None
    server.wait(timeout=5)
    return None


def trial(binary, router, mode, python_url, warmup, requests, env):
    with subprocess.Popen(
        [binary, "-router", router, "-mode", mode, "-python", python_url],
        env=env, stdout=subprocess.PIPE, text=True,
    ) as server:
        try:
            port = int(server.stdout.readline())
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            samples = []
            errors = 0
            started = 0
            try:
                for i in range(warmup + requests):
                    tick = time.perf_counter_ns()
                    if i == warmup:
                        started = tick
                    try:
                        connection.request("GET", "/api/probe")
                        response = connection.getresponse()
                        valid = (
                            response.status == 200
                            and response.headers.get_content_type() == "application/json"
                            and json.loads(response.read()) == EXPECTED
                        )
                        if not valid:
                            connection.close()
                    except (OSError, ValueError, http.client.HTTPException):
                        connection.close()
                        valid = False
                    if i < warmup and not valid:
                        raise RuntimeError(f"warmup failed for {router}/{mode}")
                    if i >= warmup:
                        errors += not valid
                        samples.append((time.perf_counter_ns() - tick) / 1000)
                elapsed = (time.perf_counter_ns() - started) / 1_000_000_000
            finally:
                connection.close()
            samples.sort()
            result = {
                "router": router, "mode": mode, "requests": requests,
                "errors": errors, "p50_us": round(samples[math.ceil(requests * .50) - 1], 3),
                "p95_us": round(samples[math.ceil(requests * .95) - 1], 3),
                "requests_per_second": round((requests - errors) / elapsed, 2),
            }
        finally:
            rss = stop_server(server)
        return {**result, "peak_rss_kib": rss}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-url", default="http://127.0.0.1:8001")
    args = parser.parse_args()
    rounds, warmup, requests = 5, 250, 2000
    env = dict(os.environ, GOMAXPROCS="2")
    results = []
    with tempfile.TemporaryDirectory(prefix="rehub-router-") as temp:
        binary = str(Path(temp) / "router")
        subprocess.run(
            ["go", "build", "-mod=readonly", "-buildvcs=false", "-trimpath", "-o", binary, "."],
            cwd=HERE, check=True, env=env,
        )
        for mode in MODES:
            for index in range(rounds):
                for router in ROUTERS[index % len(ROUTERS):] + ROUTERS[:index % len(ROUTERS)]:
                    results.append({"round": index + 1, **trial(binary, router, mode, args.python_url, warmup, requests, env)})

    summary = {}
    for mode in MODES:
        summary[mode] = {}
        for router in ROUTERS:
            runs = [r for r in results if r["router"] == router and r["mode"] == mode]
            entry = {"errors": sum(r["errors"] for r in runs), "requests": rounds * requests}
            for key in ("p50_us", "p95_us", "requests_per_second", "peak_rss_kib"):
                values = [r[key] for r in runs if r[key] is not None]
                entry[key] = statistics.median(values) if values else None
            summary[mode][router] = entry

    quota_path = Path("/sys/fs/cgroup/cpu.max")
    print(json.dumps({
        "environment": {
            "os": platform.platform(), "machine": platform.machine(),
            "go": subprocess.check_output(["go", "version"], text=True, env=env).strip(),
            "python": platform.python_version(), "gomaxprocs": 2,
            "cpu_quota": quota_path.read_text().strip() if quota_path.is_file() else None,
        },
        "rounds": rounds, "warmup_per_trial": warmup, "requests_per_trial": requests,
        "summary": summary, "trials": results,
    }, indent=2))


if __name__ == "__main__":
    main()
