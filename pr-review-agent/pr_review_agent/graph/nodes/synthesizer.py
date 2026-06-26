"""Synthesizer node: deterministic merge of blast-radius graph and file summaries."""

from pr_review_agent.graph.state import PRReviewState
from pr_review_agent.models.domain import BlastRadius, FileSummary, RepositoryContext


def _service_name(file_path: str) -> str:
    return file_path.split("/", 1)[0] if "/" in file_path else file_path


def synthesize_repository_context(
    blast_radius: BlastRadius, file_summaries: list[FileSummary]
) -> RepositoryContext:
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

    for summary in file_summaries:
        risk_areas.extend(summary.risks)

    if blast_radius.graph_truncated:
        risk_areas.append(
            "Blast-radius analysis was truncated (repo larger than the configured file cap) — "
            "this review may be missing some affected components."
        )

    risk_areas = list(dict.fromkeys(risk_areas))

    return RepositoryContext(
        affected_components=sorted(affected_components),
        affected_services=sorted(affected_services),
        affected_tests=sorted(affected_tests),
        architecture_constraints=[],
        risk_areas=risk_areas,
    )


def run(state: PRReviewState) -> PRReviewState:
    repository_context = synthesize_repository_context(
        state["blast_radius"],
        state.get("file_summaries", []),
    )
    return {
        **state,
        "repository_context": repository_context,
        "phase_status": {**state.get("phase_status", {}), "synthesizer": "done"},
    }
