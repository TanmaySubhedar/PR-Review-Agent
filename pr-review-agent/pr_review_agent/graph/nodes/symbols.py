"""Symbols node: extract symbols from changed files, parse hunks, produce diff analysis state keys."""

import re as _re
from dataclasses import dataclass, field as dc_field
from typing import Literal

from pr_review_agent.graph.state import PRReviewState
from pr_review_agent.models.domain import (
    DiffHunk,
    DiffPosition,
    FileDiff,
    Symbol,
)
from pr_review_agent.tools.treesitter import parse_file

# ---- constants ----------------------------------------------------------------

SENSITIVE_PATH_KEYWORDS = (
    "auth", "token", "security", "payment", "billing",
    "crypto", "password", "secret", "admin", "permission", "session",
)
_HIGH_RISK_THRESHOLD = 5
_MEDIUM_RISK_THRESHOLD = 3

# ---- internal tree-sitter symbol (keeps byte offsets for call extraction) -----

@dataclass
class _RawSymbol:
    name: str
    symbol_type: str
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    is_async: bool = False
    param_count: int | None = None


# ---- tree-sitter helpers -------------------------------------------------------

def _text(node, source: bytes) -> str:
    return source[node.start_byte: node.end_byte].decode("utf-8", errors="replace")


def _has_async_child(node) -> bool:
    return any(c.type == "async" for c in node.children)


def _count_params(def_node) -> int | None:
    params_node = def_node.child_by_field_name("parameters")
    if params_node is None:
        return None
    return sum(1 for c in params_node.children if c.type not in ("(", ")", ","))


def _walk_python(node, source: bytes, in_class: bool) -> list[_RawSymbol]:
    symbols: list[_RawSymbol] = []
    for child in node.children:
        target = child
        if child.type == "decorated_definition":
            target = next(
                (c for c in child.children if c.type in ("function_definition", "class_definition")),
                None,
            )
            if target is None:
                continue
        if target.type == "function_definition":
            name_node = target.child_by_field_name("name")
            if name_node:
                symbols.append(_RawSymbol(
                    name=_text(name_node, source),
                    symbol_type="method" if in_class else "function",
                    start_line=child.start_point[0] + 1,
                    end_line=child.end_point[0] + 1,
                    start_byte=child.start_byte,
                    end_byte=child.end_byte,
                    is_async=_has_async_child(target),
                    param_count=_count_params(target),
                ))
            body = target.child_by_field_name("body")
            if body:
                symbols.extend(_walk_python(body, source, in_class=False))
        elif target.type == "class_definition":
            name_node = target.child_by_field_name("name")
            if name_node:
                symbols.append(_RawSymbol(
                    name=_text(name_node, source),
                    symbol_type="class",
                    start_line=child.start_point[0] + 1,
                    end_line=child.end_point[0] + 1,
                    start_byte=child.start_byte,
                    end_byte=child.end_byte,
                ))
            body = target.child_by_field_name("body")
            if body:
                symbols.extend(_walk_python(body, source, in_class=True))
        elif target.type in ("import_statement", "import_from_statement"):
            symbols.append(_RawSymbol(
                name=_text(target, source).strip(),
                symbol_type="import",
                start_line=child.start_point[0] + 1,
                end_line=child.end_point[0] + 1,
                start_byte=child.start_byte,
                end_byte=child.end_byte,
            ))
        elif child.children:
            symbols.extend(_walk_python(child, source, in_class=in_class))
    return symbols


def _walk_jsts(node, source: bytes) -> list[_RawSymbol]:
    symbols: list[_RawSymbol] = []
    for child in node.children:
        if child.type == "function_declaration":
            name_node = child.child_by_field_name("name")
            if name_node:
                symbols.append(_RawSymbol(
                    name=_text(name_node, source),
                    symbol_type="function",
                    start_line=child.start_point[0] + 1,
                    end_line=child.end_point[0] + 1,
                    start_byte=child.start_byte,
                    end_byte=child.end_byte,
                    is_async=_has_async_child(child),
                    param_count=_count_params(child),
                ))
            body = child.child_by_field_name("body")
            if body:
                symbols.extend(_walk_jsts(body, source))
        elif child.type == "class_declaration":
            name_node = child.child_by_field_name("name")
            if name_node:
                symbols.append(_RawSymbol(
                    name=_text(name_node, source),
                    symbol_type="class",
                    start_line=child.start_point[0] + 1,
                    end_line=child.end_point[0] + 1,
                    start_byte=child.start_byte,
                    end_byte=child.end_byte,
                ))
            body = child.child_by_field_name("body")
            if body:
                symbols.extend(_walk_jsts(body, source))
        elif child.type == "method_definition":
            name_node = child.child_by_field_name("name")
            if name_node:
                symbols.append(_RawSymbol(
                    name=_text(name_node, source),
                    symbol_type="method",
                    start_line=child.start_point[0] + 1,
                    end_line=child.end_point[0] + 1,
                    start_byte=child.start_byte,
                    end_byte=child.end_byte,
                    is_async=_has_async_child(child),
                    param_count=_count_params(child),
                ))
        elif child.type == "variable_declarator":
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            if name_node and value_node and value_node.type in ("arrow_function", "function", "function_expression"):
                symbols.append(_RawSymbol(
                    name=_text(name_node, source),
                    symbol_type="function",
                    start_line=child.start_point[0] + 1,
                    end_line=child.end_point[0] + 1,
                    start_byte=child.start_byte,
                    end_byte=child.end_byte,
                    is_async=_has_async_child(value_node),
                    param_count=_count_params(value_node),
                ))
        elif child.type == "import_statement":
            symbols.append(_RawSymbol(
                name=_text(child, source).strip(),
                symbol_type="import",
                start_line=child.start_point[0] + 1,
                end_line=child.end_point[0] + 1,
                start_byte=child.start_byte,
                end_byte=child.end_byte,
            ))
        elif child.children:
            symbols.extend(_walk_jsts(child, source))
    return symbols


def extract_raw_symbols(file_path: str, source: bytes) -> list[_RawSymbol]:
    language_name, tree = parse_file(file_path, source)
    if tree is None:
        return []
    if language_name == "python":
        return _walk_python(tree.root_node, source, in_class=False)
    return _walk_jsts(tree.root_node, source)


def extract_symbols(file_path: str, source: bytes) -> list[Symbol]:
    """Public helper: returns domain Symbol objects (no byte offsets)."""
    return [
        Symbol(
            name=s.name,
            file=file_path,
            symbol_type=s.symbol_type,
            start_line=s.start_line,
            end_line=s.end_line,
            is_async=s.is_async,
            param_count=s.param_count,
        )
        for s in extract_raw_symbols(file_path, source)
    ]


def _collect_calls(node, source: bytes, call_node_type: str) -> list[tuple[str, int]]:
    calls: list[tuple[str, int]] = []
    if node.type == call_node_type:
        func = node.child_by_field_name("function")
        if func is not None:
            name = None
            if func.type == "identifier":
                name = _text(func, source)
            elif func.type in ("attribute", "member_expression"):
                attr = func.child_by_field_name("attribute") or func.child_by_field_name("property")
                if attr is not None:
                    name = _text(attr, source)
            if name:
                calls.append((name, node.start_byte))
    for child in node.children:
        calls.extend(_collect_calls(child, source, call_node_type))
    return calls


def extract_calls(file_path: str, source: bytes) -> list[tuple[str, int]]:
    language_name, tree = parse_file(file_path, source)
    if tree is None:
        return []
    call_node_type = "call" if language_name == "python" else "call_expression"
    return _collect_calls(tree.root_node, source, call_node_type)


# ---- diff position helpers ----------------------------------------------------

_HUNK_HEADER_RE = _re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)")


def _parse_hunk_header(line: str):
    m = _HUNK_HEADER_RE.match(line)
    if not m:
        return None
    old_start, old_count, new_start, new_count, _ = m.groups()
    return (
        int(old_start),
        int(old_count) if old_count is not None else 1,
        int(new_start),
        int(new_count) if new_count is not None else 1,
    )


def hunk_new_line_ranges(patch_text: str) -> list[tuple[int, int]]:
    ranges = []
    for line in patch_text.splitlines():
        parsed = _parse_hunk_header(line)
        if parsed is None:
            continue
        _, _, new_start, new_count = parsed
        if new_count == 0:
            ranges.append((max(new_start, 1), max(new_start, 1)))
        else:
            ranges.append((new_start, new_start + new_count - 1))
    return ranges


def parse_hunks(file_path: str, patch_text: str) -> list[DiffHunk]:
    """Parse a file's unified patch into structured DiffHunk objects."""
    hunks: list[DiffHunk] = []
    current_header = ""
    current_parsed = None
    current_lines: list[str] = []

    def _flush():
        if current_parsed is not None:
            old_start, old_count, new_start, new_count = current_parsed
            hunks.append(DiffHunk(
                file=file_path,
                old_start=old_start, old_count=old_count,
                new_start=new_start, new_count=new_count,
                header=current_header,
                lines=list(current_lines),
            ))

    for line in patch_text.splitlines():
        parsed = _parse_hunk_header(line)
        if parsed is not None:
            _flush()
            current_header = line
            current_parsed = parsed
            current_lines = []
        elif current_parsed is not None:
            current_lines.append(line)

    _flush()
    return hunks


def compute_diff_positions(file_path: str, patch_text: str) -> list[DiffPosition]:
    positions: list[DiffPosition] = []
    old_line = new_line = 0
    position = 0
    for line in patch_text.splitlines():
        position += 1
        header = _parse_hunk_header(line)
        if header is not None:
            old_line, _, new_line, _ = header
            positions.append(DiffPosition(file=file_path, new_line=None, old_line=None, position=position, hunk_header=line))
            continue
        if line.startswith("\\"):
            positions.append(DiffPosition(file=file_path, new_line=None, old_line=None, position=position, hunk_header=""))
            continue
        if line.startswith("-"):
            positions.append(DiffPosition(file=file_path, new_line=None, old_line=old_line, position=position, hunk_header=""))
            old_line += 1
        elif line.startswith("+"):
            positions.append(DiffPosition(file=file_path, new_line=new_line, old_line=None, position=position, hunk_header=""))
            new_line += 1
        else:
            positions.append(DiffPosition(file=file_path, new_line=new_line, old_line=old_line, position=position, hunk_header=""))
            old_line += 1
            new_line += 1
    return positions


def find_diff_position(diff_positions: list[DiffPosition], file_path: str, new_line: int) -> DiffPosition | None:
    return next((dp for dp in diff_positions if dp.file == file_path and dp.new_line == new_line), None)


# ---- diff analysis logic -------------------------------------------------------

def _changed_symbols_for_file(fd: FileDiff, new_raw: list[_RawSymbol]) -> list[Symbol]:
    """Map a file diff to Symbol objects annotated with change_type."""
    file = fd.file

    if fd.status == "removed" or fd.new_source is None:
        old_src = fd.old_source
        if old_src is None:
            return []
        return [
            Symbol(name=s.name, file=file, symbol_type=s.symbol_type,
                   start_line=s.start_line, end_line=s.end_line,
                   is_async=s.is_async, param_count=s.param_count,
                   change_type="deleted")
            for s in extract_raw_symbols(file, old_src)
        ]

    if fd.status == "added":
        return [
            Symbol(name=s.name, file=file, symbol_type=s.symbol_type,
                   start_line=s.start_line, end_line=s.end_line,
                   is_async=s.is_async, param_count=s.param_count,
                   change_type="added")
            for s in new_raw
        ]

    touched_ranges = hunk_new_line_ranges(fd.patch)
    return [
        Symbol(name=s.name, file=file, symbol_type=s.symbol_type,
               start_line=s.start_line, end_line=s.end_line,
               is_async=s.is_async, param_count=s.param_count,
               change_type="modified")
        for s in new_raw
        if any(s.start_line <= end and start <= s.end_line for start, end in touched_ranges)
    ]


def _detect_signature_changes(fd: FileDiff, changed: list[Symbol], new_raw: list[_RawSymbol]) -> list[str]:
    if fd.status != "modified" or fd.old_source is None or fd.new_source is None:
        return []
    new_by_id = {(s.name, s.start_line): s for s in new_raw}
    old_by_name: dict[str, list[_RawSymbol]] = {}
    for s in extract_raw_symbols(fd.file, fd.old_source):
        old_by_name.setdefault(s.name, []).append(s)
    findings = []
    for sym in changed:
        if sym.symbol_type not in ("function", "method") or sym.change_type != "modified":
            continue
        new_sym = new_by_id.get((sym.name, sym.start_line))
        candidates = old_by_name.get(sym.name)
        if new_sym is None or not candidates:
            continue
        old_sym = min(candidates, key=lambda s: abs(s.start_line - new_sym.start_line))
        if old_sym.is_async != new_sym.is_async:
            findings.append(f"{sym.name}() changed between sync and async - likely breaks existing callers")
        elif (old_sym.param_count is not None and new_sym.param_count is not None
              and old_sym.param_count != new_sym.param_count):
            findings.append(
                f"{sym.name}() parameter count changed ({old_sym.param_count} → {new_sym.param_count}) "
                "- likely breaks existing callers"
            )
    return findings


def _bucket_score(score: int) -> Literal["low", "medium", "high"]:
    if score >= _HIGH_RISK_THRESHOLD:
        return "high"
    if score >= _MEDIUM_RISK_THRESHOLD:
        return "medium"
    return "low"


def _score_risk(file_diffs: list[FileDiff], changed: list[Symbol], sig_changes: list[str]) -> tuple[int, list[str]]:
    score = 0
    factors: list[str] = []
    sensitive = [fd.file for fd in file_diffs if any(kw in fd.file.lower() for kw in SENSITIVE_PATH_KEYWORDS)]
    if sensitive:
        score += 3
        factors.append(f"touches sensitive-sounding paths: {', '.join(sensitive)}")
    if sig_changes:
        score += len(sig_changes)
        factors.extend(sig_changes)
    deletions = [s for s in changed if s.change_type == "deleted"]
    if deletions:
        score += min(len(deletions), 3)
        factors.append(f"{len(deletions)} symbol(s) deleted")
    total_lines = sum(fd.lines_changed for fd in file_diffs)
    if total_lines > 200:
        score += 1
        factors.append(f"large diff ({total_lines} lines changed)")
    if len(file_diffs) > 5:
        score += 1
        factors.append(f"{len(file_diffs)} files changed")
    if not changed:
        factors.append("no recognizable symbols changed (untracked language or non-code diff)")
    return score, factors


# ---- node entry point ----------------------------------------------------------

def run(state: PRReviewState) -> PRReviewState:
    file_diffs = state["file_diffs"]
    run_id = state["review_run_id"]

    changed_symbols: list[Symbol] = []
    diff_positions: list[DiffPosition] = []
    parsed_hunks: list[DiffHunk] = []
    sig_changes: list[str] = []

    for fd in file_diffs:
        new_raw = extract_raw_symbols(fd.file, fd.new_source) if fd.new_source is not None else []
        file_syms = _changed_symbols_for_file(fd, new_raw)
        changed_symbols.extend(file_syms)
        sig_changes.extend(_detect_signature_changes(fd, file_syms, new_raw))
        diff_positions.extend(compute_diff_positions(fd.file, fd.patch))
        parsed_hunks.extend(parse_hunks(fd.file, fd.patch))

    score, risk_factors = _score_risk(file_diffs, changed_symbols, sig_changes)

    return {
        **state,
        "parsed_hunks": parsed_hunks,
        "changed_symbols": changed_symbols,
        "risk_level": _bucket_score(score),
        "risk_score": score,
        "risk_factors": risk_factors,
        "diff_positions": diff_positions,
        "phase_status": {**state.get("phase_status", {}), "symbols": "done"},
    }
