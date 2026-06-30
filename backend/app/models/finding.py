import uuid
from typing import Optional

from sqlmodel import Field, SQLModel


class Finding(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    review_run_id: str = Field(foreign_key="reviewrun.id", index=True)
    file: str
    line: Optional[int] = None
    dimension: str
    finding: str
    evidence: str
    severity: str
    confidence: float
    published: bool = False
    discarded: bool = False
    # Stable 16-char sha256 prefix over (file, dimension, finding_text).
    # Excludes line number so identity survives line drift from unrelated hunks.
    # NULL on rows written before this field was added.
    fingerprint: Optional[str] = None
