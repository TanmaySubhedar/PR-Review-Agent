"""Critic node: validate each finding; attempt one refinement for borderline cases."""

import asyncio
import re

from pr_review_agent._llm import complete_structured
from pr_review_agent.config import settings
from pr_review_agent.graph.nodes.symbols import find_diff_position
from pr_review_agent.graph.state import PRReviewState
from pr_review_agent.models.domain import (
    ContextFileSelection,
    CriticJudgment,
    CriticVerdict,
    Finding,
    RefinedFinding,
    RepositoryContext,
    ValidatedFinding,
)
from pr_review_agent.prompts import critic as critic_prompts
from pr_review_agent.prompts.reviewer import SYSTEM_PROMPT as REVIEWER_SYSTEM, refinement_user_prompt

_HEDGE_WORDS = ("may", "might", "could", "possibly", "potentially")
_HEDGE_RE = re.compile(r"\b(" + "|".join(_HEDGE_WORDS) + r")\b", re.IGNORECASE)

_MAX_REFINEMENTS = 3
_BORDERLINE_MIN = 0.4


def _cap_severity_if_hedged(finding: Finding) -> Finding:
    if finding.severity in ("major", "blocking") and _HEDGE_RE.search(finding.finding):
        return finding.model_copy(update={"severity": "minor"})
    return finding


def _heuristic_evidence_check(
    finding: Finding,
    diff_positions,
    context_files: list[ContextFileSelection],
    changed_symbols,
) -> tuple[bool, object]:
    if not finding.evidence.strip():
        return False, None
    known_files = {s.file for s in context_files} | {sym.file for sym in changed_symbols}
    if finding.file not in known_files:
        return False, None
    if finding.line is None:
        return True, None
    return True, find_diff_position(diff_positions, finding.file, finding.line)


async def _validate_one(
    finding: Finding,
    state: PRReviewState,
) -> ValidatedFinding:
    finding = _cap_severity_if_hedged(finding)
    evidence_grounded, diff_position = _heuristic_evidence_check(
        finding,
        state.get("diff_positions", []),
        state.get("context_files", []),
        state.get("changed_symbols", []),
    )

    if not evidence_grounded:
        return ValidatedFinding(
            finding=finding,
            verdict=CriticVerdict(
                evidence_grounded=False,
                respects_repo_context=False,
                actionable=False,
                confidence=0.0,
            ),
            publish=False,
            downgrade_to_summary=False,
            diff_position=None,
        )

    user = critic_prompts.user_prompt(finding, state["repository_context"])
    judgment: CriticJudgment = await complete_structured(
        CriticJudgment, critic_prompts.SYSTEM_PROMPT, user
    )

    severity_sane = not (finding.severity == "blocking" and not finding.evidence.strip())
    verdict = CriticVerdict(
        evidence_grounded=True,
        respects_repo_context=judgment.respects_repo_context,
        actionable=judgment.actionable,
        confidence=judgment.confidence,
        refinement_suggestion=judgment.refinement_suggestion,
    )
    publish = (
        verdict.respects_repo_context
        and verdict.actionable
        and severity_sane
        and verdict.confidence >= settings.critic_confidence_threshold
    )
    downgrade = publish and diff_position is None

    return ValidatedFinding(
        finding=finding,
        verdict=verdict,
        publish=publish and not downgrade,
        downgrade_to_summary=downgrade,
        diff_position=diff_position,
    )


async def _try_refine(vf: ValidatedFinding, state: PRReviewState) -> tuple[ValidatedFinding, dict]:
    """Produce a strengthened version of a borderline finding and re-validate it."""
    suggestion = vf.verdict.refinement_suggestion or "Provide a more specific evidence quote and confirm the exact line number."
    user = refinement_user_prompt(vf.finding, suggestion)
    refined: RefinedFinding = await complete_structured(RefinedFinding, REVIEWER_SYSTEM, user)
    refined_finding = Finding(
        file=refined.file,
        line=refined.line,
        dimension=refined.dimension,
        finding=refined.finding,
        evidence=refined.evidence,
        severity=refined.severity,
    )
    new_vf = await _validate_one(refined_finding, state)
    outcome = "published" if (new_vf.publish or new_vf.downgrade_to_summary) else "filtered"
    return new_vf, {
        "original_finding": vf.finding.finding[:100],
        "concern": suggestion[:100],
        "was_refined": True,
        "outcome": outcome,
    }


async def _validate_all(state: PRReviewState) -> tuple[list[ValidatedFinding], list[dict]]:
    validated = [await _validate_one(f, state) for f in state.get("findings", [])]

    threshold = settings.critic_confidence_threshold
    refinement_notes: list[dict] = []
    refinement_count = 0

    for i, vf in enumerate(validated):
        if refinement_count >= _MAX_REFINEMENTS:
            break
        v = vf.verdict
        if (
            not vf.publish
            and not vf.downgrade_to_summary
            and v.evidence_grounded
            and v.actionable
            and v.respects_repo_context
            and _BORDERLINE_MIN <= v.confidence < threshold
        ):
            new_vf, note = await _try_refine(vf, state)
            validated[i] = new_vf
            refinement_notes.append(note)
            refinement_count += 1

    return validated, refinement_notes


def run(state: PRReviewState) -> PRReviewState:
    validated_findings, refinement_notes = asyncio.run(_validate_all(state))
    return {
        **state,
        "validated_findings": validated_findings,
        "critic_refinement_notes": refinement_notes,
        "phase_status": {**state.get("phase_status", {}), "critic": "done"},
    }
