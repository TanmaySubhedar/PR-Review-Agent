# AI Usage Log — PR-Review-Agent

> Auto-maintained by the `/ai-usage` skill. Updated each session.

## Summary

| Metric | Count |
|---|---|
| Total sessions tracked | 5 |
| Total tool calls (AI) | 254 |
| Files AI-generated | 49 |
| Files human-written | 0 |
| Files accepted | 69 |
| Files rejected | 1 |
| Bugs introduced by AI | 5 |
| Bugs fixed by AI | 5 |
| **AI-written %** | **100%** |
| **Human-written %** | **0%** |

> *Tool call total = 141 main-agent + 113 subagent (F4: 77, F5: 36)*

## Tool Call Totals

| Tool | Times Called |
|---|---|
| Read | 52 |
| Write | 37 |
| Edit | 19 |
| Bash | 6 |
| PowerShell | 18 |
| Grep | 0 |
| Glob | 3 |
| Agent / Workflow | 2 |
| Skill | 6 |
| Artifact | 0 |
| Other | 0 |

## Skills Authored & Fired

| Skill Name | Authored By | Times Fired |
|---|---|---|
| ai-usage | human-directed / AI-written | 5 |
| init | built-in | 1 |

## Slash Commands & Subagents Used

| Command / Subagent | Purpose | Times |
|---|---|---|
| /ai-usage | Update AI usage log | 5 |
| /init | Generate CLAUDE.md from codebase analysis | 1 |
| F4 subagent (worktree) | Unit tests: symbol extraction, risk scoring, prompts, LLM wrapper | 1 |
| F5 subagent (worktree) | Interactive publish flow + PR-number log history in cli.py | 1 |

## Session Log

### Session 1 — 2026-06-25

**Task:** Task 1 — Repository setup. Created the full `pr-review-agent/` CLI package from scratch by refactoring the existing FastAPI webhook backend into a self-contained Typer CLI with GitHub API polling, SQLite persistence, and a graph-based review pipeline.

**Tools called this session:**
- Read: 18, Write: 27, Edit: 0, Bash: 2, PowerShell: 4, Grep: 0, Glob: 3, Skill: 1

**Files touched:**
| File | Action | Origin |
|---|---|---|
| pr-review-agent/pyproject.toml | created | AI |
| pr-review-agent/README.md | created | AI |
| pr-review-agent/.gitignore | created | AI |
| pr-review-agent/pr_review_agent/__init__.py | created | AI |
| pr-review-agent/pr_review_agent/__main__.py | created | AI |
| pr-review-agent/pr_review_agent/cli.py | created | AI |
| pr-review-agent/pr_review_agent/config.py | created | AI |
| pr-review-agent/pr_review_agent/db.py | created | AI |
| pr-review-agent/pr_review_agent/_llm.py | created | AI |
| pr-review-agent/pr_review_agent/models/__init__.py | created | AI |
| pr-review-agent/pr_review_agent/models/config.py | created | AI |
| pr-review-agent/pr_review_agent/models/domain.py | created | AI |
| pr-review-agent/pr_review_agent/models/db.py | created | AI |
| pr-review-agent/pr_review_agent/tools/__init__.py | created | AI |
| pr-review-agent/pr_review_agent/tools/github.py | created | AI |
| pr-review-agent/pr_review_agent/tools/treesitter.py | created | AI |
| pr-review-agent/pr_review_agent/tools/graphify_mcp.py | created | AI |
| pr-review-agent/pr_review_agent/prompts/__init__.py | created | AI |
| pr-review-agent/pr_review_agent/prompts/file_reader.py | created | AI |
| pr-review-agent/pr_review_agent/prompts/reviewer.py | created | AI |
| pr-review-agent/pr_review_agent/prompts/critic.py | created | AI |
| pr-review-agent/pr_review_agent/graph/__init__.py | created | AI |
| pr-review-agent/pr_review_agent/graph/state.py | created | AI |
| pr-review-agent/pr_review_agent/graph/graph.py | created | AI |
| pr-review-agent/pr_review_agent/graph/nodes/__init__.py | created | AI |
| pr-review-agent/pr_review_agent/graph/nodes/ingest.py | created | AI |
| pr-review-agent/pr_review_agent/graph/nodes/symbols.py | created | AI |
| pr-review-agent/pr_review_agent/graph/nodes/graphify.py | created | AI |
| pr-review-agent/pr_review_agent/graph/nodes/context.py | created | AI |
| pr-review-agent/pr_review_agent/graph/nodes/readers.py | created | AI |
| pr-review-agent/pr_review_agent/graph/nodes/synthesizer.py | created | AI |
| pr-review-agent/pr_review_agent/graph/nodes/reviewer.py | created | AI |
| pr-review-agent/pr_review_agent/graph/nodes/critic.py | created | AI |
| tests/ (5 files + fixtures) | created | AI |
| .claude/skills/ai-usage/SKILL.md | created | AI |

**Accepted / Rejected:**
- Accepted: 35 file operations
- Rejected: 1 — `Glob` on `~/.claude/skills` (user redirected to create skill in workspace instead)

**Bugs:**
- Introduced: 0
- Fixed: 0

**Notes:** All 29 tests pass (smoke imports × 23, DB CRUD × 3, config × 3). `pip install -e .` succeeded first try. `pr-agent --help` and `python -m pr_review_agent --help` both work. One rejection: user redirected the skill scope from global to project-local.

---

### Session 2 — 2026-06-25

**Task:** Task 2 completion — Rename canonical model classes and `PRReviewState` keys throughout the codebase. Updated `cli.py` (full rewrite to use `RunRecord`, `FindingRecord`, `pr_metadata`, `validated_findings`, `verdict.confidence`), `tests/test_db.py`, and `tests/test_config.py`. Dropped stale `runs.db` and confirmed 29/29 tests pass.

**Tools called this session:**
- Read: 7, Write: 1, Edit: 3, PowerShell: 2, Skill: 1

**Files touched:**
| File | Action | Origin |
|---|---|---|
| pr_review_agent/cli.py | rewritten (Task 2 model names) | AI |
| tests/test_db.py | edited (ReviewRun→RunRecord, Finding→FindingRecord) | AI |
| tests/test_config.py | edited (AgentSettings→Settings) | AI |
| ai_usage.md | updated | AI |

**Accepted / Rejected:**
- Accepted: 3 file operations (cli.py rewrite, two test file edits)
- Rejected: 0

**Bugs:**
- Introduced: 0
- Fixed: 0 (model rename was a planned refactor, not a bug)

**Notes:** Context was compacted mid-session after Task 2 node rewrites (models/domain, graph/state, all nodes, prompts). Resumed directly into `cli.py` rewrite. The `Finding` name collision (SQLModel table vs domain model) was resolved by renaming the DB table to `FindingRecord` with explicit `__tablename__`. Deleted `~/.pr-agent/runs.db` to force schema recreation with updated table names.

---

### Session 3 — 2026-06-25

**Task:** F2–F5 implementation — Persistent repo management, unified diff parser, Graphify MCP client, unit tests (symbol extraction / risk scoring / prompts / LLM wrapper), interactive publish flow in CLI, and PR-number log history. Suite grew from 29 → 187 tests.

**Tools called this session (main agent):**
- Read: 8, Write: 8, Edit: 4, Bash: 4, PowerShell: 7, Agent: 2, Skill: 1

**Subagent tool calls:**
- F4 agent (worktree): 77 tool calls
- F5 agent (worktree): 36 tool calls

**Files touched:**
| File | Action | Origin |
|---|---|---|
| pr_review_agent/graph/nodes/ingest.py | rewritten (persistent clone via ensure_local_repo) | AI |
| pr_review_agent/graph/graph.py | rewritten (removed shutil.rmtree cleanup) | AI |
| pr_review_agent/tools/graphify_mcp.py | rewritten (full GraphifyMCPClient + is_available) | AI |
| pr_review_agent/graph/nodes/graphify.py | edited (MCP branch + _compute_blast_radius_mcp) | AI |
| tests/test_smoke_imports.py | edited (added tools.repo, tools.diff_parser) | AI |
| tests/fixtures/sample_diff.patch | overwritten (added second file api/routes.py) | AI |
| tests/test_diff_parser.py | created | AI |
| tests/test_repo_prepare.py | created | AI |
| tests/test_graphify_client.py | created | AI |
| tests/test_blast_radius.py | created | AI |
| tests/test_llm_wrapper.py | created (F4 subagent) | AI |
| tests/test_prompts.py | created (F4 subagent) | AI |
| tests/test_risk_scoring.py | created (F4 subagent) | AI |
| tests/test_symbol_extraction.py | created (F4 subagent) | AI |
| tests/fixtures/sample_repo_files/api/routes.py | created (F4 subagent) | AI |
| tests/fixtures/sample_repo_files/ui/components.ts | created (F4 subagent) | AI |
| pr_review_agent/cli.py | rewritten (F5: findings table, publish gate, logs --pr) | AI |
| tests/test_render_and_publish.py | created (F5 subagent) | AI |
| ai_usage.md | updated | AI |

**Accepted / Rejected:**
- Accepted: 18 file operations (13 new, 5 modified)
- Rejected: 0

**Bugs:**
- Introduced: 1 — `test_closed_stdout_raises` used `return_value` on a mock that still had `side_effect` set (list-based), causing `StopIteration` instead of the expected empty-string return
- Fixed: 1 — cleared `side_effect = None` before setting `return_value = ""`

**Notes:** F4 and F5 ran in parallel using worktree-isolated subagents. Since `pr-review-agent/` is entirely untracked by git, worktrees share the untracked directory — F5 agent's `cli.py` changes landed in main directly. F4 files had to be copied from the worktree path. Both completed with all tests passing in their respective environments; merged result: 187/187 green. F6 (end-to-end mocked pipeline test) is the only remaining task.

---

### Session 4 — 2026-06-25

**Task:** Real-world testing and bug triage — fixed 4 bugs discovered during first live PR review run: empty pipeline (0 findings), GitHub 422 position error, graphify rebuilding on every run, and wrong cache key (head_sha → base_sha). Suite grew from 187 → 203 tests. Also generated CLAUDE.md via `/init`.

**Tools called this session:**
- Read: ~18, Write: 1, Edit: ~12, PowerShell: ~5, Skill: 2

**Files touched:**
| File | Action | Origin |
|---|---|---|
| pr_review_agent/graph/nodes/context.py | edited (seed context from file_diffs, not only changed_symbols) | AI |
| pr_review_agent/graph/nodes/ingest.py | edited (guard for empty file_diffs with helpful error) | AI |
| pr_review_agent/tools/github.py | edited (renamed status case + previous_filename lookup) | AI |
| pr_review_agent/tools/graphify_mcp.py | edited (SHA-based caching via sentinel file) | AI |
| pr_review_agent/graph/nodes/graphify.py | edited (base_sha cache key, early exit on no actionable symbols) | AI |
| pr_review_agent/graph/state.py | edited (added graphify_graph_rebuilt field) | AI |
| pr_review_agent/graph/graph.py | edited (on_phase_done callback + PhaseDoneCallback type) | AI |
| pr_review_agent/cli.py | edited (per-phase diagnostics, line+side inline comments, fallback retry) | AI |
| tests/test_graphify_client.py | edited (8 new SHA-based caching tests; head_sha → base_sha) | AI |
| tests/test_render_and_publish.py | edited (assert string: removed trailing period) | AI |
| manual.md | created | AI |
| pr-review-agent/CLAUDE.md | created (via /init skill) | AI |
| ai_usage.md | updated (session 3 log; this file) | AI |

**Accepted / Rejected:**
- Accepted: 13 file operations
- Rejected: 0

**Bugs:**
- Introduced: 4 (all in AI code from earlier sessions, found during first live run)
- Fixed: 4
  1. context.py only seeded files from changed_symbols → empty context when tree-sitter found nothing (unsupported languages)
  2. GitHub 422 "Position could not be resolved" — used diff-offset `position` field; should use `line` + `side: "RIGHT"`
  3. graphify_mcp.py called `graphify update` on every pipeline run (~180s stall); no caching
  4. Cache key was `head_sha` (PR tip) instead of `base_sha` (target branch) — invalidated on every PR push

**Notes:** The 0-findings bug was a cascading failure: empty `changed_symbols` → empty `context_files` → readers made 0 LLM calls → reviewer produced nothing. Fixed at the source (context.py). The graphify cache key fix was user-directed: user correctly identified that graphify indexes the base branch codebase, so the cache should be keyed on `base_sha`, not `head_sha`. Sentinel file approach (`graphify-out/.graph_sha`) survives across sessions.

---

### Session 5 — 2026-06-25

**Task:** AI usage log update only (`/ai-usage`).

**Tools called this session:**
- Read: 1, Skill: 1

**Files touched:**
| File | Action | Origin |
|---|---|---|
| ai_usage.md | updated | AI |

**Accepted / Rejected:**
- Accepted: 1
- Rejected: 0

**Bugs:**
- Introduced: 0
- Fixed: 0
