# pr-review-agent

Repository-aware autonomous PR review CLI. Fetches PRs via the GitHub API, runs an 8-phase agentic pipeline (diff analysis → blast radius → context → review → critic), and optionally posts findings as inline GitHub review comments.

---

## Prerequisites

| Requirement | Check |
|---|---|
| Python 3.11+ | `python --version` |
| graphify binary | `graphify --help` (must be on PATH) |
| GitHub Personal Access Token | Classic PAT with `repo` scope (or `public_repo` for public repos only) |
| LLM credentials | Azure OpenAI **or** plain OpenAI |

---

## Install

```bash
cd pr-review-agent
pip install -e .[dev]

# Verify
prv --help
```

---

## Setup

```bash
prv setup
```

The interactive prompt walks through:

```
GitHub personal access token (leave blank to skip): ghp_YOUR_TOKEN_HERE
LLM backend? [azure/openai]: azure

Azure OpenAI API key: YOUR_AZURE_KEY
Azure OpenAI endpoint: https://YOUR_RESOURCE.openai.azure.com/
Azure deployment / model: gpt-4o

Default repository (owner/repo, leave blank to skip): octocat/Hello-World
Critic confidence threshold (0.0–1.0): 0.7

Config saved to ~/.prv/config.toml
Database initialised at ~/.prv/runs.db
```

Config file after setup (`~/.prv/config.toml`):

```toml
github_token = "ghp_..."
azure_openai_api_key = "..."
azure_openai_endpoint = "https://..."
azure_openai_model = "gpt-4o"
default_repo = "octocat/Hello-World"
critic_confidence_threshold = 0.7
```

All config values can be overridden with environment variables (take precedence over config.toml):

```
PR_AGENT_GITHUB_TOKEN
PR_AGENT_AZURE_OPENAI_API_KEY
PR_AGENT_AZURE_OPENAI_ENDPOINT
PR_AGENT_AZURE_OPENAI_MODEL
PR_AGENT_OPENAI_API_KEY
```

---

## Commands

| Command | Description |
|---|---|
| `prv setup` | Interactive setup: save credentials to `~/.prv/config.toml` |
| `prv health` | Check config, credentials, DB, and graphify availability |
| `prv review <repo> <pr>` | Run a full review pipeline on a PR (e.g. `owner/repo 42`) |
| `prv list` | List open GitHub PRs for a repo, or recent stored review runs |
| `prv status <run-id>` | Show status and findings for a review run |
| `prv logs <run-id>` | Show per-phase timing logs for a run |

### Health check

```bash
prv health
```

```
  ✓  Config file exists  ~/.prv/config.toml
  ✓  GitHub token set    PR_AGENT_GITHUB_TOKEN overrides config
  ✓  LLM key present     azure_openai_api_key or openai_api_key
  ✓  LLM model set       gpt-4o
  ✓  Database exists     ~/.prv/runs.db
  ✓  Graphify on PATH    /usr/local/bin/graphify

All checks passed.
```

### Browse and review

```bash
# Browse open PRs interactively
prv list --repo owner/repo

# Review directly
prv review owner/repo 47
```

---

## Pipeline

Eight phases run sequentially. Live progress is printed as each phase starts and completes:

```
────────────── Reviewing owner/repo #47 ──────────────
  → ingest …       ✓ ingest      (2.3s)
  → symbols …      ✓ symbols     (0.4s)
  → graphify …     ✓ graphify    (8.1s)
  → context …      ✓ context     (0.1s)
  → readers …      ✓ readers     (6.7s)
  → synthesizer …  ✓ synthesizer (0.2s)
  → reviewer …     ✓ reviewer    (4.5s)
  → critic …       ✓ critic      (3.8s)
```

| Phase | What it does | Network |
|---|---|---|
| **ingest** | Fetches PR metadata + file diffs from GitHub API; clones/fetches repo to `~/.prv/repos/owner/repo/` | GitHub API + git |
| **symbols** | Tree-sitter AST extraction on changed files → symbol list + initial risk score | None |
| **graphify** | *Agentic:* runs an LLM agent that queries the graphify index (`get_callers`, `get_callees`, `get_related`) iteratively, deciding which symbols need deeper traversal based on risk level. Produces a blast radius graph. Falls back to NetworkX if graphify is unavailable. | None (local binary) |
| **context** | Selects candidate context files based on blast radius output | None |
| **readers** | *Agentic dispatch:* LLM decides which context files are worth reading and assigns each a targeted focus question. Reads selected files concurrently. | LLM API |
| **synthesizer** | Assembles a `RepositoryContext` from file summaries deterministically | None |
| **reviewer** | LLM generates findings across 5 dimensions: correctness, architecture, testing, maintainability, **intent** | LLM API |
| **critic** | LLM validates each finding; filters those below `critic_confidence_threshold`. *Agentic refinement:* borderline findings (confidence 0.4–threshold, actionable, context-respecting) get one strengthening attempt before a final pass/fail decision. | LLM API |

### Review dimensions

| Dimension | What it checks |
|---|---|
| **correctness** | Logic errors, off-by-one, null/error handling, data races |
| **architecture** | Layer violations, coupling, missed abstractions |
| **testing** | Coverage gaps for changed code paths |
| **maintainability** | Readability, naming, magic values, complexity |
| **intent** | Diff actually implements what the PR description claims; flags scope creep or missing behaviour |

---

## Findings output

```
                    Findings (4)
Sev       Dimension       File               Line  Finding                                  Conf
major     correctness     auth/utils.py      42    Missing input validation on user_id ...  0.87
major     architecture    api/routes.py      15    Direct DB call in route handler viol...  0.81
minor     testing         auth/utils.py      38    hash_password has no unit test covera...  0.74
info      maintainability api/routes.py      29    Magic string "Bearer" should be a na...  0.71

4 findings (3 publishable, 0 summary-only, 1 filtered)
```

| Label | Meaning |
|---|---|
| publishable | Confidence ≥ threshold **and** has a mappable diff position — becomes an inline PR comment |
| summary-only | Confidence ≥ threshold but no mappable diff line — appears in the PR review body only |
| filtered | Below confidence threshold; stored in the local DB but not posted |

---

## Publish decision

```
────────────────────── Summary ──────────────────────
Run ID   : a3f8e2b1
Risk     : medium
Post this review to GitHub? (y/N):
```

- `y` → posts inline comments and a summary review body to the PR
- Enter (default `N`) → saves results locally only

`RunRecord` and `FindingRecord` rows are written to `~/.prv/runs.db` **before** this prompt, regardless of the publish decision.

---

## View results later

```bash
# By run ID
prv status a3f8e2b1

# By PR number
prv logs --pr 47
prv logs --pr 47 --repo owner/repo   # when multiple repos share the same PR number

# Phase timing log
prv logs a3f8e2b1

# Recent run history (last 20 runs)
prv list
```

---

## Configuration reference

All settings live in `~/.prv/config.toml`. Any field can be overridden with `PR_AGENT_<UPPER_FIELD_NAME>`.

| Field | Default | Description |
|---|---|---|
| `github_token` | — | GitHub PAT |
| `azure_openai_api_key` | — | Azure OpenAI API key |
| `azure_openai_endpoint` | — | Azure resource endpoint URL |
| `azure_openai_api_version` | `2024-02-01` | Azure API version |
| `azure_openai_model` | `gpt-4o` | Azure deployment name or plain OpenAI model ID |
| `openai_api_key` | — | Plain OpenAI API key (used when Azure fields are absent) |
| `openai_base_url` | — | Custom base URL (for proxies or local models) |
| `critic_confidence_threshold` | `0.7` | Findings below this confidence are filtered |
| `blast_radius_max_files` | `20` | Max source files in the NetworkX fallback graph |
| `blast_radius_max_depth` | `2` | BFS depth for caller/callee traversal (fallback path) |
| `default_repo` | — | Used when `--repo` is omitted |

---

## File layout

```
~/.prv/
  config.toml          # credentials and settings
  runs.db              # SQLite database (RunRecord, FindingRecord, PhaseLog)
  repos/
    owner/
      repo/            # persistent git clone, checked out to the reviewed head SHA
```

Repos are cloned once and fetched on subsequent reviews — the first review of a large repo will be slower than later ones.

---

## Tips

- Pick a **public Python or TypeScript repo** with a small open PR (3–15 files changed) for your first test. Review quality is easiest to evaluate on repos you already know.
- **Avoid for a first run:** monorepos (slow clone), PRs with only non-code changes (tree-sitter finds no symbols), private repos without `repo` scope on the PAT.
- To increase limits for larger repos: set `blast_radius_max_files = 50` and `blast_radius_max_depth = 3` in config.toml.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `prv: command not found` | Package not installed or not on PATH | Re-run `pip install -e .`; confirm `pip` and shell share the same Python env |
| `health` shows `✗ GitHub token set` | Token missing from config and env | Run `prv setup` or set `$env:PR_AGENT_GITHUB_TOKEN` |
| `health` shows `✗ Graphify on PATH` | `graphify` binary not found | Install graphify or add its directory to PATH; blast radius falls back to NetworkX |
| `Pipeline failed: 401` in ingest | GitHub token invalid or expired | Regenerate the PAT and re-run `prv setup` |
| `Pipeline failed: rate limit` in readers/reviewer | LLM API quota exceeded | Wait for quota reset or reduce `blast_radius_max_files` |
| `No findings` after a successful run | All findings filtered by confidence threshold | Lower `critic_confidence_threshold` in config.toml (e.g. `0.5`) and re-run |
| `No unique node match` in graphify phase | Symbol name not in the graphify graph | Expected for symbols in files tree-sitter can't parse; graphify skips them silently |
