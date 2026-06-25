from pydantic import BaseModel


class CriticJudgment(BaseModel):
    """What only an LLM can reasonably judge about a finding - whether it
    respects the synthesized repository context and is actionable, plus the
    model's own confidence. Evidence-grounding (file/line really exists in
    the diff) is deliberately NOT asked of the LLM - it's checked
    deterministically in critic_agent.py instead, see that module's docstring."""

    respects_repo_context: bool
    actionable: bool
    confidence: float
    rationale: str
