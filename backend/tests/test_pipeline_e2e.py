from pathlib import Path

from app.pipeline import context_readers, critic_agent, review_agent
from app.pipeline.diff_analysis import FileDiff
from app.pipeline.orchestrator import run_review_pipeline
from app.schemas.context_package import ReaderOutput
from app.schemas.critic_judgment import CriticJudgment
from app.schemas.pr_event import PREvent
from app.schemas.review_finding import ReviewFinding, ReviewFindingsResponse

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "sample_repo"

PATCH = (
    "@@ -7,5 +7,9 @@\n"
    " def validate_token(token):\n"
    "     payload = decode(token)\n"
    "+    if is_expired(payload):\n"
    "+        return None\n"
    "     return payload\n"
)


class FakeGitHubClient:
    def __init__(self):
        self.published = []

    def create_review(self, repo_full_name, pr_number, summary_body, inline_comments):
        self.published.append((repo_full_name, pr_number, summary_body, inline_comments))


def _pr_event() -> PREvent:
    return PREvent(
        repo_full_name="example-org/example-repo",
        pr_number=42,
        pr_url="https://github.com/example-org/example-repo/pull/42",
        title="Fix token expiry check",
        description="Adds an expiry check before returning the decoded payload.",
        base_sha="base0000",
        head_sha="head0000",
        base_ref="main",
        head_ref="fix/token-expiry",
        clone_url="https://github.com/example-org/example-repo.git",
    )


async def test_full_pipeline_runs_end_to_end_with_mocked_llm_and_fake_github(monkeypatch):
    new_source = (FIXTURE_REPO / "auth/utils.py").read_bytes()
    file_diffs = [FileDiff(file="auth/utils.py", patch=PATCH, status="modified", new_source=new_source)]

    async def fake_reader(schema, system_prompt, user_prompt, **kwargs):
        return ReaderOutput(file="placeholder", purpose="p", relevance="r", risks=["Auth bypass risk if untested"])

    async def fake_review(schema, system_prompt, user_prompt, **kwargs):
        return ReviewFindingsResponse(
            findings=[
                ReviewFinding(
                    file="auth/utils.py",
                    line=10,
                    dimension="correctness",
                    finding="Expiry check added correctly before returning payload",
                    evidence="if is_expired(payload): return None",
                    severity="minor",
                ),
                ReviewFinding(
                    file="totally/made/up.py",
                    line=999,
                    dimension="testing",
                    finding="Hallucinated finding on a file the agent never actually read",
                    evidence="nonexistent",
                    severity="major",
                ),
            ]
        )

    async def fake_critic(schema, system_prompt, user_prompt, **kwargs):
        return CriticJudgment(respects_repo_context=True, actionable=True, confidence=0.9, rationale="ok")

    # context_readers, review_agent and critic_agent each import complete_structured
    # into their own module namespace, so each needs patching independently -
    # this also documents that they're three separate LLM call sites.
    monkeypatch.setattr(context_readers, "complete_structured", fake_reader)
    monkeypatch.setattr(review_agent, "complete_structured", fake_review)
    monkeypatch.setattr(critic_agent, "complete_structured", fake_critic)

    github_client = FakeGitHubClient()
    pr_event = _pr_event()

    phases_seen = []
    result = await run_review_pipeline(
        "run-e2e",
        pr_event,
        file_diffs,
        FIXTURE_REPO,
        github_client,
        on_phase=lambda phase, status: phases_seen.append((phase, status)),
    )

    assert result.diff_analysis.risk_level in ("medium", "high")
    assert len(result.diff_analysis.changed_symbols) == 1
    assert result.diff_analysis.changed_symbols[0].symbol_name == "validate_token"

    assert result.blast_radius.entries[0].callers  # AuthMiddleware/AdminMiddleware/test found it

    assert "AuthMiddleware" in result.repository_context.affected_components

    assert len(result.findings) == 2

    # the grounded finding (real file+line in the diff) must publish inline;
    # the hallucinated one must be caught by critic_agent's evidence-grounding
    # heuristic and discarded entirely, never reaching GitHub.
    scored_by_file = {sf.finding.file: sf for sf in result.scored_findings}
    assert scored_by_file["auth/utils.py"].publish is True
    assert scored_by_file["totally/made/up.py"].critic.evidence_grounded is False
    assert scored_by_file["totally/made/up.py"].publish is False

    assert len(github_client.published) == 1
    _, _, summary_body, inline_comments = github_client.published[0]
    assert len(inline_comments) == 1
    assert inline_comments[0]["path"] == "auth/utils.py"
    assert "risk:" in summary_body

    done_phases = {phase for phase, status in phases_seen if status == "done"}
    assert done_phases == {
        "diff_analysis", "blast_radius", "context_retrieval", "synthesis", "review", "critic", "publish",
    }
