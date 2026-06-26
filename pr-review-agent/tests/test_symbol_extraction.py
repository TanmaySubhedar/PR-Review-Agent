"""Unit tests for symbol extraction and diff hunk parsing."""

from pathlib import Path

import pytest

from pr_review_agent.graph.nodes.symbols import extract_symbols, parse_hunks
from pr_review_agent.models.domain import DiffHunk
from pr_review_agent.tools.treesitter import detect_language

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sample_repo_files"


# ---------------------------------------------------------------------------
# detect_language
# ---------------------------------------------------------------------------

def test_detect_language_python():
    assert detect_language("auth/utils.py") == "python"


def test_detect_language_typescript():
    assert detect_language("ui/components.ts") == "typescript"


def test_detect_language_unsupported():
    assert detect_language("file.rb") is None


# ---------------------------------------------------------------------------
# extract_symbols — Python
# ---------------------------------------------------------------------------

def test_extract_symbols_python_returns_list():
    source = (FIXTURE_DIR / "auth" / "utils.py").read_bytes()
    symbols = extract_symbols("auth/utils.py", source)
    assert isinstance(symbols, list)
    assert len(symbols) > 0


def test_extract_symbols_python_has_function_type():
    source = (FIXTURE_DIR / "auth" / "utils.py").read_bytes()
    symbols = extract_symbols("auth/utils.py", source)
    types = {s.symbol_type for s in symbols}
    assert "function" in types


def test_extract_symbols_python_hash_password_present():
    source = (FIXTURE_DIR / "auth" / "utils.py").read_bytes()
    symbols = extract_symbols("auth/utils.py", source)
    names = [s.name for s in symbols]
    assert "hash_password" in names


def test_extract_symbols_python_verify_password_present():
    source = (FIXTURE_DIR / "auth" / "utils.py").read_bytes()
    symbols = extract_symbols("auth/utils.py", source)
    names = [s.name for s in symbols]
    assert "verify_password" in names


def test_extract_symbols_python_start_line_positive():
    source = (FIXTURE_DIR / "auth" / "utils.py").read_bytes()
    symbols = extract_symbols("auth/utils.py", source)
    for sym in symbols:
        assert sym.start_line >= 1


def test_extract_symbols_python_file_field_set():
    source = (FIXTURE_DIR / "auth" / "utils.py").read_bytes()
    symbols = extract_symbols("auth/utils.py", source)
    for sym in symbols:
        assert sym.file == "auth/utils.py"


def test_extract_symbols_python_end_line_gte_start():
    source = (FIXTURE_DIR / "auth" / "utils.py").read_bytes()
    symbols = extract_symbols("auth/utils.py", source)
    for sym in symbols:
        assert sym.end_line >= sym.start_line


# ---------------------------------------------------------------------------
# extract_symbols — Python api/routes.py (async functions + class with methods)
# ---------------------------------------------------------------------------

def test_extract_symbols_routes_py_async_function():
    source = (FIXTURE_DIR / "api" / "routes.py").read_bytes()
    symbols = extract_symbols("api/routes.py", source)
    async_funcs = [s for s in symbols if s.is_async]
    assert len(async_funcs) >= 1


def test_extract_symbols_routes_py_class_present():
    source = (FIXTURE_DIR / "api" / "routes.py").read_bytes()
    symbols = extract_symbols("api/routes.py", source)
    classes = [s for s in symbols if s.symbol_type == "class"]
    assert len(classes) >= 1


def test_extract_symbols_routes_py_methods_present():
    source = (FIXTURE_DIR / "api" / "routes.py").read_bytes()
    symbols = extract_symbols("api/routes.py", source)
    methods = [s for s in symbols if s.symbol_type == "method"]
    names = [m.name for m in methods]
    assert "register" in names
    assert "login" in names


def test_extract_symbols_routes_py_get_user_function():
    source = (FIXTURE_DIR / "api" / "routes.py").read_bytes()
    symbols = extract_symbols("api/routes.py", source)
    names = [s.name for s in symbols]
    assert "get_user" in names


# ---------------------------------------------------------------------------
# extract_symbols — TypeScript
# ---------------------------------------------------------------------------

def test_extract_symbols_typescript_returns_list():
    source = (FIXTURE_DIR / "ui" / "components.ts").read_bytes()
    symbols = extract_symbols("ui/components.ts", source)
    assert isinstance(symbols, list)
    assert len(symbols) > 0


def test_extract_symbols_typescript_render_user():
    source = (FIXTURE_DIR / "ui" / "components.ts").read_bytes()
    symbols = extract_symbols("ui/components.ts", source)
    names = [s.name for s in symbols]
    assert "renderUser" in names


def test_extract_symbols_typescript_fetch_user():
    source = (FIXTURE_DIR / "ui" / "components.ts").read_bytes()
    symbols = extract_symbols("ui/components.ts", source)
    names = [s.name for s in symbols]
    assert "fetchUser" in names


def test_extract_symbols_typescript_function_type():
    source = (FIXTURE_DIR / "ui" / "components.ts").read_bytes()
    symbols = extract_symbols("ui/components.ts", source)
    types = {s.symbol_type for s in symbols}
    assert "function" in types


# ---------------------------------------------------------------------------
# extract_symbols — edge cases
# ---------------------------------------------------------------------------

def test_extract_symbols_empty_source_returns_empty():
    result = extract_symbols("auth/utils.py", b"")
    assert result == []


def test_extract_symbols_unsupported_extension_returns_empty():
    result = extract_symbols("file.rb", b"def foo\n  42\nend\n")
    assert result == []


def test_extract_symbols_unsupported_extension_any_content():
    result = extract_symbols("script.sh", b"#!/bin/bash\necho hello\n")
    assert result == []


# ---------------------------------------------------------------------------
# parse_hunks
# ---------------------------------------------------------------------------

_SIMPLE_PATCH = (
    "@@ -1,5 +1,7 @@\n"
    " import hashlib\n"
    "+import secrets\n"
    "\n"
    " def hash_password(password: str) -> str:\n"
    "-    return hashlib.md5(password.encode()).hexdigest()\n"
    "+    salt = secrets.token_hex(16)\n"
    "+    return salt\n"
)


def test_parse_hunks_returns_list():
    result = parse_hunks("auth/utils.py", _SIMPLE_PATCH)
    assert isinstance(result, list)


def test_parse_hunks_non_empty_for_valid_patch():
    result = parse_hunks("auth/utils.py", _SIMPLE_PATCH)
    assert len(result) >= 1


def test_parse_hunks_returns_diff_hunk_objects():
    result = parse_hunks("auth/utils.py", _SIMPLE_PATCH)
    for hunk in result:
        assert isinstance(hunk, DiffHunk)


def test_parse_hunks_file_field():
    result = parse_hunks("auth/utils.py", _SIMPLE_PATCH)
    for hunk in result:
        assert hunk.file == "auth/utils.py"


def test_parse_hunks_header_contains_at():
    result = parse_hunks("auth/utils.py", _SIMPLE_PATCH)
    for hunk in result:
        assert "@@" in hunk.header


def test_parse_hunks_empty_patch_returns_empty():
    result = parse_hunks("auth/utils.py", "")
    assert result == []


def test_parse_hunks_multi_hunk_patch():
    patch = (
        "@@ -1,3 +1,4 @@\n"
        " line1\n"
        "+added1\n"
        " line2\n"
        " line3\n"
        "@@ -10,3 +11,4 @@\n"
        " line10\n"
        "+added2\n"
        " line11\n"
        " line12\n"
    )
    result = parse_hunks("some/file.py", patch)
    assert len(result) == 2


def test_parse_hunks_lines_contain_diff_markers():
    result = parse_hunks("auth/utils.py", _SIMPLE_PATCH)
    all_lines = [line for hunk in result for line in hunk.lines]
    # At least one added line
    assert any(line.startswith("+") for line in all_lines)
    # At least one removed line
    assert any(line.startswith("-") for line in all_lines)


def test_parse_hunks_new_start_from_sample_diff():
    """Verify parse_hunks round-trips the sample_diff.patch hunk header."""
    sample_patch = Path(__file__).parent / "fixtures" / "sample_diff.patch"
    patch_text = sample_patch.read_text(encoding="utf-8")
    # The sample diff touches auth/utils.py
    auth_patch_lines = []
    in_file = False
    for line in patch_text.splitlines():
        if line.startswith("diff --git") and "auth/utils.py" in line:
            in_file = True
        elif line.startswith("diff --git") and in_file:
            break
        if in_file:
            auth_patch_lines.append(line)
    auth_patch = "\n".join(auth_patch_lines)
    if auth_patch:
        hunks = parse_hunks("auth/utils.py", auth_patch)
        assert len(hunks) >= 1
