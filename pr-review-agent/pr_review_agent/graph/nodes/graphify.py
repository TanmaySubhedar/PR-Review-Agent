"""Graphify node: build repo call graph and compute blast radius for changed symbols."""

import asyncio
import re
from collections import defaultdict
from pathlib import Path

import networkx as nx

from pr_review_agent._llm import AgentStep, run_agent_loop
from pr_review_agent.config import settings
from pr_review_agent.graph.nodes.symbols import extract_raw_symbols, extract_calls
from pr_review_agent.graph.state import PRReviewState
from pr_review_agent.models.domain import (
    BlastRadius,
    BlastRadiusEntry,
    DocRef,
    Symbol,
    SymbolRef,
)
from pr_review_agent.prompts import blast_radius_agent as br_prompts
from pr_review_agent.tools.graphify_mcp import GraphifyMCPClient, is_available
from pr_review_agent.tools.treesitter import detect_language

# ---- repo graph constants -------------------------------------------------------

IGNORED_DIR_NAMES = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".pytest_cache", ".mypy_cache",
}
JSTS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs")
DOC_EXTENSIONS = (".md", ".mdx", ".rst", ".txt")
TEST_PATH_RE = re.compile(
    r"(^|/)(tests?/|__tests__/)|(^|/)test_[^/]+\.py$|_test\.py$|\.(test|spec)\.[jt]sx?$"
)
_PY_RELATIVE_IMPORT_RE = re.compile(r"^from\s+(\.+)(\S*)\s+import")
_PY_ABS_IMPORT_RE = re.compile(r"^(?:from|import)\s+([\w.]+)")
_JSTS_IMPORT_PATH_RE = re.compile(r"""from\s+["']([^"']+)["']""")


def _iter_source_files(root: Path) -> list[str]:
    files: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIR_NAMES for part in path.relative_to(root).parts):
            continue
        if detect_language(str(path)) is None:
            continue
        files.append(str(path.relative_to(root)).replace("\\", "/"))
    return sorted(files)


def _resolve_python_import(current_file: str, import_text: str, known_files: set[str]) -> str | None:
    current_dir = Path(current_file).parent
    rel_match = _PY_RELATIVE_IMPORT_RE.match(import_text)
    if rel_match:
        dots, module = rel_match.groups()
        base = current_dir
        for _ in range(len(dots) - 1):
            base = base.parent
        module_path = base / module.replace(".", "/") if module else base
    else:
        abs_match = _PY_ABS_IMPORT_RE.match(import_text)
        if not abs_match:
            return None
        module_path = Path(abs_match.group(1).replace(".", "/"))
    for candidate in (f"{module_path}.py", f"{module_path}/__init__.py"):
        normalized = str(candidate).replace("\\", "/").lstrip("/")
        if normalized in known_files:
            return normalized
    return None


def _resolve_jsts_import(current_file: str, import_text: str, known_files: set[str]) -> str | None:
    match = _JSTS_IMPORT_PATH_RE.search(import_text)
    if not match:
        return None
    import_path = match.group(1)
    if not import_path.startswith("."):
        return None
    base = (Path(current_file).parent / import_path).as_posix()
    base = re.sub(r"/+", "/", base)
    for ext in JSTS_EXTENSIONS:
        if (base + ext).lstrip("/") in known_files:
            return (base + ext).lstrip("/")
    for ext in JSTS_EXTENSIONS:
        candidate = f"{base}/index{ext}".lstrip("/")
        if candidate in known_files:
            return candidate
    return None


def build_repo_graph(root: Path, max_files: int | None = None) -> tuple[nx.DiGraph, bool]:
    files = _iter_source_files(root)
    truncated = max_files is not None and len(files) > max_files
    if max_files is not None:
        files = files[:max_files]
    known_files = set(files)
    graph = nx.DiGraph()
    name_index: dict[str, list[str]] = defaultdict(list)
    file_defs: dict[str, list[tuple[str, list[str]]]] = {}

    for file_path in files:
        source = (root / file_path).read_bytes()
        graph.add_node(file_path, kind="module")
        raw_symbols = extract_raw_symbols(file_path, source)
        calls = extract_calls(file_path, source)
        defs_in_file: list[tuple[str, list[str]]] = []
        for sym in raw_symbols:
            if sym.symbol_type == "import":
                resolver = _resolve_python_import if file_path.endswith(".py") else _resolve_jsts_import
                target = resolver(file_path, sym.name, known_files)
                if target and target != file_path:
                    graph.add_edge(file_path, target, kind="imports")
                continue
            node_id = f"{file_path}::{sym.name}:{sym.start_line}"
            graph.add_node(node_id, kind="symbol", file=file_path, name=sym.name,
                           symbol_type=sym.symbol_type, start_line=sym.start_line, end_line=sym.end_line)
            graph.add_edge(file_path, node_id, kind="contains")
            name_index[sym.name].append(node_id)
            def_calls = [name for name, byte_off in calls if sym.start_byte <= byte_off <= sym.end_byte]
            defs_in_file.append((node_id, def_calls))
        file_defs[file_path] = defs_in_file

    for items in file_defs.values():
        for node_id, def_calls in items:
            for called_name in def_calls:
                for callee_id in name_index.get(called_name, []):
                    if callee_id != node_id:
                        graph.add_edge(node_id, callee_id, kind="calls")

    return graph, truncated


def find_symbol_node(graph: nx.DiGraph, file_path: str, symbol_name: str, near_line: int | None = None) -> str | None:
    candidates = [
        n for n, data in graph.nodes(data=True)
        if data.get("kind") == "symbol" and data.get("file") == file_path and data.get("name") == symbol_name
    ]
    if not candidates:
        return None
    if near_line is None or len(candidates) == 1:
        return candidates[0]
    return min(candidates, key=lambda n: abs(graph.nodes[n]["start_line"] - near_line))


# ---- blast radius queries -------------------------------------------------------

def _sym_ref(graph: nx.DiGraph, node_id: str, relationship: str) -> SymbolRef:
    data = graph.nodes[node_id]
    return SymbolRef(file=data["file"], symbol_name=data["name"], line=data["start_line"], relationship=relationship)


def _bfs_symbols(graph: nx.DiGraph, start: str, edge_kind: str, reverse: bool, max_depth: int) -> dict[str, int]:
    distances: dict[str, int] = {}
    frontier = [start]
    seen = {start}
    depth = 0
    while frontier and depth < max_depth:
        depth += 1
        next_frontier = []
        for node in frontier:
            neighbors = graph.predecessors(node) if reverse else graph.successors(node)
            for nb in neighbors:
                ed = graph.get_edge_data(nb, node) if reverse else graph.get_edge_data(node, nb)
                if ed is None or ed.get("kind") != edge_kind or nb in seen:
                    continue
                seen.add(nb)
                if graph.nodes[nb].get("kind") == "symbol":
                    distances[nb] = depth
                next_frontier.append(nb)
        frontier = next_frontier
    return distances


def _find_callers(graph: nx.DiGraph, node_id: str, depth: int) -> list[tuple[str, int]]:
    return list(_bfs_symbols(graph, node_id, "calls", reverse=True, max_depth=depth).items())


def _find_callees(graph: nx.DiGraph, node_id: str, depth: int) -> list[tuple[str, int]]:
    return list(_bfs_symbols(graph, node_id, "calls", reverse=False, max_depth=depth).items())


def _find_related(graph: nx.DiGraph, node_id: str, depth: int) -> list[str]:
    file_path = graph.nodes[node_id]["file"]
    related = [n for n in graph.successors(file_path) if graph.nodes[n].get("kind") == "symbol" and n != node_id]
    seen_files = {file_path}
    frontier = [file_path]
    d = 0
    while frontier and d < depth:
        d += 1
        next_frontier = []
        for f in frontier:
            pairs = list(graph.adj[f].items()) + [(p, graph.get_edge_data(p, f)) for p in graph.predecessors(f)]
            for nb, ed in pairs:
                if graph.nodes.get(nb, {}).get("kind") != "module" or ed is None or ed.get("kind") != "imports":
                    continue
                if nb in seen_files:
                    continue
                seen_files.add(nb)
                next_frontier.append(nb)
                related.extend(n for n in graph.successors(nb) if graph.nodes[n].get("kind") == "symbol")
        frontier = next_frontier
    return related


def _find_tests(graph: nx.DiGraph, node_id: str, depth: int) -> list[str]:
    callers = _bfs_symbols(graph, node_id, "calls", reverse=True, max_depth=depth)
    return [n for n in callers if TEST_PATH_RE.search(graph.nodes[n]["file"])]


def _list_doc_files(root: Path) -> list[str]:
    files: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIR_NAMES for part in path.relative_to(root).parts):
            continue
        if path.suffix.lower() in DOC_EXTENSIONS:
            files.append(str(path.relative_to(root)).replace("\\", "/"))
    return sorted(files)


def _find_docs(root: Path, symbol_name: str, doc_files: list[str], limit: int = 5) -> list[DocRef]:
    refs: list[DocRef] = []
    for fp in doc_files:
        try:
            text = (root / fp).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if symbol_name in line:
                refs.append(DocRef(file=fp, line=i, match_snippet=line.strip()[:200]))
                if len(refs) >= limit:
                    return refs
    return refs


# ---- blast radius + risk refinement --------------------------------------------

def compute_blast_radius(root: Path, changed_symbols: list[Symbol], depth: int | None = None) -> BlastRadius:
    d = depth if depth is not None else settings.blast_radius_max_depth
    graph, truncated = build_repo_graph(root, max_files=settings.blast_radius_max_files)
    doc_files = _list_doc_files(root)
    entries: list[BlastRadiusEntry] = []

    for sym in changed_symbols:
        if sym.symbol_type in ("import", "variable"):
            continue
        node_id = find_symbol_node(graph, sym.file, sym.name, near_line=sym.start_line)
        if node_id is None:
            entries.append(BlastRadiusEntry(symbol=sym.name, file=sym.file, call_distance=0))
            continue
        callers = _find_callers(graph, node_id, d)
        callees = _find_callees(graph, node_id, d)
        related = _find_related(graph, node_id, d)
        tests = _find_tests(graph, node_id, d)
        entries.append(BlastRadiusEntry(
            symbol=sym.name,
            file=sym.file,
            callers=[_sym_ref(graph, n, "caller") for n, _ in callers],
            callees=[_sym_ref(graph, n, "callee") for n, _ in callees],
            related_components=[_sym_ref(graph, n, "sibling") for n in related],
            tests=[_sym_ref(graph, n, "test") for n in tests],
            docs=_find_docs(root, sym.name, doc_files),
            call_distance=min((d_ for _, d_ in callers), default=0),
        ))
    return BlastRadius(entries=entries, graph_node_count=graph.number_of_nodes(), graph_truncated=truncated)


def _refine_risk(state: PRReviewState, blast_radius: BlastRadius) -> dict:
    from pr_review_agent.graph.nodes.symbols import _bucket_score

    score = state.get("risk_score", 0)
    factors = list(state.get("risk_factors", []))
    max_fan_in = max((len(e.callers) for e in blast_radius.entries), default=0)
    if max_fan_in >= 5:
        score += 3
    elif max_fan_in >= 2:
        score += 2
    elif max_fan_in == 1:
        score += 1
    untested = [e for e in blast_radius.entries if e.callers and not e.tests]
    if untested:
        score += 2
        names = ", ".join(sorted({e.symbol for e in untested}))
        factors.append(f"called by other code but has no test coverage: {names}")
    if max_fan_in:
        caller_names = sorted({c.symbol_name for e in blast_radius.entries for c in e.callers})
        factors.append(f"blast radius: up to {max_fan_in} caller(s) ({', '.join(caller_names)})")
    return {"risk_level": _bucket_score(score), "risk_score": score, "risk_factors": factors}


# ---- Agentic MCP blast radius --------------------------------------------------

_GRAPHIFY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_callers",
            "description": "Find symbols that call the given symbol, up to the specified depth.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Symbol name to query"},
                    "depth": {"type": "integer", "description": "Traversal depth (1–4)", "default": 2},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_callees",
            "description": "Find symbols called by the given symbol.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "depth": {"type": "integer", "default": 2},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_related",
            "description": "Find all symbols and modules related to the given symbol across all edge types.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "depth": {"type": "integer", "default": 2},
                },
                "required": ["symbol"],
            },
        },
    },
]


def _build_blast_radius_from_trace(
    trace: list[AgentStep],
    changed_symbols: list[Symbol],
) -> BlastRadius:
    """Aggregate tool call results from the agent loop into a BlastRadius object."""
    symbol_data: dict[str, dict[str, set[str]]] = {}

    for step in trace:
        sym_name = step.args.get("symbol", "")
        if not sym_name:
            continue
        if sym_name not in symbol_data:
            symbol_data[sym_name] = {"callers": set(), "callees": set(), "related": set()}
        result_names = [
            n.strip() for n in step.result.strip().splitlines()
            if n.strip() and not n.strip().startswith("No ")
        ]
        if step.tool == "get_callers":
            symbol_data[sym_name]["callers"].update(result_names)
        elif step.tool == "get_callees":
            symbol_data[sym_name]["callees"].update(result_names)
        elif step.tool == "get_related":
            symbol_data[sym_name]["related"].update(result_names)

    entries: list[BlastRadiusEntry] = []
    for sym in changed_symbols:
        if sym.symbol_type in ("import", "variable"):
            continue
        data = symbol_data.get(sym.name, {"callers": set(), "callees": set(), "related": set()})
        entries.append(BlastRadiusEntry(
            symbol=sym.name,
            file=sym.file,
            callers=[SymbolRef(file="", symbol_name=c, line=0, relationship="caller") for c in data["callers"]],
            callees=[SymbolRef(file="", symbol_name=c, line=0, relationship="callee") for c in data["callees"]],
            related_components=[SymbolRef(file="", symbol_name=r, line=0, relationship="sibling") for r in data["related"]],
            call_distance=1 if data["callers"] else 0,
        ))
    return BlastRadius(entries=entries, graph_node_count=0, graph_truncated=False)


async def _compute_blast_radius_agentic(
    client: GraphifyMCPClient,
    changed_symbols: list[Symbol],
    base_sha: str | None,
    risk_level: str,
) -> tuple[BlastRadius, bool, list[dict]]:
    """Agent-loop blast-radius analysis. Returns (blast_radius, graph_rebuilt, query_trace)."""
    rebuilt = client.ensure_index(base_sha)

    async def handle_get_callers(args: dict) -> str:
        names = client.get_callers(args.get("symbol", ""), depth=int(args.get("depth", 2)))
        return "\n".join(names) if names else "No callers found."

    async def handle_get_callees(args: dict) -> str:
        names = client.get_callees(args.get("symbol", ""), depth=int(args.get("depth", 2)))
        return "\n".join(names) if names else "No callees found."

    async def handle_get_related(args: dict) -> str:
        names = client.get_related(args.get("symbol", ""), depth=int(args.get("depth", 2)))
        return "\n".join(names) if names else "No related nodes found."

    handlers = {
        "get_callers": handle_get_callers,
        "get_callees": handle_get_callees,
        "get_related": handle_get_related,
    }

    actionable = [s for s in changed_symbols if s.symbol_type not in ("import", "variable")]
    _, trace = await run_agent_loop(
        tools=_GRAPHIFY_TOOLS,
        tool_handlers=handlers,
        system_prompt=br_prompts.SYSTEM_PROMPT,
        initial_user_message=br_prompts.initial_user_message(actionable, risk_level),
        max_steps=20,
    )

    blast_radius = _build_blast_radius_from_trace(trace, changed_symbols)
    query_trace = [
        {"tool": s.tool, "symbol": s.args.get("symbol", ""), "depth": s.args.get("depth", 2),
         "result_count": len([l for l in s.result.splitlines() if l.strip() and not l.strip().startswith("No ")])}
        for s in trace
    ]
    return blast_radius, rebuilt, query_trace


# ---- node entry point ----------------------------------------------------------

def run(state: PRReviewState) -> PRReviewState:
    repo_path: Path | None = state.get("repo_path")
    changed_symbols: list[Symbol] = state.get("changed_symbols", [])
    pr_meta = state.get("pr_metadata")
    base_sha: str | None = pr_meta.base_sha if pr_meta else None
    risk_level: str = state.get("risk_level", "low")

    actionable = [s for s in changed_symbols if s.symbol_type not in ("import", "variable")]
    query_trace: list[dict] = []

    if not actionable:
        blast_radius = BlastRadius(entries=[], graph_node_count=0, graph_truncated=False)
        graph_rebuilt = False
    elif is_available() and repo_path:
        with GraphifyMCPClient(repo_path) as client:
            blast_radius, graph_rebuilt, query_trace = asyncio.run(
                _compute_blast_radius_agentic(client, changed_symbols, base_sha, risk_level)
            )
    else:
        blast_radius = compute_blast_radius(repo_path or Path("."), changed_symbols)
        graph_rebuilt = False

    refined = _refine_risk(state, blast_radius)
    return {
        **state,
        "blast_radius": blast_radius,
        "graphify_ready": True,
        "graphify_graph_rebuilt": graph_rebuilt,
        "blast_radius_query_trace": query_trace,
        **refined,
        "phase_status": {**state.get("phase_status", {}), "graphify": "done"},
    }
