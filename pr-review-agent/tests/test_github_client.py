"""Tests for GitHubClient — all GitHub API calls are mocked."""

from unittest.mock import MagicMock, patch

import pytest

from pr_review_agent.models.domain import PRMetadata
from pr_review_agent.tools.github import GitHubClient


# ---------------------------------------------------------------------------
# Helpers: build mock PyGithub objects
# ---------------------------------------------------------------------------

def _make_mock_pull(
    number=42,
    title="Fix auth bug",
    body="Improves auth",
    html_url="https://github.com/owner/repo/pull/42",
    base_sha="base123",
    head_sha="head456",
    base_ref="main",
    head_ref="feature/fix",
):
    pull = MagicMock()
    pull.number = number
    pull.title = title
    pull.body = body
    pull.html_url = html_url
    pull.base.sha = base_sha
    pull.head.sha = head_sha
    pull.base.ref = base_ref
    pull.head.ref = head_ref

    file1 = MagicMock()
    file1.filename = "auth/utils.py"
    pull.get_files.return_value = [file1]

    commit1 = MagicMock()
    commit1.sha = "abc123"
    commit1.commit.message = "Fix null dereference"
    commit1.commit.author.name = "octocat"
    pull.get_commits.return_value = [commit1]
    return pull


def _make_mock_repo(pull, clone_url="https://github.com/owner/repo.git"):
    repo = MagicMock()
    repo.clone_url = clone_url
    repo.get_pull.return_value = pull
    repo.get_commit.return_value = MagicMock()
    return repo


def _make_client(repo_mock):
    with patch("pr_review_agent.tools.github.Github") as MockGithub, \
         patch("pr_review_agent.tools.github.Auth"):
        instance = MockGithub.return_value
        instance.get_repo.return_value = repo_mock
        client = GitHubClient(token="ghp_test")
        client._gh = instance
        return client


# ---------------------------------------------------------------------------
# fetch_pr_metadata
# ---------------------------------------------------------------------------

def test_fetch_pr_metadata_returns_prmetadata():
    pull = _make_mock_pull()
    repo = _make_mock_repo(pull)
    client = _make_client(repo)

    result = client.fetch_pr_metadata("owner/repo", 42)

    assert isinstance(result, PRMetadata)
    assert result.pr_number == 42
    assert result.repo_full_name == "owner/repo"
    assert result.title == "Fix auth bug"
    assert result.head_sha == "head456"
    assert result.base_sha == "base123"
    assert result.base_ref == "main"
    assert result.head_ref == "feature/fix"
    assert result.clone_url == "https://github.com/owner/repo.git"
    assert "auth/utils.py" in result.changed_files
    assert len(result.commits) == 1
    assert result.commits[0].sha == "abc123"


def test_fetch_pr_metadata_empty_body_defaults_to_empty_string():
    pull = _make_mock_pull(body=None)
    repo = _make_mock_repo(pull)
    client = _make_client(repo)

    result = client.fetch_pr_metadata("owner/repo", 42)
    assert result.description == ""


# ---------------------------------------------------------------------------
# list_open_prs
# ---------------------------------------------------------------------------

def test_list_open_prs_returns_expected_shape():
    pr1 = MagicMock()
    pr1.number = 10
    pr1.title = "Add feature X"
    pr1.html_url = "https://github.com/owner/repo/pull/10"
    pr1.head.sha = "sha10abc"
    pr1.user.login = "alice"

    pr2 = MagicMock()
    pr2.number = 11
    pr2.title = "Fix bug Y"
    pr2.html_url = "https://github.com/owner/repo/pull/11"
    pr2.head.sha = "sha11def"
    pr2.user.login = "bob"

    repo = MagicMock()
    repo.get_pulls.return_value = [pr1, pr2]

    client = _make_client(repo)
    result = client.list_open_prs("owner/repo")

    assert len(result) == 2
    assert result[0]["number"] == 10
    assert result[0]["title"] == "Add feature X"
    assert result[0]["author"] == "alice"
    assert result[0]["head_sha"] == "sha10abc"
    assert result[1]["number"] == 11


def test_list_open_prs_no_user_returns_empty_author():
    pr = MagicMock()
    pr.number = 5
    pr.title = "Bot PR"
    pr.html_url = "https://github.com/owner/repo/pull/5"
    pr.head.sha = "sha5"
    pr.user = None

    repo = MagicMock()
    repo.get_pulls.return_value = [pr]

    client = _make_client(repo)
    result = client.list_open_prs("owner/repo")

    assert result[0]["author"] == ""


# ---------------------------------------------------------------------------
# create_review
# ---------------------------------------------------------------------------

def test_create_review_calls_pull_create_review():
    pull = _make_mock_pull()
    repo = _make_mock_repo(pull)
    client = _make_client(repo)

    inline = [{"path": "auth/utils.py", "position": 3, "body": "Consider X"}]
    client.create_review("owner/repo", 42, "Summary body", inline)

    pull.create_review.assert_called_once()
    call_kwargs = pull.create_review.call_args.kwargs
    assert call_kwargs["body"] == "Summary body"
    assert call_kwargs["event"] == "COMMENT"
    assert call_kwargs["comments"] == inline


def test_create_review_empty_inline_comments():
    pull = _make_mock_pull()
    repo = _make_mock_repo(pull)
    client = _make_client(repo)

    client.create_review("owner/repo", 42, "Only a summary", [])

    pull.create_review.assert_called_once()
    call_kwargs = pull.create_review.call_args.kwargs
    assert call_kwargs["comments"] == []
