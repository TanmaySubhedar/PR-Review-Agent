import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.github.client import GitHubClient

logger = logging.getLogger(__name__)
from app.pipeline.blast_radius.engine import compute_blast_radius
from app.pipeline.context_readers import read_all_contexts
from app.pipeline.context_retrieval import select_context_files
from app.pipeline.context_synthesis import synthesize_repository_context
from app.pipeline.critic_agent import score_findings
from app.pipeline.diff_analysis import FileDiff, analyze_diff, refine_risk_with_blast_radius
from app.pipeline.publisher import publish_review
from app.pipeline.review_agent import generate_findings
from app.schemas.blast_radius import BlastRadius
from app.schemas.context_package import ContextPackage
from app.schemas.diff_analysis import DiffAnalysis
from app.schemas.pr_event import PREvent
from app.schemas.repository_context import RepositoryContext
from app.schemas.review_finding import ReviewFinding
from app.schemas.scored_finding import ScoredFinding

PhaseCallback = Callable[[str, str], None]  # (phase_name, status) -> None

_SEVERITY_RANK = {"info": 0, "minor": 1, "major": 2, "blocking": 3}


def _recalibrate_risk(blast_risk: str, scored_findings: list[ScoredFinding]) -> str:
    """Blend blast-radius risk with actual finding severity.

    Blast radius alone over-fires on PRs that touch high-fan-in components
    but only make additive/cosmetic changes. Once the critic has scored
    findings we have ground-truth evidence — use it to cap the label.

    Rules (top-to-bottom, first match wins):
      - blocking finding           → always high
      - major finding              → high if blast=high, else medium
      - minor/info + blast=high    → medium  (downgrade)
      - minor/info + blast=medium  → low
      - no surviving findings      → low
    """
    live = [sf for sf in scored_findings if sf.publish or sf.downgrade_to_summary]
    if not live:
        return "low"
    top = max(_SEVERITY_RANK[sf.finding.severity] for sf in live)
    if top >= _SEVERITY_RANK["blocking"]:
        return "high"
    if top >= _SEVERITY_RANK["major"]:
        return blast_risk if blast_risk == "high" else "medium"
    if blast_risk == "high":
        return "medium"
    if blast_risk == "medium":
        return "low"
    return "low"


@dataclass
class PipelineResult:
    diff_analysis: DiffAnalysis
    blast_radius: BlastRadius
    context_package: ContextPackage
    repository_context: RepositoryContext
    findings: list[ReviewFinding]
    scored_findings: list[ScoredFinding]
    publish_result: dict
    change_summary: str
    suggested_pr_description: str


def _noop_callback(phase: str, status: str) -> None:
    return None


async def run_review_pipeline(
    review_run_id: str,
    pr_event: PREvent,
    file_diffs: list[FileDiff],
    workspace_root: Path,
    github_client: GitHubClient,
    on_phase: PhaseCallback = _noop_callback,
    previous_findings: list[ReviewFinding] | None = None,
    previous_fingerprints: list[str | None] | None = None,
) -> PipelineResult:
    """Runs phases 2-9 of the architecture (ingestion/phase 1 already happened
    to produce `pr_event`). `workspace_root` is a checked-out copy of the PR
    head - decoupled from *how* it was obtained (real shallow clone in
    production via app.pipeline.blast_radius.workspace.cloned_pr_head, or a
    fixture directory in tests) so this function is fully unit-testable.

    `previous_findings` are the published findings from the most recent prior
    review run on this same PR, if any - passing them lets the review agent
    compare against what it said last time instead of re-deriving everything
    from scratch on every push."""

    run_tag = f"[{review_run_id[:8]}] [{pr_event.repo_full_name}#{pr_event.pr_number}]"
    logger.info("%s pipeline started — %d file(s) changed", run_tag, len(file_diffs))

    on_phase("diff_analysis", "running")
    logger.info("%s [1/7] DIFF ANALYSIS starting", run_tag)
    t = time.monotonic()
    diff_analysis = analyze_diff(review_run_id, file_diffs)
    on_phase("diff_analysis", "done")
    logger.info("%s [1/7] DIFF ANALYSIS done in %.1fs — %d changed symbol(s), risk=%s",
                run_tag, time.monotonic() - t, len(diff_analysis.changed_symbols), diff_analysis.risk_level)

    on_phase("blast_radius", "running")
    logger.info("%s [2/7] BLAST RADIUS starting", run_tag)
    t = time.monotonic()
    blast_radius = compute_blast_radius(workspace_root, diff_analysis.changed_symbols)
    diff_analysis = refine_risk_with_blast_radius(diff_analysis, blast_radius)
    on_phase("blast_radius", "done")
    logger.info("%s [2/7] BLAST RADIUS done in %.1fs — %d entries, risk refined to %s",
                run_tag, time.monotonic() - t, len(blast_radius.entries), diff_analysis.risk_level)

    on_phase("context_retrieval", "running")
    logger.info("%s [3/7] CONTEXT RETRIEVAL starting", run_tag)
    t = time.monotonic()
    selections = select_context_files(diff_analysis, blast_radius)
    pr_summary = f"{pr_event.title}\n{pr_event.description}".strip()
    reader_outputs = await read_all_contexts(workspace_root, selections, pr_summary)
    context_package = ContextPackage(selections=selections, reader_outputs=reader_outputs)
    on_phase("context_retrieval", "done")
    logger.info("%s [3/7] CONTEXT RETRIEVAL done in %.1fs — %d file(s) read",
                run_tag, time.monotonic() - t, len(reader_outputs))

    on_phase("synthesis", "running")
    logger.info("%s [4/7] SYNTHESIS starting", run_tag)
    t = time.monotonic()
    added_symbols = {cs.symbol_name for cs in diff_analysis.changed_symbols if cs.change_type == "added"}
    repository_context = synthesize_repository_context(blast_radius, reader_outputs, added_symbols)
    on_phase("synthesis", "done")
    logger.info("%s [4/7] SYNTHESIS done in %.1fs — %d risk area(s)",
                run_tag, time.monotonic() - t, len(repository_context.risk_areas))

    on_phase("review", "running")
    logger.info("%s [5/7] REVIEW AGENT starting (LLM call)", run_tag)
    t = time.monotonic()
    review_response = await generate_findings(
        pr_event, file_diffs, diff_analysis, repository_context,
        previous_findings=previous_findings,
        previous_fingerprints=previous_fingerprints,
    )
    findings = review_response.findings
    on_phase("review", "done")
    logger.info("%s [5/7] REVIEW AGENT done in %.1fs — %d finding(s) generated",
                run_tag, time.monotonic() - t, len(findings))

    on_phase("critic", "running")
    logger.info("%s [6/7] CRITIC starting (LLM call)", run_tag)
    t = time.monotonic()
    scored_findings = await score_findings(findings, diff_analysis, context_package, repository_context)
    diff_analysis.risk_level = _recalibrate_risk(diff_analysis.risk_level, scored_findings)
    on_phase("critic", "done")
    published  = sum(1 for sf in scored_findings if sf.publish)
    summarized = sum(1 for sf in scored_findings if sf.downgrade_to_summary)
    discarded  = sum(1 for sf in scored_findings if not sf.publish and not sf.downgrade_to_summary)
    logger.info("%s [6/7] CRITIC done in %.1fs — %d published, %d summarized, %d discarded | final risk=%s",
                run_tag, time.monotonic() - t, published, summarized, discarded, diff_analysis.risk_level)

    on_phase("publish", "running")
    logger.info("%s [7/7] PUBLISH starting", run_tag)
    t = time.monotonic()
    publish_result = publish_review(
        github_client, pr_event, diff_analysis, repository_context, scored_findings, review_response.change_summary
    )
    on_phase("publish", "done")
    logger.info("%s [7/7] PUBLISH done in %.1fs — %d inline comment(s) posted",
                run_tag, time.monotonic() - t, publish_result.get("inline_comments", 0))

    logger.info("%s pipeline complete — final risk=%s", run_tag, diff_analysis.risk_level)

    return PipelineResult(
        diff_analysis=diff_analysis,
        blast_radius=blast_radius,
        context_package=context_package,
        repository_context=repository_context,
        findings=findings,
        scored_findings=scored_findings,
        publish_result=publish_result,
        change_summary=review_response.change_summary,
        suggested_pr_description=review_response.suggested_pr_description,
    )
