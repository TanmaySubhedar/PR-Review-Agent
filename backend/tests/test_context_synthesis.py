from pathlib import Path

from app.pipeline.blast_radius.engine import compute_blast_radius
from app.pipeline.context_synthesis import synthesize_repository_context
from app.schemas.context_package import ReaderOutput
from app.schemas.diff_analysis import ChangedSymbol

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "sample_repo"


def test_synthesize_repository_context_merges_blast_radius_and_readers():
    changed = [
        ChangedSymbol(
            file="auth/utils.py",
            symbol_name="validate_token",
            symbol_type="function",
            change_type="modified",
            start_line=8,
            end_line=12,
        )
    ]
    blast_radius = compute_blast_radius(FIXTURE_REPO, changed)
    reader_outputs = [
        ReaderOutput(
            file="auth/middleware.py",
            purpose="Auth middleware",
            relevance="Calls validate_token on every request",
            risks=["Auth bypass if expiry isn't re-checked"],
        )
    ]

    repo_context = synthesize_repository_context(blast_radius, reader_outputs)

    assert "AuthMiddleware" in repo_context.affected_components
    assert "AdminMiddleware" in repo_context.affected_components
    assert "auth" in repo_context.affected_services
    assert "admin" in repo_context.affected_services
    assert "tests/test_auth.py" in repo_context.affected_tests
    assert "Auth bypass if expiry isn't re-checked" in repo_context.risk_areas
    assert any("validate_token is called by" in r for r in repo_context.risk_areas)


def test_synthesize_repository_context_flags_truncated_graph():
    blast_radius = compute_blast_radius(FIXTURE_REPO, [])
    blast_radius.graph_truncated = True

    repo_context = synthesize_repository_context(blast_radius, [])

    assert any("truncated" in r for r in repo_context.risk_areas)
