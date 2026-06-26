"""Ingest node: fetch PRMetadata and file diffs from the GitHub API, then clone the PR head."""

from pr_review_agent.config import settings
from pr_review_agent.graph.state import PRReviewState
from pr_review_agent.tools.github import GitHubClient
from pr_review_agent.tools.repo import ensure_local_repo


def _build_raw_diff(file_diffs) -> str:
    """Concatenate all file patches into a single unified diff string."""
    parts = []
    for fd in file_diffs:
        if fd.patch:
            parts.append(f"--- a/{fd.file}\n+++ b/{fd.file}\n{fd.patch}")
    return "\n".join(parts)


def run(state: PRReviewState) -> PRReviewState:
    gh = GitHubClient()
    repo_full_name = state["repo_full_name"]
    pr_number = state["pr_number"]

    pr_metadata = gh.fetch_pr_metadata(repo_full_name, pr_number)
    file_diffs = gh.fetch_file_diffs(repo_full_name, pr_number)

    if not file_diffs:
        raise ValueError(
            f"PR #{pr_number} in {repo_full_name} has no changed files. "
            "The PR may have empty commits, or its head and base branches point to the same tree. "
            "Open the PR on GitHub and confirm it shows file changes in the 'Files changed' tab."
        )

    repo_path = ensure_local_repo(
        pr_metadata.clone_url,
        repo_full_name,
        pr_metadata.head_sha,
        github_token=settings.github_token or None,
    )
    raw_diff = _build_raw_diff(file_diffs)

    return {
        **state,
        "pr_metadata": pr_metadata,
        "file_diffs": file_diffs,
        "raw_diff": raw_diff,
        "repo_path": repo_path,
        "phase_status": {**state.get("phase_status", {}), "ingest": "done"},
    }
