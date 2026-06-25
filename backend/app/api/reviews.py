from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.models import Finding, PhaseLog, ReviewRun

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


@router.get("")
def list_reviews(session: Session = Depends(get_session)) -> list[ReviewRun]:
    return list(session.exec(select(ReviewRun).order_by(ReviewRun.created_at.desc())))


@router.get("/{review_run_id}")
def get_review(review_run_id: str, session: Session = Depends(get_session)) -> ReviewRun:
    run = session.get(ReviewRun, review_run_id)
    if not run:
        raise HTTPException(status_code=404, detail="review run not found")
    return run


@router.get("/{review_run_id}/findings")
def get_findings(review_run_id: str, session: Session = Depends(get_session)) -> list[Finding]:
    return list(
        session.exec(select(Finding).where(Finding.review_run_id == review_run_id))
    )


@router.get("/{review_run_id}/phases")
def get_phases(review_run_id: str, session: Session = Depends(get_session)) -> list[PhaseLog]:
    return list(
        session.exec(select(PhaseLog).where(PhaseLog.review_run_id == review_run_id))
    )
