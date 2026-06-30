from app.github.client import GitHubClient
from app.schemas.diff_analysis import DiffAnalysis
from app.schemas.pr_event import PREvent
from app.schemas.repository_context import RepositoryContext
from app.schemas.scored_finding import ScoredFinding

_SEVERITY_RANK = {"info": 0, "minor": 1, "major": 2, "blocking": 3}


def compute_overall_severity(scored_findings: list[ScoredFinding]) -> str:
    """The PR's overall verdict, derived as a pure function of the highest
    severity among findings that actually survived the critic gate - never
    a separate LLM call. An LLM asked to summarize/score a whole PR can give
    a different answer for the same input on different runs; a max() over
    already-decided severities can't, so this can never flip-flop on an
    unchanged diff."""
    published = [sf for sf in scored_findings if sf.publish or sf.downgrade_to_summary]
    if not published:
        return "none"
    return max((sf.finding.severity for sf in published), key=lambda s: _SEVERITY_RANK[s])


def build_inline_comments(scored_findings: list[ScoredFinding]) -> list[dict]:
    return [
        {
            "path": sf.finding.file,
            "position": sf.diff_position.position,
            "body": f"**[{sf.finding.dimension}/{sf.finding.severity}]** {sf.finding.finding}\n\n{sf.finding.evidence}",
        }
        for sf in scored_findings
        if sf.publish and sf.diff_position is not None
    ]


def build_summary_body(
    diff_analysis: DiffAnalysis,
    repository_context: RepositoryContext,
    scored_findings: list[ScoredFinding],
    change_summary: str = "",
) -> str:
    overall_severity = compute_overall_severity(scored_findings)
    lines = [f"## Automated PR Review (risk: {diff_analysis.risk_level}, overall severity: {overall_severity})", ""]

    if change_summary:
        lines.append("### What changed")
        lines.append(change_summary)
        lines.append("")

    if repository_context.risk_areas:
        lines.append("<details>")
        lines.append(f"<summary><strong>Blast-radius warnings</strong> ({len(repository_context.risk_areas)} items)</summary>")
        lines.append("")
        lines.extend(f"- {r}" for r in repository_context.risk_areas)
        lines.append("")
        lines.append("</details>")
        lines.append("")

    # All non-discarded findings surfaced in summary so reviewers see bugs without hunting inline comments
    published_all = [sf for sf in scored_findings if sf.publish or sf.downgrade_to_summary]
    if published_all:
        lines.append("### Issues found")
        _SEV_ICON = {"blocking": "🔴", "major": "🟠", "minor": "🟡", "info": "⚪"}
        for sf in published_all:
            icon = _SEV_ICON.get(sf.finding.severity, "•")
            location = f"`{sf.finding.file}`" + (f":{sf.finding.line}" if sf.finding.line is not None else "")
            anchor = " _(inline)_" if (sf.publish and sf.diff_position is not None) else " _(summary only)_"
            lines.append(
                f"- {icon} **{sf.finding.dimension}/{sf.finding.severity}** — "
                f"{location}{anchor}: {sf.finding.finding}"
            )
        lines.append("")

    inline_count = sum(1 for sf in scored_findings if sf.publish and sf.diff_position is not None)
    downgraded = [sf for sf in scored_findings if sf.downgrade_to_summary]
    discarded_count = len(scored_findings) - len(published_all)
    lines.append(
        f"_{inline_count} inline comment(s) posted, {len(downgraded)} summarized above, "
        f"{discarded_count} filtered out by the critic gate._"
    )
    return "\n".join(lines)


def publish_review(
    github_client: GitHubClient,
    pr_event: PREvent,
    diff_analysis: DiffAnalysis,
    repository_context: RepositoryContext,
    scored_findings: list[ScoredFinding],
    change_summary: str = "",
) -> dict:
    summary_body = build_summary_body(diff_analysis, repository_context, scored_findings, change_summary)
    inline_comments = build_inline_comments(scored_findings)

    github_client.create_review(pr_event.repo_full_name, pr_event.pr_number, summary_body, inline_comments)

    return {"inline_comments": len(inline_comments), "summary_posted": True}
