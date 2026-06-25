from app.pipeline.diff_analysis import FileDiff, analyze_diff, refine_risk_with_blast_radius
from app.schemas.blast_radius import BlastRadius, BlastRadiusEntry, SymbolRef

OLD_SOURCE = b"""def validate_token(token):
    payload = decode(token)
    return payload
"""

NEW_SOURCE = b"""def validate_token(token):
    payload = decode(token)
    if is_expired(payload):
        return None
    return payload
"""

PATCH = (
    "@@ -1,3 +1,5 @@\n"
    " def validate_token(token):\n"
    "     payload = decode(token)\n"
    "+    if is_expired(payload):\n"
    "+        return None\n"
    "     return payload\n"
)


def test_analyze_diff_finds_modified_symbol_and_risk():
    file_diff = FileDiff(
        file="auth/utils.py",
        patch=PATCH,
        status="modified",
        new_source=NEW_SOURCE,
        old_source=OLD_SOURCE,
        lines_changed=2,
    )

    result = analyze_diff("run-1", [file_diff])

    assert len(result.changed_symbols) == 1
    symbol = result.changed_symbols[0]
    assert symbol.symbol_name == "validate_token"
    assert symbol.symbol_type == "function"
    assert symbol.change_type == "modified"

    # "auth" in the path alone is enough to reach at least medium risk
    assert result.risk_level in ("medium", "high")
    assert any("sensitive" in f for f in result.risk_factors)

    # diff positions must be threaded through unchanged for phase 9 to use later
    assert len(result.diff_positions) > 0


def test_analyze_diff_unchanged_symbol_outside_hunk_is_excluded():
    new_source = NEW_SOURCE + b"\n\ndef unrelated_helper():\n    return 1\n"
    file_diff = FileDiff(
        file="auth/utils.py",
        patch=PATCH,
        status="modified",
        new_source=new_source,
        old_source=OLD_SOURCE,
        lines_changed=2,
    )

    result = analyze_diff("run-1", [file_diff])

    names = {s.symbol_name for s in result.changed_symbols}
    assert "validate_token" in names
    assert "unrelated_helper" not in names


def test_analyze_diff_added_file_marks_all_symbols_added():
    file_diff = FileDiff(
        file="auth/new_module.py",
        patch="@@ -0,0 +1,3 @@\n+def helper():\n+    return 1\n+\n",
        status="added",
        new_source=b"def helper():\n    return 1\n",
        old_source=None,
        lines_changed=2,
    )

    result = analyze_diff("run-1", [file_diff])

    assert len(result.changed_symbols) == 1
    assert result.changed_symbols[0].change_type == "added"


def test_analyze_diff_detects_async_to_sync_breaking_change():
    old_source = b"async def resolve_user(self, token):\n    return await fetch(token)\n"
    new_source = b"def resolve_user(self, token):\n    return fetch(token)\n"
    patch = (
        "@@ -1,2 +1,2 @@\n"
        "-async def resolve_user(self, token):\n"
        "-    return await fetch(token)\n"
        "+def resolve_user(self, token):\n"
        "+    return fetch(token)\n"
    )
    file_diff = FileDiff(
        file="backend/app.py", patch=patch, status="modified", new_source=new_source, old_source=old_source
    )

    result = analyze_diff("run-1", [file_diff])

    assert any("sync and async" in f for f in result.risk_factors)


def test_analyze_diff_does_not_collide_same_named_methods_across_classes():
    """Regression test: two classes in the same file each define a method
    called 'process'. Only A.process flips sync->async; B.process is
    unchanged. A bare-name lookup would collapse both into one dict entry
    and could compare B's (unchanged) text against itself, missing A's real
    breaking change entirely."""
    old_source = (
        b"class A:\n"
        b"    def process(self, x):\n"
        b"        return x\n"
        b"\n"
        b"class B:\n"
        b"    async def process(self, x):\n"
        b"        return x\n"
    )
    new_source = (
        b"class A:\n"
        b"    async def process(self, x):\n"
        b"        return x\n"
        b"\n"
        b"class B:\n"
        b"    async def process(self, x):\n"
        b"        return x\n"
    )
    patch = (
        "@@ -1,3 +1,3 @@\n"
        " class A:\n"
        "-    def process(self, x):\n"
        "+    async def process(self, x):\n"
        "         return x\n"
    )
    file_diff = FileDiff(
        file="backend/app.py", patch=patch, status="modified", new_source=new_source, old_source=old_source
    )

    result = analyze_diff("run-1", [file_diff])

    assert any("sync and async" in f for f in result.risk_factors)


def test_analyze_diff_detects_parameter_count_change():
    old_source = b"def process(self, x):\n    return x\n"
    new_source = b"def process(self, x, y):\n    return x\n"
    patch = (
        "@@ -1,2 +1,2 @@\n"
        "-def process(self, x):\n"
        "+def process(self, x, y):\n"
        "     return x\n"
    )
    file_diff = FileDiff(
        file="backend/app.py", patch=patch, status="modified", new_source=new_source, old_source=old_source
    )

    result = analyze_diff("run-1", [file_diff])

    assert any("parameter count changed" in f for f in result.risk_factors)


def test_risk_score_carries_through_refinement_without_lossy_rebucketing():
    """A diff-only score of exactly 3 (medium) plus a blast-radius bonus of 1
    must land at 4, not silently snap back to the medium-threshold floor of 3
    as it would if refinement re-derived a base score from the bucket alone."""
    file_diff = FileDiff(file="auth/utils.py", patch=PATCH, status="modified", new_source=NEW_SOURCE, old_source=OLD_SOURCE)
    diff_analysis = analyze_diff("run-1", [file_diff])
    assert diff_analysis.risk_score == 3  # sensitive path only

    blast_radius = BlastRadius(
        entries=[
            BlastRadiusEntry(
                symbol="validate_token",
                file="auth/utils.py",
                callers=[SymbolRef(file="x.py", symbol_name="caller", line=1, relationship="caller")],
                tests=[SymbolRef(file="tests/test_x.py", symbol_name="test_it", line=1, relationship="test")],
            )
        ]
    )
    refined = refine_risk_with_blast_radius(diff_analysis, blast_radius)

    assert refined.risk_score == 4  # 3 (sensitive path) + 1 (single caller, tested)
    assert refined.risk_level == "medium"


def test_refine_risk_with_blast_radius_escalates_widely_called_untested_symbol():
    """Reproduces a real case: a diff-only score of 'low' (no sensitive path,
    no deletions, small diff) must become 'high' once blast radius shows the
    symbol is called from many places and has zero test coverage - exactly
    the case that was originally mis-scored as 'low'."""
    file_diff = FileDiff(
        file="backend/app.py",
        patch="@@ -95,3 +95,1 @@\n def _fix_enums(value):\n-    if isinstance(value, list):\n-        return [_fix_enums(v) for v in value]\n",
        status="modified",
        new_source=b"def _fix_enums(value):\n    return value\n",
        old_source=b"def _fix_enums(value):\n    if isinstance(value, list):\n        return [_fix_enums(v) for v in value]\n",
    )
    diff_analysis = analyze_diff("run-1", [file_diff])
    assert diff_analysis.risk_level == "low"

    callers = [
        SymbolRef(file=f, symbol_name=name, line=1, relationship="caller")
        for f, name in [
            ("backend/app.py", "chat"),
            ("backend/app.py", "chat_stream"),
            ("backend/app.py", "collect_and_yield"),
            ("backend/app.py", "collect_response"),
            ("backend/app.py", "generate"),
            ("backend/app.py", "run"),
            ("backend/app.py", "serialize_component"),
        ]
    ]
    blast_radius = BlastRadius(
        entries=[
            BlastRadiusEntry(symbol="_fix_enums", file="backend/app.py", callers=callers, tests=[])
        ]
    )

    refined = refine_risk_with_blast_radius(diff_analysis, blast_radius)

    assert refined.risk_level == "high"
    assert any("no test coverage" in f for f in refined.risk_factors)
