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

_SYSTEM_PROMPT = load_prompt("critic_agent_system.md")

HEDGE_WORDS = ("may", "might", "could", "possibly", "potentially")
_HEDGE_LANGUAGE_RE = re.compile(r"\b(" + "|".join(HEDGE_WORDS) + r")\b", re.IGNORECASE)


def _cap_severity_if_hedged(finding: ReviewFinding) -> ReviewFinding:
    """Deterministic backstop for the review agent's own severity-discipline
    instruction: a major/blocking finding whose description is hedged
    ('may', 'could', 'might lead to') is describing a risk category, not a
    proven failure, and gets capped to minor rather than discarded outright -
    the underlying observation can still be useful, just not at that severity."""
    if finding.severity in ("major", "blocking") and _HEDGE_LANGUAGE_RE.search(finding.finding):
        return finding.model_copy(update={"severity": "minor"})
    return finding


def _heuristic_evidence_check(
    finding: ReviewFinding, diff_analysis: DiffAnalysis, context_package: ContextPackage
):
    """Deterministic, non-LLM gate: does this finding cite a file/line and
    evidence text that actually exist? This is the single highest-leverage
    check (it directly prevents posting a comment on a line that doesn't
    exist) so it runs in code rather than being asked of the critic LLM,
    which would add an unreliable extra hop to the one failure mode that
    must not slip through.

    Returns (evidence_grounded, diff_position-or-None). `diff_position` is
    None either when ungrounded, or when grounded but not anchorable inline
    (caller downgrades to a summary comment in that case)."""
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


async def score_findings(
    findings: list[ReviewFinding],
    diff_analysis: DiffAnalysis,
    context_package: ContextPackage,
    repository_context: RepositoryContext,
) -> list[ScoredFinding]:
    return [
        await score_finding(f, diff_analysis, context_package, repository_context) for f in findings
    ]
