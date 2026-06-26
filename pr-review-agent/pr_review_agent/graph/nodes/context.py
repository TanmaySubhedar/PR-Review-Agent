"""Context node: select context files ranked by blast-radius proximity."""

from pr_review_agent.config import settings
from pr_review_agent.graph.state import PRReviewState
from pr_review_agent.models.domain import ContextFileSelection

_BASE_SCORE = {
    "changed_file": 100.0,
    "direct_caller": 80.0,
    "direct_callee": 70.0,
    "test_coverage": 60.0,
    "same_module": 50.0,
    "dependency_chain": 40.0,
    "historical_relevance": 10.0,
}


def select_context_files(
    state: PRReviewState, max_files: int | None = None
) -> list[ContextFileSelection]:
    changed_symbols = state["changed_symbols"]
    blast_radius = state["blast_radius"]
    file_diffs = state.get("file_diffs", [])
    max_files = max_files if max_files is not None else settings.blast_radius_max_files
    best: dict[str, ContextFileSelection] = {}

    def offer(file: str, reason: str, score: float) -> None:
        existing = best.get(file)
        if existing is None or score > existing.score:
            best[file] = ContextFileSelection(file=file, selection_reason=reason, score=score)

    # Always include every changed file directly — this ensures context is never
    # empty when symbol extraction finds nothing (unsupported language, binary, >1MB).
    for fd in file_diffs:
        if fd.status != "removed":
            offer(fd.file, "changed_file", _BASE_SCORE["changed_file"])

    for sym in changed_symbols:
        offer(sym.file, "changed_file", _BASE_SCORE["changed_file"])

    for entry in blast_radius.entries:
        for ref in entry.callers:
            offer(ref.file, "direct_caller", _BASE_SCORE["direct_caller"])
        for ref in entry.callees:
            offer(ref.file, "direct_callee", _BASE_SCORE["direct_callee"])
        for ref in entry.tests:
            offer(ref.file, "test_coverage", _BASE_SCORE["test_coverage"])
        for ref in entry.related_components:
            same_dir = "/" in entry.file and ref.file.rsplit("/", 1)[0] == entry.file.rsplit("/", 1)[0]
            reason = "same_module" if same_dir else "dependency_chain"
            offer(ref.file, reason, _BASE_SCORE[reason])

    ranked = sorted(best.values(), key=lambda s: s.score, reverse=True)
    return ranked[:max_files]


def run(state: PRReviewState) -> PRReviewState:
    context_files = select_context_files(state)
    return {
        **state,
        "context_files": context_files,
        "phase_status": {**state.get("phase_status", {}), "context": "done"},
    }
