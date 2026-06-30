import asyncio
import logging

from app.pipeline.runner import execute_review_run
from app.schemas.pr_event import PREvent

logger = logging.getLogger(__name__)


async def review_queue_worker(queue: "asyncio.Queue[tuple[str, PREvent]]") -> None:
    """Single-consumer worker that processes PR reviews one at a time.

    Two simultaneous webhooks both enqueue a (run_id, pr_event) tuple; this
    worker dequeues and awaits each one fully before picking up the next.
    execute_review_run handles its own DB session and all exception/status
    transitions — this wrapper only ensures sequential ordering."""
    logger.info("review queue worker started")
    while True:
        try:
            run_id, pr_event = await queue.get()
            logger.info("worker: dequeued run %s for %s#%s (queue depth now %d)",
                        run_id[:8], pr_event.repo_full_name, pr_event.pr_number, queue.qsize())
            try:
                await execute_review_run(run_id, pr_event)
            except Exception:
                logger.exception("worker: run %s raised unhandled exception", run_id[:8])
            finally:
                queue.task_done()
        except asyncio.CancelledError:
            logger.info("review queue worker cancelled — stopping")
            break
        except Exception:
            logger.exception("worker: unexpected error in queue loop, continuing")
