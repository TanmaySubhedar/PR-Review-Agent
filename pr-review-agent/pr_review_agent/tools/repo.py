"""Persistent local repo management. Repos are cached at ~/.pr-agent/repos/<owner>/<repo>/."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from pr_review_agent.config import settings

_REPOS_ROOT = Path.home() / ".pr-agent" / "repos"
_CREDENTIAL_RE = re.compile(r"https://x-access-token:[^@\s]+@")


def _auth_url(clone_url: str, token: str | None) -> str:
    if not token or "@" in clone_url.split("://", 1)[-1]:
        return clone_url
    scheme, rest = clone_url.split("://", 1)
    return f"{scheme}://x-access-token:{token}@{rest}"


def _run(args: list[str], cwd: Path) -> None:
    try:
        subprocess.run(args, cwd=str(cwd), check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        msg = _CREDENTIAL_RE.sub("https://x-access-token:***@", exc.stderr or str(exc))
        raise RuntimeError(f"git command failed: {msg}") from None


def _repo_dir(repo_full_name: str) -> Path:
    owner, name = repo_full_name.split("/", 1)
    return _REPOS_ROOT / owner / name


def ensure_local_repo(
    clone_url: str,
    repo_full_name: str,
    head_sha: str,
    github_token: str | None = None,
) -> Path:
    """Clone to ~/.pr-agent/repos/<owner>/<repo>/ if absent, fetch if present, then checkout head_sha."""
    token = github_token or settings.github_token or None
    auth_url = _auth_url(clone_url, token)
    repo_path = _repo_dir(repo_full_name)

    if not (repo_path / ".git").exists():
        repo_path.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "--filter=blob:none", "--quiet", auth_url, str(repo_path)], cwd=repo_path.parent)
    else:
        fetch_latest(repo_path, token=token, clone_url=clone_url)

    checkout_sha(repo_path, head_sha)
    return repo_path


def checkout_sha(repo_path: Path, sha: str) -> None:
    """Check out a specific commit SHA in detached-HEAD mode."""
    _run(["git", "checkout", "--quiet", "--detach", sha], cwd=repo_path)


def fetch_latest(repo_path: Path, *, token: str | None = None, clone_url: str | None = None) -> None:
    """Fetch all remotes and prune deleted refs. Optionally re-embed credentials."""
    if token and clone_url:
        auth_url = _auth_url(clone_url, token)
        _run(["git", "remote", "set-url", "origin", auth_url], cwd=repo_path)
    _run(["git", "fetch", "--all", "--prune", "--quiet"], cwd=repo_path)
