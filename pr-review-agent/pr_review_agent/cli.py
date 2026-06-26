"""Typer CLI — entry point for the `prv` command."""

from __future__ import annotations

import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from pr_review_agent.graph.state import PRReviewState
from pr_review_agent.tools.treesitter import detect_language

app = typer.Typer(
    name="prv",
    help="Repository-aware autonomous PR review CLI.",
    no_args_is_help=True,
)
console = Console()

_SEV_COLORS = {"blocking": "red bold", "major": "red", "minor": "yellow", "info": "dim"}

_SUPPORTED_EXTS = {".py", ".js", ".jsx", ".mjs", ".ts", ".tsx"}


def _sev(severity: str) -> str:
    color = _SEV_COLORS.get(severity, "")
    return f"[{color}]{severity}[/{color}]" if color else severity


def _phase_summary(phase: str, state: PRReviewState) -> str | None:
    """Return a one-line diagnostic string shown after each completed phase."""
    if phase == "ingest":
        fds = state.get("file_diffs", [])
        meta = state.get("pr_metadata")
        title = f'"{meta.title[:60]}"' if meta else "?"
        sha = meta.head_sha[:8] if meta else "?"
        return f"[dim]{len(fds)} file(s) · {title} · sha {sha}[/dim]"

    if phase == "symbols":
        syms = state.get("changed_symbols", [])
        fds = state.get("file_diffs", [])
        risk = state.get("risk_level", "?")
        exts = sorted({Path(fd.file).suffix.lower() for fd in fds if Path(fd.file).suffix})
        unsupported = [e for e in exts if e not in _SUPPORTED_EXTS]
        supported = [e for e in exts if e in _SUPPORTED_EXTS]
        lang_note = ""
        if unsupported:
            lang_note = f" · [yellow]unsupported: {' '.join(unsupported)}[/yellow]"
        if supported:
            lang_note += f" · supported: {' '.join(supported)}"
        counts = Counter(s.symbol_type for s in syms)
        sym_str = (
            ", ".join(f"{v} {k}" for k, v in counts.most_common())
            if syms else "[yellow]0 symbols[/yellow]"
        )
        return f"[dim]{sym_str} · risk: {risk}{lang_note}[/dim]"

    if phase == "graphify":
        br = state.get("blast_radius")
        rebuilt = state.get("graphify_graph_rebuilt")
        if br is None or (not br.entries and rebuilt is False):
            return "[dim]skipped — no actionable symbols[/dim]"
        cache_note = "rebuilt" if rebuilt else "cached graph reused"
        if not br or not br.entries:
            return f"[dim]{cache_note}  ·  0 blast radius entries[/dim]"
        return f"[dim]{len(br.entries)} blast radius entries  ·  {cache_note}[/dim]"

    if phase == "context":
        cf = state.get("context_files", [])
        if not cf:
            return "[red]0 context files — reviewer will have no file context[/red]"
        names = "  ".join(f.file for f in cf[:6])
        more = f"  +{len(cf) - 6} more" if len(cf) > 6 else ""
        return f"[dim]{len(cf)} file(s): {names}{more}[/dim]"

    if phase == "readers":
        summaries = state.get("file_summaries", [])
        if not summaries:
            return "[yellow]0 summaries — no files were read[/yellow]"
        return f"[dim]{len(summaries)} file summary/summaries generated[/dim]"

    if phase == "synthesizer":
        rc = state.get("repository_context")
        if rc is None:
            return "[dim]no repository context[/dim]"
        comps = len(rc.affected_components)
        risks = len(rc.risk_areas)
        return f"[dim]{comps} affected component(s) · {risks} risk area(s)[/dim]"

    if phase == "reviewer":
        findings = state.get("findings", [])
        if not findings:
            return "[yellow]0 raw findings[/yellow]"
        by_dim = Counter(f.dimension for f in findings)
        detail = "  ".join(f"{v} {k}" for k, v in by_dim.most_common())
        return f"[dim]{len(findings)} finding(s): {detail}[/dim]"

    if phase == "critic":
        vf = state.get("validated_findings", [])
        passed = sum(1 for f in vf if f.publish or f.downgrade_to_summary)
        filtered = sum(1 for f in vf if not f.publish and not f.downgrade_to_summary)
        if not vf:
            return "[yellow]0 findings validated[/yellow]"
        return f"[dim]{len(vf)} validated · {passed} pass · {filtered} filtered[/dim]"

    return None


def _strip_markup(s: str) -> str:
    """Remove Rich markup tags for plain-text DB storage."""
    return re.sub(r"\[/?[^\]]*\]", "", s).strip()


def _render_findings_table(con: Console, findings_list: list) -> None:
    """Render a findings table. Accepts list[ValidatedFinding] or list[FindingRecord]."""
    from pr_review_agent.models.domain import ValidatedFinding

    table = Table(title=f"Findings ({len(findings_list)})")
    table.add_column("Sev", justify="center")
    table.add_column("Dimension")
    table.add_column("File")
    table.add_column("Line", justify="right")
    table.add_column("Finding", max_width=70)
    table.add_column("Conf", justify="right")

    for item in findings_list:
        if isinstance(item, ValidatedFinding):
            f = item.finding
            severity = f.severity
            dimension = f.dimension
            file_ = f.file
            line = str(f.line) if f.line else "—"
            finding_text = f.finding[:70]
            conf = f"{item.verdict.confidence:.2f}"
        else:
            # FindingRecord
            severity = item.severity
            dimension = item.dimension
            file_ = item.file
            line = str(item.line) if item.line else "—"
            finding_text = item.finding[:70]
            conf = f"{item.confidence:.2f}"

        table.add_row(
            _sev(severity),
            dimension,
            file_,
            line,
            finding_text,
            conf,
        )

    con.print(table)


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------

@app.command()
def setup(
    github_token: Optional[str] = typer.Option(None, "--github-token", "-t", help="GitHub personal access token"),
    azure_key: Optional[str] = typer.Option(None, "--azure-key", help="Azure OpenAI API key"),
    azure_endpoint: Optional[str] = typer.Option(None, "--azure-endpoint", help="Azure OpenAI endpoint URL"),
    azure_model: Optional[str] = typer.Option(None, "--azure-model", help="Azure deployment / model name"),
    openai_key: Optional[str] = typer.Option(None, "--openai-key", help="Plain OpenAI API key (fallback)"),
) -> None:
    """Interactive setup: save credentials to ~/.pr-agent/config.toml."""
    from pr_review_agent.config import save_settings
    from pr_review_agent.db import init_db

    console.rule("[bold]prv setup[/bold]")

    values: dict = {}

    if github_token:
        values["github_token"] = github_token
    else:
        tok = typer.prompt("GitHub personal access token (leave blank to skip)", default="", hide_input=True)
        if tok:
            values["github_token"] = tok

    if azure_key:
        values["azure_openai_api_key"] = azure_key
    if azure_endpoint:
        values["azure_openai_endpoint"] = azure_endpoint
    if azure_model:
        values["azure_openai_model"] = azure_model
    if openai_key:
        values["openai_api_key"] = openai_key

    if not any(k in values for k in ("azure_openai_api_key", "openai_api_key")):
        llm_choice = typer.prompt("LLM backend? [azure/openai]", default="azure").strip().lower()
        if llm_choice == "azure":
            values["azure_openai_api_key"] = typer.prompt("Azure OpenAI API key", hide_input=True, default="")
            values["azure_openai_endpoint"] = typer.prompt("Azure OpenAI endpoint", default="")
            values["azure_openai_model"] = typer.prompt("Azure deployment / model", default="gpt-4o")
        else:
            values["openai_api_key"] = typer.prompt("OpenAI API key", hide_input=True, default="")

    default_repo = typer.prompt("Default repository (owner/repo, leave blank to skip)", default="").strip()
    if default_repo:
        values["default_repo"] = default_repo

    threshold_raw = typer.prompt("Critic confidence threshold (0.0–1.0)", default="0.7").strip()
    try:
        threshold = float(threshold_raw)
        if not 0.0 <= threshold <= 1.0:
            raise ValueError
        values["critic_confidence_threshold"] = threshold
    except ValueError:
        console.print("[yellow]Invalid threshold; keeping default 0.7[/yellow]")

    save_settings(values)
    init_db()
    console.print("[green]Config saved to ~/.pr-agent/config.toml[/green]")
    console.print("[green]Database initialised at ~/.pr-agent/runs.db[/green]")


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------

@app.command()
def health() -> None:
    """Check system health: config, credentials, DB, and Graphify availability."""
    from pr_review_agent.config import _CONFIG_FILE, load_settings
    from pr_review_agent.db import _DB_DIR

    ok = True

    def _row(label: str, good: bool, detail: str = "") -> None:
        nonlocal ok
        icon = "[green]✓[/green]" if good else "[red]✗[/red]"
        suffix = f"  [dim]{detail}[/dim]" if detail else ""
        console.print(f"  {icon}  {label}{suffix}")
        if not good:
            ok = False

    console.rule("[bold]prv health[/bold]")

    cfg_exists = Path(_CONFIG_FILE).exists()
    _row("Config file exists", cfg_exists, str(_CONFIG_FILE))

    if cfg_exists:
        s = load_settings()
        _row("GitHub token set", bool(s.github_token), "PR_AGENT_GITHUB_TOKEN overrides config")
        has_llm = bool(s.azure_openai_api_key or s.openai_api_key)
        _row("LLM key present", has_llm, "azure_openai_api_key or openai_api_key")
        _row("LLM model set", bool(s.azure_openai_model), s.azure_openai_model or "—")
    else:
        _row("GitHub token set", False, "run `prv setup` first")
        _row("LLM key present", False)
        _row("LLM model set", False)

    db_path = _DB_DIR / "runs.db"
    _row("Database exists", db_path.exists(), str(db_path))

    graphify_path = shutil.which("graphify")
    _row("Graphify on PATH", graphify_path is not None, graphify_path or "not found — blast radius uses NetworkX fallback")

    console.print()
    if ok:
        console.print("[green bold]All checks passed.[/green bold]")
    else:
        console.print("[red bold]One or more checks failed.[/red bold]")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# review
# ---------------------------------------------------------------------------

@app.command()
def review(
    repo: str = typer.Argument(..., help="Repository in owner/name format, e.g. octocat/Hello-World"),
    pr_number: int = typer.Argument(..., help="Pull request number"),
    no_post: bool = typer.Option(False, "--no-post", help="Skip posting the review to GitHub"),
) -> None:
    """Run a full review pipeline on a PR and persist results."""
    from pr_review_agent.db import get_session, init_db
    from pr_review_agent.graph.graph import run_pipeline
    from pr_review_agent.models.db import FindingRecord, PhaseLog, RunRecord
    from pr_review_agent.tools.github import GitHubClient

    init_db()
    console.rule(f"[bold]Reviewing {repo} #{pr_number}[/bold]")

    phase_times: dict[str, datetime] = {}
    phase_end_times: dict[str, datetime] = {}
    phase_states: dict[str, PRReviewState] = {}

    def on_phase(phase: str, status: str) -> None:
        now = datetime.now(timezone.utc)
        if status == "running":
            phase_times[phase] = now
            console.print(f"  [cyan]→ {phase}[/cyan] …")
        else:
            phase_end_times[phase] = now
            elapsed = (now - phase_times.get(phase, now)).total_seconds()
            console.print(f"  [green]✓ {phase}[/green]  ({elapsed:.1f}s)")

    def on_phase_done(phase: str, state: PRReviewState) -> None:
        phase_states[phase] = state
        summary = _phase_summary(phase, state)
        if summary:
            console.print(f"    {summary}")

    try:
        result = run_pipeline(repo, pr_number, on_phase=on_phase, on_phase_done=on_phase_done)
    except Exception as exc:
        console.print(f"[red]Pipeline failed:[/red] {exc}")
        raise typer.Exit(code=1)

    state = result.state
    pr_meta = state["pr_metadata"]
    risk_level = state.get("risk_level", "low")
    risk_factors = state.get("risk_factors", [])
    validated = state.get("validated_findings", [])

    # Render findings table before any publish prompt
    if validated:
        _render_findings_table(console, validated)

    publishable = [vf for vf in validated if vf.publish]
    summary_only = [vf for vf in validated if vf.downgrade_to_summary]
    filtered = [vf for vf in validated if not vf.publish and not vf.downgrade_to_summary]

    console.print(
        f"{len(validated)} findings "
        f"({len(publishable)} publishable, "
        f"{len(summary_only)} summary-only, "
        f"{len(filtered)} filtered)"
    )

    # Always persist RunRecord and FindingRecord regardless of publish decision
    with get_session() as session:
        run_row = RunRecord(
            id=result.review_run_id,
            repo_full_name=repo,
            pr_number=pr_number,
            pr_url=pr_meta.pr_url,
            title=pr_meta.title,
            head_sha=pr_meta.head_sha,
            base_sha=pr_meta.base_sha,
            status="done",
            risk_level=risk_level,
        )
        session.add(run_row)

        for phase_name in ("ingest", "symbols", "graphify", "context", "readers", "synthesizer", "reviewer", "critic"):
            ps = phase_states.get(phase_name, state)
            detail_markup = _phase_summary(phase_name, ps) or ""
            session.add(PhaseLog(
                review_run_id=result.review_run_id,
                phase=phase_name,
                status=state["phase_status"].get(phase_name, "done"),
                detail=_strip_markup(detail_markup) or None,
                started_at=phase_times.get(phase_name),
                finished_at=phase_end_times.get(phase_name),
            ))

        for vf in validated:
            f = vf.finding
            session.add(FindingRecord(
                review_run_id=result.review_run_id,
                file=f.file,
                line=f.line,
                dimension=f.dimension,
                finding=f.finding,
                evidence=f.evidence,
                severity=f.severity,
                confidence=vf.verdict.confidence,
                published=vf.publish,
                discarded=not vf.publish and not vf.downgrade_to_summary,
            ))

        session.commit()

    console.rule("[bold]Summary[/bold]")
    console.print(f"Run ID   : {result.review_run_id}")
    console.print(f"Risk     : {risk_level}")

    # Publish gate — always prompt (never auto-post)
    answer = typer.prompt("Post this review to GitHub? (y/N)", default="N")
    if answer.strip().lower() == "y":
        try:
            gh = GitHubClient()

            # Use line+side (new-style API) instead of position (diff-offset).
            # line is the actual new-file line number — more reliable, avoids
            # off-by-one errors in diff-position counting.
            inline = [
                {
                    "path": vf.finding.file,
                    "line": vf.finding.line,
                    "side": "RIGHT",
                    "body": (
                        f"**[{vf.finding.severity.upper()}]** {vf.finding.finding}\n\n"
                        f"*Evidence:* {vf.finding.evidence}"
                    ),
                }
                for vf in validated
                if vf.publish and vf.diff_position and vf.finding.line is not None
            ]

            risk_color = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk_level, "")
            body = f"## PR Review — risk: **{risk_color} {risk_level}**\n\n"
            if risk_factors:
                body += "**Risk factors:**\n" + "\n".join(f"- {r}" for r in risk_factors) + "\n\n"
            body_summary_parts = "\n\n".join(
                f"**[{vf.finding.severity.upper()} / {vf.finding.dimension}]** "
                f"`{vf.finding.file}`{f':{vf.finding.line}' if vf.finding.line else ''}\n{vf.finding.finding}"
                for vf in summary_only
            )
            if body_summary_parts:
                body += "**Summary findings:**\n\n" + body_summary_parts

            try:
                gh.create_review(repo, pr_number, body, inline)
                console.print(f"[green]Review posted to GitHub ({len(inline)} inline comment(s)).[/green]")
            except Exception as post_exc:
                if inline and "position" in str(post_exc).lower() or "422" in str(post_exc):
                    # Line numbers the LLM produced may be outside the diff window;
                    # retry with the summary body only so the review still lands.
                    console.print(f"[yellow]Inline comments rejected ({post_exc}); retrying with summary body only.[/yellow]")
                    gh.create_review(repo, pr_number, body, [])
                    console.print("[green]Review posted to GitHub (summary only — inline comments skipped).[/green]")
                else:
                    raise
        except Exception as exc:
            console.print(f"[yellow]Warning: could not post GitHub review: {exc}[/yellow]")
    else:
        console.print(f"Review saved locally. Run `prv status {result.review_run_id[:8]}` to view.")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@app.command(name="list")
def list_runs(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of recent runs to show"),
    repo: Optional[str] = typer.Option(None, "--repo", "-r", help="Repository (owner/name). When given, shows open GitHub PRs instead of stored runs."),
) -> None:
    """List open GitHub PRs for a repo, or recent stored review runs."""
    if repo:
        _list_open_prs(repo)
    else:
        _list_stored_runs(limit)


def _list_open_prs(repo: str) -> None:
    """Fetch open PRs from GitHub and offer an interactive selector."""
    from pr_review_agent.graph.graph import run_pipeline
    from pr_review_agent.tools.github import GitHubClient

    try:
        gh = GitHubClient()
        prs = gh.list_open_prs(repo)
    except Exception as exc:
        console.print(f"[red]Could not fetch PRs for {repo}:[/red] {exc}")
        raise typer.Exit(code=1)

    if not prs:
        console.print(f"[yellow]No open PRs found in {repo}.[/yellow]")
        return

    table = Table(title=f"Open PRs — {repo}")
    table.add_column("#", justify="right", style="cyan")
    table.add_column("PR", justify="right")
    table.add_column("Title")
    table.add_column("Author")
    table.add_column("Head SHA", style="dim")

    for i, pr in enumerate(prs, start=1):
        table.add_row(
            str(i),
            str(pr["number"]),
            pr["title"],
            pr.get("author", ""),
            pr["head_sha"][:8],
        )

    console.print(table)

    raw = typer.prompt("\nSelect PR number to review (or Enter to cancel)", default="").strip()
    if not raw:
        return

    pr_number: int | None = None
    if raw.isdigit():
        num = int(raw)
        if 1 <= num <= len(prs):
            pr_number = prs[num - 1]["number"]
        else:
            for pr in prs:
                if pr["number"] == num:
                    pr_number = num
                    break

    if pr_number is None:
        console.print("[yellow]Selection cancelled or not recognised.[/yellow]")
        return

    console.print(f"\nStarting review of {repo} #{pr_number} …\n")
    from pr_review_agent.cli import review as _review_cmd
    _review_cmd(repo=repo, pr_number=pr_number, no_post=False)


def _list_stored_runs(limit: int) -> None:
    """Show recently stored review runs from the local DB."""
    from pr_review_agent.db import get_session, init_db
    from pr_review_agent.models.db import RunRecord
    from sqlmodel import select

    init_db()

    with get_session() as session:
        stmt = select(RunRecord).order_by(RunRecord.created_at.desc()).limit(limit)
        runs = session.exec(stmt).all()

    if not runs:
        console.print("[yellow]No review runs found. Use `prv list --repo owner/name` to see open PRs.[/yellow]")
        raise typer.Exit()

    table = Table(title="Recent Review Runs")
    table.add_column("Run ID", style="dim", no_wrap=True, max_width=12)
    table.add_column("Repository")
    table.add_column("PR", justify="right")
    table.add_column("Risk", justify="center")
    table.add_column("Status", justify="center")
    table.add_column("Created At")

    for run in runs:
        risk_color = {"high": "red", "medium": "yellow", "low": "green"}.get(run.risk_level or "", "")
        risk_str = f"[{risk_color}]{run.risk_level or '—'}[/{risk_color}]" if risk_color else (run.risk_level or "—")
        table.add_row(
            run.id[:8],
            run.repo_full_name,
            str(run.pr_number),
            risk_str,
            run.status,
            run.created_at.strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@app.command()
def status(
    run_id: str = typer.Argument(..., help="Review run ID (or prefix)"),
) -> None:
    """Show status and findings for a review run."""
    from pr_review_agent.db import get_session, init_db
    from pr_review_agent.models.db import FindingRecord, RunRecord
    from sqlmodel import select

    init_db()

    with get_session() as session:
        stmt = select(RunRecord).where(RunRecord.id.startswith(run_id))
        run = session.exec(stmt).first()
        if run is None:
            console.print(f"[red]No run found matching '{run_id}'[/red]")
            raise typer.Exit(code=1)

        stmt2 = select(FindingRecord).where(FindingRecord.review_run_id == run.id)
        findings = session.exec(stmt2).all()

    console.rule(f"[bold]{run.repo_full_name} #{run.pr_number}[/bold]")
    console.print(f"Status  : {run.status}")
    console.print(f"Risk    : {run.risk_level or '—'}")
    console.print(f"Title   : {run.title}")
    console.print(f"Head SHA: {run.head_sha[:8]}")
    console.print(f"Created : {run.created_at.strftime('%Y-%m-%d %H:%M')}")

    if not findings:
        console.print("\n[yellow]No findings stored.[/yellow]")
        return

    console.print()
    table = Table(title=f"Findings ({len(findings)})")
    table.add_column("Sev", justify="center")
    table.add_column("Dim")
    table.add_column("File")
    table.add_column("Line", justify="right")
    table.add_column("Finding", max_width=60)
    table.add_column("Conf", justify="right")
    table.add_column("Pub", justify="center")

    for f in findings:
        table.add_row(
            _sev(f.severity),
            f.dimension,
            f.file,
            str(f.line) if f.line else "—",
            f.finding[:60],
            f"{f.confidence:.2f}",
            "✓" if f.published else "✗",
        )

    console.print(table)


# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------

@app.command()
def logs(
    run_id: str = typer.Argument(None, help="Run ID to show logs for"),
    pr: int = typer.Option(None, "--pr", help="PR number to look up latest run for"),
    repo: str = typer.Option("", "--repo", help="Repo owner/name filter for --pr lookup"),
) -> None:
    """Show per-phase timing logs for a run, or findings for a PR number."""
    from pr_review_agent.db import get_session, init_db
    from pr_review_agent.models.db import FindingRecord, PhaseLog, RunRecord
    from sqlmodel import select

    init_db()

    if pr is not None:
        # Look up the most recent run for the given PR number
        with get_session() as session:
            stmt = select(RunRecord).where(RunRecord.pr_number == pr)
            if repo:
                stmt = stmt.where(RunRecord.repo_full_name == repo)
            stmt = stmt.order_by(RunRecord.id.desc()).limit(1)
            run = session.exec(stmt).first()

            if run is None:
                console.print(f"[red]No run found for PR #{pr}" + (f" in {repo}" if repo else "") + "[/red]")
                raise typer.Exit(1)

            stmt2 = select(FindingRecord).where(FindingRecord.review_run_id == run.id)
            findings = list(session.exec(stmt2).all())

        console.rule(f"[bold]Findings for {run.repo_full_name} #{run.pr_number}[/bold]")
        _render_findings_table(console, findings)
        return

    # Fall back to run_id-based phase log display
    if not run_id:
        console.print("[red]Provide a run_id argument or --pr option.[/red]")
        raise typer.Exit(1)

    with get_session() as session:
        stmt = select(RunRecord).where(RunRecord.id.startswith(run_id))
        run = session.exec(stmt).first()
        if run is None:
            console.print(f"[red]No run found matching '{run_id}'[/red]")
            raise typer.Exit(code=1)

        stmt2 = select(PhaseLog).where(PhaseLog.review_run_id == run.id)
        phase_logs = session.exec(stmt2).all()

    console.rule(f"[bold]Phase logs for {run.repo_full_name} #{run.pr_number}[/bold]")

    if not phase_logs:
        console.print("[yellow]No phase logs stored.[/yellow]")
        return

    table = Table()
    table.add_column("Phase")
    table.add_column("Status", justify="center")
    table.add_column("Started At")
    table.add_column("Finished At")
    table.add_column("Detail", max_width=60)

    for log in phase_logs:
        status_color = {"done": "green", "failed": "red", "running": "cyan", "pending": "dim"}.get(log.status, "")
        table.add_row(
            log.phase,
            f"[{status_color}]{log.status}[/{status_color}]" if status_color else log.status,
            log.started_at.strftime("%H:%M:%S") if log.started_at else "—",
            log.finished_at.strftime("%H:%M:%S") if log.finished_at else "—",
            log.detail or "",
        )

    console.print(table)
