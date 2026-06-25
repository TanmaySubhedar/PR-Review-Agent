import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class ReviewRun(SQLModel, table=True):
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
    change_summary: Optional[str] = None
    suggested_pr_description: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
