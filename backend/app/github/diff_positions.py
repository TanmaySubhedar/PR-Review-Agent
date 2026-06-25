import re

from app.schemas.diff_analysis import DiffPosition

_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_hunk_header(line: str) -> tuple[int, int, int, int] | None:
    """Parse a "@@ -a,b +c,d @@" header into (old_start, old_count, new_start, new_count)."""
    m = _HUNK_HEADER_RE.match(line)
    if not m:
        return None
    old_start, old_count, new_start, new_count = m.groups()
    return (
        int(old_start),
        int(old_count) if old_count is not None else 1,
        int(new_start),
        int(new_count) if new_count is not None else 1,
    )


def hunk_new_line_ranges(patch_text: str) -> list[tuple[int, int]]:
    """The (new_start, new_end) line ranges (inclusive, in the post-change file)
    covered by each hunk - used to decide which symbols in the new file a diff
    actually touches."""
    ranges: list[tuple[int, int]] = []
    for line in patch_text.splitlines():
        parsed = parse_hunk_header(line)
        if parsed is None:
            continue
        _, _, new_start, new_count = parsed
        if new_count == 0:
            # pure deletion hunk - anchor on the line just before it
            ranges.append((max(new_start, 1), max(new_start, 1)))
        else:
            ranges.append((new_start, new_start + new_count - 1))
    return ranges


def compute_diff_positions(file_path: str, patch_text: str) -> list[DiffPosition]:
    """Map every line of a file's unified-diff patch text to GitHub's 1-indexed
    `position` (offset within that file's patch), plus the corresponding
    old/new file line numbers where applicable.

    This must be computed once here (phase 2) and threaded through to phase 9,
    since GitHub's Review API anchors inline comments by `position`, not by
    the file's own line number, and a comment can only land on a line that
    appears in some hunk of this patch.
    """
    positions: list[DiffPosition] = []
    old_line = new_line = 0
    position = 0

    for line in patch_text.splitlines():
        position += 1

        header = parse_hunk_header(line)
        if header is not None:
            old_line, _, new_line, _ = header
            positions.append(
                DiffPosition(
                    file=file_path, new_line=None, old_line=None,
                    position=position, hunk_header=line,
                )
            )
            continue

        if line.startswith("\\"):
            # e.g. "\ No newline at end of file" - consumes a position, no line number
            positions.append(
                DiffPosition(file=file_path, new_line=None, old_line=None, position=position, hunk_header="")
            )
            continue

        if line.startswith("-"):
            positions.append(
                DiffPosition(file=file_path, new_line=None, old_line=old_line, position=position, hunk_header="")
            )
            old_line += 1
        elif line.startswith("+"):
            positions.append(
                DiffPosition(file=file_path, new_line=new_line, old_line=None, position=position, hunk_header="")
            )
            new_line += 1
        else:
            positions.append(
                DiffPosition(file=file_path, new_line=new_line, old_line=old_line, position=position, hunk_header="")
            )
            old_line += 1
            new_line += 1

    return positions


def find_diff_position(diff_positions: list[DiffPosition], file_path: str, new_line: int) -> DiffPosition | None:
    """Look up the DiffPosition for a finding anchored at (file, new_line).
    Returns None if that line isn't inside any hunk - the caller must downgrade
    the finding to a summary comment in that case (GitHub will reject it inline)."""
    return next((dp for dp in diff_positions if dp.file == file_path and dp.new_line == new_line), None)


def position_for_new_line(diff_positions: list[DiffPosition], file_path: str, new_line: int) -> int | None:
    dp = find_diff_position(diff_positions, file_path, new_line)
    return dp.position if dp else None
