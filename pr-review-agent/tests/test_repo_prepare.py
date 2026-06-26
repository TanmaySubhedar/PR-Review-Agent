"""Tests for persistent repo management (tools/repo.py). All git calls are mocked."""

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

import pr_review_agent.tools.repo as repo_module
from pr_review_agent.tools.repo import (
    _auth_url,
    _repo_dir,
    checkout_sha,
    ensure_local_repo,
    fetch_latest,
)

_CLONE_URL = "https://github.com/owner/repo.git"
_REPO_NAME = "owner/repo"
_HEAD_SHA = "abc123def456"


# ---------------------------------------------------------------------------
# _auth_url
# ---------------------------------------------------------------------------

def test_auth_url_embeds_token():
    result = _auth_url("https://github.com/owner/repo.git", "ghp_token")
    assert "x-access-token:ghp_token@" in result


def test_auth_url_no_token_returns_unchanged():
    result = _auth_url(_CLONE_URL, None)
    assert result == _CLONE_URL


def test_auth_url_already_has_credentials():
    url = "https://x-access-token:abc@github.com/owner/repo.git"
    assert _auth_url(url, "other") == url


# ---------------------------------------------------------------------------
# _repo_dir
# ---------------------------------------------------------------------------

def test_repo_dir_structure():
    d = _repo_dir("myorg/myrepo")
    assert d.parts[-1] == "myrepo"
    assert d.parts[-2] == "myorg"


# ---------------------------------------------------------------------------
# ensure_local_repo — clone path (repo does NOT exist)
# ---------------------------------------------------------------------------

def test_ensure_clones_when_absent(tmp_path):
    fake_repo = tmp_path / "owner" / "repo"

    with patch.object(repo_module, "_REPOS_ROOT", tmp_path), \
         patch.object(repo_module, "_run") as mock_run:

        result = ensure_local_repo(_CLONE_URL, _REPO_NAME, _HEAD_SHA, github_token="tok")

    calls = mock_run.call_args_list
    # First call must be git clone
    assert calls[0][0][0][0] == "git"
    assert calls[0][0][0][1] == "clone"
    # Last call must be checkout
    assert calls[-1][0][0][1] == "checkout"
    assert _HEAD_SHA in calls[-1][0][0]


def test_ensure_clones_auth_url_contains_token(tmp_path):
    with patch.object(repo_module, "_REPOS_ROOT", tmp_path), \
         patch.object(repo_module, "_run") as mock_run:

        ensure_local_repo(_CLONE_URL, _REPO_NAME, _HEAD_SHA, github_token="ghp_secret")

    clone_call = mock_run.call_args_list[0]
    clone_args = clone_call[0][0]
    # Auth URL (one of the args) must contain the token
    assert any("ghp_secret" in str(a) for a in clone_args)


# ---------------------------------------------------------------------------
# ensure_local_repo — fetch path (repo DOES exist)
# ---------------------------------------------------------------------------

def test_ensure_fetches_when_present(tmp_path):
    fake_git = tmp_path / "owner" / "repo" / ".git"
    fake_git.mkdir(parents=True)

    with patch.object(repo_module, "_REPOS_ROOT", tmp_path), \
         patch.object(repo_module, "_run") as mock_run:

        ensure_local_repo(_CLONE_URL, _REPO_NAME, _HEAD_SHA)

    call_cmds = [c[0][0] for c in mock_run.call_args_list]
    # Should have a fetch call somewhere before checkout
    assert any("fetch" in cmd for cmd in call_cmds)
    # Should NOT have a clone call
    assert not any("clone" in cmd for cmd in call_cmds)


def test_ensure_does_not_clone_when_present(tmp_path):
    fake_git = tmp_path / "owner" / "repo" / ".git"
    fake_git.mkdir(parents=True)

    with patch.object(repo_module, "_REPOS_ROOT", tmp_path), \
         patch.object(repo_module, "_run") as mock_run:

        ensure_local_repo(_CLONE_URL, _REPO_NAME, _HEAD_SHA)

    call_cmds = [c[0][0] for c in mock_run.call_args_list]
    assert not any("clone" in cmd for cmd in call_cmds)


# ---------------------------------------------------------------------------
# checkout_sha
# ---------------------------------------------------------------------------

def test_checkout_sha_calls_git_checkout(tmp_path):
    with patch.object(repo_module, "_run") as mock_run:
        checkout_sha(tmp_path, "deadbeef")

    args = mock_run.call_args[0][0]
    assert args[0] == "git"
    assert "checkout" in args
    assert "--detach" in args
    assert "deadbeef" in args


# ---------------------------------------------------------------------------
# fetch_latest
# ---------------------------------------------------------------------------

def test_fetch_latest_calls_git_fetch(tmp_path):
    with patch.object(repo_module, "_run") as mock_run:
        fetch_latest(tmp_path)

    args = mock_run.call_args[0][0]
    assert "fetch" in args


def test_fetch_latest_with_token_sets_remote_url(tmp_path):
    with patch.object(repo_module, "_run") as mock_run:
        fetch_latest(tmp_path, token="tok", clone_url=_CLONE_URL)

    all_calls = [c[0][0] for c in mock_run.call_args_list]
    # First call should set-url, second should fetch
    assert any("set-url" in cmd for cmd in all_calls)
    assert any("fetch" in cmd for cmd in all_calls)


# ---------------------------------------------------------------------------
# Error scrubbing
# ---------------------------------------------------------------------------

def test_run_scrubs_token_from_error(tmp_path):
    import subprocess
    err = subprocess.CalledProcessError(128, ["git"], stderr="fatal: https://x-access-token:super_secret@github.com/repo")

    with patch("pr_review_agent.tools.repo.subprocess.run", side_effect=err):
        with pytest.raises(RuntimeError) as exc_info:
            from pr_review_agent.tools.repo import _run
            _run(["git", "clone", "https://x-access-token:super_secret@github.com/repo"], tmp_path)

    assert "super_secret" not in str(exc_info.value)
    assert "***" in str(exc_info.value)
