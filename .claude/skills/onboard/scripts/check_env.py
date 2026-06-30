#!/usr/bin/env python3
"""
check_env.py — Validate .env at the repo root without reading secret values.
Checks that required fields are present, non-empty, and not placeholder strings.
Never prints or logs any credential value.
Exits 0 if valid, 1 if any issue found.
"""

import sys
from pathlib import Path

PASS = "[OK]  "
FAIL = "[FAIL]"
WARN = "[WARN]"

# Values that indicate the field was never filled in (copied from .env.example unchanged)
PLACEHOLDER_PATTERNS = {
    "AZURE_OPENAI_ENDPOINT": "https://your-resource.openai.azure.com/",
}

# Fields that must be non-empty for the app to work
REQUIRED_FIELDS = [
    "GITHUB_TOKEN",
]

# At least one of these LLM path groups must be fully filled
LLM_PATHS = [
    {
        "name": "Azure OpenAI",
        "fields": ["AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"],
    },
    {
        "name": "Direct OpenAI",
        "fields": ["OPENAI_API_KEY"],
    },
]


def parse_env(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict. Skips comments and blank lines.
    Values are stored as-is; callers must not print them."""
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        env[key.strip()] = value.strip()
    return env


def check_field_present(env: dict, key: str) -> tuple[bool, str]:
    if key not in env:
        return False, f"{key} is missing from .env"
    if not env[key]:
        return False, f"{key} is present but empty"
    if key in PLACEHOLDER_PATTERNS and env[key] == PLACEHOLDER_PATTERNS[key]:
        return False, f"{key} still has the placeholder value from .env.example"
    return True, f"{key} is set"


def main():
    repo_root = Path(__file__).resolve().parents[4]
    env_path = repo_root / ".env"

    print("\n.env Validation")
    print("=" * 50)

    if not env_path.exists():
        print(f"  {FAIL}  .env not found at {env_path}")
        print(
            "\n  Copy .env.example to .env first:\n"
            "    Windows:  Copy-Item .env.example .env\n"
            "    Unix:     cp .env.example .env\n"
            "  Then fill in the required fields.\n"
        )
        sys.exit(1)

    print(f"  {PASS}  .env found at {env_path}")

    env = parse_env(env_path)
    all_ok = True

    # Check required GitHub fields
    print("\n  GitHub credentials")
    for key in REQUIRED_FIELDS:
        ok, msg = check_field_present(env, key)
        print(f"    {PASS if ok else FAIL}  {msg}")
        if not ok:
            all_ok = False

    # Check LLM configuration — at least one path must be fully configured
    print("\n  LLM credentials (need Azure OpenAI OR direct OpenAI)")
    llm_ok = False
    for path in LLM_PATHS:
        path_ok = True
        path_results = []
        for key in path["fields"]:
            ok, msg = check_field_present(env, key)
            path_results.append((ok, msg))
            if not ok:
                path_ok = False
        if path_ok:
            for ok, msg in path_results:
                print(f"    {PASS}  {msg}")
            print(f"    {PASS}  {path['name']} path is fully configured")
            llm_ok = True
            break
        else:
            # Show what's missing for this path
            for ok, msg in path_results:
                if not ok:
                    print(f"    {WARN}  [{path['name']}] {msg}")

    if not llm_ok:
        print(
            f"\n    {FAIL}  No LLM path is fully configured.\n"
            "         Fill in AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT\n"
            "         OR uncomment and fill in OPENAI_API_KEY."
        )
        all_ok = False

    print()
    if all_ok:
        print(f"  {PASS}  .env looks good — all required fields are set.")
    else:
        print(f"  {FAIL}  Fix the issues above, then re-run this script.")
    print()

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
