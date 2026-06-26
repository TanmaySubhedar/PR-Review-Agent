"""Graph state — the typed dict that flows between all pipeline nodes."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, TypedDict

from pr_review_agent.models.domain import (
    BlastRadius,
    ContextFileSelection,
    DiffHunk,
    DiffPosition,
    FileDiff,
    FileSummary,
    FileDispatchDecision,
    Finding,
    PRMetadata,
    RepositoryContext,
    Symbol,
    ValidatedFinding,
)


class PRReviewState(TypedDict, total=False):
    # ---- bootstrap inputs -----------------------------------------------
    repo_full_name: str
    pr_number: int
    review_run_id: str

    # ---- ingest node ----------------------------------------------------
    pr_metadata: PRMetadata
    file_diffs: list[FileDiff]        # per-file diffs with source bytes
    raw_diff: str                      # concatenated unified diff as plain text
    repo_path: Path                    # shallow-cloned PR head on disk

    # ---- symbols node ---------------------------------------------------
    parsed_hunks: list[DiffHunk]       # structured view of every @@ hunk
    changed_symbols: list[Symbol]      # symbols whose lines overlap the diff
    risk_level: Literal["low", "medium", "high"]
    risk_score: int
    risk_factors: list[str]
    diff_positions: list[DiffPosition] # GitHub inline-comment anchors

    # ---- graphify node --------------------------------------------------
    graphify_ready: bool               # True once the repo graph is built
    graphify_graph_rebuilt: bool       # True = fresh build, False = reused cached graph
    blast_radius: BlastRadius
    blast_radius_query_trace: list[dict]  # trace of tool calls made by blast-radius agent

    # ---- context node ---------------------------------------------------
    context_files: list[ContextFileSelection]  # ranked file selection

    # ---- readers node ---------------------------------------------------
    dispatch_decision: FileDispatchDecision  # which files were selected + focus questions
    context_file_contents: dict[str, str]    # file path → raw text (clipped)
    file_summaries: list[FileSummary]        # LLM summaries per context file

    # ---- synthesizer node -----------------------------------------------
    repository_context: RepositoryContext

    # ---- reviewer node --------------------------------------------------
    findings: list[Finding]

    # ---- critic node ----------------------------------------------------
    validated_findings: list[ValidatedFinding]
    critic_refinement_notes: list[dict]  # borderline findings that were refined

    # ---- carry-forward from prior run -----------------------------------
    previous_findings: list[Finding] | None

    # ---- housekeeping ---------------------------------------------------
    phase_status: dict[str, str]   # phase_name → "running"|"done"|"failed"
    error: str | None
