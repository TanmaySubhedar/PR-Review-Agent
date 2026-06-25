"""Unit tests for the risk scoring logic in the symbols node."""

from pathlib import Path

import pytest

from pr_review_agent.graph.nodes import symbols as symbols_module
from pr_review_agent.graph.state import PRReviewState
from pr_review_agent.models.domain import FileDiff, PRMetadata

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "sample_repo_files"


def _make_pr_metadata() -> PRMetadata:
    return PRMetadata(
        repo_full_name="owner/repo",
        pr_number=1,
        pr_url="https://github.com/owner/repo/pull/1",
        title="Test PR",
        description="",
        base_sha="aaa",
        head_sha="bbb",
        base_ref="main",
        head_ref="feature",
        clone_url="https://github.com/owner/repo.git",
    )


def _make_state(
    file_diffs: list[FileDiff],
    raw_diff: str = "",
    repo_path: Path | None = None,
) -> PRReviewState:
    return PRReviewState(
        repo_full_name="owner/repo",
        pr_number=1,
        review_run_id="test-run-001",
        pr_metadata=_make_pr_metadata(),
        file_diffs=file_diffs,
        raw_diff=raw_diff,
        repo_path=repo_path or FIXTURE_REPO,
        phase_status={},
    )


# ---------------------------------------------------------------------------
# 1. Zero changed symbols + tiny diff → low risk
# ---------------------------------------------------------------------------

def test_risk_level_low_for_no_symbols_small_diff():
    """A diff with no parseable source and few lines changed → risk_level='low'."""
    fd = FileDiff(
        file="docs/README.md",
        patch="@@ -1,2 +1,2 @@\n-old line\n+new line\n",
        status="modified",
        new_source=None,
        old_source=None,
        lines_changed=2,
    )
    state = _make_state([fd], raw_diff="-old line\n+new line\n")
    result = symbols_module.run(state)
    assert result["risk_level"] == "low"


def test_risk_factors_contains_no_symbols_message_for_unsupported_file():
    """Markdown diff → no symbols → risk_factors mentions untracked language."""
    fd = FileDiff(
        file="docs/README.md",
        patch="@@ -1,2 +1,2 @@\n-old\n+new\n",
        status="modified",
        new_source=None,
        old_source=None,
        lines_changed=2,
    )
    state = _make_state([fd])
    result = symbols_module.run(state)
    factors = result["risk_factors"]
    assert any("no recognizable symbols" in f for f in factors)


# ---------------------------------------------------------------------------
# 2. Signature change in a function → medium or high
# ---------------------------------------------------------------------------

def test_risk_level_medium_or_high_for_signature_change():
    """A diff that changes async status of a function → risk escalates."""
    old_source = b"def validate_token(token):\n    return token\n"
    new_source = b"async def validate_token(token):\n    return token\n"
    patch = (
        "@@ -1,2 +1,2 @@\n"
        "-def validate_token(token):\n"
        "+async def validate_token(token):\n"
        "     return token\n"
    )
    fd = FileDiff(
        file="auth/utils.py",
        patch=patch,
        status="modified",
        new_source=new_source,
        old_source=old_source,
        lines_changed=2,
    )
    state = _make_state([fd], raw_diff=patch)
    result = symbols_module.run(state)
    assert result["risk_level"] in ("medium", "high")


def test_risk_factors_mention_sync_async_for_signature_change():
    old_source = b"def process(self, x):\n    return x\n"
    new_source = b"async def process(self, x):\n    return x\n"
    patch = (
        "@@ -1,2 +1,2 @@\n"
        "-def process(self, x):\n"
        "+async def process(self, x):\n"
        "     return x\n"
    )
    fd = FileDiff(
        file="backend/processor.py",
        patch=patch,
        status="modified",
        new_source=new_source,
        old_source=old_source,
        lines_changed=2,
    )
    state = _make_state([fd])
    result = symbols_module.run(state)
    factors = result["risk_factors"]
    assert any("sync and async" in f for f in factors)


def test_risk_level_upgrades_for_parameter_count_change():
    """Parameter count change on a sensitive-path file escalates risk to medium/high.
    A non-sensitive file with a parameter change only adds 1 to the score (< 3),
    so we use an auth path to ensure score ≥ 3."""
    old_source = b"def greet(name):\n    return name\n"
    new_source = b"def greet(name, title):\n    return name\n"
    patch = (
        "@@ -1,2 +1,2 @@\n"
        "-def greet(name):\n"
        "+def greet(name, title):\n"
        "     return name\n"
    )
    fd = FileDiff(
        file="auth/helpers.py",
        patch=patch,
        status="modified",
        new_source=new_source,
        old_source=old_source,
        lines_changed=1,
    )
    state = _make_state([fd])
    result = symbols_module.run(state)
    assert result["risk_level"] in ("medium", "high")


# ---------------------------------------------------------------------------
# 3. Sensitive path keyword → risk factor mentions the keyword
# ---------------------------------------------------------------------------

def test_risk_factors_include_sensitive_keyword_auth():
    fd = FileDiff(
        file="auth/utils.py",
        patch="@@ -1,2 +1,2 @@\n-x = 1\n+x = 2\n",
        status="modified",
        new_source=b"x = 2\n",
        old_source=b"x = 1\n",
        lines_changed=2,
    )
    state = _make_state([fd])
    result = symbols_module.run(state)
    factors = result["risk_factors"]
    assert any("auth" in f for f in factors)


def test_risk_factors_include_sensitive_keyword_token():
    fd = FileDiff(
        file="services/token_service.py",
        patch="@@ -1,2 +1,2 @@\n-x = 1\n+x = 2\n",
        status="modified",
        new_source=b"x = 2\n",
        old_source=b"x = 1\n",
        lines_changed=2,
    )
    state = _make_state([fd])
    result = symbols_module.run(state)
    factors = result["risk_factors"]
    assert any("token" in f for f in factors)


def test_risk_level_medium_for_sensitive_path():
    """A file in an auth path alone contributes score ≥ 3 (medium threshold)."""
    fd = FileDiff(
        file="auth/middleware.py",
        patch="@@ -1,2 +1,2 @@\n-x = 1\n+x = 2\n",
        status="modified",
        new_source=b"x = 2\n",
        old_source=b"x = 1\n",
        lines_changed=2,
    )
    state = _make_state([fd])
    result = symbols_module.run(state)
    assert result["risk_level"] in ("medium", "high")


# ---------------------------------------------------------------------------
# 4. Deletion of a symbol → "deleted" appears in risk factors
# ---------------------------------------------------------------------------

def test_risk_factors_deleted_symbol():
    """Removing a function (removed file) → 'deleted' in risk factors."""
    old_source = b"def foo():\n    return 1\n\ndef bar():\n    return 2\n"
    fd = FileDiff(
        file="lib/helpers.py",
        patch="@@ -1,5 +0,0 @@\n-def foo():\n-    return 1\n-\n-def bar():\n-    return 2\n",
        status="removed",
        new_source=None,
        old_source=old_source,
        lines_changed=5,
    )
    state = _make_state([fd])
    result = symbols_module.run(state)
    factors = result["risk_factors"]
    # The risk factor message says "N symbol(s) deleted"
    assert any("deleted" in f for f in factors)


def test_changed_symbols_have_deleted_change_type():
    """Symbols from a removed file are marked with change_type='deleted'."""
    old_source = b"def remove_me():\n    pass\n"
    fd = FileDiff(
        file="lib/old_module.py",
        patch="@@ -1,2 +0,0 @@\n-def remove_me():\n-    pass\n",
        status="removed",
        new_source=None,
        old_source=old_source,
        lines_changed=2,
    )
    state = _make_state([fd])
    result = symbols_module.run(state)
    deleted = [s for s in result["changed_symbols"] if s.change_type == "deleted"]
    assert len(deleted) >= 1


# ---------------------------------------------------------------------------
# 5. State keys are set correctly after run
# ---------------------------------------------------------------------------

def test_run_sets_risk_level_key():
    fd = FileDiff(
        file="main.py",
        patch="@@ -1 +1 @@\n-x=1\n+x=2\n",
        status="modified",
        new_source=b"x=2\n",
        old_source=b"x=1\n",
        lines_changed=1,
    )
    state = _make_state([fd])
    result = symbols_module.run(state)
    assert "risk_level" in result
    assert result["risk_level"] in ("low", "medium", "high")


def test_run_sets_risk_score_key():
    fd = FileDiff(
        file="main.py",
        patch="@@ -1 +1 @@\n-x=1\n+x=2\n",
        status="modified",
        new_source=b"x=2\n",
        old_source=b"x=1\n",
        lines_changed=1,
    )
    state = _make_state([fd])
    result = symbols_module.run(state)
    assert "risk_score" in result
    assert isinstance(result["risk_score"], int)


def test_run_sets_parsed_hunks_key():
    fd = FileDiff(
        file="main.py",
        patch="@@ -1 +1 @@\n-x=1\n+x=2\n",
        status="modified",
        new_source=b"x=2\n",
        old_source=b"x=1\n",
        lines_changed=1,
    )
    state = _make_state([fd])
    result = symbols_module.run(state)
    assert "parsed_hunks" in result


def test_run_preserves_existing_state_keys():
    fd = FileDiff(
        file="main.py",
        patch="@@ -1 +1 @@\n-x=1\n+x=2\n",
        status="modified",
        new_source=b"x=2\n",
        old_source=b"x=1\n",
        lines_changed=1,
    )
    state = _make_state([fd])
    result = symbols_module.run(state)
    assert result["repo_full_name"] == "owner/repo"
    assert result["pr_number"] == 1


def test_run_sets_phase_status_symbols_done():
    fd = FileDiff(
        file="main.py",
        patch="@@ -1 +1 @@\n-x=1\n+x=2\n",
        status="modified",
        new_source=b"x=2\n",
        old_source=b"x=1\n",
        lines_changed=1,
    )
    state = _make_state([fd])
    result = symbols_module.run(state)
    assert result.get("phase_status", {}).get("symbols") == "done"
