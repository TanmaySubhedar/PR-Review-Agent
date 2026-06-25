# pr-review-agent

Repository-aware autonomous PR review CLI. Fetches PRs via the GitHub API, runs a multi-phase analysis pipeline (diff analysis → blast radius → context reading → review → critic), and optionally posts findings as GitHub review comments.

## Setup

```bash
pip install -e .
pr-agent setup
```

Configuration is stored in `~/.pr-agent/config.toml`. Review run history is kept in `~/.pr-agent/runs.db`.

## Commands

| Command | Description |
|---|---|
| `pr-agent setup` | Interactive setup: save GitHub token and LLM credentials |
| `pr-agent review <repo> <pr>` | Run a full review on a PR (e.g. `owner/repo 42`) |
| `pr-agent list` | List recent review runs |
| `pr-agent status <run-id>` | Show status and findings for a review run |
| `pr-agent logs <run-id>` | Show per-phase timing logs for a run |

## Environment overrides

All config values can be overridden with environment variables:

```
PR_AGENT_GITHUB_TOKEN
PR_AGENT_AZURE_OPENAI_API_KEY
PR_AGENT_AZURE_OPENAI_ENDPOINT
PR_AGENT_AZURE_OPENAI_MODEL
PR_AGENT_OPENAI_API_KEY
```
