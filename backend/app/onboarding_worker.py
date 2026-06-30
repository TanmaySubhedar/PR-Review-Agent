import asyncio
import logging
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session

from app.config import settings
from app.db import engine
from app.models.repository import Repository
from app.pipeline.blast_radius.graph_store import compress_graph
from app.pipeline.blast_radius.repo_graph import build_repo_graph
from app.pipeline.blast_radius.workspace import authenticated_clone_url

logger = logging.getLogger(__name__)

_CREDENTIAL_RE = re.compile(r"https://x-access-token:[^@\s]+@")


async def onboarding_worker(queue: "asyncio.Queue[str]") -> None:
    """Single-consumer worker — clones a repo and builds its call graph one at a time."""
    logger.info("onboarding worker started")
    while True:
        try:
            repo_id = await queue.get()
            logger.info("onboarding: starting %s", repo_id[:8])
            try:
                await _onboard_repo(repo_id)
            except Exception:
                logger.exception("onboarding: repo %s failed", repo_id[:8])
            finally:
                queue.task_done()
        except asyncio.CancelledError:
            logger.info("onboarding worker cancelled — stopping")
            break
        except Exception:
            logger.exception("onboarding: unexpected error in queue loop, continuing")


async def _onboard_repo(repo_id: str) -> None:
    with Session(engine) as session:
        repo = session.get(Repository, repo_id)
        if repo is None:
            logger.error("onboarding: repo %s not found in DB", repo_id)
            return

    clone_url = authenticated_clone_url(repo.clone_url, settings.github_token)
    tmp_dir = Path(tempfile.mkdtemp(prefix="pr-onboard-"))
    try:
        _set_status(repo_id, "cloning")
        _clone_default_branch(clone_url, repo.default_branch, tmp_dir)
        logger.info("onboarding: %s cloned to %s", repo.full_name, tmp_dir)

        _set_status(repo_id, "building_graph")
        loop = asyncio.get_event_loop()
        graph, truncated = await loop.run_in_executor(
            None,
            lambda: build_repo_graph(tmp_dir, max_files=settings.repo_onboarding_max_files),
        )
        logger.info("onboarding: %s graph built — %d nodes, %d edges",
                    repo.full_name, graph.number_of_nodes(), graph.number_of_edges())

        graph_text = compress_graph(graph)

        with Session(engine) as session:
            r = session.get(Repository, repo_id)
            if r is None:
                return
            r.graph_json = graph_text
            r.graph_node_count = graph.number_of_nodes()
            r.graph_edge_count = graph.number_of_edges()
            r.graph_truncated = truncated
            r.onboarding_status = "ready"
            r.onboarding_error = None
            r.updated_at = datetime.now(timezone.utc)
            session.add(r)
            session.commit()
        logger.info("onboarding: %s complete", repo.full_name)

    except Exception as exc:
        with Session(engine) as session:
            r = session.get(Repository, repo_id)
            if r is not None:
                r.onboarding_status = "failed"
                r.onboarding_error = str(exc)
                r.updated_at = datetime.now(timezone.utc)
                session.add(r)
                session.commit()
        raise
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _set_status(repo_id: str, status: str) -> None:
    with Session(engine) as session:
        r = session.get(Repository, repo_id)
        if r is not None:
            r.onboarding_status = status
            r.updated_at = datetime.now(timezone.utc)
            session.add(r)
            session.commit()


def _clone_default_branch(clone_url: str, branch: str, dest: Path) -> None:
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", branch,
             "--single-branch", clone_url, str(dest)],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as exc:
        msg = _CREDENTIAL_RE.sub("https://x-access-token:***@", exc.stderr or str(exc))
        raise RuntimeError(f"git clone failed: {msg}") from None
