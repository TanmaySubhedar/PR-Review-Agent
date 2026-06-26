import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.llm.azure_client import complete_structured
from app.models import Finding, ReviewRun

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])

_MAX_RUNS = 20
_MAX_FINDINGS_PER_RUN = 10


class ChatRequest(BaseModel):
    message: str
    review_run_id: str | None = None


class ChatResponse(BaseModel):
    response: str


class _Answer(BaseModel):
    answer: str


_SYSTEM_PROMPT = """You are Sentinel PR, an intelligent AI assistant specializing in code review analysis.

You have access to pull request review data including:
- PR metadata (title, repo, risk level, status)
- Change summaries explaining what was changed and why
- Code findings across 7 dimensions: correctness, security, performance, logging, architecture, testing, maintainability
- Risk assessments from blast-radius analysis (which functions are affected and how many callers they have)

Answer questions clearly and helpfully. When citing specific findings, mention the file, dimension, and severity.
If asked why code was changed, use the change_summary field.
If asked about risk, explain the blast-radius reasoning (fan-in callers, test coverage gaps).
If you genuinely lack enough context, say so honestly — do not guess or fabricate details.
Format responses with markdown where it improves readability. Keep answers focused and concise."""


def _fmt_run(run: ReviewRun, findings: list[Finding]) -> str:
    parts = [f"## PR #{run.pr_number}: {run.title}"]
    parts.append(f"- Repository: {run.repo_full_name}")
    parts.append(f"- Status: {run.status} | Risk Level: {run.risk_level or 'not assessed'}")
    parts.append(f"- PR URL: {run.pr_url}")
    parts.append(f"- Reviewed at: {run.created_at}")

    if run.change_summary:
        parts.append(f"- Change Summary: {run.change_summary}")

    if run.error:
        parts.append(f"- Pipeline Error: {run.error}")

    published = [f for f in findings if f.published]
    if findings:
        parts.append(
            f"- Findings: {len(findings)} total ({len(published)} published to GitHub as inline comments)"
        )
        for f in findings[:_MAX_FINDINGS_PER_RUN]:
            loc = f.file + (f":{f.line}" if f.line else "")
            tag = "published" if f.published else "filtered by critic"
            parts.append(f"  [{f.dimension}/{f.severity}] {loc}: {f.finding} ({tag})")
    else:
        parts.append("- No findings generated")

    return "\n".join(parts)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    session: Session = Depends(get_session),
) -> ChatResponse:
    if body.review_run_id:
        run = session.get(ReviewRun, body.review_run_id)
        if not run:
            return ChatResponse(
                response="I couldn't find that review run. It may have been deleted or the ID is incorrect."
            )
        findings = list(session.exec(select(Finding).where(Finding.review_run_id == run.id)).all())
        context = f"Context: Single PR review\n\n{_fmt_run(run, findings)}"
    else:
        runs = list(
            session.exec(select(ReviewRun).order_by(ReviewRun.created_at.desc()).limit(_MAX_RUNS)).all()
        )
        if not runs:
            return ChatResponse(
                response="No pull requests have been reviewed yet. Configure a GitHub webhook and open a PR to get started."
            )
        parts = []
        for run in runs:
            findings = list(session.exec(select(Finding).where(Finding.review_run_id == run.id)).all())
            parts.append(_fmt_run(run, findings))
        context = (
            f"Context: {len(runs)} reviewed pull request(s)\n\n" + "\n\n---\n\n".join(parts)
        )

    user_prompt = f"{context}\n\n---\n\nUser question: {body.message}"
    result = await complete_structured(_Answer, _SYSTEM_PROMPT, user_prompt)
    return ChatResponse(response=result.answer)
