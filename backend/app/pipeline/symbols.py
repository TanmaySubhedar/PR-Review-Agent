from dataclasses import dataclass
from typing import Literal

from app.pipeline.treesitter_support import parse_file

SymbolType = Literal["function", "class", "method", "import", "variable"]


@dataclass
class RawSymbol:
    name: str
    symbol_type: SymbolType
    start_line: int  # 1-indexed, inclusive
    end_line: int  # 1-indexed, inclusive
    start_byte: int
    end_byte: int
    is_async: bool = False
    param_count: int | None = None  # None for non-callables (class/import)


def _text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _has_async_child(node) -> bool:
    """Both tree-sitter-python and tree-sitter-javascript/typescript represent
    `async` as a direct child token of the function/method node (verified
    empirically against both grammars), so checking for it structurally is
    exact - unlike scanning the symbol's source text for the word 'async',
    which can false-positive on a decorator/comment line above the def."""
    return any(c.type == "async" for c in node.children)


def _count_params(def_node) -> int | None:
    """Both grammars expose the parameter list via the same 'parameters'
    field name (the node TYPE differs - `parameters` vs `formal_parameters` -
    but the field name on the parent def node doesn't), so one implementation
    covers Python/JS/TS. Returns None if there's no conventional parameter
    list to count (e.g. a no-parens single-param arrow function)."""
    params_node = def_node.child_by_field_name("parameters")
    if params_node is None:
        return None
    return sum(1 for c in params_node.children if c.type not in ("(", ")", ","))


def _walk_python(node, source: bytes, in_class: bool) -> list[RawSymbol]:
    symbols: list[RawSymbol] = []
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
                symbols.append(
                    RawSymbol(
                        name=_text(name_node, source),
                        symbol_type="method" if in_class else "function",
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        start_byte=child.start_byte,
                        end_byte=child.end_byte,
                        is_async=_has_async_child(target),
                        param_count=_count_params(target),
                    )
                )
            body = target.child_by_field_name("body")
            if body:
                symbols.extend(_walk_python(body, source, in_class=False))
        elif target.type == "class_definition":
            name_node = target.child_by_field_name("name")
            if name_node:
                symbols.append(
                    RawSymbol(
                        name=_text(name_node, source),
                        symbol_type="class",
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        start_byte=child.start_byte,
                        end_byte=child.end_byte,
                    )
                )
            body = target.child_by_field_name("body")
            if body:
                symbols.extend(_walk_python(body, source, in_class=True))
        elif target.type in ("import_statement", "import_from_statement"):
            symbols.append(
                RawSymbol(
                    name=_text(target, source).strip(),
                    symbol_type="import",
                    start_line=child.start_point[0] + 1,
                    end_line=child.end_point[0] + 1,
                    start_byte=child.start_byte,
                    end_byte=child.end_byte,
                )
            )
        elif child.children:
            symbols.extend(_walk_python(child, source, in_class=in_class))
    return symbols


def _walk_jsts(node, source: bytes) -> list[RawSymbol]:
    symbols: list[RawSymbol] = []
    for child in node.children:
        if child.type == "function_declaration":
            name_node = child.child_by_field_name("name")
            if name_node:
                symbols.append(
                    RawSymbol(
                        name=_text(name_node, source),
                        symbol_type="function",
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        start_byte=child.start_byte,
                        end_byte=child.end_byte,
                        is_async=_has_async_child(child),
                        param_count=_count_params(child),
                    )
                )
            body = child.child_by_field_name("body")
            if body:
                symbols.extend(_walk_jsts(body, source))
        elif child.type == "class_declaration":
            name_node = child.child_by_field_name("name")
            if name_node:
                symbols.append(
                    RawSymbol(
                        name=_text(name_node, source),
                        symbol_type="class",
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        start_byte=child.start_byte,
                        end_byte=child.end_byte,
                    )
                )
            body = child.child_by_field_name("body")
            if body:
                symbols.extend(_walk_jsts(body, source))
        elif child.type == "method_definition":
            name_node = child.child_by_field_name("name")
            if name_node:
                symbols.append(
                    RawSymbol(
                        name=_text(name_node, source),
                        symbol_type="method",
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        start_byte=child.start_byte,
                        end_byte=child.end_byte,
                        is_async=_has_async_child(child),
                        param_count=_count_params(child),
                    )
                )
        elif child.type == "variable_declarator":
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            if (
                name_node is not None
                and value_node is not None
                and value_node.type in ("arrow_function", "function", "function_expression")
            ):
                symbols.append(
                    RawSymbol(
                        name=_text(name_node, source),
                        symbol_type="function",
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        start_byte=child.start_byte,
                        end_byte=child.end_byte,
                        is_async=_has_async_child(value_node),
                        param_count=_count_params(value_node),
                    )
                )
        elif child.type == "import_statement":
            symbols.append(
                RawSymbol(
                    name=_text(child, source).strip(),
                    symbol_type="import",
                    start_line=child.start_point[0] + 1,
                    end_line=child.end_point[0] + 1,
                    start_byte=child.start_byte,
                    end_byte=child.end_byte,
                )
            )
        elif child.children:
            symbols.extend(_walk_jsts(child, source))
    return symbols


def extract_symbols(file_path: str, source: bytes) -> list[RawSymbol]:
    """Extract top-level and nested function/class/method/import symbols from
    a source file. Returns [] for unsupported languages (anything outside the
    v1 scope of Python/JS/TS/TSX)."""
    language_name, tree = parse_file(file_path, source)
    if tree is None:
        return []
    if language_name == "python":
        return _walk_python(tree.root_node, source, in_class=False)
    return _walk_jsts(tree.root_node, source)


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
    """Best-effort call-site extraction: returns (called_name, start_byte) for
    every call expression in the file. Resolution to a specific definition
    happens by name in the blast-radius graph builder, not here - this mirrors
    how Graphify-style tools label graph edges as best-effort/inferred rather
    than fully resolved, which is the right tradeoff without a full type
    checker."""
    language_name, tree = parse_file(file_path, source)
    if tree is None:
        return []
    call_node_type = "call" if language_name == "python" else "call_expression"
    return _collect_calls(tree.root_node, source, call_node_type)
