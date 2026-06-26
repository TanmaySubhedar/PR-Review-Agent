from app.schemas.blast_radius import BlastRadius
from app.schemas.context_package import ReaderOutput
from app.schemas.repository_context import RepositoryContext


def _service_name(file_path: str) -> str:
    return file_path.split("/", 1)[0] if "/" in file_path else file_path


def synthesize_repository_context(
    blast_radius: BlastRadius,
    reader_outputs: list[ReaderOutput],
    added_symbol_names: set[str] | None = None,
) -> RepositoryContext:
    """Deterministic merge of the blast-radius graph + reader outputs.

    Synthesis stays non-LLM by design: the readers (phase 5) already did the
    LLM reasoning per file, and the review agent (phase 7) is the next LLM
    call - inserting a third LLM hop here would add cost/latency without a
    clear question only an LLM could answer, since this phase is pure
    aggregation of already-structured data.
    """
    affected_components: set[str] = set()
    affected_services: set[str] = set()
    affected_tests: set[str] = set()
    risk_areas: list[str] = []

    _MAX_CALLER_NAMES = 5
    _MIN_FAN_IN_FOR_RISK = 2  # single caller is low noise; only flag fan-in >= 2
    _added = added_symbol_names or set()

    for entry in blast_radius.entries:
        all_refs = entry.callers + entry.callees + entry.related_components
        affected_components.update(ref.symbol_name for ref in all_refs)
        affected_services.update(_service_name(ref.file) for ref in all_refs)
        affected_tests.update(ref.file for ref in entry.tests)

        # exclude callers that are themselves newly added in this PR —
        # new-to-new calls don't represent existing code at risk
        if entry.symbol in _added:
            continue
        caller_names = sorted({ref.symbol_name for ref in entry.callers if ref.symbol_name not in _added})
        if len(caller_names) >= _MIN_FAN_IN_FOR_RISK:
            shown = caller_names[:_MAX_CALLER_NAMES]
            remainder = len(caller_names) - len(shown)
            names_str = ", ".join(shown) + (f" …+{remainder} more" if remainder else "")
            risk_areas.append(
                f"{entry.symbol} is called by {len(caller_names)} component(s) "
                f"({names_str}); failures here cascade to all of them."
            )
        if not entry.tests and len(caller_names) >= _MIN_FAN_IN_FOR_RISK:
            risk_areas.append(f"{entry.symbol} has no test coverage reachable in its call graph.")

    # reader.risks are generic LLM-generated per-file statements already
    # included in the review agent's context — no need to repeat them in the
    # summary body where they add noise without actionability.

    if blast_radius.graph_truncated:
        risk_areas.append(
            "Blast-radius analysis was truncated (repo larger than the configured file cap) - "
            "this review may be missing some affected components."
        )

    # de-dupe while preserving order
    risk_areas = list(dict.fromkeys(risk_areas))

    return RepositoryContext(
        affected_components=sorted(affected_components),
        affected_services=sorted(affected_services),
        affected_tests=sorted(affected_tests),
        architecture_constraints=[],
        risk_areas=risk_areas,
    )
