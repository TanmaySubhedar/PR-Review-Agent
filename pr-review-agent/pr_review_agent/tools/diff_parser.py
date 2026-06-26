"""Pure-text unified diff parser. No GitHub API required."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pr_review_agent.models.domain import FileDiff

_DIFF_GIT_HEADER_RE = re.compile(r"^diff --git a/(.+?) b/(.+)$")
_NEW_FILE_RE = re.compile(r"^new file mode")
_DELETED_FILE_RE = re.compile(r"^deleted file mode")
_RENAME_FROM_RE = re.compile(r"^rename from (.+)$")
_RENAME_TO_RE = re.compile(r"^rename to (.+)$")
_BINARY_RE = re.compile(r"^Binary files? ")
_MINUS_RE = re.compile(r"^--- (?:a/(.+)|/dev/null)$")
_PLUS_RE = re.compile(r"^\+\+\+ (?:b/(.+)|/dev/null)$")


@dataclass
class _FileBlock:
    """Accumulated state for a single file in the diff."""
    a_path: str = ""
    b_path: str = ""
    status: str = "modified"
    is_binary: bool = False
    patch_lines: list[str] = field(default_factory=list)


def parse_diff(raw_diff: str) -> list[FileDiff]:
    """Parse a unified diff string into FileDiff objects.

    Handles multiple files, multiple hunks, added/deleted/modified/renamed
    files, and binary files. new_source and old_source are always None
    (text-only parse).
    """
    blocks: list[_FileBlock] = []
    current: _FileBlock | None = None

    for line in raw_diff.splitlines():
        # Start of a new file section
        m = _DIFF_GIT_HEADER_RE.match(line)
        if m:
            if current is not None:
                blocks.append(current)
            current = _FileBlock(a_path=m.group(1), b_path=m.group(2))
            continue

        if current is None:
            continue

        if _NEW_FILE_RE.match(line):
            current.status = "added"
        elif _DELETED_FILE_RE.match(line):
            current.status = "removed"
        elif _BINARY_RE.match(line):
            current.is_binary = True
        else:
            m_from = _RENAME_FROM_RE.match(line)
            if m_from:
                current.a_path = m_from.group(1)
                current.status = "renamed"
                continue
            m_to = _RENAME_TO_RE.match(line)
            if m_to:
                current.b_path = m_to.group(1)
                current.status = "renamed"
                continue

        # Collect hunk content (skip --- / +++ file headers)
        if line.startswith("@@") or (
            line and line[0] in (" ", "+", "-", "\\")
            and not _MINUS_RE.match(line)
            and not _PLUS_RE.match(line)
        ):
            current.patch_lines.append(line)

    if current is not None:
        blocks.append(current)

    result: list[FileDiff] = []
    for block in blocks:
        file_path = block.b_path if block.status != "removed" else block.a_path
        patch_text = "\n".join(block.patch_lines)
        lines_changed = sum(
            1 for ln in block.patch_lines if ln.startswith("+") or ln.startswith("-")
        )
        result.append(FileDiff(
            file=file_path,
            patch=patch_text,
            status=block.status,
            new_source=None,
            old_source=None,
            lines_changed=lines_changed,
        ))

    return result
