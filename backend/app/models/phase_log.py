import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class PhaseLog(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    review_run_id: str = Field(foreign_key="reviewrun.id", index=True)
    phase: str  # ingestion|diff_analysis|blast_radius|context_retrieval|synthesis|review|critic|publish
    status: str = Field(default="pending")  # pending|running|done|failed
    detail: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
