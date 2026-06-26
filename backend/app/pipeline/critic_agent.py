import logging
import re

from app.config import settings
from app.github.diff_positions import find_diff_position
from app.llm.azure_client import complete_structured
from app.llm.prompts import load_prompt
from app.schemas.context_package import ContextPackage
from app.schemas.critic_judgment import CriticJudgment
from app.schemas.diff_analysis import DiffAnalysis
from app.schemas.repository_context import RepositoryContext
from app.schemas.review_finding import ReviewFinding
from app.schemas.scored_finding import CriticScore, ScoredFinding

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = load_prompt("critic_agent_system.md")

HEDGE_WORDS = ("may", "might", "could", "possibly", "potentially")
_HEDGE_LANGUAGE_RE = re.compile(r"\b(" + "|".join(HEDGE_WORDS) + r")\b", re.IGNORECASE)

# Findings with confidence in [_BORDERLINE_MIN, threshold) get one refinement
# attempt; findings below _BORDERLINE_MIN are too weak to bother refining.
_BORDERLINE_MIN = 0.4
_MAX_REFINEMENTS = 3

_REFINEMENT_SYSTEM = (
    "You are a code review refiner. A finding narrowly missed the quality bar because its "
    "evidence lacked specificity. Produce a tighter version with more concrete evidence.\n"
    "Rules:\n"
    "- Do not invent new issues — only strengthen the evidence for the existing finding\n"
    "- Quote the exact line(s) from the diff that demonstrate the problem\n"
    "- If you cannot cite concrete evidence, reproduce the finding unchanged\n"
    "- Keep the same file and dimension; downgrade severity only if the evidence demands it"
)


def _cap_severity_if_hedged(finding: ReviewFinding) -> ReviewFinding:
    """Deterministic backstop: a major/blocking finding whose description is
    hedged ('may cause', 'could lead to') is a risk hypothesis, not a proven
    failure — cap it to minor rather than discard it outright."""
    if finding.severity in ("major", "blocking") and _HEDGE_LANGUAGE_RE.search(finding.finding):
        return finding.model_copy(update={"severity": "minor"})
    return finding


def _heuristic_evidence_check(
    finding: ReviewFinding, diff_analysis: DiffAnalysis, context_package: ContextPackage
):
    """Code-level gate: does the finding cite a file/line that actually exists
    in the diff? Runs before the LLM critic so we never ask an LLM to judge
    a finding that references a non-existent location.

    Returns (evidence_grounded, diff_position-or-None). diff_position is None
    when grounded but not anchorable inline (caller downgrades to summary)."""
    if not finding.evidence.strip():
        return False, None

    known_files = {s.file for s in context_package.selections} | {
        cs.file for cs in diff_analysis.changed_symbols
    }
    if finding.file not in known_files:
        return False, None

    if finding.line is None:
        return True, None

    return True, find_diff_position(diff_analysis.diff_positions, finding.file, finding.line)


async def score_finding(
    finding: ReviewFinding,
    diff_analysis: DiffAnalysis,
    context_package: ContextPackage,
    repository_context: RepositoryContext,
) -> ScoredFinding:
    finding = _cap_severity_if_hedged(finding)
    evidence_grounded, diff_position = _heuristic_evidence_check(finding, diff_analysis, context_package)

    if not evidence_grounded:
        return ScoredFinding(
            finding=finding,
            critic=CriticScore(
                evidence_grounded=False, respects_repo_context=False, actionable=False, confidence=0.0
            ),
            publish=False,
            downgrade_to_summary=False,
            diff_position=None,
        )

    user_prompt = (
        f"Finding:\nfile={finding.file} line={finding.line} dimension={finding.dimension} "
        f"severity={finding.severity}\nfinding={finding.finding}\nevidence={finding.evidence}\n\n"
        f"Repository context:\n"
        f"affected_components={repository_context.affected_components}\n"
        f"affected_services={repository_context.affected_services}\n"
        f"affected_tests={repository_context.affected_tests}\n"
        f"architecture_constraints={repository_context.architecture_constraints}\n"
        f"risk_areas={repository_context.risk_areas}"
    )
    judgment = await complete_structured(CriticJudgment, _SYSTEM_PROMPT, user_prompt)

    severity_sane = not (finding.severity == "blocking" and not finding.evidence.strip())

    critic_score = CriticScore(
        evidence_grounded=True,
        respects_repo_context=judgment.respects_repo_context,
        actionable=judgment.actionable,
        confidence=judgment.confidence,
        refinement_suggestion=judgment.refinement_suggestion,
    )

    publish = (
        critic_score.respects_repo_context
        and critic_score.actionable
        and severity_sane
        and critic_score.confidence >= settings.critic_confidence_threshold
    )
    downgrade = publish and diff_position is None

    return ScoredFinding(
        finding=finding,
        critic=critic_score,
        publish=publish and not downgrade,
        downgrade_to_summary=downgrade,
        diff_position=diff_position,
    )


def _refinement_user_prompt(finding: ReviewFinding, suggestion: str) -> str:
    return (
        f"Original finding:\n"
        f"file={finding.file} line={finding.line}\n"
        f"dimension={finding.dimension} severity={finding.severity}\n"
        f"finding={finding.finding}\n"
        f"evidence={finding.evidence}\n\n"
        f"Critic feedback: {suggestion}\n\n"
        f"Produce a refined version with stronger, more concrete evidence."
    )


async def _try_refine(
    scored: ScoredFinding,
    diff_analysis: DiffAnalysis,
    context_package: ContextPackage,
    repository_context: RepositoryContext,
) -> ScoredFinding:
    """Ask the LLM to produce a more evidence-grounded version of a borderline
    finding, then re-score it. Returns the original scored finding unchanged if
    refinement fails or makes things worse."""
    suggestion = (
        scored.critic.refinement_suggestion
        or "Provide a more specific evidence quote and confirm the exact line number."
    )
    try:
        refined = await complete_structured(
            ReviewFinding, _REFINEMENT_SYSTEM, _refinement_user_prompt(scored.finding, suggestion)
        )
        new_scored = await score_finding(refined, diff_analysis, context_package, repository_context)
        outcome = "published" if (new_scored.publish or new_scored.downgrade_to_summary) else "filtered"
        logger.info(
            "critic refinement: conf %.2f → %.2f (%s) — %s",
            scored.critic.confidence, new_scored.critic.confidence,
            outcome, scored.finding.finding[:80],
        )
        return new_scored
    except Exception as exc:
        logger.warning("critic refinement failed, keeping original: %s", exc)
        return scored


async def score_findings(
    findings: list[ReviewFinding],
    diff_analysis: DiffAnalysis,
    context_package: ContextPackage,
    repository_context: RepositoryContext,
) -> list[ScoredFinding]:
    scored = [
        await score_finding(f, diff_analysis, context_package, repository_context) for f in findings
    ]

    threshold = settings.critic_confidence_threshold
    refinement_count = 0

    for i, sf in enumerate(scored):
        if refinement_count >= _MAX_REFINEMENTS:
            break
        v = sf.critic
        # Only refine findings that: passed heuristic gates, are clearly
        # actionable and context-respecting, but just missed the confidence bar.
        if (
            not sf.publish
            and not sf.downgrade_to_summary
            and v.evidence_grounded
            and v.actionable
            and v.respects_repo_context
            and _BORDERLINE_MIN <= v.confidence < threshold
        ):
            scored[i] = await _try_refine(sf, diff_analysis, context_package, repository_context)
            refinement_count += 1

    return scored
