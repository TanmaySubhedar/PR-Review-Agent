import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class Repository(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    full_name: str = Field(unique=True, index=True)  # "owner/repo"
    clone_url: str
    default_branch: str = Field(default="main")

    # Lifecycle: pending | cloning | building_graph | ready | failed
    onboarding_status: str = Field(default="pending")
    onboarding_error: Optional[str] = None

    # Graph data stored as gzip+base64-compressed NetworkX node-link JSON.
    # NULL until onboarding_status == "ready".
    graph_json: Optional[str] = None
    graph_node_count: Optional[int] = None
    graph_edge_count: Optional[int] = None
    graph_truncated: bool = False

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
