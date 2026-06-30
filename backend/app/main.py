import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from app.api import chat, health, reviews, webhooks
from app.api import repos as repos_api
from app.db import engine, init_db
from app.models.repository import Repository
from app.models.review_run import ReviewRun
from app.onboarding_worker import onboarding_worker
from app.queue_worker import review_queue_worker
from app.schemas.pr_event import PREvent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)


def _cleanup_stuck_runs() -> None:
    """Reset any runs/repos left in an in-progress state from a previous process.

    The in-memory queue is gone after a restart; rows stuck in "queued" or
    "analyzing" will never advance. Mark them failed so the dashboard shows a
    clean state."""
    with Session(engine) as session:
        stuck_runs = session.exec(
            select(ReviewRun).where(
                ReviewRun.status.in_(["queued", "received", "analyzing"])
            )
        ).all()
        for run in stuck_runs:
            run.status = "failed"
            run.error = "server restarted while this review was in progress"
            session.add(run)

        stuck_repos = session.exec(
            select(Repository).where(
                Repository.onboarding_status.in_(["pending", "cloning", "building_graph"])
            )
        ).all()
        for repo in stuck_repos:
            repo.onboarding_status = "failed"
            repo.onboarding_error = "server restarted during onboarding"
            session.add(repo)

        if stuck_runs or stuck_repos:
            session.commit()
            logger.warning(
                "cleanup: reset %d stuck run(s) and %d stuck repo(s) to 'failed'",
                len(stuck_runs), len(stuck_repos),
            )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    init_db()
    _cleanup_stuck_runs()

    # Sequential PR review queue
    review_queue: asyncio.Queue[tuple[str, PREvent]] = asyncio.Queue()
    app.state.review_queue = review_queue
    review_worker_task = asyncio.create_task(review_queue_worker(review_queue))

    # Sequential repo onboarding queue
    onboarding_queue: asyncio.Queue[str] = asyncio.Queue()
    app.state.onboarding_queue = onboarding_queue
    onboard_worker_task = asyncio.create_task(onboarding_worker(onboarding_queue))

    yield

    for task in (review_worker_task, onboard_worker_task):
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass


app = FastAPI(title="PR Analyzer", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(webhooks.router)
app.include_router(reviews.router)
app.include_router(chat.router)
app.include_router(repos_api.router)
