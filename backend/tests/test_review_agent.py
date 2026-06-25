from app.pipeline import review_agent
from app.pipeline.critic_agent import HEDGE_WORDS
from app.pipeline.diff_analysis import FileDiff
from app.schemas.diff_analysis import ChangedSymbol, DiffAnalysis
from app.schemas.pr_event import PREvent
from app.schemas.repository_context import RepositoryContext
from app.schemas.review_finding import ReviewFinding, ReviewFindingsResponse


def _pr_event() -> PREvent:
    return PREvent(
        repo_full_name="example-org/example-repo",
        pr_number=42,
        pr_url="https://github.com/example-org/example-repo/pull/42",
        title="Fix token expiry check",
        description="Adds an expiry check before returning the decoded payload.",
        base_sha="base",
        head_sha="head",
        base_ref="main",
        head_ref="fix/token-expiry",
        clone_url="https://github.com/example-org/example-repo.git",
    )


async def test_generate_findings_passes_through_mocked_llm_output(monkeypatch):
    captured = {}

    async def fake_complete_structured(schema, system_prompt, user_prompt, **kwargs):
        captured["system_prompt"] = system_prompt
        captured["user_prompt"] = user_prompt
        return ReviewFindingsResponse(
            findings=[
                ReviewFinding(
                    file="auth/utils.py",
                    line=10,
                    dimension="correctness",
                    finding="Expiry check happens after decode but before signature validation.",
                    evidence="if is_expired(payload): return None",
                    severity="major",
                )
            ],
            change_summary="Adds an expiry check before returning the decoded token payload.",
            suggested_pr_description="## What changed\nAdds an expiry check.\n\n## Why\nPrevents expired tokens from being accepted.",
        )

    monkeypatch.setattr(review_agent, "complete_structured", fake_complete_structured)

    file_diffs = [
        FileDiff(
            file="auth/utils.py",
            patch="@@ -1,3 +1,5 @@\n+    if is_expired(payload):\n+        return None\n",
            status="modified",
        )
    ]
    diff_analysis = DiffAnalysis(
        review_run_id="run-1",
        changed_symbols=[
            ChangedSymbol(
                file="auth/utils.py",
                symbol_name="validate_token",
                symbol_type="function",
                change_type="modified",
                start_line=8,
                end_line=12,
            )
        ],
        risk_level="medium",
        risk_factors=["touches sensitive-sounding paths: auth/utils.py"],
    )
    repository_context = RepositoryContext(
        affected_components=["AuthMiddleware"],
        affected_services=["auth"],
        affected_tests=["tests/test_auth.py"],
        risk_areas=["validate_token is called by 2 component(s)"],
    )

    response = await review_agent.generate_findings(_pr_event(), file_diffs, diff_analysis, repository_context)

    assert len(response.findings) == 1
    assert response.findings[0].file == "auth/utils.py"
    assert response.change_summary
    assert response.suggested_pr_description
    assert "auth/utils.py" in captured["user_prompt"]
    assert "AuthMiddleware" in captured["user_prompt"]
    assert "medium" in captured["user_prompt"]

    # without previous findings, the re-review instructions must not be added
    assert "reviewed before" not in captured["system_prompt"]


def test_system_prompt_covers_all_seven_checklist_dimensions():
    for dimension in ("correctness", "architecture", "testing", "maintainability", "security", "performance", "logging"):
        assert dimension in review_agent._SYSTEM_PROMPT


def test_system_prompt_requires_change_summary_and_pr_description():
    assert "change_summary" in review_agent._SYSTEM_PROMPT
    assert "suggested_pr_description" in review_agent._SYSTEM_PROMPT


def test_hedge_word_list_in_prompt_matches_critic_agents_single_source_of_truth():
    """review_agent's prompt text and critic_agent's deterministic regex
    backstop must reference the exact same word list - this test breaks if
    anyone reverts to a hand-written, independently-maintained copy in
    either file."""
    for word in HEDGE_WORDS:
        assert word in review_agent._SYSTEM_PROMPT


async def test_generate_findings_includes_previous_findings_and_re_review_instructions(monkeypatch):
    captured = {}

    async def fake_complete_structured(schema, system_prompt, user_prompt, **kwargs):
        captured["system_prompt"] = system_prompt
        captured["user_prompt"] = user_prompt
        return ReviewFindingsResponse(findings=[], change_summary="x", suggested_pr_description="y")

    monkeypatch.setattr(review_agent, "complete_structured", fake_complete_structured)

    file_diffs = [FileDiff(file="backend/cache.py", patch="@@ -1,1 +1,1 @@\n-x\n+y\n", status="modified")]
    diff_analysis = DiffAnalysis(review_run_id="run-1", changed_symbols=[], risk_level="low")
    repository_context = RepositoryContext()
    previous_findings = [
        ReviewFinding(
            file="backend/cache.py",
            line=12,
            dimension="correctness",
            finding="get_cached_response reads the cache without acquiring the lock.",
            evidence="return _cache[key]",
            severity="major",
        )
    ]

    await review_agent.generate_findings(
        _pr_event(), file_diffs, diff_analysis, repository_context, previous_findings=previous_findings
    )

    assert "reviewed before" in captured["system_prompt"]
    assert "resolved" in captured["system_prompt"] and "still present" in captured["system_prompt"]
    assert "get_cached_response reads the cache" in captured["user_prompt"]
