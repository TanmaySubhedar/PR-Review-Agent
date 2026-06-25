import re
from collections import defaultdict
from pathlib import Path

import networkx as nx

from app.pipeline.symbols import extract_calls, extract_symbols
from app.pipeline.treesitter_support import detect_language

IGNORED_DIR_NAMES = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".pytest_cache", ".mypy_cache",
}

_PY_RELATIVE_IMPORT_RE = re.compile(r"^from\s+(\.+)(\S*)\s+import")
_PY_ABS_IMPORT_RE = re.compile(r"^(?:from|import)\s+([\w.]+)")
_JSTS_IMPORT_PATH_RE = re.compile(r"""from\s+["']([^"']+)["']""")

JSTS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs")


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
        return None  # external package - no local node to link to

    base = (Path(current_file).parent / import_path).as_posix()
    base = re.sub(r"/+", "/", base)

    candidates = [base + ext for ext in JSTS_EXTENSIONS]
    candidates += [f"{base}/index{ext}" for ext in JSTS_EXTENSIONS]
    for candidate in candidates:
        normalized = candidate.lstrip("/")
        if normalized in known_files:
            return normalized
    return None


def build_repo_graph(root: Path, max_files: int | None = None) -> tuple[nx.DiGraph, bool]:
    """Build a best-effort call/import graph for the repo checked out at
    `root`. Mirrors what Graphify-style tools do (Tree-sitter -> graph, no
    LLM involved) but scoped to exactly the queries blast-radius needs:
    callers, callees, same-module siblings, and import-linked modules.

    Returns (graph, truncated) - `truncated` is True if max_files capped the
    walk, which the caller should surface in BlastRadius.graph_truncated.
    """
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

        symbols = extract_symbols(file_path, source)
        calls = extract_calls(file_path, source)

        defs_in_file: list[tuple[str, list[str]]] = []
        for sym in symbols:
            if sym.symbol_type == "import":
                resolver = _resolve_python_import if file_path.endswith(".py") else _resolve_jsts_import
                target = resolver(file_path, sym.name, known_files)
                if target and target != file_path:
                    graph.add_edge(file_path, target, kind="imports")
                continue

            node_id = f"{file_path}::{sym.name}:{sym.start_line}"
            graph.add_node(
                node_id,
                kind="symbol",
                file=file_path,
                name=sym.name,
                symbol_type=sym.symbol_type,
                start_line=sym.start_line,
                end_line=sym.end_line,
            )
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
    """Find the graph node id for a (file, symbol_name), preferring the
    definition closest to `near_line` when a name is defined more than once
    in the same file (e.g. overloaded/duplicate method names)."""
    candidates = [
        n
        for n, data in graph.nodes(data=True)
        if data.get("kind") == "symbol" and data.get("file") == file_path and data.get("name") == symbol_name
    ]
    if not candidates:
        return None
    if near_line is None or len(candidates) == 1:
        return candidates[0]
    return min(candidates, key=lambda n: abs(graph.nodes[n]["start_line"] - near_line))
