import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

_CREDENTIAL_IN_URL_RE = re.compile(r"https://x-access-token:[^@\s]+@")


def authenticated_clone_url(clone_url: str, token: str | None) -> str:
    """Embed a token into an https clone URL so `git fetch` works against
    private repos. No-op if there's no token or the URL already has
    credentials."""
    if not token or "@" in clone_url.split("://", 1)[-1]:
        return clone_url
    scheme, rest = clone_url.split("://", 1)
    return f"{scheme}://x-access-token:{token}@{rest}"


@contextmanager
def cloned_pr_head(base_clone_url: str, pr_number: int, head_sha: str):
    """Shallow-clone a PR's head commit into a scratch directory.

    Fetches `pull/<n>/head` from the *base* repo's clone URL rather than the
    fork's, since that ref exists on the base repo even when the PR comes
    from a fork - this avoids needing fork credentials/URLs at all.

    `base_clone_url` may already have a token embedded (see
    authenticated_clone_url) for private repos - any subprocess error is
    scrubbed of credentials before it can propagate into ReviewRun.error,
    which is displayed as-is on the dashboard.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="pr-analyzer-"))
    try:
        _run(["git", "init", "--quiet"], cwd=tmp_dir)
        _run(["git", "remote", "add", "origin", base_clone_url], cwd=tmp_dir)
        _run(
            ["git", "fetch", "--quiet", "--depth", "1", "origin", f"pull/{pr_number}/head"],
            cwd=tmp_dir,
        )
        _run(["git", "checkout", "--quiet", "FETCH_HEAD"], cwd=tmp_dir)
        yield tmp_dir
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _run(args: list[str], cwd: Path) -> None:
    try:
        subprocess.run(args, cwd=str(cwd), check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        message = _CREDENTIAL_IN_URL_RE.sub("https://x-access-token:***@", exc.stderr or str(exc))
        raise RuntimeError(f"git command failed: {message}") from None
