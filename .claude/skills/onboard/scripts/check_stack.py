#!/usr/bin/env python3
"""
check_stack.py -Verify the Docker Compose stack is up and reachable.
Checks that both services are running and their HTTP endpoints respond correctly.
Exits 0 if healthy, 1 if anything is down.
"""

import subprocess
import sys
import urllib.request
import urllib.error
import json
from pathlib import Path

PASS = "[OK]  "
FAIL = "[FAIL]"
WARN = "[WARN]"

BACKEND_HEALTH_URL = "http://localhost:8001/health"
FRONTEND_URL = "http://localhost:5173"
COMPOSE_FILE = str(Path(__file__).resolve().parents[4] / "deployment" / "docker-compose.yml")


def get_compose_services() -> list[dict]:
    """Return list of service status dicts from docker compose ps --format json."""
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", COMPOSE_FILE, "ps", "--format", "json"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return []
        lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
        services = []
        for line in lines:
            try:
                services.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return services
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def check_http(url: str, expect_json_key: str | None = None) -> tuple[bool, str]:
    try:
        req = urllib.request.urlopen(url, timeout=5)
        body = req.read().decode("utf-8")
        if expect_json_key:
            data = json.loads(body)
            if expect_json_key not in data:
                return False, f"response missing '{expect_json_key}' key"
            return True, f"HTTP {req.status} -{expect_json_key}={data[expect_json_key]!r}"
        return True, f"HTTP {req.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, f"connection refused -is the container running? ({e.reason})"
    except json.JSONDecodeError:
        return False, "invalid JSON in response"
    except Exception as e:
        return False, str(e)


def main():
    print("\nDocker Stack Health Check")
    print("=" * 50)

    # --- Container status ---
    print("\n  Container status")
    services = get_compose_services()

    expected = {"backend", "frontend"}
    found = {}
    for svc in services:
        name = svc.get("Service") or svc.get("Name", "")
        state = svc.get("State", "unknown")
        status = svc.get("Status", "")
        found[name] = (state, status)

    all_ok = True
    for name in sorted(expected):
        if name not in found:
            print(f"    {FAIL}  {name}: not found -run: docker compose -f deployment/docker-compose.yml up -d")
            all_ok = False
        else:
            state, status = found[name]
            running = state.lower() in ("running", "up")
            icon = PASS if running else FAIL
            print(f"    {icon}  {name}: {state} ({status})")
            if not running:
                all_ok = False

    # --- Endpoint checks ---
    print("\n  Endpoint checks")

    ok, msg = check_http(BACKEND_HEALTH_URL, expect_json_key="status")
    print(f"    {PASS if ok else FAIL}  Backend  {BACKEND_HEALTH_URL}  ->  {msg}")
    if not ok:
        all_ok = False

    ok, msg = check_http(FRONTEND_URL)
    print(f"    {PASS if ok else FAIL}  Frontend {FRONTEND_URL}  ->  {msg}")
    if not ok:
        all_ok = False

    print()
    if all_ok:
        print(f"  {PASS}  Stack is healthy. Dashboard: {FRONTEND_URL}  |  API docs: http://localhost:8001/docs")
    else:
        print(f"  {FAIL}  Some services are not healthy -check the container logs:")
        print(f"         docker compose -f deployment/docker-compose.yml logs --tail=50")
    print()

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
