from typing import Literal

from pydantic import BaseModel


class ReviewFinding(BaseModel):
    file: str
    line: int | None = None
    dimension: Literal[
        "correctness", "architecture", "testing", "maintainability",
        "security", "performance", "logging",
    ]
    finding: str
    evidence: str
    severity: Literal["info", "minor", "major", "blocking"]


class PreviousFindingStatus(BaseModel):
    """Per-fingerprint verdict returned by the review agent on re-review.
    Replaces pure prose matching with a structured, code-verifiable judgment."""
    fingerprint: str
    status: Literal["resolved", "still_present", "unrelated"]


class ReviewFindingsResponse(BaseModel):
    """Structured-output wrapper. The OpenAI/Azure structured-output API
    requires a single JSON object as the root, not a bare list."""
    findings: list[ReviewFinding]
    change_summary: str
    suggested_pr_description: str
    previous_finding_statuses: list[PreviousFindingStatus] = []
