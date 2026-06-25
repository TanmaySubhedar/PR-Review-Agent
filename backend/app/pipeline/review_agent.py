from app.llm.azure_client import complete_structured
from app.pipeline.critic_agent import HEDGE_WORDS
from app.pipeline.diff_analysis import FileDiff
from app.schemas.diff_analysis import DiffAnalysis
from app.schemas.pr_event import PREvent
from app.schemas.repository_context import RepositoryContext
from app.schemas.review_finding import ReviewFinding, ReviewFindingsResponse

_MAX_PATCH_CHARS = 6000
_HEDGE_WORDS_LIST = ", ".join(f"'{w}'" for w in HEDGE_WORDS)

_SYSTEM_PROMPT = (
    "You are a repository-aware PR review agent. You are given a pull request's "
    "diff, a risk assessment of what changed, and synthesized repository context "
    "describing the blast radius of the change (what calls it, what it calls, "
    "what tests cover it, and known risk areas). Never review the diff in "
    "isolation - ground every finding in both the diff and the repository "
    "context provided.\n\n"
    "Review across exactly these dimensions:\n"
    "- correctness: logic errors, edge cases, null/undefined handling, exception handling\n"
    "- architecture: layer violations, pattern violations, coupling concerns "
    "(use the repository context's affected_components/services to judge this)\n"
    "- testing: missing tests or incomplete coverage for affected paths "
    "(use affected_tests and risk_areas to judge this)\n"
    "- maintainability: readability, duplication, complexity\n\n"
    "Every finding MUST cite an exact file and, where the issue is in changed "
    "code, an exact line number from the diff. The `evidence` field must quote "
    "or precisely describe the specific code backing the finding - never give "
    "a vague or generic finding. If you have no high-confidence finding for a "
    "dimension, omit it rather than inventing one. Return only actionable "
    "findings a developer could fix immediately.\n\n"
    "Concurrency and shared-state correctness findings need a concrete trace, "
    "not a pattern match: before raising a finding about shared/concurrent "
    "state (locks, caches, race conditions), identify every function in the "
    "diff that reads or writes the shared state, and for each one state "
    "whether it acquires the relevant lock/guard before touching it. Only "
    "raise the finding if you can name at least one access path that does "
    "not acquire it. If every access path is guarded, do not raise the "
    "finding at all - do not flag something just because the word 'thread', "
    "'lock', or 'cache' appears nearby.\n\n"
    "'No test coverage' is a testing finding, never a correctness finding on "
    "its own - missing tests and an actual bug are different claims. Do not "
    f"write a correctness finding using hedge language ({_HEDGE_WORDS_LIST}, "
    "or similar) as a substitute for identifying a real failure. If you "
    "cannot describe a concrete input, the code path it takes, and the "
    "observable wrong behavior that results, downgrade the finding to "
    "testing or omit it entirely.\n\n"
    "Severity must match the rigor of the evidence, not the topic: `major` "
    "and `blocking` require the finding body to describe a reproducible "
    "failure (a specific input/scenario and what goes wrong). If the "
    f"explanation only hedges with one of ({_HEDGE_WORDS_LIST}) or otherwise "
    "only describes a hypothetical risk category instead of a concrete "
    "trace, cap the severity at `minor` - a backstop will also catch this "
    "deterministically, but do not rely on it."
)

_RE_REVIEW_INSTRUCTIONS = (
    "\n\nThis PR was reviewed before. Previous findings are listed below. For "
    "EACH previous finding, you must explicitly decide one of: resolved (the "
    "code that caused it changed enough that it no longer applies), still "
    "present (you can point to the exact unchanged or insufficiently-changed "
    "code that still causes it), or unrelated (it's about a part of the diff "
    "that's no longer relevant). Only mark something 'still present' if you "
    "can cite the current code showing the issue remains - do not re-raise a "
    "finding just because it was raised last time without re-checking it "
    "against the current diff. Only include 'still present' and genuinely "
    "new findings in your output; do not include resolved or unrelated ones."
)


def _format_diff_section(file_diffs: list[FileDiff]) -> str:
    parts = []
    for fd in file_diffs:
        parts.append(f"--- {fd.file} ({fd.status}) ---\n{fd.patch[:_MAX_PATCH_CHARS]}")
    return "\n\n".join(parts)


def _format_repository_context(repository_context: RepositoryContext) -> str:
    return (
        f"Affected components: {', '.join(repository_context.affected_components) or 'none identified'}\n"
        f"Affected services/modules: {', '.join(repository_context.affected_services) or 'none identified'}\n"
        f"Affected tests: {', '.join(repository_context.affected_tests) or 'none identified'}\n"
        f"Architecture constraints: {', '.join(repository_context.architecture_constraints) or 'none configured'}\n"
        f"Known risk areas:\n- " + "\n- ".join(repository_context.risk_areas or ["none identified"])
    )


def _format_previous_findings(previous_findings: list[ReviewFinding]) -> str:
    lines = []
    for f in previous_findings:
        location = f"{f.file}" + (f":{f.line}" if f.line is not None else "")
        lines.append(f"- [{f.dimension}/{f.severity}] {location}: {f.finding}\n  evidence: {f.evidence}")
    return "\n".join(lines)


async def generate_findings(
    pr_event: PREvent,
    file_diffs: list[FileDiff],
    diff_analysis: DiffAnalysis,
    repository_context: RepositoryContext,
    previous_findings: list[ReviewFinding] | None = None,
):
    user_prompt = (
        f"PR title: {pr_event.title}\n"
        f"PR description: {pr_event.description or '(none)'}\n\n"
        f"Risk level: {diff_analysis.risk_level}\n"
        f"Risk factors: {', '.join(diff_analysis.risk_factors) or 'none'}\n\n"
        f"Repository context:\n{_format_repository_context(repository_context)}\n\n"
        f"Diff:\n{_format_diff_section(file_diffs)}"
    )

    system_prompt = _SYSTEM_PROMPT
    if previous_findings:
        system_prompt += _RE_REVIEW_INSTRUCTIONS
        user_prompt += f"\n\nPrevious review's findings on this PR:\n{_format_previous_findings(previous_findings)}"

    response = await complete_structured(ReviewFindingsResponse, system_prompt, user_prompt)
    return response.findings
