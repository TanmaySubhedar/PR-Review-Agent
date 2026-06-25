from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.github.client import GitHubClient
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

    on_phase("diff_analysis", "running")
    diff_analysis = analyze_diff(review_run_id, file_diffs)
    on_phase("diff_analysis", "done")

    on_phase("blast_radius", "running")
    blast_radius = compute_blast_radius(workspace_root, diff_analysis.changed_symbols)
    diff_analysis = refine_risk_with_blast_radius(diff_analysis, blast_radius)
    on_phase("blast_radius", "done")

    on_phase("context_retrieval", "running")
    selections = select_context_files(diff_analysis, blast_radius)
    pr_summary = f"{pr_event.title}\n{pr_event.description}".strip()
    reader_outputs = await read_all_contexts(workspace_root, selections, pr_summary)
    context_package = ContextPackage(selections=selections, reader_outputs=reader_outputs)
    on_phase("context_retrieval", "done")

    on_phase("synthesis", "running")
    repository_context = synthesize_repository_context(blast_radius, reader_outputs)
    on_phase("synthesis", "done")

    on_phase("review", "running")
    review_response = await generate_findings(
        pr_event, file_diffs, diff_analysis, repository_context, previous_findings=previous_findings
    )
    findings = review_response.findings
    on_phase("review", "done")

    on_phase("critic", "running")
    scored_findings = await score_findings(findings, diff_analysis, context_package, repository_context)
    on_phase("critic", "done")

    on_phase("publish", "running")
    publish_result = publish_review(
        github_client, pr_event, diff_analysis, repository_context, scored_findings, review_response.change_summary
    )
    on_phase("publish", "done")

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
