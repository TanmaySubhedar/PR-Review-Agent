import json as _json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from sqlmodel import Session

from app.config import settings
from app.db import get_session
from app.github.signature import verify_signature
from app.models import PhaseLog, ReviewRun
from app.pipeline.ingestion import is_relevant_pull_request_event, parse_pull_request_event
from app.pipeline.runner import execute_review_run

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    session: Session = Depends(get_session),
):
    raw_body = await request.body()

    if settings.github_webhook_secret and not verify_signature(
        raw_body, x_hub_signature_256, settings.github_webhook_secret
    ):
        raise HTTPException(status_code=401, detail="invalid webhook signature")

    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"event={x_github_event}"}

    outer = await request.json()
    # smee.io wraps the GitHub payload as a JSON-encoded string under "payload"
    if isinstance(outer, dict) and "payload" in outer and isinstance(outer["payload"], str):
        payload = _json.loads(outer["payload"])
    else:
        payload = outer

    if not is_relevant_pull_request_event(payload):
        return {"status": "ignored", "reason": f"action={payload.get('action')}"}

    pr_event = parse_pull_request_event(payload)

    run = ReviewRun(
        repo_full_name=pr_event.repo_full_name,
        pr_number=pr_event.pr_number,
        pr_url=pr_event.pr_url,
        title=pr_event.title,
        head_sha=pr_event.head_sha,
        base_sha=pr_event.base_sha,
        status="received",
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    for phase in [
        "ingestion",
        "diff_analysis",
        "blast_radius",
        "context_retrieval",
        "synthesis",
        "review",
        "critic",
        "publish",
    ]:
        session.add(PhaseLog(review_run_id=run.id, phase=phase))
    session.commit()

    logger.info("queued review run %s for %s#%s", run.id, pr_event.repo_full_name, pr_event.pr_number)

    background_tasks.add_task(execute_review_run, run.id, pr_event)

    return {"status": "queued", "review_run_id": run.id}
