from app.github.diff_positions import (
    compute_diff_positions,
    hunk_new_line_ranges,
    position_for_new_line,
)

PATCH = (
    "@@ -1,3 +1,5 @@\n"
    " def validate_token(token):\n"
    "     payload = decode(token)\n"
    "+    if is_expired(payload):\n"
    "+        return None\n"
    "     return payload\n"
)


def test_hunk_new_line_ranges():
    assert hunk_new_line_ranges(PATCH) == [(1, 5)]


def test_compute_diff_positions_maps_added_lines():
    positions = compute_diff_positions("auth/utils.py", PATCH)

    added = [p for p in positions if p.new_line is not None and p.old_line is None]
    assert [p.new_line for p in added] == [3, 4]

    removed = [p for p in positions if p.old_line is not None and p.new_line is None]
    assert removed == []

    # hunk header itself occupies position 1 and carries no line numbers
    assert positions[0].new_line is None and positions[0].old_line is None
    assert positions[0].hunk_header == "@@ -1,3 +1,5 @@"


def test_position_for_new_line_resolves_and_misses():
    positions = compute_diff_positions("auth/utils.py", PATCH)

    assert position_for_new_line(positions, "auth/utils.py", 3) is not None
    # line 999 was never part of this diff - must miss so the caller downgrades to a summary comment
    assert position_for_new_line(positions, "auth/utils.py", 999) is None
