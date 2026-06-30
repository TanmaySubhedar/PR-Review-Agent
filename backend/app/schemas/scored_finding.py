from pydantic import BaseModel

from app.schemas.diff_analysis import DiffPosition
from app.schemas.review_finding import ReviewFinding


class CriticScore(BaseModel):
    evidence_grounded: bool
    respects_repo_context: bool
    actionable: bool
    confidence: float
    refinement_suggestion: str | None = None


class ScoredFinding(BaseModel):
    finding: ReviewFinding
    critic: CriticScore
    publish: bool
    downgrade_to_summary: bool = False
    diff_position: DiffPosition | None = None
