# PR Review Agent — Manual

## Prerequisites

| Requirement | Check |
|---|---|
| Python 3.11+ | `python --version` |
| graphify binary | `graphify --help` (must be on PATH) |
| GitHub Personal Access Token | Classic PAT with `repo` scope (or `public_repo` for public repos only) |
| LLM credentials | Azure OpenAI **or** plain OpenAI |

---

## Step 1 — Install the package

```powershell
cd path/to/pr-review-agent
pip install -e .[dev]
```

Verify:

```powershell
pr-agent --help
```

Expected output:

```
Usage: pr-agent [OPTIONS] COMMAND [ARGS]...
  Repository-aware autonomous PR review CLI.
Commands:
  setup    Interactive setup: save credentials to ~/.pr-agent/config.toml.
  health   Check system health: config, credentials, DB, and Graphify availability.
  review   Run a full review pipeline on a PR and persist results.
  list     List open GitHub PRs for a repo, or recent stored review runs.
  status   Show status and findings for a review run.
  logs     Show per-phase timing logs for a run, or findings for a PR number.
```

---

## Step 2 — Configure credentials

```powershell
pr-agent setup
```

The interactive prompt walks through:

```
──────────────────────────────────────────────────────────── pr-agent setup ────

GitHub personal access token (leave blank to skip): ghp_YOUR_TOKEN_HERE
LLM backend? [azure/openai]: azure

Azure OpenAI API key: YOUR_AZURE_KEY
Azure OpenAI endpoint: https://YOUR_RESOURCE.openai.azure.com/
Azure deployment / model: gpt-4o

Default repository (owner/repo, leave blank to skip): octocat/Hello-World
Critic confidence threshold (0.0–1.0): 0.7

Config saved to ~/.pr-agent/config.toml
Database initialised at ~/.pr-agent/runs.db
```

For plain OpenAI instead of Azure, choose `openai` at the backend prompt and provide an `sk-...` key.

**What `~/.pr-agent/config.toml` looks like after setup:**

```toml
github_token = "ghp_..."
azure_openai_api_key = "..."
azure_openai_endpoint = "https://..."
azure_openai_model = "gpt-4o"
default_repo = "octocat/Hello-World"
critic_confidence_threshold = 0.7
```

**Alternative: environment variables** (override config.toml, useful for CI or quick testing)

```powershell
$env:PR_AGENT_GITHUB_TOKEN          = "ghp_..."
$env:PR_AGENT_AZURE_OPENAI_API_KEY  = "..."
$env:PR_AGENT_AZURE_OPENAI_ENDPOINT = "https://..."
$env:PR_AGENT_AZURE_OPENAI_MODEL    = "gpt-4o"
```

All `PR_AGENT_*` env vars take precedence over any value in config.toml.

---

## Step 3 — Verify system health

```powershell
pr-agent health
```

Expected (all green):

```
  ✓  Config file exists  ~/.pr-agent/config.toml
  ✓  GitHub token set    PR_AGENT_GITHUB_TOKEN overrides config
  ✓  LLM key present     azure_openai_api_key or openai_api_key
  ✓  LLM model set       gpt-4o
  ✓  Database exists     ~/.pr-agent/runs.db
  ✓  Graphify on PATH    /usr/local/bin/graphify

All checks passed.
```

A red `✗` row with exit code 1 indicates what needs fixing before proceeding.

---

## Step 4 — Find a PR to review

**Option A — Browse open PRs interactively:**

```powershell
pr-agent list --repo owner/repo
```

Fetches open PRs from GitHub and displays a table:

```
               Open PRs — owner/repo
 #   PR   Title                    Author     Head SHA
 1   47   fix: handle null tokens  alice      a1b2c3d4
 2   45   feat: add retry logic    bob        e5f6g7h8
 3   43   chore: update deps       carol      i9j0k1l2

Select PR number to review (or Enter to cancel): 1
```

Entering `1` launches the full review pipeline immediately for PR #47.

**Option B — Review directly if you already know the PR number:**

```powershell
pr-agent review owner/repo 47
```

---

## Step 5 — What happens during `pr-agent review`

The pipeline runs 8 phases sequentially. Live progress is printed as each phase starts and completes:

```
────────────── Reviewing owner/repo #47 ──────────────
  → ingest …
  ✓ ingest  (2.3s)
  → symbols …
  ✓ symbols  (0.4s)
  → graphify …
  ✓ graphify  (8.1s)
  → context …
  ✓ context  (0.1s)
  → readers …
  ✓ readers  (6.7s)
  → synthesizer …
  ✓ synthesizer  (0.2s)
  → reviewer …
  ✓ reviewer  (4.5s)
  → critic …
  ✓ critic  (3.8s)
```

### What each phase does

| Phase | What it does | Network |
|---|---|---|
| **ingest** | Fetches PR metadata + file diffs from GitHub API; clones/fetches repo to `~/.pr-agent/repos/owner/repo/` | GitHub API + git |
| **symbols** | Tree-sitter AST extraction on changed files → symbol list + initial risk score | None |
| **graphify** | Runs `graphify update <repo>`, then `graphify affected <symbol>` for each changed function/class to compute blast radius | None (local binary) |
| **context** | Selects relevant context files based on blast radius output | None |
| **readers** | LLM summarizes each context file (up to 5 concurrent calls) | LLM API |
| **synthesizer** | Assembles repository context from file summaries deterministically | None |
| **reviewer** | LLM generates findings across 4 dimensions: correctness, architecture, testing, maintainability | LLM API |
| **critic** | LLM validates each finding; filters those below `critic_confidence_threshold` | LLM API |

---

## Step 6 — Findings output

After the pipeline completes, a Rich table is printed:

```
                        Findings (4)
Sev       Dimension       File               Line  Finding                                  Conf
major     correctness     auth/utils.py      42    Missing input validation on user_id ...  0.87
major     architecture    api/routes.py      15    Direct DB call in route handler viol...  0.81
minor     testing         auth/utils.py      38    hash_password has no unit test covera...  0.74
info      maintainability api/routes.py      29    Magic string "Bearer" should be a na...  0.71

4 findings (3 publishable, 0 summary-only, 1 filtered)
```

**Count breakdown:**

| Label | Meaning |
|---|---|
| publishable | Confidence ≥ threshold and has a mappable diff position — will become inline PR comments |
| summary-only | Confidence ≥ threshold but no mappable diff line — appears in the PR review body only |
| filtered | Below confidence threshold; stored in the local DB but not posted |

---

## Step 7 — Publish decision

```
────────────────────── Summary ──────────────────────
Run ID   : a3f8e2b1
Risk     : medium
Post this review to GitHub? (y/N):
```

- Type `y` + Enter → posts inline comments and a summary review body to the PR via the GitHub API
- Press Enter (default `N`) → saves results locally only; no GitHub API call is made

The `RunRecord` and `FindingRecord` rows are written to `~/.pr-agent/runs.db` **before** this prompt, regardless of the publish decision.

If posting fails (e.g. token lacks `write:discussion`), a yellow warning is printed — the local DB record is already saved and the run is not lost.

---

## Step 8 — View results later

**By run ID** (printed after the review completes):

```powershell
pr-agent status a3f8e2b1
```

Shows PR title, risk level, head SHA, and all stored findings with published/discarded flags.

**By PR number** (no need to remember the run ID):

```powershell
pr-agent logs --pr 47

# With repo filter when multiple repos share a PR number:
pr-agent logs --pr 47 --repo owner/repo
```

**Phase timing log** (by run ID):

```powershell
pr-agent logs a3f8e2b1
```

**Recent run history** (last 20 runs from the local DB):

```powershell
pr-agent list
```

---

## Recommended first test target

Pick a **public Python or TypeScript repo** with a small open PR (3–15 files changed). The review quality is easiest to evaluate on repos you already know.

**Avoid for a first run:**

- Monorepos — slow clone, many symbols, longer graphify index build
- PRs with only non-code changes (README, YAML config) — tree-sitter finds no symbols; findings will be sparse
- Private repos unless your GitHub token has `repo` scope (not just `public_repo`)

---

## Configuration reference

All settings live in `~/.pr-agent/config.toml`. Any field can be overridden with a `PR_AGENT_<UPPER_FIELD_NAME>` environment variable.

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
| `blast_radius_max_files` | `20` | Max source files to include in the NetworkX graph |
| `blast_radius_max_depth` | `2` | BFS depth for caller/callee traversal |
| `default_repo` | — | Used when `--repo` is omitted |

To increase limits for larger repos:

```toml
blast_radius_max_files = 50
blast_radius_max_depth = 3
```

---

## File layout

```
~/.pr-agent/
  config.toml          # credentials and settings
  runs.db              # SQLite database (RunRecord, FindingRecord, PhaseLog)
  repos/
    owner/
      repo/            # persistent git clone, checked out to the reviewed head SHA
```

Repos are cloned once and fetched on subsequent reviews of the same repo — the first review of a large repo will be slower than later ones.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `pr-agent: command not found` | Package not installed or not on PATH | Re-run `pip install -e .`; confirm `pip` and the shell share the same Python env |
| `health` shows `✗ GitHub token set` | Token missing from config and env | Run `pr-agent setup` or set `$env:PR_AGENT_GITHUB_TOKEN` |
| `health` shows `✗ Graphify on PATH` | `graphify` binary not found | Install graphify or add its directory to `$env:PATH`; blast radius falls back to NetworkX |
| `Pipeline failed: 401` in ingest | GitHub token invalid or expired | Regenerate the PAT and re-run `pr-agent setup` |
| `Pipeline failed: rate limit` in readers/reviewer | LLM API quota exceeded | Wait for quota reset or reduce `blast_radius_max_files` to shorten the context sent |
| `No findings` after a successful run | All findings filtered by confidence threshold | Lower `critic_confidence_threshold` in config.toml (e.g. to `0.5`) and re-run |
| `No unique node match` in graphify phase | Symbol name not in the graphify graph | Expected for symbols in files tree-sitter can't parse; graphify skips them silently |
