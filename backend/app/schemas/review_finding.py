from typing import Literal

from pydantic import BaseModel


class ReviewFinding(BaseModel):
    file: str
    line: int | None = None
    dimension: Literal["correctness", "architecture", "testing", "maintainability"]
    finding: str
    evidence: str
    severity: Literal["info", "minor", "major", "blocking"]


class ReviewFindingsResponse(BaseModel):
    """Structured-output wrapper - the OpenAI/Azure structured-output API
    requires a single JSON object as the root, not a bare list."""

    findings: list[ReviewFinding]
