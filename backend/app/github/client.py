from typing import Protocol

from github import Auth, Github

from app.config import settings
from app.pipeline.diff_analysis import FileDiff
from app.schemas.pr_event import CommitInfo


class GitHubClient(Protocol):
    """Thin interface the rest of the pipeline depends on, so the PAT-based
    implementation below can be swapped for GitHub App installation-token
    auth later without touching ingestion/publisher code."""

    def fetch_pr_event_details(self, repo_full_name: str, pr_number: int) -> tuple[list[str], list[CommitInfo]]: ...

    def fetch_file_diffs(self, repo_full_name: str, pr_number: int) -> list[FileDiff]: ...

    def create_review(
        self, repo_full_name: str, pr_number: int, summary_body: str, inline_comments: list[dict]
    ) -> None: ...


class PATGitHubClient:
    def __init__(self, token: str | None = None):
        token = token or settings.github_token
        self._gh = Github(auth=Auth.Token(token)) if token else Github()

    def fetch_pr_event_details(self, repo_full_name: str, pr_number: int) -> tuple[list[str], list[CommitInfo]]:
        pull = self._gh.get_repo(repo_full_name).get_pull(pr_number)
        changed_files = [f.filename for f in pull.get_files()]
        commits = [
            CommitInfo(sha=c.sha, message=c.commit.message, author=c.commit.author.name)
            for c in pull.get_commits()
        ]
        return changed_files, commits

    def fetch_file_diffs(self, repo_full_name: str, pr_number: int) -> list[FileDiff]:
        repo = self._gh.get_repo(repo_full_name)
        pull = repo.get_pull(pr_number)

        file_diffs: list[FileDiff] = []
        for f in pull.get_files():
            status = "added" if f.status == "added" else "removed" if f.status == "removed" else "modified"

            new_source = None
            if status != "removed":
                try:
                    new_source = repo.get_contents(f.filename, ref=pull.head.sha).decoded_content
                except Exception:
                    new_source = None

            old_source = None
            if status != "added":
                try:
                    old_source = repo.get_contents(f.filename, ref=pull.base.sha).decoded_content
                except Exception:
                    old_source = None

            file_diffs.append(
                FileDiff(
                    file=f.filename,
                    patch=f.patch or "",
                    status=status,
                    new_source=new_source,
                    old_source=old_source,
                    lines_changed=f.additions + f.deletions,
                )
            )
        return file_diffs

    def create_review(
        self, repo_full_name: str, pr_number: int, summary_body: str, inline_comments: list[dict]
    ) -> None:
        repo = self._gh.get_repo(repo_full_name)
        pull = repo.get_pull(pr_number)
        commit = repo.get_commit(pull.head.sha)
        pull.create_review(commit=commit, body=summary_body, event="COMMENT", comments=inline_comments)
