from datetime import datetime, timezone

from sqlmodel import Session, SQLModel, create_engine

from app.models import Finding, ReviewRun
from app.pipeline.runner import _MAX_PREVIOUS_FINDINGS, _fetch_previous_findings


def _make_session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _make_run(session: Session, *, repo: str, pr_number: int, status: str, created_at: datetime) -> ReviewRun:
    run = ReviewRun(
        repo_full_name=repo,
        pr_number=pr_number,
        pr_url="https://github.com/x/y/pull/1",
        title="t",
        head_sha="h",
        base_sha="b",
        status=status,
        created_at=created_at,
        updated_at=created_at,
    )
    session.add(run)
    session.commit()
    return run


def test_fetch_previous_findings_returns_empty_when_no_prior_run():
    session = _make_session()
    _make_run(session, repo="o/r", pr_number=1, status="done", created_at=datetime.now(timezone.utc))

    result = _fetch_previous_findings(session, "o/r", 1, exclude_run_id="some-other-run")

    assert result == []


def test_fetch_previous_findings_picks_most_recent_done_run_and_only_published():
    session = _make_session()
    older = _make_run(session, repo="o/r", pr_number=1, status="done", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    newer = _make_run(session, repo="o/r", pr_number=1, status="done", created_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
    current = _make_run(session, repo="o/r", pr_number=1, status="analyzing", created_at=datetime(2026, 1, 3, tzinfo=timezone.utc))

    session.add(Finding(review_run_id=older.id, file="old.py", line=1, dimension="correctness", finding="old finding", evidence="x", severity="major", confidence=0.9, published=True))
    session.add(Finding(review_run_id=newer.id, file="new.py", line=2, dimension="correctness", finding="new finding", evidence="y", severity="major", confidence=0.9, published=True))
    session.add(Finding(review_run_id=newer.id, file="new.py", line=3, dimension="testing", finding="discarded finding", evidence="z", severity="minor", confidence=0.2, published=False, discarded=True))
    session.commit()

    result = _fetch_previous_findings(session, "o/r", 1, exclude_run_id=current.id)

    assert len(result) == 1
    assert result[0].file == "new.py"
    assert result[0].finding == "new finding"


def test_fetch_previous_findings_excludes_current_run_even_if_marked_done():
    session = _make_session()
    current = _make_run(session, repo="o/r", pr_number=1, status="done", created_at=datetime.now(timezone.utc))
    session.add(Finding(review_run_id=current.id, file="x.py", line=1, dimension="correctness", finding="f", evidence="e", severity="major", confidence=0.9, published=True))
    session.commit()

    result = _fetch_previous_findings(session, "o/r", 1, exclude_run_id=current.id)

    assert result == []


def test_fetch_previous_findings_caps_at_max_and_keeps_highest_confidence():
    session = _make_session()
    older = _make_run(session, repo="o/r", pr_number=1, status="done", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    current = _make_run(session, repo="o/r", pr_number=1, status="analyzing", created_at=datetime(2026, 1, 2, tzinfo=timezone.utc))

    for i in range(_MAX_PREVIOUS_FINDINGS + 5):
        session.add(
            Finding(
                review_run_id=older.id,
                file=f"f{i}.py",
                line=i,
                dimension="correctness",
                finding=f"finding {i}",
                evidence="e",
                severity="major",
                confidence=i / 100,  # later i = higher confidence
                published=True,
            )
        )
    session.commit()

    result = _fetch_previous_findings(session, "o/r", 1, exclude_run_id=current.id)

    assert len(result) == _MAX_PREVIOUS_FINDINGS
    # the highest-confidence findings (largest i) must be the ones kept
    kept_files = {f.file for f in result}
    assert "f19.py" in kept_files  # i=19 has the highest confidence among 0..19
    assert "f0.py" not in kept_files
