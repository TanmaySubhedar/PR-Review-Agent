from app.config import settings
from app.schemas.blast_radius import BlastRadius
from app.schemas.context_package import ContextFileSelection
from app.schemas.diff_analysis import DiffAnalysis

# Ranking weights follow the architecture doc's stated order: call distance ->
# dependency strength -> test coverage -> same module/package -> historical
# relevance. "historical_relevance" has no signal in v1 (would need git-blame
# / review-history mining) and is intentionally left unused rather than faked.
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
    diff_analysis: DiffAnalysis, blast_radius: BlastRadius, max_files: int | None = None
) -> list[ContextFileSelection]:
    max_files = max_files if max_files is not None else settings.blast_radius_max_files
    best: dict[str, ContextFileSelection] = {}

    def offer(file: str, reason: str, score: float) -> None:
        existing = best.get(file)
        if existing is None or score > existing.score:
            best[file] = ContextFileSelection(file=file, selection_reason=reason, score=score)

    for symbol in diff_analysis.changed_symbols:
        offer(symbol.file, "changed_file", _BASE_SCORE["changed_file"])

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
