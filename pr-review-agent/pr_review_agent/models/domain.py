"""Domain models for the review pipeline. Self-contained — no backend dependency."""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# GitHub / PR metadata
# ---------------------------------------------------------------------------

class CommitInfo(BaseModel):
    sha: str
    message: str
    author: str


class PRMetadata(BaseModel):
    repo_full_name: str
    pr_number: int
    pr_url: str
    title: str
    description: str = ""
    base_sha: str
    head_sha: str
    base_ref: str
    head_ref: str
    clone_url: str
    changed_files: list[str] = []
    commits: list[CommitInfo] = []


# ---------------------------------------------------------------------------
# Diff models
# ---------------------------------------------------------------------------

@dataclass
class FileDiff:
    """Per-file diff inputs. Dataclass so tree-sitter nodes can mutate freely."""
    file: str
    patch: str
    status: Literal["added", "modified", "removed", "renamed"] = "modified"
    new_source: bytes | None = None
    old_source: bytes | None = None
    lines_changed: int = field(default=0)


class DiffHunk(BaseModel):
    """One parsed @@ hunk from a unified diff."""
    file: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str       # the raw "@@ -a,b +c,d @@" line
    lines: list[str]  # all lines in this hunk (including +/- prefix)


class DiffPosition(BaseModel):
    """GitHub inline-comment anchor: 1-indexed offset within a file's patch text."""
    file: str
    new_line: int | None
    old_line: int | None
    position: int
    hunk_header: str


# ---------------------------------------------------------------------------
# Symbols
# ---------------------------------------------------------------------------

class Symbol(BaseModel):
    """A named code symbol extracted from a source file."""
    name: str
    file: str
    symbol_type: Literal["function", "class", "method", "import", "variable"]
    start_line: int
    end_line: int
    is_async: bool = False
    param_count: int | None = None
    # Set when the symbol came from a diff — None for symbols in context files
    change_type: Literal["added", "modified", "deleted"] | None = None


# ---------------------------------------------------------------------------
# Blast radius
# ---------------------------------------------------------------------------

class SymbolRef(BaseModel):
    file: str
    symbol_name: str
    line: int
    relationship: Literal["caller", "callee", "sibling", "test", "implements", "imports"]


class DocRef(BaseModel):
    file: str
    line: int | None
    match_snippet: str


class BlastRadiusEntry(BaseModel):
    symbol: str
    file: str
    callers: list[SymbolRef] = []
    callees: list[SymbolRef] = []
    related_components: list[SymbolRef] = []
    tests: list[SymbolRef] = []
    docs: list[DocRef] = []
    call_distance: int = 0


class BlastRadius(BaseModel):
    entries: list[BlastRadiusEntry] = []
    graph_node_count: int = 0
    graph_truncated: bool = False


# ---------------------------------------------------------------------------
# Context selection
# ---------------------------------------------------------------------------

class ContextFileSelection(BaseModel):
    file: str
    selection_reason: Literal[
        "changed_file",
        "direct_caller",
        "direct_callee",
        "dependency_chain",
        "test_coverage",
        "same_module",
        "historical_relevance",
    ]
    score: float


class FileFocusQuestion(BaseModel):
    """A focus question assigned to one file by the dispatch agent."""
    file: str
    question: str


class FileDispatchDecision(BaseModel):
    """LLM dispatch decision: which context files to read and what to focus on."""
    files_to_read: list[str]
    focus_questions: list[FileFocusQuestion]
    skipped_files: list[str]
    reasoning: str


# ---------------------------------------------------------------------------
# File summaries  (LLM reader output)
# ---------------------------------------------------------------------------

class FileSummary(BaseModel):
    """LLM-generated summary for one context file."""
    file: str
    purpose: str
    relevance: str
    risks: list[str] = []


# ---------------------------------------------------------------------------
# Repository context  (deterministic synthesis)
# ---------------------------------------------------------------------------

class RepositoryContext(BaseModel):
    affected_components: list[str] = []
    affected_services: list[str] = []
    affected_tests: list[str] = []
    architecture_constraints: list[str] = []
    risk_areas: list[str] = []


# ---------------------------------------------------------------------------
# Review findings
# ---------------------------------------------------------------------------

class Finding(BaseModel):
    """A single review finding produced by the reviewer LLM."""
    file: str
    line: int | None = None
    dimension: Literal["correctness", "architecture", "testing", "maintainability", "intent"]
    finding: str
    evidence: str
    severity: Literal["info", "minor", "major", "blocking"]


class FindingsResponse(BaseModel):
    """Structured-output wrapper for the reviewer LLM call."""
    findings: list[Finding]


class RefinedFinding(BaseModel):
    """A strengthened version of a borderline finding requested by the critic refinement loop."""
    file: str
    line: int | None = None
    dimension: Literal["correctness", "architecture", "testing", "maintainability", "intent"]
    finding: str
    evidence: str
    severity: Literal["info", "minor", "major", "blocking"]


# ---------------------------------------------------------------------------
# Critic / validated findings
# ---------------------------------------------------------------------------

class CriticJudgment(BaseModel):
    """Structured output returned by the critic LLM for one finding."""
    respects_repo_context: bool
    actionable: bool
    confidence: float
    refinement_suggestion: str  # empty string when not applicable


class CriticVerdict(BaseModel):
    """Full critic assessment stored with each validated finding."""
    evidence_grounded: bool
    respects_repo_context: bool
    actionable: bool
    confidence: float
    refinement_suggestion: str = ""  # empty string when no suggestion


class ValidatedFinding(BaseModel):
    """A finding that has passed (or failed) the critic gate."""
    finding: Finding
    verdict: CriticVerdict
    publish: bool
    downgrade_to_summary: bool = False
    diff_position: DiffPosition | None = None


# ---------------------------------------------------------------------------
# Internal diff-analysis aggregate  (not in graph state directly)
# ---------------------------------------------------------------------------

class _DiffAnalysis(BaseModel):
    """Internal aggregate used by the symbols node before writing to state."""
    review_run_id: str
    changed_symbols: list[Symbol]
    parsed_hunks: list[DiffHunk]
    risk_level: Literal["low", "medium", "high"]
    risk_score: int = 0
    risk_factors: list[str] = []
    diff_positions: list[DiffPosition] = []
