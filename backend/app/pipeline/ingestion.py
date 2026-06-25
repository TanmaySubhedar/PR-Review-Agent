from typing import Any

from app.schemas.pr_event import CommitInfo, PREvent

RELEVANT_ACTIONS = {"opened", "synchronize", "reopened", "ready_for_review"}


def is_relevant_pull_request_event(payload: dict[str, Any]) -> bool:
    return payload.get("action") in RELEVANT_ACTIONS and "pull_request" in payload


def parse_pull_request_event(payload: dict[str, Any]) -> PREvent:
    pr = payload["pull_request"]
    repo = payload["repository"]
    return PREvent(
        repo_full_name=repo["full_name"],
        pr_number=pr["number"],
        pr_url=pr["html_url"],
        title=pr.get("title", ""),
        description=pr.get("body") or "",
        base_sha=pr["base"]["sha"],
        head_sha=pr["head"]["sha"],
        base_ref=pr["base"]["ref"],
        head_ref=pr["head"]["ref"],
        # the *base* repo's clone URL - refs/pull/<n>/head lives there even
        # when the PR comes from a fork, so this is what the blast-radius
        # workspace clone (app/pipeline/blast_radius/workspace.py) fetches from
        clone_url=repo["clone_url"],
        changed_files=[],
        commits=[],
    )


def fetch_changed_files_and_commits(
    github_client: Any, pr_event: PREvent
) -> tuple[list[str], list[CommitInfo]]:
    """Populate changed_files/commits via the GitHub API. Called after the
    PREvent is parsed from the webhook, since the webhook payload itself
    doesn't include the full file/commit list."""
    repo = github_client.get_repo(pr_event.repo_full_name)
    pull = repo.get_pull(pr_event.pr_number)
    changed_files = [f.filename for f in pull.get_files()]
    commits = [
        CommitInfo(sha=c.sha, message=c.commit.message, author=c.commit.author.name)
        for c in pull.get_commits()
    ]
    return changed_files, commits
