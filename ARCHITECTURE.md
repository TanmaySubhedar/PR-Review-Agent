# How a review run actually happens

This documents the real, current execution path - not the aspirational
9-phase doc, but what the code in this repo actually does, file by file,
function by function, in the order it runs. See [README.md](README.md) for
how to set the system up and run it.

## End-to-end flow

```
GitHub                         backend/app/api/webhooks.py
  │  PR opened/updated            github_webhook()
  ├──── POST /webhooks/github ───────▶│
  │                                   │ verify signature, parse payload,
  │                                   │ create ReviewRun + 8 PhaseLog rows
  │◀──── 200 {"status":"queued"} ─────┤
  │                                   │ background_tasks.add_task(...)
  │                                   ▼
  │                          backend/app/pipeline/runner.py
  │                            execute_review_run()
  │                                   │
  │                          fetch PR details + file diffs (GitHub API)
  │                          fetch previous run's findings (local DB)
  │                          shallow git clone of PR head (temp dir)
  │                                   │
  │                                   ▼
  │                       backend/app/pipeline/orchestrator.py
  │                         run_review_pipeline()  - 7 phases, see below
  │                                   │
  │                          write Finding rows, set ReviewRun.status="done"
  │                                   │
  │◀──── POST review (comments) ─────┤  (inside phase 7, publisher.py)
  ▼
PR now has inline comments + a summary
```

## Step by step

### 1. Webhook arrives

**File:** [`backend/app/api/webhooks.py`](backend/app/api/webhooks.py) → `github_webhook()`

- Verifies `X-Hub-Signature-256` against `GITHUB_WEBHOOK_SECRET` (`app/github/signature.py::verify_signature`).
- Bails out immediately (no further processing) unless the event is `pull_request` **and** the action is one of `opened`, `synchronize`, `reopened`, `ready_for_review` (`app/pipeline/ingestion.py::is_relevant_pull_request_event`).
- Parses the JSON payload into a `PREvent` (`app/pipeline/ingestion.py::parse_pull_request_event`).
- Inserts one `ReviewRun` row (status=`received`) and one `PhaseLog` row per phase (`ingestion`, `diff_analysis`, `blast_radius`, `context_retrieval`, `synthesis`, `review`, `critic`, `publish`), all `pending`.
- Schedules `runner.execute_review_run(run.id, pr_event)` as a FastAPI `BackgroundTask` and returns `200` to GitHub right away.

Everything below happens **after** GitHub already got its response.

### 2. The background task

**File:** [`backend/app/pipeline/runner.py`](backend/app/pipeline/runner.py) → `execute_review_run()`

1. `run.status = "analyzing"`, commit.
2. Phase `ingestion`: `github_client.fetch_pr_event_details()` (real changed-files + commits from GitHub's API) and `fetch_file_diffs()` (patch text + old/new file bytes per changed file) — both in `app/github/client.py`.
3. `_fetch_previous_findings()` — looks up the most recent prior `done` `ReviewRun` for this same repo+PR number, returns its published `Finding` rows as `ReviewFinding` objects (capped at 15, highest-confidence first).
4. `authenticated_clone_url()` + `cloned_pr_head()` (`app/pipeline/blast_radius/workspace.py`) — shallow-clones the PR's head commit into a temp directory via `git fetch origin pull/<n>/head`, auto-deleted when the `with` block exits.
5. Calls `orchestrator.run_review_pipeline(...)` (phases 1-7 below) inside that `with` block.
6. On return: `run.risk_level = result.diff_analysis.risk_level`, `run.status = "done"`, one `Finding` row written per scored finding, commit.
7. The whole thing is wrapped in one `try/except` — any exception sets `run.status = "failed"` and `run.error = str(exc)` instead, and marks whichever `PhaseLog` was `running` as `failed`.

### 3. The pipeline (`run_review_pipeline`)

**File:** [`backend/app/pipeline/orchestrator.py`](backend/app/pipeline/orchestrator.py)

Runs these in strict sequence. Each phase's output is passed directly as Python objects into the next - no DB round-trips in between, only at the start (loading `pr_event`) and the end (writing `Finding` rows back in `runner.py`).

| # | Phase | Function | File | LLM call? |
|---|-------|----------|------|-----------|
| 1 | Diff analysis | `analyze_diff()` | `app/pipeline/diff_analysis.py` | no |
| 2 | Blast radius | `compute_blast_radius()` → `refine_risk_with_blast_radius()` | `app/pipeline/blast_radius/engine.py`, `diff_analysis.py` | no |
| 3 | Context retrieval | `select_context_files()` → `read_all_contexts()` | `context_retrieval.py`, `context_readers.py` | yes - one call per selected file, in parallel |
| 4 | Synthesis | `synthesize_repository_context()` | `context_synthesis.py` | no |
| 5 | Review | `generate_findings()` | `review_agent.py` | yes - one call |
| 6 | Critic | `score_findings()` → `score_finding()` | `critic_agent.py` | yes - one call per finding |
| 7 | Publish | `publish_review()` | `publisher.py` | no |

#### Phase 1 — Diff analysis (`diff_analysis.py`)

For each changed file: parses old/new source with Tree-sitter (`pipeline/symbols.py::extract_symbols`), figures out which functions/classes/methods the diff's hunks actually touch (`_changed_symbols_for_file`), and detects breaking signature changes - async↔sync flips or parameter-count changes (`_detect_signature_changes`). Scores risk from sensitive-path keywords, signature changes, deletions, and diff size (`_score_risk`), producing a `risk_score` (int) and bucketed `risk_level` (`_bucket_score`).

#### Phase 2 — Blast radius (`blast_radius/engine.py`)

Builds a call/import graph of the **whole cloned repo** with Tree-sitter (`repo_graph.py::build_repo_graph`), then for each changed symbol walks the graph (`queries.py`) to find callers, callees, same-module siblings, covering tests, and lexically-matched docs. `refine_risk_with_blast_radius` then adds to the *same* `risk_score` from phase 1 based on caller fan-in and missing test coverage, and re-buckets - one shared scoring scale, not two independent ones.

#### Phase 3 — Context retrieval (`context_retrieval.py` + `context_readers.py`)

Ranks every file touched by the blast radius (changed file > direct caller > callee > test > same-module > dependency-chain) and keeps the top N (`BLAST_RADIUS_MAX_FILES`). Fires one Azure OpenAI call per selected file, bounded by a semaphore (`READER_CONCURRENCY`), asking "what does this file do and why does it matter to this PR" - these run concurrently via `asyncio.gather`.

#### Phase 4 — Synthesis (`context_synthesis.py`)

Pure aggregation, no LLM call: merges the blast-radius graph data and the phase-3 reader outputs into one `RepositoryContext` (affected components/services/tests, risk areas).

#### Phase 5 — Review (`review_agent.py`)

One Azure OpenAI call: the diff + risk assessment + repository context (+ previous run's findings, if any, with explicit resolved/still-present/unrelated instructions) → a list of `ReviewFinding`s across 7 dimensions (correctness, architecture, testing, maintainability, security, performance, logging), plus a `change_summary` and a `suggested_pr_description`. The prompt (`prompts/review_agent_system.md`) requires a concrete evidence trace for correctness/security/performance findings and caps severity to match the rigor of the evidence.

#### Phase 6 — Critic (`critic_agent.py`)

For each finding: a **deterministic** check first (does the cited file/line/evidence actually exist in the diff or context? is the severity hedged with no concrete trace, in which case cap it to `minor`?) - this never calls the LLM for findings that fail it. Findings that pass get a second Azure OpenAI call judging `respects_repo_context`, `actionable`, and `confidence`. `publish = all gates true AND confidence >= threshold`; if the finding is grounded but its line isn't inside any diff hunk, it's downgraded to a summary-only bullet instead of an inline comment.

#### Phase 7 — Publish (`publisher.py`)

Maps each publishable finding's `(file, line)` to GitHub's diff `position` (`app/github/diff_positions.py`), builds the inline comments + one summary body (the `change_summary` first, then risk level, deterministic overall-severity rollup via `compute_overall_severity`, risk areas, downgraded findings, counts), and calls `github_client.create_review(...)` - one GitHub API call posting everything at once.

## Where it ends

- **Success:** `publish_review()` returns a result dict → `run_review_pipeline()` returns a `PipelineResult` → `execute_review_run()` writes `Finding` rows and sets `ReviewRun.status = "done"` → function returns. Background task finished.
- **Failure:** any exception anywhere in the above propagates to `execute_review_run()`'s `except Exception` → `ReviewRun.status = "failed"`, `ReviewRun.error` set, the in-flight `PhaseLog` marked `failed`.

Either way: no retry, no polling loop, no second invocation. One webhook event in, one straight-line pass through, one DB write and (on success) one GitHub API call out.

## Data contracts between phases

Each phase consumes and produces a typed Pydantic model from `backend/app/schemas/`:

```
PREvent  →  DiffAnalysis  →  BlastRadius  →  ContextPackage  →  RepositoryContext  →  list[ReviewFinding]  →  list[ScoredFinding]
```

These are plain in-memory objects passed phase-to-phase by `run_review_pipeline()` - only `ReviewRun` and `Finding` (in `backend/app/models/`) are ever persisted to the database.
