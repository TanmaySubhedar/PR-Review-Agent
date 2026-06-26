import logging
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.config import settings
from app.db import engine
from app.github.client import GitHubClient, PATGitHubClient
from app.models import Finding, PhaseLog, ReviewRun
from app.pipeline.blast_radius.workspace import authenticated_clone_url, cloned_pr_head
from app.pipeline.orchestrator import run_review_pipeline
from app.schemas.pr_event import PREvent
from app.schemas.review_finding import ReviewFinding

logger = logging.getLogger(__name__)

# Bounds how many prior findings get dumped into the re-review prompt - without
# this, a PR with many review iterations could accumulate an ever-growing
# previous-findings block. Capped on confidence so the most credible findings
# survive if a single run ever produced more than this.
_MAX_PREVIOUS_FINDINGS = 15


def _fetch_previous_findings(
    session: Session, repo_full_name: str, pr_number: int, exclude_run_id: str
) -> list[ReviewFinding]:
    """Published findings from the most recent prior completed run on this
    same PR, so the review agent can compare against what it said last time
    instead of treating every push as a brand-new review with no memory."""
    previous_run = session.exec(
        select(ReviewRun)
        .where(
            ReviewRun.repo_full_name == repo_full_name,
            ReviewRun.pr_number == pr_number,
            ReviewRun.id != exclude_run_id,
            ReviewRun.status == "done",
        )
        .order_by(ReviewRun.created_at.desc())
        .limit(1)
    ).first()
    if previous_run is None:
        return []

    rows = session.exec(
        select(Finding)
        .where(Finding.review_run_id == previous_run.id, Finding.published.is_(True))
        .order_by(Finding.confidence.desc())
        .limit(_MAX_PREVIOUS_FINDINGS)
    ).all()

    previous_findings = []
    for row in rows:
        try:
            previous_findings.append(ReviewFinding.model_validate(row, from_attributes=True))
        except Exception:
            logger.warning("skipping unreadable previous finding %s for re-review comparison", row.id)
    return previous_findings


def _set_phase(session: Session, review_run_id: str, phase: str, status: str, detail: str | None = None) -> None:
    log = session.exec(
        select(PhaseLog).where(PhaseLog.review_run_id == review_run_id, PhaseLog.phase == phase)
    ).first()
    if log is None:
        return
    log.status = status
    log.detail = detail
    now = datetime.now(timezone.utc)
    if status == "running":
        log.started_at = now
    elif status in ("done", "failed"):
        log.finished_at = now
    session.add(log)
    session.commit()


async def execute_review_run(review_run_id: str, pr_event: PREvent) -> None:
    """Entry point scheduled as a FastAPI background task from the webhook
    handler. Owns its own DB session since it runs after the HTTP response
    that created the ReviewRun row has already been sent."""
    with Session(engine) as session:
        run = session.get(ReviewRun, review_run_id)
        if run is None:
            logger.error("review run %s not found, aborting pipeline", review_run_id)
            return

        github_client: GitHubClient = PATGitHubClient()

        def on_phase(phase: str, status: str) -> None:
            _set_phase(session, review_run_id, phase, status)

        run_tag = f"[{review_run_id[:8]}] [{pr_event.repo_full_name}#{pr_event.pr_number}]"
        try:
            run.status = "analyzing"
            session.add(run)
            session.commit()
            logger.info("%s review started", run_tag)

            _set_phase(session, review_run_id, "ingestion", "running")
            logger.info("%s [0/7] INGESTION starting — fetching PR details from GitHub", run_tag)
            t0 = __import__("time").monotonic()
            changed_files, commits = github_client.fetch_pr_event_details(
                pr_event.repo_full_name, pr_event.pr_number
            )
            pr_event.changed_files = changed_files
            pr_event.commits = commits
            file_diffs = github_client.fetch_file_diffs(pr_event.repo_full_name, pr_event.pr_number)
            _set_phase(session, review_run_id, "ingestion", "done")
            logger.info("%s [0/7] INGESTION done in %.1fs — %d file(s), %d commit(s)",
                        run_tag, __import__("time").monotonic() - t0, len(file_diffs), len(commits))

            previous_findings = _fetch_previous_findings(
                session, pr_event.repo_full_name, pr_event.pr_number, review_run_id
            )

            clone_url = authenticated_clone_url(pr_event.clone_url, settings.github_token)
            with cloned_pr_head(clone_url, pr_event.pr_number, pr_event.head_sha) as workspace_root:
                result = await run_review_pipeline(
                    review_run_id,
                    pr_event,
                    file_diffs,
                    workspace_root,
                    github_client,
                    on_phase=on_phase,
                    previous_findings=previous_findings,
                )

            run.risk_level = result.diff_analysis.risk_level
            run.change_summary = result.change_summary
            run.suggested_pr_description = result.suggested_pr_description
            run.status = "done"
            session.add(run)

            for sf in result.scored_findings:
                session.add(
                    Finding(
                        review_run_id=review_run_id,
                        file=sf.finding.file,
                        line=sf.finding.line,
                        dimension=sf.finding.dimension,
                        finding=sf.finding.finding,
                        evidence=sf.finding.evidence,
                        severity=sf.finding.severity,
                        confidence=sf.critic.confidence,
                        published=sf.publish or sf.downgrade_to_summary,
                        discarded=not sf.publish and not sf.downgrade_to_summary,
                    )
                )
            session.commit()
        except Exception as exc:
            logger.exception("%s pipeline FAILED — %s", run_tag, exc)
            run.status = "failed"
            run.error = str(exc)
            session.add(run)
            session.commit()
            current_phase = session.exec(
                select(PhaseLog).where(PhaseLog.review_run_id == review_run_id, PhaseLog.status == "running")
            ).first()
            if current_phase is not None:
                _set_phase(session, review_run_id, current_phase.phase, "failed", detail=str(exc))
