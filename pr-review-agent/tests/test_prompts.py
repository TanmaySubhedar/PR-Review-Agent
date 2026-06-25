"""Unit tests for all prompt builder modules."""

import pytest

from pr_review_agent.models.domain import (
    CriticVerdict,
    DiffPosition,
    FileDiff,
    FileSummary,
    Finding,
    RepositoryContext,
    ValidatedFinding,
)
from pr_review_agent.prompts import critic as critic_module
from pr_review_agent.prompts import file_reader as file_reader_module
from pr_review_agent.prompts import reviewer as reviewer_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_finding(
    file: str = "auth/utils.py",
    line: int = 10,
    finding: str = "The password is stored in plaintext on line 10.",
    evidence: str = "password = plain",
    dimension: str = "correctness",
    severity: str = "major",
) -> Finding:
    return Finding(
        file=file,
        line=line,
        dimension=dimension,
        finding=finding,
        evidence=evidence,
        severity=severity,
    )


def _make_repo_context(
    affected_components: list[str] | None = None,
    affected_services: list[str] | None = None,
    affected_tests: list[str] | None = None,
    architecture_constraints: list[str] | None = None,
    risk_areas: list[str] | None = None,
) -> RepositoryContext:
    return RepositoryContext(
        affected_components=affected_components or ["AuthService"],
        affected_services=affected_services or ["auth"],
        affected_tests=affected_tests or ["tests/test_auth.py"],
        architecture_constraints=architecture_constraints or [],
        risk_areas=risk_areas or ["validate_token called from 3 places"],
    )


def _make_file_diff(
    file: str = "auth/utils.py",
    patch: str = "@@ -1,2 +1,2 @@\n-old\n+new\n",
    status: str = "modified",
) -> FileDiff:
    return FileDiff(file=file, patch=patch, status=status)


# ---------------------------------------------------------------------------
# reviewer.build_prompts
# ---------------------------------------------------------------------------

def test_reviewer_build_prompts_returns_tuple():
    system, user = reviewer_module.build_prompts(
        pr_title="Fix token expiry check",
        pr_description="Adds expiry check.",
        risk_level="medium",
        risk_factors=["touches sensitive-sounding paths: auth/utils.py"],
        repository_context=_make_repo_context(),
        file_diffs=[_make_file_diff()],
    )
    assert isinstance(system, str)
    assert isinstance(user, str)


def test_reviewer_build_prompts_returns_two_non_empty_strings():
    result = reviewer_module.build_prompts(
        pr_title="Add login endpoint",
        pr_description="",
        risk_level="low",
        risk_factors=[],
        repository_context=_make_repo_context(),
        file_diffs=[_make_file_diff()],
    )
    system, user = result
    assert len(system) > 0
    assert len(user) > 0


def test_reviewer_system_prompt_contains_correctness():
    system, _ = reviewer_module.build_prompts(
        pr_title="Refactor auth module",
        pr_description="",
        risk_level="low",
        risk_factors=[],
        repository_context=_make_repo_context(),
        file_diffs=[_make_file_diff()],
    )
    assert "correctness" in system


def test_reviewer_user_prompt_contains_pr_title():
    pr_title = "My Unique PR Title XYZ123"
    _, user = reviewer_module.build_prompts(
        pr_title=pr_title,
        pr_description="Some description.",
        risk_level="high",
        risk_factors=["auth path"],
        repository_context=_make_repo_context(),
        file_diffs=[_make_file_diff()],
    )
    assert pr_title in user


def test_reviewer_user_prompt_contains_risk_level():
    _, user = reviewer_module.build_prompts(
        pr_title="PR",
        pr_description="",
        risk_level="high",
        risk_factors=["large diff"],
        repository_context=_make_repo_context(),
        file_diffs=[_make_file_diff()],
    )
    assert "high" in user


def test_reviewer_user_prompt_contains_file_name():
    _, user = reviewer_module.build_prompts(
        pr_title="PR",
        pr_description="",
        risk_level="low",
        risk_factors=[],
        repository_context=_make_repo_context(),
        file_diffs=[_make_file_diff(file="auth/utils.py")],
    )
    assert "auth/utils.py" in user


def test_reviewer_user_prompt_no_previous_no_rereview():
    system, _ = reviewer_module.build_prompts(
        pr_title="PR",
        pr_description="",
        risk_level="low",
        risk_factors=[],
        repository_context=_make_repo_context(),
        file_diffs=[_make_file_diff()],
        previous_findings=None,
    )
    assert "reviewed before" not in system


def test_reviewer_system_prompt_contains_rereview_when_previous_findings():
    """When previous_findings is non-empty, re-review suffix is appended."""
    previous = [_make_finding()]
    system, _ = reviewer_module.build_prompts(
        pr_title="PR",
        pr_description="",
        risk_level="low",
        risk_factors=[],
        repository_context=_make_repo_context(),
        file_diffs=[_make_file_diff()],
        previous_findings=previous,
    )
    assert "reviewed before" in system


def test_reviewer_user_prompt_contains_previous_finding_text():
    """Previous finding text must appear in the user prompt."""
    previous = [_make_finding(finding="Specific finding text ABC")]
    _, user = reviewer_module.build_prompts(
        pr_title="PR",
        pr_description="",
        risk_level="low",
        risk_factors=[],
        repository_context=_make_repo_context(),
        file_diffs=[_make_file_diff()],
        previous_findings=previous,
    )
    assert "Specific finding text ABC" in user


def test_reviewer_system_prompt_no_rereview_for_empty_previous():
    """Empty list (not None) → no re-review suffix."""
    system, _ = reviewer_module.build_prompts(
        pr_title="PR",
        pr_description="",
        risk_level="low",
        risk_factors=[],
        repository_context=_make_repo_context(),
        file_diffs=[_make_file_diff()],
        previous_findings=[],
    )
    assert "reviewed before" not in system


def test_reviewer_system_prompt_contains_architecture():
    system, _ = reviewer_module.build_prompts(
        pr_title="PR",
        pr_description="",
        risk_level="low",
        risk_factors=[],
        repository_context=_make_repo_context(),
        file_diffs=[_make_file_diff()],
    )
    assert "architecture" in system


# ---------------------------------------------------------------------------
# critic.user_prompt
# ---------------------------------------------------------------------------

def test_critic_user_prompt_returns_string():
    finding = _make_finding()
    context = _make_repo_context()
    result = critic_module.user_prompt(finding, context)
    assert isinstance(result, str)


def test_critic_user_prompt_non_empty():
    finding = _make_finding()
    context = _make_repo_context()
    result = critic_module.user_prompt(finding, context)
    assert len(result) > 0


def test_critic_user_prompt_contains_finding_text():
    finding_text = "The session is not invalidated on logout."
    finding = _make_finding(finding=finding_text)
    context = _make_repo_context()
    result = critic_module.user_prompt(finding, context)
    assert finding_text in result


def test_critic_user_prompt_contains_file_name():
    finding = _make_finding(file="auth/session.py")
    context = _make_repo_context()
    result = critic_module.user_prompt(finding, context)
    assert "auth/session.py" in result


def test_critic_user_prompt_contains_affected_components():
    context = _make_repo_context(affected_components=["SessionManager"])
    finding = _make_finding()
    result = critic_module.user_prompt(finding, context)
    assert "SessionManager" in result


def test_critic_user_prompt_contains_evidence():
    evidence = "session.invalidate() is never called"
    finding = _make_finding(evidence=evidence)
    context = _make_repo_context()
    result = critic_module.user_prompt(finding, context)
    assert evidence in result


def test_critic_user_prompt_contains_dimension():
    finding = _make_finding(dimension="architecture")
    context = _make_repo_context()
    result = critic_module.user_prompt(finding, context)
    assert "architecture" in result


# ---------------------------------------------------------------------------
# file_reader.user_prompt
# ---------------------------------------------------------------------------

def test_file_reader_user_prompt_returns_string():
    result = file_reader_module.user_prompt(
        pr_summary="Fix the login flow.",
        file_path="auth/middleware.py",
        selection_reason="direct_caller",
        file_content="def middleware():\n    pass\n",
    )
    assert isinstance(result, str)


def test_file_reader_user_prompt_non_empty():
    result = file_reader_module.user_prompt(
        pr_summary="Add caching.",
        file_path="cache/store.py",
        selection_reason="dependency_chain",
        file_content="class Store: pass\n",
    )
    assert len(result) > 0


def test_file_reader_user_prompt_contains_file_path():
    file_path = "auth/middleware.py"
    result = file_reader_module.user_prompt(
        pr_summary="Fix auth.",
        file_path=file_path,
        selection_reason="direct_caller",
        file_content="def middleware(): pass\n",
    )
    assert file_path in result


def test_file_reader_user_prompt_contains_pr_summary():
    pr_summary = "Refactor the token validation logic"
    result = file_reader_module.user_prompt(
        pr_summary=pr_summary,
        file_path="auth/utils.py",
        selection_reason="changed_file",
        file_content="def validate(): pass\n",
    )
    assert pr_summary in result


def test_file_reader_user_prompt_contains_file_content():
    file_content = "def unique_function_xyz(): return 42\n"
    result = file_reader_module.user_prompt(
        pr_summary="PR summary",
        file_path="some/file.py",
        selection_reason="same_module",
        file_content=file_content,
    )
    assert "unique_function_xyz" in result


def test_file_reader_user_prompt_contains_selection_reason():
    result = file_reader_module.user_prompt(
        pr_summary="PR",
        file_path="x.py",
        selection_reason="direct_caller",
        file_content="",
    )
    assert "direct_caller" in result


def test_file_reader_user_prompt_truncates_long_content():
    """Content longer than MAX_FILE_CHARS should be truncated."""
    long_content = "x = 1\n" * 2000  # much longer than 8000 chars
    result = file_reader_module.user_prompt(
        pr_summary="PR",
        file_path="big_file.py",
        selection_reason="changed_file",
        file_content=long_content,
    )
    # Result must exist and not contain the full content
    assert len(result) < len(long_content) + 200  # prompt overhead is small
