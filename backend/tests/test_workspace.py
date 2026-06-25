import subprocess

import pytest

from app.pipeline.blast_radius import workspace


def test_authenticated_clone_url_embeds_token():
    result = workspace.authenticated_clone_url("https://github.com/owner/repo.git", "secret-token")
    assert result == "https://x-access-token:secret-token@github.com/owner/repo.git"


def test_authenticated_clone_url_noop_without_token():
    result = workspace.authenticated_clone_url("https://github.com/owner/repo.git", None)
    assert result == "https://github.com/owner/repo.git"


def test_authenticated_clone_url_noop_if_already_has_credentials():
    url = "https://x-access-token:already-there@github.com/owner/repo.git"
    assert workspace.authenticated_clone_url(url, "secret-token") == url


def test_run_scrubs_token_from_git_error(monkeypatch):
    def fake_run(args, cwd, check, capture_output, text):
        raise subprocess.CalledProcessError(
            128,
            args,
            stderr="fatal: unable to access 'https://x-access-token:secret-token@github.com/owner/repo.git/': "
            "The requested URL returned error: 403",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError) as exc_info:
        workspace._run(["git", "fetch"], cwd=workspace.Path("."))

    assert "secret-token" not in str(exc_info.value)
    assert "x-access-token:***@" in str(exc_info.value)
