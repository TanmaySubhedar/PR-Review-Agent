"""System and user prompt templates for the reviewer LLM call."""

from pr_review_agent.models.domain import (
    FileDiff,
    Finding,
    RepositoryContext,
)

HEDGE_WORDS = ("may", "might", "could", "possibly", "potentially")
_HEDGE_WORDS_LIST = ", ".join(f"'{w}'" for w in HEDGE_WORDS)
_MAX_PATCH_CHARS = 6000

SYSTEM_PROMPT = (
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
    "- maintainability: readability, duplication, complexity\n"
    "- intent: verify that the diff's actual changes match what the PR description "
    "claims to do. Flag unexplained deletions or renames, scope creep (changes "
    "unrelated to the stated goal), or a description that promises a behaviour the "
    "diff does not implement. Only raise an intent finding if there is a clear "
    "discrepancy; do not raise one simply because the description is terse.\n\n"
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
    "finding at all.\n\n"
    "'No test coverage' is a testing finding, never a correctness finding on "
    "its own. Do not write a correctness finding using hedge language "
    f"({_HEDGE_WORDS_LIST}, or similar) as a substitute for identifying a "
    "real failure. If you cannot describe a concrete input, the code path "
    "it takes, and the observable wrong behavior that results, downgrade the "
    "finding to testing or omit it entirely.\n\n"
    "Severity must match the rigor of the evidence, not the topic: `major` "
    "and `blocking` require the finding body to describe a reproducible "
    "failure (a specific input/scenario and what goes wrong). If the "
    f"explanation only hedges with one of ({_HEDGE_WORDS_LIST}) or otherwise "
    "only describes a hypothetical risk category, cap the severity at `minor`."
)

RE_REVIEW_SUFFIX = (
    "\n\nThis PR was reviewed before. Previous findings are listed below. For "
    "EACH previous finding, you must explicitly decide one of: resolved (the "
    "code that caused it changed enough that it no longer applies), still "
    "present (you can point to the exact unchanged or insufficiently-changed "
    "code that still causes it), or unrelated (it's about a part of the diff "
    "that's no longer relevant). Only include 'still present' and genuinely "
    "new findings in your output; do not include resolved or unrelated ones."
)


def _format_diff(file_diffs: list[FileDiff]) -> str:
    parts = []
    for fd in file_diffs:
        parts.append(f"--- {fd.file} ({fd.status}) ---\n{fd.patch[:_MAX_PATCH_CHARS]}")
    return "\n\n".join(parts)


def _format_repo_context(ctx: RepositoryContext) -> str:
    return (
        f"Affected components: {', '.join(ctx.affected_components) or 'none identified'}\n"
        f"Affected services/modules: {', '.join(ctx.affected_services) or 'none identified'}\n"
        f"Affected tests: {', '.join(ctx.affected_tests) or 'none identified'}\n"
        f"Architecture constraints: {', '.join(ctx.architecture_constraints) or 'none configured'}\n"
        "Known risk areas:\n- " + "\n- ".join(ctx.risk_areas or ["none identified"])
    )


def _format_previous(previous: list[Finding]) -> str:
    lines = []
    for f in previous:
        loc = f.file + (f":{f.line}" if f.line is not None else "")
        lines.append(f"- [{f.dimension}/{f.severity}] {loc}: {f.finding}\n  evidence: {f.evidence}")
    return "\n".join(lines)


def refinement_user_prompt(original: Finding, suggestion: str) -> str:
    """Prompt asking the reviewer to produce a stronger version of a borderline finding."""
    loc = original.file + (f":{original.line}" if original.line is not None else "")
    return (
        f"The following finding was submitted for review but was judged as borderline — "
        f"the evidence was not specific enough to confidently publish.\n\n"
        f"Original finding:\n"
        f"  location: {loc}\n"
        f"  dimension: {original.dimension}\n"
        f"  severity: {original.severity}\n"
        f"  finding: {original.finding}\n"
        f"  evidence: {original.evidence}\n\n"
        f"Critic's suggestion for improvement:\n  {suggestion}\n\n"
        "Rewrite this finding with more specific evidence. Cite the exact code, "
        "the concrete input or condition that triggers the issue, and the observable "
        "wrong behaviour. Keep the same file and approximate line. If you cannot "
        "strengthen it, return the original text unchanged."
    )


def build_prompts(
    pr_title: str,
    pr_description: str,
    risk_level: str,
    risk_factors: list[str],
    repository_context: RepositoryContext,
    file_diffs: list[FileDiff],
    previous_findings: list[Finding] | None = None,
) -> tuple[str, str]:
    user = (
        f"PR title: {pr_title}\n"
        f"PR description: {pr_description or '(none)'}\n\n"
        f"Risk level: {risk_level}\n"
        f"Risk factors: {', '.join(risk_factors) or 'none'}\n\n"
        f"Repository context:\n{_format_repo_context(repository_context)}\n\n"
        f"Diff:\n{_format_diff(file_diffs)}"
    )
    system = SYSTEM_PROMPT
    if previous_findings:
        system += RE_REVIEW_SUFFIX
        user += f"\n\nPrevious review's findings on this PR:\n{_format_previous(previous_findings)}"
    return system, user
