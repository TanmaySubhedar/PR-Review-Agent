from dataclasses import dataclass, field
from typing import Literal

from app.github.diff_positions import compute_diff_positions, hunk_new_line_ranges
from app.pipeline.symbols import RawSymbol, extract_symbols
from app.schemas.blast_radius import BlastRadius
from app.schemas.diff_analysis import ChangedSymbol, DiffAnalysis

SENSITIVE_PATH_KEYWORDS = (
    "auth",
    "token",
    "security",
    "payment",
    "billing",
    "crypto",
    "password",
    "secret",
    "admin",
    "permission",
    "session",
)

_HIGH_RISK_THRESHOLD = 7
_MEDIUM_RISK_THRESHOLD = 4


def _bucket_score(score: int) -> Literal["low", "medium", "high"]:
    """Single source of truth for score->level cutoffs, shared by the
    diff-only pass and the blast-radius refinement pass so the two phases
    can never disagree about what 'medium' means."""
    if score >= _HIGH_RISK_THRESHOLD:
        return "high"
    if score >= _MEDIUM_RISK_THRESHOLD:
        return "medium"
    return "low"


@dataclass
class FileDiff:
    """The minimal per-file inputs diff analysis needs - deliberately decoupled
    from PyGithub/GitHub so this phase is unit-testable against fixtures and
    swappable for a different VCS later."""

    file: str
    patch: str
    status: Literal["added", "modified", "removed", "renamed"] = "modified"
    new_source: bytes | None = None
    old_source: bytes | None = None
    lines_changed: int = field(default=0)


def _changed_symbols_for_file(file_diff: FileDiff, new_symbols: list[RawSymbol]) -> list[ChangedSymbol]:
    if file_diff.status == "removed" or file_diff.new_source is None:
        if file_diff.old_source is None:
            return []
        return [
            ChangedSymbol(
                file=file_diff.file,
                symbol_name=s.name,
                symbol_type=s.symbol_type,
                change_type="deleted",
                start_line=s.start_line,
                end_line=s.end_line,
            )
            for s in extract_symbols(file_diff.file, file_diff.old_source)
        ]

    if file_diff.status == "added":
        return [
            ChangedSymbol(
                file=file_diff.file,
                symbol_name=s.name,
                symbol_type=s.symbol_type,
                change_type="added",
                start_line=s.start_line,
                end_line=s.end_line,
            )
            for s in new_symbols
        ]

    touched_ranges = hunk_new_line_ranges(file_diff.patch)
    changed: list[ChangedSymbol] = []
    for s in new_symbols:
        overlaps = any(
            s.start_line <= end and start <= s.end_line for start, end in touched_ranges
        )
        if overlaps:
            changed.append(
                ChangedSymbol(
                    file=file_diff.file,
                    symbol_name=s.name,
                    symbol_type=s.symbol_type,
                    change_type="modified",
                    start_line=s.start_line,
                    end_line=s.end_line,
                )
            )
    return changed


def _detect_signature_changes(
    file_diff: FileDiff, changed_symbols: list[ChangedSymbol], new_symbols: list[RawSymbol]
) -> list[str]:
    """Best-effort breaking-change detector: did a modified function/method's
    async-ness or parameter count change? Both are much stronger risk signals
    than the diff's size or the symbol's naming convention - either can break
    every caller regardless of how small the diff looks.

    Matches the new symbol by (name, start_line) - exact, since changed_symbols
    were derived directly from new_symbols - and the old symbol by name with
    closest start_line, since duplicate names across classes/scopes in the
    same file would otherwise collide on a bare-name lookup."""
    if file_diff.status != "modified" or file_diff.old_source is None or file_diff.new_source is None:
        return []

    new_by_identity = {(s.name, s.start_line): s for s in new_symbols}
    old_by_name: dict[str, list[RawSymbol]] = {}
    for s in extract_symbols(file_diff.file, file_diff.old_source):
        old_by_name.setdefault(s.name, []).append(s)

    findings = []
    for cs in changed_symbols:
        if cs.symbol_type not in ("function", "method") or cs.change_type != "modified":
            continue
        new_sym = new_by_identity.get((cs.symbol_name, cs.start_line))
        candidates = old_by_name.get(cs.symbol_name)
        if new_sym is None or not candidates:
            continue
        old_sym = min(candidates, key=lambda s: abs(s.start_line - new_sym.start_line))

        if old_sym.is_async != new_sym.is_async:
            findings.append(f"{cs.symbol_name}() changed between sync and async - likely breaks existing callers")
        elif (
            old_sym.param_count is not None
            and new_sym.param_count is not None
            and old_sym.param_count != new_sym.param_count
        ):
            findings.append(
                f"{cs.symbol_name}() parameter count changed ({old_sym.param_count} -> {new_sym.param_count}) "
                "- likely breaks existing callers"
            )
    return findings


def _score_risk(
    file_diffs: list[FileDiff], changed_symbols: list[ChangedSymbol], signature_changes: list[str]
) -> tuple[int, list[str]]:
    score = 0
    factors: list[str] = []

    sensitive_files = [
        fd.file
        for fd in file_diffs
        if any(kw in fd.file.lower() for kw in SENSITIVE_PATH_KEYWORDS)
    ]
    if sensitive_files:
        score += 3
        factors.append(f"touches sensitive-sounding paths: {', '.join(sensitive_files)}")

    if signature_changes:
        score += len(signature_changes)
        factors.extend(signature_changes)

    deletions = [s for s in changed_symbols if s.change_type == "deleted"]
    if deletions:
        score += min(len(deletions), 3)
        factors.append(f"{len(deletions)} symbol(s) deleted")

    total_lines_changed = sum(fd.lines_changed for fd in file_diffs)
    if total_lines_changed > 200:
        score += 1
        factors.append(f"large diff ({total_lines_changed} lines changed)")

    if len(file_diffs) > 5:
        score += 1
        factors.append(f"{len(file_diffs)} files changed")

    if not changed_symbols:
        factors.append("no recognizable symbols changed (untracked language or non-code diff)")

    return score, factors


def analyze_diff(review_run_id: str, file_diffs: list[FileDiff]) -> DiffAnalysis:
    changed_symbols: list[ChangedSymbol] = []
    diff_positions = []
    signature_changes: list[str] = []
    for fd in file_diffs:
        new_symbols = extract_symbols(fd.file, fd.new_source) if fd.new_source is not None else []
        file_changed_symbols = _changed_symbols_for_file(fd, new_symbols)
        changed_symbols.extend(file_changed_symbols)
        signature_changes.extend(_detect_signature_changes(fd, file_changed_symbols, new_symbols))
        diff_positions.extend(compute_diff_positions(fd.file, fd.patch))

    score, risk_factors = _score_risk(file_diffs, changed_symbols, signature_changes)

    return DiffAnalysis(
        review_run_id=review_run_id,
        changed_symbols=changed_symbols,
        risk_level=_bucket_score(score),
        risk_score=score,
        risk_factors=risk_factors,
        diff_positions=diff_positions,
    )


def refine_risk_with_blast_radius(diff_analysis: DiffAnalysis, blast_radius: BlastRadius) -> DiffAnalysis:
    """Upgrade risk_level once blast-radius data exists.

    Key invariant: only MODIFIED/DELETED symbols drive fan-in risk.  A new
    function that calls other new functions in the same PR looks like fan-in
    from the graph's perspective, but carries no real cascade risk — nothing
    pre-existing depends on it yet.  We exclude symbols whose change_type is
    'added' from the fan-in calculation to avoid inflating risk for purely
    additive PRs."""
    score = diff_analysis.risk_score
    factors: list[str] = list(diff_analysis.risk_factors)

    # only modified/deleted symbols can break existing callers
    added_names = {cs.symbol_name for cs in diff_analysis.changed_symbols if cs.change_type == "added"}
    existing_change_entries = [e for e in blast_radius.entries if e.symbol not in added_names]

    # callers that are themselves newly added don't represent existing dependents
    def _existing_callers(entry):
        return [c for c in entry.callers if c.symbol_name not in added_names]

    max_fan_in = max((len(_existing_callers(e)) for e in existing_change_entries), default=0)
    if max_fan_in >= 5:
        score += 3
    elif max_fan_in >= 2:
        score += 2
    elif max_fan_in == 1:
        score += 1

    untested_but_used = [e for e in existing_change_entries if _existing_callers(e) and not e.tests]
    if untested_but_used:
        score += 1
        names = ", ".join(sorted({e.symbol for e in untested_but_used}))
        factors.append(f"modified symbols with callers but no test coverage: {names}")

    if max_fan_in:
        caller_names = sorted({c.symbol_name for e in existing_change_entries for c in _existing_callers(e)})
        shown = caller_names[:5]
        rest = len(caller_names) - len(shown)
        suffix = f" …+{rest} more" if rest else ""
        factors.append(f"blast radius: up to {max_fan_in} existing caller(s) ({', '.join(shown)}{suffix})")

    return diff_analysis.model_copy(
        update={"risk_level": _bucket_score(score), "risk_score": score, "risk_factors": factors}
    )
