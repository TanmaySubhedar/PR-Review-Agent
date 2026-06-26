"""Graphify CLI client. Uses `graphify update` + `graphify affected` subprocesses."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

# Matches lines like:  "- _validate_one() [calls] pr_review_agent/graph/nodes/critic.py:L46"
_AFFECTED_LINE_RE = re.compile(r"^- (.+?) \[")

# Sentinel file written alongside graph.json recording the SHA it was built for.
_SHA_SENTINEL = ".graph_sha"


class GraphifyClient:
    """Thin wrapper around the graphify CLI for blast-radius queries."""

    def __init__(self, repo_path: str | Path) -> None:
        self._repo_path = Path(repo_path)
        self._graph_path = self._repo_path / "graphify-out" / "graph.json"
        self._sentinel_path = self._repo_path / "graphify-out" / _SHA_SENTINEL

    # ------------------------------------------------------------------
    # Context manager (no persistent process — just a convenience wrapper)
    # ------------------------------------------------------------------

    def __enter__(self) -> "GraphifyClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        pass

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def graph_is_current(self, base_sha: str) -> bool:
        """Return True if a valid graph already exists for this base branch SHA."""
        return (
            self._graph_path.exists()
            and self._sentinel_path.exists()
            and self._sentinel_path.read_text().strip() == base_sha
        )

    def ensure_index(self, base_sha: str | None = None) -> bool:
        """Build the graphify index, skipping if the graph is already current.

        Returns True if the graph was (re)built, False if it was reused.
        Pass base_sha (the PR target branch SHA) as the cache key — the graph
        only needs rebuilding when the base branch advances, not on every PR push.
        Omit to always rebuild.
        """
        if base_sha and self.graph_is_current(base_sha):
            return False  # graph already up to date for this base branch state

        subprocess.run(
            ["graphify", "update", str(self._repo_path)],
            check=True,
            capture_output=True,
            text=True,
        )

        if base_sha:
            self._sentinel_path.parent.mkdir(parents=True, exist_ok=True)
            self._sentinel_path.write_text(base_sha)

        return True

    # ------------------------------------------------------------------
    # Graph queries
    # ------------------------------------------------------------------

    def get_callers(self, symbol: str, depth: int = 2) -> list[str]:
        """Return symbol names that call (directly or transitively) this symbol."""
        return self._affected(symbol, relations=["calls"], depth=depth)

    def get_callees(self, symbol: str, depth: int = 2) -> list[str]:
        """Forward traversal not supported by graphify CLI; returns []."""
        return []

    def get_related(self, symbol: str, depth: int = 2) -> list[str]:
        """Return all nodes related to symbol across all edge types."""
        return self._affected(symbol, relations=None, depth=depth)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _affected(
        self,
        symbol: str,
        *,
        relations: list[str] | None,
        depth: int,
    ) -> list[str]:
        cmd = [
            "graphify", "affected", symbol,
            "--depth", str(depth),
            "--graph", str(self._graph_path),
        ]
        for r in (relations or []):
            cmd += ["--relation", r]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 or "No unique node match" in result.stdout:
            return []
        return self._parse_affected(result.stdout)

    @staticmethod
    def _parse_affected(output: str) -> list[str]:
        names: list[str] = []
        for line in output.splitlines():
            m = _AFFECTED_LINE_RE.match(line)
            if not m:
                continue
            raw = m.group(1).strip()
            name = raw.rstrip("()").lstrip(".")
            if name:
                names.append(name)
        return names


# Backward-compatible alias used in graph/nodes/graphify.py imports
GraphifyMCPClient = GraphifyClient


def is_available() -> bool:
    """Return True if the graphify binary is on PATH."""
    return shutil.which("graphify") is not None
