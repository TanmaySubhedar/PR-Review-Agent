"""Tree-sitter language detection and parsing. Supports Python, JS, TS, TSX."""

from functools import lru_cache
from pathlib import Path

import tree_sitter_javascript as tsjs
import tree_sitter_python as tspython
import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser

_EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
}


def detect_language(file_path: str) -> str | None:
    return _EXTENSION_TO_LANGUAGE.get(Path(file_path).suffix.lower())


@lru_cache(maxsize=None)
def _language(name: str) -> Language:
    if name == "python":
        return Language(tspython.language())
    if name == "javascript":
        return Language(tsjs.language())
    if name == "typescript":
        return Language(tsts.language_typescript())
    if name == "tsx":
        return Language(tsts.language_tsx())
    raise ValueError(f"unsupported language: {name}")


@lru_cache(maxsize=None)
def get_parser(language_name: str) -> Parser:
    return Parser(_language(language_name))


def parse_file(file_path: str, source: bytes):
    """Returns (language_name, tree) or (None, None) for unsupported extensions."""
    language_name = detect_language(file_path)
    if language_name is None:
        return None, None
    tree = get_parser(language_name).parse(source)
    return language_name, tree
