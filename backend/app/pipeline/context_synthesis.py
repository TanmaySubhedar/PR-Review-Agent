from app.schemas.blast_radius import BlastRadius
from app.schemas.context_package import ReaderOutput
from app.schemas.repository_context import RepositoryContext


def _service_name(file_path: str) -> str:
    return file_path.split("/", 1)[0] if "/" in file_path else file_path


def synthesize_repository_context(
    blast_radius: BlastRadius, reader_outputs: list[ReaderOutput]
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

    for entry in blast_radius.entries:
        all_refs = entry.callers + entry.callees + entry.related_components
        affected_components.update(ref.symbol_name for ref in all_refs)
        affected_services.update(_service_name(ref.file) for ref in all_refs)
        affected_tests.update(ref.file for ref in entry.tests)

        if entry.callers:
            caller_names = sorted({ref.symbol_name for ref in entry.callers})
            risk_areas.append(
                f"{entry.symbol} is called by {len(caller_names)} component(s) "
                f"({', '.join(caller_names)}); failures here cascade to all of them."
            )
        if not entry.tests:
            risk_areas.append(f"{entry.symbol} has no test coverage reachable in its call graph.")

    for reader in reader_outputs:
        risk_areas.extend(reader.risks)

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
