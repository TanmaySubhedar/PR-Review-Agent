from typing import Literal

from pydantic import BaseModel


class SymbolRef(BaseModel):
    file: str
    symbol_name: str
    line: int
    relationship: Literal["caller", "callee", "sibling", "test", "implements", "imports"]


class DocRef(BaseModel):
    file: str
    line: int | None
    match_snippet: str


class BlastRadiusEntry(BaseModel):
    symbol: str
    file: str
    callers: list[SymbolRef] = []
    callees: list[SymbolRef] = []
    related_components: list[SymbolRef] = []
    tests: list[SymbolRef] = []
    docs: list[DocRef] = []
    call_distance: int = 0


class BlastRadius(BaseModel):
    entries: list[BlastRadiusEntry] = []
    graph_node_count: int = 0
    graph_truncated: bool = False
