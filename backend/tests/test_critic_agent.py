import pytest

from app.pipeline import critic_agent
from app.schemas.context_package import ContextFileSelection, ContextPackage
from app.schemas.critic_judgment import CriticJudgment
from app.schemas.diff_analysis import ChangedSymbol, DiffAnalysis, DiffPosition
from app.schemas.repository_context import RepositoryContext
from app.schemas.review_finding import ReviewFinding

PATCH = (
    "@@ -1,3 +1,5 @@\n"
    " def validate_token(token):\n"
    "     payload = decode(token)\n"
    "+    if is_expired(payload):\n"
    "+        return None\n"
    "     return payload\n"
)


def _diff_analysis() -> DiffAnalysis:
    from app.github.diff_positions import compute_diff_positions

    return DiffAnalysis(
        review_run_id="run-1",
        changed_symbols=[
            ChangedSymbol(
                file="auth/utils.py",
                symbol_name="validate_token",
                symbol_type="function",
                change_type="modified",
                start_line=1,
                end_line=6,
            )
        ],
        risk_level="medium",
        diff_positions=compute_diff_positions("auth/utils.py", PATCH),
    )


def _context_package() -> ContextPackage:
    return ContextPackage(
        selections=[
            ContextFileSelection(file="auth/utils.py", selection_reason="changed_file", score=100.0),
            ContextFileSelection(file="auth/middleware.py", selection_reason="direct_caller", score=80.0),
        ]
    )


def _repo_context() -> RepositoryContext:
    return RepositoryContext(affected_components=["AuthMiddleware"], affected_services=["auth"])


async def test_score_finding_discards_hallucinated_file_without_calling_llm(monkeypatch):
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("LLM should not be called for an ungrounded finding")

    monkeypatch.setattr(critic_agent, "complete_structured", fail_if_called)

    finding = ReviewFinding(
        file="nonexistent/file.py",
        line=1,
        dimension="correctness",
        finding="Bug",
        evidence="some code",
        severity="major",
    )

    result = await critic_agent.score_finding(finding, _diff_analysis(), _context_package(), _repo_context())

    assert result.critic.evidence_grounded is False
    assert result.critic.confidence == 0.0
    assert result.publish is False


async def test_score_finding_discards_empty_evidence_without_calling_llm(monkeypatch):
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("LLM should not be called for an ungrounded finding")

    monkeypatch.setattr(critic_agent, "complete_structured", fail_if_called)

    finding = ReviewFinding(
        file="auth/utils.py", line=3, dimension="correctness", finding="Bug", evidence="   ", severity="major"
    )

    result = await critic_agent.score_finding(finding, _diff_analysis(), _context_package(), _repo_context())

    assert result.critic.evidence_grounded is False
    assert result.publish is False


async def test_score_finding_publishes_when_grounded_and_high_confidence(monkeypatch):
    async def fake_complete_structured(schema, system_prompt, user_prompt, **kwargs):
        return CriticJudgment(
            respects_repo_context=True, actionable=True, confidence=0.9, rationale="solid"
        )

    monkeypatch.setattr(critic_agent, "complete_structured", fake_complete_structured)

    finding = ReviewFinding(
        file="auth/utils.py",
        line=3,
        dimension="correctness",
        finding="Expiry check should happen before decode trust",
        evidence="if is_expired(payload): return None",
        severity="major",
    )

    result = await critic_agent.score_finding(finding, _diff_analysis(), _context_package(), _repo_context())

    assert result.critic.evidence_grounded is True
    assert result.publish is True
    assert result.downgrade_to_summary is False
    assert result.diff_position is not None


async def test_score_finding_downgrades_to_summary_when_line_outside_any_hunk(monkeypatch):
    async def fake_complete_structured(schema, system_prompt, user_prompt, **kwargs):
        return CriticJudgment(respects_repo_context=True, actionable=True, confidence=0.9, rationale="ok")

    monkeypatch.setattr(critic_agent, "complete_structured", fake_complete_structured)

    finding = ReviewFinding(
        file="auth/middleware.py",  # in context selections, but not in the diff at all
        line=42,
        dimension="architecture",
        finding="This caller doesn't handle the new None return value",
        evidence="return validate_token(request.token)",
        severity="major",
    )

    result = await critic_agent.score_finding(finding, _diff_analysis(), _context_package(), _repo_context())

    assert result.critic.evidence_grounded is True
    assert result.publish is False
    assert result.downgrade_to_summary is True
    assert result.diff_position is None


async def test_score_finding_discards_when_confidence_below_threshold(monkeypatch):
    async def fake_complete_structured(schema, system_prompt, user_prompt, **kwargs):
        return CriticJudgment(respects_repo_context=True, actionable=True, confidence=0.2, rationale="weak")

    monkeypatch.setattr(critic_agent, "complete_structured", fake_complete_structured)

    finding = ReviewFinding(
        file="auth/utils.py",
        line=3,
        dimension="correctness",
        finding="Maybe an issue",
        evidence="if is_expired(payload): return None",
        severity="minor",
    )

    result = await critic_agent.score_finding(finding, _diff_analysis(), _context_package(), _repo_context())

    assert result.publish is False
    assert result.downgrade_to_summary is False


def test_cap_severity_if_hedged_downgrades_major_with_hedge_language():
    finding = ReviewFinding(
        file="backend/cache.py",
        line=10,
        dimension="correctness",
        finding="This could lead to a race condition under concurrent load.",
        evidence="x = _cache[key]",
        severity="major",
    )

    capped = critic_agent._cap_severity_if_hedged(finding)

    assert capped.severity == "minor"


def test_cap_severity_if_hedged_leaves_concrete_major_finding_alone():
    finding = ReviewFinding(
        file="backend/cache.py",
        line=10,
        dimension="correctness",
        finding="get_cached_response reads _cache[key] without acquiring _lock, while store_cached_response "
        "writes to it under _lock - a concurrent read during a write returns a partially-updated entry.",
        evidence="def get_cached_response(key):\n    return _cache[key]  # no lock acquired here",
        severity="major",
    )

    capped = critic_agent._cap_severity_if_hedged(finding)

    assert capped.severity == "major"


async def test_score_finding_caps_hedged_severity_before_evidence_check(monkeypatch):
    async def fake_complete_structured(schema, system_prompt, user_prompt, **kwargs):
        return CriticJudgment(respects_repo_context=True, actionable=True, confidence=0.9, rationale="ok")

    monkeypatch.setattr(critic_agent, "complete_structured", fake_complete_structured)

    finding = ReviewFinding(
        file="auth/utils.py",
        line=3,
        dimension="correctness",
        finding="This might cause issues if the cache is accessed concurrently.",
        evidence="if is_expired(payload): return None",
        severity="blocking",
    )

    result = await critic_agent.score_finding(finding, _diff_analysis(), _context_package(), _repo_context())

    assert result.finding.severity == "minor"
    assert result.publish is True


@pytest.mark.parametrize("dimension", ["correctness", "security", "performance", "logging"])
async def test_score_finding_gates_new_dimensions_identically_to_existing_ones(monkeypatch, dimension):
    """critic_agent never branches on `dimension` - confirms security/performance/
    logging findings flow through the exact same evidence-grounding and LLM-judgment
    gates as the original four dimensions, with no critic code change required."""
    async def fake_complete_structured(schema, system_prompt, user_prompt, **kwargs):
        return CriticJudgment(respects_repo_context=True, actionable=True, confidence=0.9, rationale="ok")

    monkeypatch.setattr(critic_agent, "complete_structured", fake_complete_structured)

    finding = ReviewFinding(
        file="auth/utils.py",
        line=3,
        dimension=dimension,
        finding="Concrete grounded finding for this dimension",
        evidence="if is_expired(payload): return None",
        severity="major",
    )

    result = await critic_agent.score_finding(finding, _diff_analysis(), _context_package(), _repo_context())

    assert result.critic.evidence_grounded is True
    assert result.publish is True
