"""Tests for GraphifyClient. All subprocess.run calls are mocked."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

import pr_review_agent.tools.graphify_mcp as mcp_module
from pr_review_agent.tools.graphify_mcp import (
    GraphifyClient,
    GraphifyMCPClient,  # backward-compat alias
    is_available,
)

_REPO = Path("/fake/repo")
_GRAPH = _REPO / "graphify-out" / "graph.json"

# ---------------------------------------------------------------------------
# Output fixtures
# ---------------------------------------------------------------------------

_AFFECTED_CALLS_OUTPUT = """\
Affected nodes for hash_password()
Relations: calls
Depth: 2
- verify_password() [calls] auth/utils.py:L10
- register() [calls] api/routes.py:L26
"""

_AFFECTED_ALL_OUTPUT = """\
Affected nodes for hash_password()
Relations: calls, references, imports
Depth: 2
- verify_password() [calls] auth/utils.py:L10
- utils.py [imports] api/routes.py:L1
- register() [calls] api/routes.py:L26
"""

_NO_MATCH_OUTPUT = "No unique node match for ghost_func"


def _ok(stdout: str = "", returncode: int = 0) -> MagicMock:
    r = MagicMock(spec=subprocess.CompletedProcess)
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = ""
    return r


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------

def test_is_available_true_when_binary_found():
    with patch("pr_review_agent.tools.graphify_mcp.shutil.which", return_value="/usr/bin/graphify"):
        assert is_available() is True


def test_is_available_false_when_binary_missing():
    with patch("pr_review_agent.tools.graphify_mcp.shutil.which", return_value=None):
        assert is_available() is False


# ---------------------------------------------------------------------------
# Backward-compat alias
# ---------------------------------------------------------------------------

def test_graphify_mcp_client_alias():
    assert GraphifyMCPClient is GraphifyClient


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

def test_context_manager_returns_client():
    client = GraphifyClient(_REPO)
    with client as c:
        assert c is client


def test_context_manager_exit_does_not_raise():
    with GraphifyClient(_REPO):
        pass  # no exception


# ---------------------------------------------------------------------------
# ensure_index
# ---------------------------------------------------------------------------

def test_ensure_index_calls_graphify_update():
    with patch("subprocess.run", return_value=_ok()) as mock_run:
        with GraphifyClient(_REPO) as client:
            client.ensure_index()

    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == "graphify"
    assert args[1] == "update"
    assert str(_REPO) in args


def test_ensure_index_returns_true_on_rebuild():
    with patch("subprocess.run", return_value=_ok()):
        with GraphifyClient(_REPO) as client:
            result = client.ensure_index()
    assert result is True


def test_ensure_index_raises_on_nonzero_exit():
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, ["graphify"])):
        with GraphifyClient(_REPO) as client:
            with pytest.raises(subprocess.CalledProcessError):
                client.ensure_index()


# ---------------------------------------------------------------------------
# ensure_index — SHA-based caching
# ---------------------------------------------------------------------------

def test_ensure_index_skips_when_sha_matches(tmp_path):
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    (graph_dir / "graph.json").write_text("{}")
    (graph_dir / ".graph_sha").write_text("abc123")

    client = GraphifyClient(tmp_path)
    with patch("subprocess.run") as mock_run:
        result = client.ensure_index(base_sha="abc123")

    mock_run.assert_not_called()
    assert result is False


def test_ensure_index_rebuilds_when_sha_differs(tmp_path):
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    (graph_dir / "graph.json").write_text("{}")
    (graph_dir / ".graph_sha").write_text("old_sha")

    client = GraphifyClient(tmp_path)
    with patch("subprocess.run", return_value=_ok()):
        result = client.ensure_index(base_sha="new_sha")

    assert result is True


def test_ensure_index_rebuilds_when_no_sentinel(tmp_path):
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    (graph_dir / "graph.json").write_text("{}")
    # no sentinel file

    client = GraphifyClient(tmp_path)
    with patch("subprocess.run", return_value=_ok()):
        result = client.ensure_index(base_sha="abc123")

    assert result is True


def test_ensure_index_rebuilds_when_no_graph_json(tmp_path):
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    (graph_dir / ".graph_sha").write_text("abc123")
    # no graph.json

    client = GraphifyClient(tmp_path)
    with patch("subprocess.run", return_value=_ok()):
        result = client.ensure_index(base_sha="abc123")

    assert result is True


def test_ensure_index_writes_sentinel_after_rebuild(tmp_path):
    client = GraphifyClient(tmp_path)
    with patch("subprocess.run", return_value=_ok()):
        client.ensure_index(base_sha="deadbeef")

    sentinel = tmp_path / "graphify-out" / ".graph_sha"
    assert sentinel.exists()
    assert sentinel.read_text().strip() == "deadbeef"


def test_ensure_index_no_sha_always_rebuilds(tmp_path):
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    (graph_dir / "graph.json").write_text("{}")
    (graph_dir / ".graph_sha").write_text("abc123")

    client = GraphifyClient(tmp_path)
    with patch("subprocess.run", return_value=_ok()) as mock_run:
        result = client.ensure_index()  # no sha → always rebuild

    mock_run.assert_called_once()
    assert result is True


def test_ensure_index_does_not_write_sentinel_without_sha(tmp_path):
    client = GraphifyClient(tmp_path)
    with patch("subprocess.run", return_value=_ok()):
        client.ensure_index()  # no sha

    sentinel = tmp_path / "graphify-out" / ".graph_sha"
    assert not sentinel.exists()


# ---------------------------------------------------------------------------
# get_callers
# ---------------------------------------------------------------------------

def test_get_callers_returns_symbol_names():
    with patch("subprocess.run", return_value=_ok(_AFFECTED_CALLS_OUTPUT)):
        with GraphifyClient(_REPO) as client:
            result = client.get_callers("hash_password")

    assert "verify_password" in result
    assert "register" in result


def test_get_callers_passes_relation_calls():
    with patch("subprocess.run", return_value=_ok(_AFFECTED_CALLS_OUTPUT)) as mock_run:
        with GraphifyClient(_REPO) as client:
            client.get_callers("hash_password")

    cmd = mock_run.call_args[0][0]
    assert "--relation" in cmd
    idx = cmd.index("--relation")
    assert cmd[idx + 1] == "calls"


def test_get_callers_passes_depth():
    with patch("subprocess.run", return_value=_ok(_AFFECTED_CALLS_OUTPUT)) as mock_run:
        with GraphifyClient(_REPO) as client:
            client.get_callers("sym", depth=3)

    cmd = mock_run.call_args[0][0]
    assert "--depth" in cmd
    idx = cmd.index("--depth")
    assert cmd[idx + 1] == "3"


def test_get_callers_passes_graph_path():
    with patch("subprocess.run", return_value=_ok(_AFFECTED_CALLS_OUTPUT)) as mock_run:
        with GraphifyClient(_REPO) as client:
            client.get_callers("sym")

    cmd = mock_run.call_args[0][0]
    assert "--graph" in cmd
    idx = cmd.index("--graph")
    assert str(_GRAPH) == cmd[idx + 1]


def test_get_callers_no_match_returns_empty():
    with patch("subprocess.run", return_value=_ok(_NO_MATCH_OUTPUT)):
        with GraphifyClient(_REPO) as client:
            result = client.get_callers("ghost_func")
    assert result == []


def test_get_callers_nonzero_exit_returns_empty():
    with patch("subprocess.run", return_value=_ok("error output", returncode=1)):
        with GraphifyClient(_REPO) as client:
            result = client.get_callers("sym")
    assert result == []


# ---------------------------------------------------------------------------
# get_callees
# ---------------------------------------------------------------------------

def test_get_callees_always_returns_empty():
    with patch("subprocess.run", return_value=_ok(_AFFECTED_CALLS_OUTPUT)):
        with GraphifyClient(_REPO) as client:
            result = client.get_callees("hash_password")
    assert result == []


def test_get_callees_makes_no_subprocess_call():
    with patch("subprocess.run") as mock_run:
        with GraphifyClient(_REPO) as client:
            client.get_callees("sym")
    mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# get_related
# ---------------------------------------------------------------------------

def test_get_related_returns_names():
    with patch("subprocess.run", return_value=_ok(_AFFECTED_ALL_OUTPUT)):
        with GraphifyClient(_REPO) as client:
            result = client.get_related("hash_password")

    assert "verify_password" in result
    assert "register" in result


def test_get_related_passes_depth():
    with patch("subprocess.run", return_value=_ok(_AFFECTED_ALL_OUTPUT)) as mock_run:
        with GraphifyClient(_REPO) as client:
            client.get_related("sym", depth=4)

    cmd = mock_run.call_args[0][0]
    idx = cmd.index("--depth")
    assert cmd[idx + 1] == "4"


def test_get_related_no_relation_filter():
    with patch("subprocess.run", return_value=_ok(_AFFECTED_ALL_OUTPUT)) as mock_run:
        with GraphifyClient(_REPO) as client:
            client.get_related("sym")

    cmd = mock_run.call_args[0][0]
    assert "--relation" not in cmd


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------

def test_parse_strips_trailing_parens():
    output = "- my_func() [calls] some/file.py:L5\n"
    with patch("subprocess.run", return_value=_ok(output)):
        with GraphifyClient(_REPO) as client:
            result = client.get_callers("x")
    assert "my_func" in result
    assert "my_func()" not in result


def test_parse_strips_leading_dot_for_methods():
    output = "- .register() [calls] api/routes.py:L26\n"
    with patch("subprocess.run", return_value=_ok(output)):
        with GraphifyClient(_REPO) as client:
            result = client.get_callers("x")
    assert "register" in result
    assert ".register" not in result


def test_parse_includes_module_references():
    output = "- utils.py [imports] api/routes.py:L1\n"
    with patch("subprocess.run", return_value=_ok(output)):
        with GraphifyClient(_REPO) as client:
            result = client.get_related("x")
    assert "utils.py" in result


def test_parse_empty_output_returns_empty():
    with patch("subprocess.run", return_value=_ok("")):
        with GraphifyClient(_REPO) as client:
            result = client.get_callers("x")
    assert result == []


# ---------------------------------------------------------------------------
# Integration-style: live graphify binary (skipped when not available)
# ---------------------------------------------------------------------------

pytestmark_integration = pytest.mark.skipif(
    not is_available(), reason="graphify binary not on PATH"
)


@pytestmark_integration
def test_live_is_available():
    assert is_available() is True


@pytestmark_integration
def test_live_parse_affected_output():
    """Smoke-test _parse_affected against known output format."""
    sample = """\
Affected nodes for complete_structured()
Relations: calls
Depth: 1
- _validate_one() [calls] pr_review_agent/graph/nodes/critic.py:L46
- _read_one() [calls] pr_review_agent/graph/nodes/readers.py:L15
"""
    result = GraphifyClient._parse_affected(sample)
    assert "_validate_one" in result
    assert "_read_one" in result
    assert len(result) == 2
