"""Reviewer node: call the LLM to generate review findings."""

import asyncio

from pr_review_agent._llm import complete_structured
from pr_review_agent.graph.state import PRReviewState
from pr_review_agent.models.domain import Finding, FindingsResponse
from pr_review_agent.prompts import reviewer as reviewer_prompts


async def _generate_findings(state: PRReviewState) -> list[Finding]:
    pr_meta = state["pr_metadata"]
    system, user = reviewer_prompts.build_prompts(
        pr_title=pr_meta.title,
        pr_description=pr_meta.description,
        risk_level=state.get("risk_level", "low"),
        risk_factors=state.get("risk_factors", []),
        repository_context=state["repository_context"],
        file_diffs=state["file_diffs"],
        previous_findings=state.get("previous_findings"),
    )
    response: FindingsResponse = await complete_structured(FindingsResponse, system, user)
    return response.findings


def run(state: PRReviewState) -> PRReviewState:
    findings = asyncio.run(_generate_findings(state))
    return {
        **state,
        "findings": findings,
        "phase_status": {**state.get("phase_status", {}), "reviewer": "done"},
    }
