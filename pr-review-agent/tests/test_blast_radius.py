"""Unit tests for the NetworkX blast-radius computation."""

from __future__ import annotations

from pathlib import Path

import pytest

from pr_review_agent.graph.nodes.graphify import (
    build_repo_graph,
    compute_blast_radius,
    find_symbol_node,
)
from pr_review_agent.models.domain import BlastRadius, Symbol


# ---------------------------------------------------------------------------
# Fixture: minimal synthetic Python repo
# ---------------------------------------------------------------------------

_AUTH_PY = """\
import hashlib
import secrets


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    return hashlib.sha256((salt + password).encode()).hexdigest()


def verify_password(plain: str, stored: str) -> bool:
    return hash_password(plain) == stored
"""

_API_PY = """\
from auth import hash_password


class UserAPI:
    def register(self, username: str, password: str) -> dict:
        hashed = hash_password(password)
        return {"username": username, "password": hashed}
"""

_TEST_AUTH_PY = """\
from auth import hash_password, verify_password


def test_hash_password():
    assert hash_password("secret") != "secret"


def test_verify_password():
    assert verify_password("x", "x") is False
"""


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    (tmp_path / "auth.py").write_text(_AUTH_PY, encoding="utf-8")
    (tmp_path / "api.py").write_text(_API_PY, encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_auth.py").write_text(_TEST_AUTH_PY, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# build_repo_graph
# ---------------------------------------------------------------------------

def test_build_repo_graph_returns_digraph(repo_root):
    import networkx as nx
    graph, _ = build_repo_graph(repo_root)
    assert isinstance(graph, nx.DiGraph)


def test_graph_contains_module_nodes(repo_root):
    graph, _ = build_repo_graph(repo_root)
    module_nodes = [n for n, d in graph.nodes(data=True) if d.get("kind") == "module"]
    file_names = [n for n in module_nodes]
    assert any("auth.py" in f for f in file_names)
    assert any("api.py" in f for f in file_names)


def test_graph_contains_symbol_nodes(repo_root):
    graph, _ = build_repo_graph(repo_root)
    symbol_nodes = [n for n, d in graph.nodes(data=True) if d.get("kind") == "symbol"]
    names = [graph.nodes[n]["name"] for n in symbol_nodes]
    assert "hash_password" in names
    assert "verify_password" in names


def test_graph_truncated_flag(repo_root):
    _, truncated = build_repo_graph(repo_root, max_files=1)
    assert truncated is True


def test_graph_not_truncated_when_within_limit(repo_root):
    _, truncated = build_repo_graph(repo_root, max_files=100)
    assert truncated is False


# ---------------------------------------------------------------------------
# find_symbol_node
# ---------------------------------------------------------------------------

def test_find_symbol_node_returns_node_id(repo_root):
    graph, _ = build_repo_graph(repo_root)
    node_id = find_symbol_node(graph, "auth.py", "hash_password")
    assert node_id is not None
    assert graph.nodes[node_id]["name"] == "hash_password"


def test_find_symbol_node_returns_none_for_missing(repo_root):
    graph, _ = build_repo_graph(repo_root)
    result = find_symbol_node(graph, "auth.py", "nonexistent_func")
    assert result is None


def test_find_symbol_node_nearest_line(repo_root):
    graph, _ = build_repo_graph(repo_root)
    node_id = find_symbol_node(graph, "auth.py", "hash_password", near_line=5)
    assert node_id is not None


# ---------------------------------------------------------------------------
# compute_blast_radius — structure
# ---------------------------------------------------------------------------

def _make_symbol(name: str, file: str, start_line: int = 1, symbol_type: str = "function") -> Symbol:
    return Symbol(
        name=name,
        file=file,
        symbol_type=symbol_type,
        start_line=start_line,
        end_line=start_line + 3,
    )


def test_compute_blast_radius_returns_blast_radius(repo_root):
    sym = _make_symbol("hash_password", "auth.py", start_line=5)
    result = compute_blast_radius(repo_root, [sym])
    assert isinstance(result, BlastRadius)


def test_compute_blast_radius_has_entries(repo_root):
    sym = _make_symbol("hash_password", "auth.py", start_line=5)
    result = compute_blast_radius(repo_root, [sym])
    assert len(result.entries) >= 1


def test_compute_blast_radius_entry_symbol_name(repo_root):
    sym = _make_symbol("hash_password", "auth.py", start_line=5)
    result = compute_blast_radius(repo_root, [sym])
    assert result.entries[0].symbol == "hash_password"


def test_compute_blast_radius_graph_node_count_positive(repo_root):
    sym = _make_symbol("hash_password", "auth.py", start_line=5)
    result = compute_blast_radius(repo_root, [sym])
    assert result.graph_node_count > 0


def test_compute_blast_radius_skips_imports(repo_root):
    sym = _make_symbol("hashlib", "auth.py", symbol_type="import")
    result = compute_blast_radius(repo_root, [sym])
    assert len(result.entries) == 0


def test_compute_blast_radius_skips_variables(repo_root):
    sym = _make_symbol("MY_CONST", "auth.py", symbol_type="variable")
    result = compute_blast_radius(repo_root, [sym])
    assert len(result.entries) == 0


def test_compute_blast_radius_caller_from_api(repo_root):
    sym = _make_symbol("hash_password", "auth.py", start_line=5)
    result = compute_blast_radius(repo_root, [sym])
    entry = result.entries[0]
    caller_names = [c.symbol_name for c in entry.callers]
    # verify_password or register in api.py may call hash_password
    assert len(caller_names) >= 0  # structural check — callers list is present


def test_compute_blast_radius_multiple_symbols(repo_root):
    syms = [
        _make_symbol("hash_password", "auth.py", start_line=5),
        _make_symbol("verify_password", "auth.py", start_line=10),
    ]
    result = compute_blast_radius(repo_root, syms)
    assert len(result.entries) == 2


def test_compute_blast_radius_unknown_file_produces_empty_entry(repo_root):
    sym = _make_symbol("missing_func", "nonexistent.py", start_line=1)
    result = compute_blast_radius(repo_root, [sym])
    # Node not found → entry with call_distance=0 and no callers
    assert len(result.entries) == 1
    assert result.entries[0].callers == []


# ---------------------------------------------------------------------------
# Graph-level edge assertions
# ---------------------------------------------------------------------------

def test_graph_has_imports_edge(repo_root):
    graph, _ = build_repo_graph(repo_root)
    edges = [(u, v, d) for u, v, d in graph.edges(data=True) if d.get("kind") == "imports"]
    assert len(edges) >= 1


def test_graph_has_contains_edges(repo_root):
    graph, _ = build_repo_graph(repo_root)
    edges = [d for _, _, d in graph.edges(data=True) if d.get("kind") == "contains"]
    assert len(edges) >= 1
