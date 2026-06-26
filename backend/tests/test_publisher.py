from app.pipeline.publisher import build_inline_comments, build_summary_body, compute_overall_severity, publish_review
from app.schemas.diff_analysis import DiffAnalysis, DiffPosition
from app.schemas.pr_event import PREvent
from app.schemas.repository_context import RepositoryContext
from app.schemas.review_finding import ReviewFinding
from app.schemas.scored_finding import CriticScore, ScoredFinding


class FakeGitHubClient:
    def __init__(self):
        self.calls = []

    def create_review(self, repo_full_name, pr_number, summary_body, inline_comments):
        self.calls.append((repo_full_name, pr_number, summary_body, inline_comments))


def _pr_event() -> PREvent:
    return PREvent(
        repo_full_name="example-org/example-repo",
        pr_number=42,
        pr_url="https://github.com/example-org/example-repo/pull/42",
        title="Fix token expiry",
        base_sha="base",
        head_sha="head",
        base_ref="main",
        head_ref="fix/token-expiry",
        clone_url="https://github.com/example-org/example-repo.git",
    )


def _published_finding() -> ScoredFinding:
    return ScoredFinding(
        finding=ReviewFinding(
            file="auth/utils.py",
            line=3,
            dimension="correctness",
            finding="Expiry check looks correct",
            evidence="if is_expired(payload): return None",
            severity="minor",
        ),
        critic=CriticScore(evidence_grounded=True, respects_repo_context=True, actionable=True, confidence=0.9),
        publish=True,
        diff_position=DiffPosition(file="auth/utils.py", new_line=3, old_line=None, position=4, hunk_header=""),
    )


def _downgraded_finding() -> ScoredFinding:
    return ScoredFinding(
        finding=ReviewFinding(
            file="auth/middleware.py",
            line=42,
            dimension="architecture",
            finding="Caller doesn't handle the new None return",
            evidence="return validate_token(request.token)",
            severity="major",
        ),
        critic=CriticScore(evidence_grounded=True, respects_repo_context=True, actionable=True, confidence=0.85),
        publish=False,
        downgrade_to_summary=True,
        diff_position=None,
    )


def _discarded_finding() -> ScoredFinding:
    return ScoredFinding(
        finding=ReviewFinding(
            file="auth/utils.py", line=None, dimension="maintainability", finding="weak", evidence="x", severity="info"
        ),
        critic=CriticScore(evidence_grounded=True, respects_repo_context=True, actionable=False, confidence=0.4),
        publish=False,
    )


def test_build_inline_comments_only_includes_published_with_position():
    comments = build_inline_comments([_published_finding(), _downgraded_finding(), _discarded_finding()])

    assert len(comments) == 1
    assert comments[0]["path"] == "auth/utils.py"
    assert comments[0]["position"] == 4
    assert "correctness/minor" in comments[0]["body"]


def test_build_summary_body_includes_risk_areas_and_downgraded_and_counts():
    diff_analysis = DiffAnalysis(review_run_id="run-1", changed_symbols=[], risk_level="medium")
    repository_context = RepositoryContext(risk_areas=["validate_token is called by 2 component(s)"])

    body = build_summary_body(
        diff_analysis, repository_context, [_published_finding(), _downgraded_finding(), _discarded_finding()]
    )

    assert "risk: medium" in body
    assert "validate_token is called by 2 component(s)" in body
    assert "auth/middleware.py" in body  # downgraded finding listed
    assert "1 inline comment(s) posted, 1 summarized above, 1 filtered out" in body


def test_compute_overall_severity_is_max_of_published_and_downgraded_only():
    # discarded finding is "info" but excluded; published is "minor"; downgraded is "major" -> max is "major"
    severity = compute_overall_severity([_published_finding(), _downgraded_finding(), _discarded_finding()])
    assert severity == "major"


def test_compute_overall_severity_is_none_when_nothing_survives():
    assert compute_overall_severity([_discarded_finding()]) == "none"


def test_compute_overall_severity_is_deterministic_across_repeated_calls():
    findings = [_published_finding(), _downgraded_finding(), _discarded_finding()]
    results = {compute_overall_severity(findings) for _ in range(5)}
    assert results == {"major"}


def test_build_summary_body_keeps_line_zero_not_dropped_by_truthy_check():
    downgraded_at_line_zero = ScoredFinding(
        finding=ReviewFinding(
            file="auth/middleware.py",
            line=0,
            dimension="architecture",
            finding="Issue at the very first line of the file",
            evidence="import os",
            severity="major",
        ),
        critic=CriticScore(evidence_grounded=True, respects_repo_context=True, actionable=True, confidence=0.85),
        publish=False,
        downgrade_to_summary=True,
        diff_position=None,
    )

    diff_analysis = DiffAnalysis(review_run_id="run-1", changed_symbols=[], risk_level="low")
    body = build_summary_body(diff_analysis, RepositoryContext(), [downgraded_at_line_zero])

    assert "`auth/middleware.py`:0" in body


def test_build_summary_body_includes_overall_severity():
    diff_analysis = DiffAnalysis(review_run_id="run-1", changed_symbols=[], risk_level="medium")
    body = build_summary_body(diff_analysis, RepositoryContext(), [_published_finding(), _downgraded_finding()])

    assert "overall severity: major" in body


def test_publish_review_calls_github_client_with_built_payload():
    client = FakeGitHubClient()
    diff_analysis = DiffAnalysis(review_run_id="run-1", changed_symbols=[], risk_level="low")
    repository_context = RepositoryContext()

    result = publish_review(client, _pr_event(), diff_analysis, repository_context, [_published_finding()])

    assert result == {"inline_comments": 1, "summary_posted": True}
    assert len(client.calls) == 1
    repo_full_name, pr_number, summary_body, inline_comments = client.calls[0]
    assert repo_full_name == "example-org/example-repo"
    assert pr_number == 42
    assert len(inline_comments) == 1


def test_build_summary_body_includes_change_summary_when_present():
    diff_analysis = DiffAnalysis(review_run_id="run-1", changed_symbols=[], risk_level="low")
    body = build_summary_body(
        diff_analysis, RepositoryContext(), [], change_summary="Adds an expiry check to validate_token."
    )

    assert "Adds an expiry check to validate_token." in body


def test_publish_review_passes_change_summary_through_to_github_client():
    client = FakeGitHubClient()
    diff_analysis = DiffAnalysis(review_run_id="run-1", changed_symbols=[], risk_level="low")

    publish_review(
        client, _pr_event(), diff_analysis, RepositoryContext(), [_published_finding()],
        change_summary="Adds an expiry check.",
    )

    _, _, summary_body, _ = client.calls[0]
    assert "Adds an expiry check." in summary_body


def test_build_inline_comments_supports_new_dimensions():
    finding = ScoredFinding(
        finding=ReviewFinding(
            file="backend/app.py",
            line=5,
            dimension="security",
            finding="Hardcoded API key",
            evidence='API_KEY = "sk-12345"',
            severity="blocking",
        ),
        critic=CriticScore(evidence_grounded=True, respects_repo_context=True, actionable=True, confidence=0.95),
        publish=True,
        diff_position=DiffPosition(file="backend/app.py", new_line=5, old_line=None, position=2, hunk_header=""),
    )

    comments = build_inline_comments([finding])

    assert len(comments) == 1
    assert "security/blocking" in comments[0]["body"]
