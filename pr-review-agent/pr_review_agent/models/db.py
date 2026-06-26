"""SQLModel table definitions for run history persistence."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class RunRecord(SQLModel, table=True):
    __tablename__ = "run_record"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    repo_full_name: str
    pr_number: int
    pr_url: str
    title: str
    head_sha: str
    base_sha: str
    status: str = Field(default="received")  # received|analyzing|reviewing|publishing|done|failed
    risk_level: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FindingRecord(SQLModel, table=True):
    __tablename__ = "finding_record"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    review_run_id: str = Field(foreign_key="run_record.id", index=True)
    file: str
    line: Optional[int] = None
    dimension: str
    finding: str
    evidence: str
    severity: str
    confidence: float
    published: bool = False
    discarded: bool = False


class PhaseLog(SQLModel, table=True):
    __tablename__ = "phase_log"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    review_run_id: str = Field(foreign_key="run_record.id", index=True)
    phase: str  # ingest|symbols|graphify|context|readers|synthesizer|reviewer|critic
    status: str = Field(default="pending")  # pending|running|done|failed
    detail: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
