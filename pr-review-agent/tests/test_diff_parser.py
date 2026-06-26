"""Tests for the unified diff text parser."""

from pathlib import Path

import pytest

from pr_review_agent.tools.diff_parser import parse_diff

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _patch_text() -> str:
    return (FIXTURE_DIR / "sample_diff.patch").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Basic structure
# ---------------------------------------------------------------------------

def test_parse_returns_two_files():
    result = parse_diff(_patch_text())
    assert len(result) == 2


def test_modified_file_has_correct_name():
    result = parse_diff(_patch_text())
    files = [r.file for r in result]
    assert "auth/utils.py" in files


def test_added_file_has_correct_name():
    result = parse_diff(_patch_text())
    files = [r.file for r in result]
    assert "api/routes.py" in files


# ---------------------------------------------------------------------------
# Status detection
# ---------------------------------------------------------------------------

def test_modified_file_status():
    result = parse_diff(_patch_text())
    modified = next(r for r in result if r.file == "auth/utils.py")
    assert modified.status == "modified"


def test_added_file_status():
    result = parse_diff(_patch_text())
    added = next(r for r in result if r.file == "api/routes.py")
    assert added.status == "added"


# ---------------------------------------------------------------------------
# Hunk content
# ---------------------------------------------------------------------------

def test_modified_file_has_patch():
    result = parse_diff(_patch_text())
    modified = next(r for r in result if r.file == "auth/utils.py")
    assert modified.patch.strip() != ""
    assert "sha256" in modified.patch or "SHA-256" in modified.patch


def test_added_file_has_patch():
    result = parse_diff(_patch_text())
    added = next(r for r in result if r.file == "api/routes.py")
    assert added.patch.strip() != ""
    assert "register" in added.patch


def test_lines_changed_is_positive():
    result = parse_diff(_patch_text())
    for fd in result:
        assert fd.lines_changed > 0


# ---------------------------------------------------------------------------
# Source fields
# ---------------------------------------------------------------------------

def test_new_source_is_none():
    result = parse_diff(_patch_text())
    for fd in result:
        assert fd.new_source is None


def test_old_source_is_none():
    result = parse_diff(_patch_text())
    for fd in result:
        assert fd.old_source is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_diff_returns_empty_list():
    assert parse_diff("") == []


def test_deleted_file():
    patch = (
        "diff --git a/old.py b/old.py\n"
        "deleted file mode 100644\n"
        "index abc..0000000\n"
        "--- a/old.py\n"
        "+++ /dev/null\n"
        "@@ -1,3 +0,0 @@\n"
        "-def foo(): pass\n"
        "-\n"
        "-x = 1\n"
    )
    result = parse_diff(patch)
    assert len(result) == 1
    assert result[0].file == "old.py"
    assert result[0].status == "removed"


def test_binary_file():
    patch = (
        "diff --git a/logo.png b/logo.png\n"
        "index abc..def 100644\n"
        "Binary files a/logo.png and b/logo.png differ\n"
    )
    result = parse_diff(patch)
    assert len(result) == 1
    assert result[0].file == "logo.png"


def test_renamed_file():
    patch = (
        "diff --git a/old_name.py b/new_name.py\n"
        "similarity index 90%\n"
        "rename from old_name.py\n"
        "rename to new_name.py\n"
        "index abc..def 100644\n"
        "--- a/old_name.py\n"
        "+++ b/new_name.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-old = 1\n"
        "+new = 1\n"
    )
    result = parse_diff(patch)
    assert len(result) == 1
    assert result[0].file == "new_name.py"
    assert result[0].status == "renamed"


def test_multi_file_diff():
    patch = "\n".join([
        "diff --git a/a.py b/a.py",
        "--- a/a.py",
        "+++ b/a.py",
        "@@ -1 +1 @@",
        "-x = 1",
        "+x = 2",
        "diff --git a/b.py b/b.py",
        "--- a/b.py",
        "+++ b/b.py",
        "@@ -1 +1 @@",
        "-y = 1",
        "+y = 2",
        "diff --git a/c.py b/c.py",
        "--- a/c.py",
        "+++ b/c.py",
        "@@ -1 +1 @@",
        "-z = 1",
        "+z = 2",
    ])
    result = parse_diff(patch)
    assert len(result) == 3
    assert {r.file for r in result} == {"a.py", "b.py", "c.py"}
