from pathlib import Path

from app.pipeline.blast_radius.engine import compute_blast_radius
from app.pipeline.blast_radius.repo_graph import build_repo_graph, find_symbol_node
from app.schemas.diff_analysis import ChangedSymbol

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "sample_repo"


def test_build_repo_graph_links_calls_and_imports():
    graph, truncated = build_repo_graph(FIXTURE_REPO)
    assert not truncated

    node_id = find_symbol_node(graph, "auth/utils.py", "validate_token")
    assert node_id is not None

    callers = {graph.nodes[n]["file"] for n in graph.predecessors(node_id) if graph.nodes[n].get("kind") == "symbol"}
    assert "auth/middleware.py" in callers
    assert "admin/middleware.py" in callers
    assert "tests/test_auth.py" in callers

    assert graph.has_edge("auth/middleware.py", "auth/utils.py")
    assert graph.get_edge_data("auth/middleware.py", "auth/utils.py")["kind"] == "imports"


def test_compute_blast_radius_for_validate_token():
    changed = [
        ChangedSymbol(
            file="auth/utils.py",
            symbol_name="validate_token",
            symbol_type="function",
            change_type="modified",
            start_line=8,
            end_line=12,
        )
    ]

    result = compute_blast_radius(FIXTURE_REPO, changed, max_depth=3)

    assert len(result.entries) == 1
    entry = result.entries[0]

    caller_files = {c.file for c in entry.callers}
    assert caller_files == {"auth/middleware.py", "admin/middleware.py", "tests/test_auth.py"}

    test_files = {t.file for t in entry.tests}
    assert test_files == {"tests/test_auth.py"}

    callee_names = {c.symbol_name for c in entry.callees}
    assert callee_names == {"decode", "is_expired"}

    doc_files = {d.file for d in entry.docs}
    assert "docs/auth.md" in doc_files


def test_compute_blast_radius_unknown_symbol_returns_empty_entry():
    changed = [
        ChangedSymbol(
            file="auth/utils.py",
            symbol_name="does_not_exist",
            symbol_type="function",
            change_type="added",
            start_line=1,
            end_line=2,
        )
    ]

    result = compute_blast_radius(FIXTURE_REPO, changed)

    assert len(result.entries) == 1
    assert result.entries[0].callers == []
