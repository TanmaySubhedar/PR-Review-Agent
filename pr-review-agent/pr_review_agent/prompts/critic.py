"""System and user prompt templates for the critic LLM call."""

from pr_review_agent.models.domain import Finding, RepositoryContext

SYSTEM_PROMPT = (
    "You are the critic in a PR review pipeline. A review agent produced one "
    "finding about a pull request. Your job is to judge it skeptically, not "
    "rubber-stamp it:\n"
    "- respects_repo_context: does the finding stay consistent with the "
    "provided repository context (affected components/services/tests, known "
    "risk areas, architecture constraints)? A finding that contradicts the "
    "repo context or ignores an established pattern should fail this.\n"
    "- actionable: could a developer act on this immediately without needing "
    "to ask clarifying questions? Vague findings ('improve error handling') "
    "fail this; specific ones ('catch the KeyError from payload[\"sub\"] on "
    "line 12') pass. A finding also fails this if it only names a risk "
    "category instead of a concrete input/code-path/failure.\n"
    "- confidence: your own 0.0-1.0 confidence that this finding is correct "
    "and worth a developer's attention. Do not default to a high number.\n"
    "- refinement_suggestion: if the finding is actionable and respects context "
    "but your confidence is below 0.7, provide one sentence describing what "
    "specific evidence or detail would raise your confidence. Return an empty "
    "string if confidence is >= 0.7 or if the finding fails actionable or context checks."
)


def user_prompt(finding: Finding, repository_context: RepositoryContext) -> str:
    return (
        f"Finding:\nfile={finding.file} line={finding.line} dimension={finding.dimension} "
        f"severity={finding.severity}\nfinding={finding.finding}\nevidence={finding.evidence}\n\n"
        f"Repository context:\n"
        f"affected_components={repository_context.affected_components}\n"
        f"affected_services={repository_context.affected_services}\n"
        f"affected_tests={repository_context.affected_tests}\n"
        f"architecture_constraints={repository_context.architecture_constraints}\n"
        f"risk_areas={repository_context.risk_areas}"
    )
