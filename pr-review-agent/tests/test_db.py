"""Tests for SQLite DB initialisation and basic CRUD."""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlmodel import Session, create_engine, SQLModel, select

from pr_review_agent.models.db import FindingRecord, PhaseLog, RunRecord


@pytest.fixture()
def in_memory_engine():
    """In-memory SQLite engine with all tables created."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def test_init_db_creates_tables(tmp_path):
    db_path = tmp_path / "test_runs.db"
    db_url = f"sqlite:///{db_path}"
    with (
        patch("pr_review_agent.db._DB_URL", db_url),
        patch("pr_review_agent.db._DB_DIR", tmp_path),
        patch("pr_review_agent.db.engine", create_engine(db_url, connect_args={"check_same_thread": False})),
    ):
        from pr_review_agent.db import init_db
        init_db()
    assert db_path.exists()


def test_review_run_crud(in_memory_engine):
    run_id = str(uuid.uuid4())
    with Session(in_memory_engine) as session:
        run = RunRecord(
            id=run_id,
            repo_full_name="owner/repo",
            pr_number=1,
            pr_url="https://github.com/owner/repo/pull/1",
            title="Test PR",
            head_sha="abc123",
            base_sha="def456",
        )
        session.add(run)
        session.commit()

    with Session(in_memory_engine) as session:
        fetched = session.exec(select(RunRecord).where(RunRecord.id == run_id)).first()
        assert fetched is not None
        assert fetched.status == "received"
        assert fetched.repo_full_name == "owner/repo"


def test_finding_crud(in_memory_engine):
    run_id = str(uuid.uuid4())
    with Session(in_memory_engine) as session:
        run = RunRecord(
            id=run_id, repo_full_name="owner/repo", pr_number=2,
            pr_url="https://github.com/owner/repo/pull/2",
            title="PR 2", head_sha="aaa", base_sha="bbb",
        )
        finding = FindingRecord(
            review_run_id=run_id,
            file="auth/utils.py",
            line=5,
            dimension="correctness",
            finding="Potential null dereference",
            evidence="Line 5: foo = bar.baz",
            severity="major",
            confidence=0.85,
        )
        session.add(run)
        session.add(finding)
        session.commit()

    with Session(in_memory_engine) as session:
        rows = session.exec(select(FindingRecord).where(FindingRecord.review_run_id == run_id)).all()
        assert len(rows) == 1
        assert rows[0].severity == "major"
        assert rows[0].confidence == 0.85
