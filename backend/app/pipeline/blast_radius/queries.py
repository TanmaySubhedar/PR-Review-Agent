import re
from pathlib import Path

import networkx as nx

from app.pipeline.blast_radius.repo_graph import IGNORED_DIR_NAMES
from app.schemas.blast_radius import DocRef, SymbolRef

TEST_PATH_RE = re.compile(
    r"(^|/)(tests?/|__tests__/)|(^|/)test_[^/]+\.py$|_test\.py$|\.(test|spec)\.[jt]sx?$"
)
DOC_EXTENSIONS = (".md", ".mdx", ".rst", ".txt")


def symbol_ref(graph: nx.DiGraph, node_id: str, relationship: str) -> SymbolRef:
    data = graph.nodes[node_id]
    return SymbolRef(
        file=data["file"],
        symbol_name=data["name"],
        line=data["start_line"],
        relationship=relationship,
    )


def _bfs_symbol_nodes(graph: nx.DiGraph, start: str, edge_kind: str, reverse: bool, max_depth: int) -> dict[str, int]:
    """BFS over `kind == edge_kind` edges (in either direction), returning
    {node_id: distance} for symbol nodes reached within max_depth hops."""
    distances: dict[str, int] = {}
    frontier = [start]
    seen = {start}
    depth = 0
    while frontier and depth < max_depth:
        depth += 1
        next_frontier = []
        for node in frontier:
            neighbors = graph.predecessors(node) if reverse else graph.successors(node)
            for neighbor in neighbors:
                edge_data = graph.get_edge_data(neighbor, node) if reverse else graph.get_edge_data(node, neighbor)
                if edge_data is None or edge_data.get("kind") != edge_kind:
                    continue
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                if graph.nodes[neighbor].get("kind") == "symbol":
                    distances[neighbor] = depth
                next_frontier.append(neighbor)
        frontier = next_frontier
    return distances


def find_callers(graph: nx.DiGraph, node_id: str, max_depth: int) -> list[tuple[str, int]]:
    # Exclude test files — they call production code to verify it, not to depend
    # on it at runtime. Counting them as callers inflates fan-in and produces
    # misleading "failures cascade to test_foo" risk area bullets.
    return [
        (nid, depth)
        for nid, depth in _bfs_symbol_nodes(graph, node_id, "calls", reverse=True, max_depth=max_depth).items()
        if not TEST_PATH_RE.search(graph.nodes[nid]["file"])
    ]


def find_callees(graph: nx.DiGraph, node_id: str, max_depth: int) -> list[tuple[str, int]]:
    return list(_bfs_symbol_nodes(graph, node_id, "calls", reverse=False, max_depth=max_depth).items())


def find_related_components(graph: nx.DiGraph, node_id: str, max_depth: int) -> list[str]:
    """Same-module siblings plus symbols in modules linked by import edges."""
    file_path = graph.nodes[node_id]["file"]
    related = [
        n
        for n in graph.successors(file_path)
        if graph.nodes[n].get("kind") == "symbol" and n != node_id
    ]

    seen_files = {file_path}
    frontier = [file_path]
    depth = 0
    while frontier and depth < max_depth:
        depth += 1
        next_frontier = []
        for f in frontier:
            for neighbor, edge_data in list(graph.adj[f].items()) + [
                (p, graph.get_edge_data(p, f)) for p in graph.predecessors(f)
            ]:
                if graph.nodes.get(neighbor, {}).get("kind") != "module":
                    continue
                if edge_data is None or edge_data.get("kind") != "imports":
                    continue
                if neighbor in seen_files:
                    continue
                seen_files.add(neighbor)
                next_frontier.append(neighbor)
                related.extend(
                    n for n in graph.successors(neighbor) if graph.nodes[n].get("kind") == "symbol"
                )
        frontier = next_frontier
    return related


def find_tests(graph: nx.DiGraph, node_id: str, max_depth: int) -> list[str]:
    callers = _bfs_symbol_nodes(graph, node_id, "calls", reverse=True, max_depth=max_depth)
    return [n for n in callers if TEST_PATH_RE.search(graph.nodes[n]["file"])]


def list_doc_files(root: Path) -> list[str]:
    files: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIR_NAMES for part in path.relative_to(root).parts):
            continue
        if path.suffix.lower() in DOC_EXTENSIONS:
            files.append(str(path.relative_to(root)).replace("\\", "/"))
    return sorted(files)


def find_docs(root: Path, symbol_name: str, doc_files: list[str], limit: int = 5) -> list[DocRef]:
    """Best-effort lexical match for the symbol name across doc files. No
    graph edges to walk here (docs aren't parsed into the call graph), so
    this is intentionally a cheap text search, not a peer of the
    caller/callee queries above."""
    refs: list[DocRef] = []
    for file_path in doc_files:
        try:
            text = (root / file_path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if symbol_name in line:
                refs.append(DocRef(file=file_path, line=i, match_snippet=line.strip()[:200]))
                if len(refs) >= limit:
                    return refs
    return refs
