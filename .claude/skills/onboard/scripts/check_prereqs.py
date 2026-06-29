#!/usr/bin/env python3
"""
check_prereqs.py — Verify all system prerequisites for PR-Review-Agent.
Checks Docker daemon, Docker Compose, Git, and Node.js.
Exits 0 if all pass, 1 if any fail.
"""

import subprocess
import sys
import re

PASS = "[OK]  "
FAIL = "[FAIL]"
WARN = "[WARN]"


def run(cmd):
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return 1, "", "command not found"
    except subprocess.TimeoutExpired:
        return 1, "", "timed out"


def check_docker_installed():
    code, out, err = run(["docker", "--version"])
    if code != 0:
        return False, f"not found — {err}"
    return True, out


def check_docker_running():
    code, out, err = run(["docker", "info"])
    if code != 0:
        return False, "Docker daemon is not running — start Docker Desktop"
    return True, "daemon is running"


def check_docker_compose():
    code, out, err = run(["docker", "compose", "version"])
    if code != 0:
        code, out, err = run(["docker-compose", "--version"])
        if code != 0:
            return False, "docker compose plugin not found"
        return True, out + " (standalone)"
    return True, out


def check_git():
    code, out, err = run(["git", "--version"])
    if code != 0:
        return False, "not found — install from https://git-scm.com"
    return True, out


def check_node():
    code, out, err = run(["node", "--version"])
    if code != 0:
        return False, "not found — install Node 18+ from https://nodejs.org"
    version_str = out.lstrip("v")
    try:
        major = int(version_str.split(".")[0])
    except ValueError:
        return False, f"could not parse version: {out}"
    if major < 18:
        return False, f"version {out} is too old — Node 18+ required"
    return True, out


def check_npx():
    import shutil
    # On Windows npx ships as npx.cmd which subprocess won't find without shell=True
    if shutil.which("npx") or shutil.which("npx.cmd"):
        try:
            result = subprocess.run(
                "npx --version", shell=True, capture_output=True, text=True, timeout=10
            )
            version = result.stdout.strip() or result.stderr.strip()
            return True, f"npx {version}"
        except Exception:
            return True, "found"
    return False, "npx not found — install Node 18+ from https://nodejs.org"


def main():
    checks = [
        ("Docker installed", check_docker_installed),
        ("Docker daemon running", check_docker_running),
        ("Docker Compose", check_docker_compose),
        ("Git", check_git),
        ("Node.js (>=18)", check_node),
        ("npx (for smee client)", check_npx),
    ]

    results = []
    for label, fn in checks:
        ok, detail = fn()
        results.append((ok, label, detail))

    print("\nPrerequisite Check")
    print("=" * 50)
    all_ok = True
    for ok, label, detail in results:
        icon = PASS if ok else FAIL
        print(f"  {icon}  {label}: {detail}")
        if not ok:
            all_ok = False

    print()
    if all_ok:
        print("All prerequisites satisfied.")
    else:
        print("Fix the failing checks above, then re-run this script.")
    print()

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
