from pathlib import Path

from app.config import settings
from app.pipeline.blast_radius.queries import (
    find_callees,
    find_callers,
    find_docs,
    find_related_components,
    find_tests,
    list_doc_files,
    symbol_ref,
)
from app.pipeline.blast_radius.repo_graph import build_repo_graph, find_symbol_node
from app.schemas.blast_radius import BlastRadius, BlastRadiusEntry
from app.schemas.diff_analysis import ChangedSymbol


def compute_blast_radius(
    root: Path, changed_symbols: list[ChangedSymbol], max_depth: int | None = None
) -> BlastRadius:
    depth = max_depth if max_depth is not None else settings.blast_radius_max_depth
    graph, truncated = build_repo_graph(root)
    doc_files = list_doc_files(root)

    entries: list[BlastRadiusEntry] = []
    for cs in changed_symbols:
        if cs.symbol_type in ("import", "variable"):
            continue

        node_id = find_symbol_node(graph, cs.file, cs.symbol_name, near_line=cs.start_line)
        if node_id is None:
            entries.append(BlastRadiusEntry(symbol=cs.symbol_name, file=cs.file, call_distance=0))
            continue

        callers = [(n, d) for n, d in find_callers(graph, node_id, depth)]
        callees = [(n, d) for n, d in find_callees(graph, node_id, depth)]
        related = find_related_components(graph, node_id, depth)
        tests = find_tests(graph, node_id, depth)

        entries.append(
            BlastRadiusEntry(
                symbol=cs.symbol_name,
                file=cs.file,
                callers=[symbol_ref(graph, n, "caller") for n, _ in callers],
                callees=[symbol_ref(graph, n, "callee") for n, _ in callees],
                related_components=[symbol_ref(graph, n, "sibling") for n in related],
                tests=[symbol_ref(graph, n, "test") for n in tests],
                docs=find_docs(root, cs.symbol_name, doc_files),
                call_distance=min((d for _, d in callers), default=0),
            )
        )

    return BlastRadius(
        entries=entries,
        graph_node_count=graph.number_of_nodes(),
        graph_truncated=truncated,
    )
