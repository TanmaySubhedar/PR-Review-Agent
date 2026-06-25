"""Tests for F5: finding render table, publish gate, and logs --pr option."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from typer.testing import CliRunner

from pr_review_agent.cli import app
from pr_review_agent.models.db import FindingRecord, RunRecord
from pr_review_agent.models.domain import (
    CriticVerdict,
    DiffPosition,
    Finding,
    PRMetadata,
    ValidatedFinding,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_finding(
    file: str = "auth/utils.py",
    line: int = 10,
    dimension: str = "correctness",
    finding: str = "Potential null dereference on user object",
    severity: str = "major",
) -> Finding:
    return Finding(
        file=file,
        line=line,
        dimension=dimension,
        finding=finding,
        evidence="line 10: user.name without None check",
        severity=severity,
    )


def _make_validated_finding(
    finding: Finding | None = None,
    confidence: float = 0.83,
    publish: bool = True,
    downgrade_to_summary: bool = False,
) -> ValidatedFinding:
    if finding is None:
        finding = _make_finding()
    verdict = CriticVerdict(
        evidence_grounded=True,
        respects_repo_context=True,
        actionable=True,
        confidence=confidence,
    )
    return ValidatedFinding(
        finding=finding,
        verdict=verdict,
        publish=publish,
        downgrade_to_summary=downgrade_to_summary,
        diff_position=DiffPosition(
            file=finding.file,
            new_line=finding.line,
            old_line=None,
            position=1,
            hunk_header="@@ -0,0 +1,10 @@",
        ),
    )


def _make_pr_metadata(repo: str = "owner/repo", pr_number: int = 42) -> PRMetadata:
    return PRMetadata(
        repo_full_name=repo,
        pr_number=pr_number,
        pr_url=f"https://github.com/{repo}/pull/{pr_number}",
        title="Test PR",
        base_sha="base000",
        head_sha="head000",
        base_ref="main",
        head_ref="feature",
        clone_url=f"https://github.com/{repo}.git",
    )


def _make_pipeline_result(validated_findings=None, repo="owner/repo", pr_number=42):
    """Build a minimal PipelineResult for mocking."""
    from pr_review_agent.graph.graph import PipelineResult

    run_id = str(uuid.uuid4())
    if validated_findings is None:
        validated_findings = [_make_validated_finding()]

    state = {
        "repo_full_name": repo,
        "pr_number": pr_number,
        "review_run_id": run_id,
        "pr_metadata": _make_pr_metadata(repo, pr_number),
        "validated_findings": validated_findings,
        "risk_level": "low",
        "risk_factors": [],
        "phase_status": {},
        "error": None,
    }
    return PipelineResult(state=state, review_run_id=run_id)


@pytest.fixture()
def in_memory_engine():
    """Isolated in-memory SQLite engine with all tables created."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture()
def runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# Test 1: Finding render table is built
# ---------------------------------------------------------------------------

def test_finding_render_table_appears_in_output(runner, in_memory_engine):
    """After run_pipeline, the review command should print a findings table."""
    vf = _make_validated_finding(
        finding=_make_finding(finding="Potential null dereference on user object"),
        confidence=0.83,
    )
    result_mock = _make_pipeline_result(validated_findings=[vf])

    with (
        patch("pr_review_agent.graph.graph.run_pipeline", return_value=result_mock),
        patch("pr_review_agent.tools.github.GitHubClient"),
        patch("pr_review_agent.db.init_db"),
        patch("pr_review_agent.db.engine", in_memory_engine),
    ):
        SQLModel.metadata.create_all(in_memory_engine)
        result = runner.invoke(app, ["review", "owner/repo", "42"], input="N\n")

    assert result.exit_code == 0, result.output
    # "Finding" column header should appear in the table
    assert "Finding" in result.output
    # The actual finding text should be present (Rich may wrap long text)
    assert "Potential null" in result.output


# ---------------------------------------------------------------------------
# Test 2: Publish prompt "y" triggers create_review
# ---------------------------------------------------------------------------

def test_publish_yes_calls_create_review(runner, in_memory_engine):
    """Answering 'y' at the publish prompt should call GitHubClient.create_review."""
    vf = _make_validated_finding()
    result_mock = _make_pipeline_result(validated_findings=[vf])

    mock_gh_instance = MagicMock()
    mock_gh_class = MagicMock(return_value=mock_gh_instance)

    with (
        patch("pr_review_agent.graph.graph.run_pipeline", return_value=result_mock),
        patch("pr_review_agent.tools.github.GitHubClient", mock_gh_class),
        patch("pr_review_agent.db.init_db"),
        patch("pr_review_agent.db.engine", in_memory_engine),
    ):
        SQLModel.metadata.create_all(in_memory_engine)
        result = runner.invoke(app, ["review", "owner/repo", "42"], input="y\n")

    assert result.exit_code == 0, result.output
    mock_gh_instance.create_review.assert_called_once()
    assert "Review posted to GitHub" in result.output


# ---------------------------------------------------------------------------
# Test 3: Publish prompt "N" skips create_review but stores findings
# ---------------------------------------------------------------------------

def test_publish_no_skips_create_review_but_stores(runner, in_memory_engine):
    """Answering 'N' should NOT call create_review but should persist findings."""
    vf = _make_validated_finding()
    result_mock = _make_pipeline_result(validated_findings=[vf])

    mock_gh_instance = MagicMock()
    mock_gh_class = MagicMock(return_value=mock_gh_instance)

    with (
        patch("pr_review_agent.graph.graph.run_pipeline", return_value=result_mock),
        patch("pr_review_agent.tools.github.GitHubClient", mock_gh_class),
        patch("pr_review_agent.db.init_db"),
        patch("pr_review_agent.db.engine", in_memory_engine),
    ):
        SQLModel.metadata.create_all(in_memory_engine)
        result = runner.invoke(app, ["review", "owner/repo", "42"], input="N\n")

    assert result.exit_code == 0, result.output
    mock_gh_instance.create_review.assert_not_called()
    assert "Review saved locally." in result.output

    # Verify findings were persisted
    with Session(in_memory_engine) as session:
        findings = session.exec(select(FindingRecord)).all()
        assert len(findings) == 1
        assert findings[0].severity == "major"


# ---------------------------------------------------------------------------
# Test 4: logs --pr <n> returns correct run's findings
# ---------------------------------------------------------------------------

def test_logs_pr_option_returns_correct_findings(runner, in_memory_engine):
    """logs --pr <n> should display findings for the most recent run with that PR number."""
    run_id_pr10 = str(uuid.uuid4())
    run_id_pr20 = str(uuid.uuid4())

    with Session(in_memory_engine) as session:
        # Run for PR #10
        run10 = RunRecord(
            id=run_id_pr10,
            repo_full_name="owner/repo",
            pr_number=10,
            pr_url="https://github.com/owner/repo/pull/10",
            title="PR 10",
            head_sha="abc10",
            base_sha="def10",
        )
        finding10 = FindingRecord(
            review_run_id=run_id_pr10,
            file="auth/login.py",
            line=5,
            dimension="correctness",
            finding="Missing auth check in login handler",
            evidence="line 5: no token validation",
            severity="blocking",
            confidence=0.95,
        )
        # Run for PR #20
        run20 = RunRecord(
            id=run_id_pr20,
            repo_full_name="owner/repo",
            pr_number=20,
            pr_url="https://github.com/owner/repo/pull/20",
            title="PR 20",
            head_sha="abc20",
            base_sha="def20",
        )
        finding20 = FindingRecord(
            review_run_id=run_id_pr20,
            file="utils/helpers.py",
            line=42,
            dimension="maintainability",
            finding="Function too complex, refactor recommended",
            evidence="line 42: cyclomatic complexity > 10",
            severity="minor",
            confidence=0.70,
        )
        session.add(run10)
        session.add(finding10)
        session.add(run20)
        session.add(finding20)
        session.commit()

    with (
        patch("pr_review_agent.db.init_db"),
        patch("pr_review_agent.db.engine", in_memory_engine),
    ):
        result = runner.invoke(app, ["logs", "--pr", "10"])

    assert result.exit_code == 0, result.output
    # Should show finding for PR #10
    assert "Missing auth check" in result.output
    # Should NOT show finding for PR #20
    assert "Function too complex" not in result.output


def test_logs_pr_option_not_found_exits_with_error(runner, in_memory_engine):
    """logs --pr <n> with no matching run should print an error and exit 1."""
    with (
        patch("pr_review_agent.db.init_db"),
        patch("pr_review_agent.db.engine", in_memory_engine),
    ):
        result = runner.invoke(app, ["logs", "--pr", "999"])

    assert result.exit_code == 1
    assert "No run found" in result.output


def test_logs_pr_option_with_repo_filter(runner, in_memory_engine):
    """logs --pr <n> --repo filters by repo name."""
    run_id_a = str(uuid.uuid4())
    run_id_b = str(uuid.uuid4())

    with Session(in_memory_engine) as session:
        run_a = RunRecord(
            id=run_id_a,
            repo_full_name="org/repo-a",
            pr_number=5,
            pr_url="https://github.com/org/repo-a/pull/5",
            title="Repo A PR 5",
            head_sha="aaaa",
            base_sha="bbbb",
        )
        finding_a = FindingRecord(
            review_run_id=run_id_a,
            file="module_a.py",
            line=1,
            dimension="correctness",
            finding="Bug in repo-a code path",
            evidence="line 1: bad stuff",
            severity="major",
            confidence=0.80,
        )
        run_b = RunRecord(
            id=run_id_b,
            repo_full_name="org/repo-b",
            pr_number=5,
            pr_url="https://github.com/org/repo-b/pull/5",
            title="Repo B PR 5",
            head_sha="cccc",
            base_sha="dddd",
        )
        finding_b = FindingRecord(
            review_run_id=run_id_b,
            file="module_b.py",
            line=2,
            dimension="architecture",
            finding="Architectural issue in repo-b",
            evidence="line 2: wrong pattern",
            severity="info",
            confidence=0.60,
        )
        session.add(run_a)
        session.add(finding_a)
        session.add(run_b)
        session.add(finding_b)
        session.commit()

    with (
        patch("pr_review_agent.db.init_db"),
        patch("pr_review_agent.db.engine", in_memory_engine),
    ):
        result = runner.invoke(app, ["logs", "--pr", "5", "--repo", "org/repo-b"])

    assert result.exit_code == 0, result.output
    # Rich may wrap long text; check for a substring that fits within one line
    assert "Architectural issue" in result.output
    assert "Bug in repo-a" not in result.output
