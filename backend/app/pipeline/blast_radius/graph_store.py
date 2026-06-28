"""Persistence helpers for the in-memory NetworkX call graph.

The full repo graph can be several MB uncompressed; gzip+base64 brings it
down ~10× so it fits comfortably in SQLite's TEXT column.
"""

import base64
import gzip
import json

import networkx as nx


def compress_graph(graph: nx.DiGraph) -> str:
    """Serialise a DiGraph to a gzip-compressed base64 TEXT value."""
    data = nx.node_link_data(graph)
    raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
    compressed = gzip.compress(raw, compresslevel=6)
    return base64.b64encode(compressed).decode("ascii")


def decompress_graph(text: str) -> nx.DiGraph:
    """Reconstruct a DiGraph from the value produced by compress_graph."""
    compressed = base64.b64decode(text.encode("ascii"))
    raw = gzip.decompress(compressed)
    data = json.loads(raw)
    return nx.node_link_graph(data, directed=True)
