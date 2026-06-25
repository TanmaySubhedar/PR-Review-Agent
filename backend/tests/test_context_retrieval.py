from pathlib import Path

from app.pipeline.blast_radius.engine import compute_blast_radius
from app.pipeline.context_retrieval import select_context_files
from app.schemas.diff_analysis import ChangedSymbol, DiffAnalysis

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "sample_repo"


def _diff_analysis() -> DiffAnalysis:
    return DiffAnalysis(
        review_run_id="run-1",
        changed_symbols=[
            ChangedSymbol(
                file="auth/utils.py",
                symbol_name="validate_token",
                symbol_type="function",
                change_type="modified",
                start_line=8,
                end_line=12,
            )
        ],
        risk_level="medium",
    )


def test_select_context_files_ranks_changed_file_highest():
    diff_analysis = _diff_analysis()
    blast_radius = compute_blast_radius(FIXTURE_REPO, diff_analysis.changed_symbols)

    selections = select_context_files(diff_analysis, blast_radius, max_files=20)

    by_file = {s.file: s for s in selections}
    assert by_file["auth/utils.py"].selection_reason == "changed_file"
    assert by_file["auth/utils.py"].score == max(s.score for s in selections)
    # tests/test_auth.py calls validate_token directly, so it's both a caller
    # and a test - direct_caller legitimately outranks test_coverage here.
    assert "tests/test_auth.py" in by_file
    assert by_file["tests/test_auth.py"].selection_reason == "direct_caller"
    assert selections == sorted(selections, key=lambda s: s.score, reverse=True)


def test_select_context_files_respects_max_files_cap():
    diff_analysis = _diff_analysis()
    blast_radius = compute_blast_radius(FIXTURE_REPO, diff_analysis.changed_symbols)

    selections = select_context_files(diff_analysis, blast_radius, max_files=1)

    assert len(selections) == 1
    assert selections[0].file == "auth/utils.py"
