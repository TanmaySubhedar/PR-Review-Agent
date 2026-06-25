"""GitHub API client. Polls the API directly — no webhook server required."""

from github import Auth, Github

from pr_review_agent.config import settings
from pr_review_agent.models.domain import CommitInfo, FileDiff, PRMetadata


class GitHubClient:
    def __init__(self, token: str | None = None) -> None:
        tok = token or settings.github_token
        self._gh = Github(auth=Auth.Token(tok)) if tok else Github()

    # ------------------------------------------------------------------
    # PR metadata
    # ------------------------------------------------------------------

    def fetch_pr_metadata(self, repo_full_name: str, pr_number: int) -> PRMetadata:
        """Fetch PR metadata by polling the GitHub REST API."""
        repo = self._gh.get_repo(repo_full_name)
        pull = repo.get_pull(pr_number)

        changed_files = [f.filename for f in pull.get_files()]
        commits = [
            CommitInfo(sha=c.sha, message=c.commit.message, author=c.commit.author.name)
            for c in pull.get_commits()
        ]

        return PRMetadata(
            repo_full_name=repo_full_name,
            pr_number=pr_number,
            pr_url=pull.html_url,
            title=pull.title or "",
            description=pull.body or "",
            base_sha=pull.base.sha,
            head_sha=pull.head.sha,
            base_ref=pull.base.ref,
            head_ref=pull.head.ref,
            clone_url=repo.clone_url,
            changed_files=changed_files,
            commits=commits,
        )

    # ------------------------------------------------------------------
    # File diffs
    # ------------------------------------------------------------------

    def fetch_file_diffs(self, repo_full_name: str, pr_number: int) -> list[FileDiff]:
        repo = self._gh.get_repo(repo_full_name)
        pull = repo.get_pull(pr_number)

        file_diffs: list[FileDiff] = []
        for f in pull.get_files():
            if f.status == "added":
                status = "added"
            elif f.status == "removed":
                status = "removed"
            elif f.status == "renamed":
                status = "renamed"
            else:
                status = "modified"

            new_source = None
            if status != "removed":
                try:
                    new_source = repo.get_contents(f.filename, ref=pull.head.sha).decoded_content
                except Exception:
                    pass

            old_source = None
            if status not in ("added",):
                old_name = getattr(f, "previous_filename", None) or f.filename
                try:
                    old_source = repo.get_contents(old_name, ref=pull.base.sha).decoded_content
                except Exception:
                    pass

            file_diffs.append(FileDiff(
                file=f.filename,
                patch=f.patch or "",
                status=status,
                new_source=new_source,
                old_source=old_source,
                lines_changed=f.additions + f.deletions,
            ))
        return file_diffs

    # ------------------------------------------------------------------
    # Review publication
    # ------------------------------------------------------------------

    def create_review(
        self,
        repo_full_name: str,
        pr_number: int,
        summary_body: str,
        inline_comments: list[dict],
    ) -> None:
        repo = self._gh.get_repo(repo_full_name)
        pull = repo.get_pull(pr_number)
        commit = repo.get_commit(pull.head.sha)
        pull.create_review(commit=commit, body=summary_body, event="COMMENT", comments=inline_comments)

    # ------------------------------------------------------------------
    # Open PRs polling
    # ------------------------------------------------------------------

    def list_open_prs(self, repo_full_name: str) -> list[dict]:
        repo = self._gh.get_repo(repo_full_name)
        return [
            {
                "number": pr.number,
                "title": pr.title,
                "url": pr.html_url,
                "head_sha": pr.head.sha,
                "author": pr.user.login if pr.user else "",
            }
            for pr in repo.get_pulls(state="open")
        ]
