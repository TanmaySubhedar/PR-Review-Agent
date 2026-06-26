# Known Limitations

Current limitations of the pr-review-agent as of v0.1. These are known gaps, not bugs.

---

## Triggering & Execution

**Manual initiation only**
Every review requires a developer to run `pr-agent review`. There is no webhook receiver or automatic triggering on PR open/push events.

**Synchronous, blocking execution**
The pipeline runs inline in the CLI process. For large PRs (many context files, slow LLM calls) the terminal blocks for the full duration — typically 60–120 seconds. There is no background execution or ability to start a review and check back later.

**No concurrent reviews**
Two team members cannot trigger reviews simultaneously. The second invocation will queue behind or contend with the first.

---

## Code Intelligence

**Graphify index not updated on merge**
The graphify index is rebuilt at review time if stale (time-based heuristic), but is not triggered when a PR actually merges. Over time, as PRs merge, the graph can drift from the current state of `main`. An event-driven rebuild on `pull_request.closed + merged` would keep it accurate.

**No type-level symbol context**
Tree-sitter identifies which symbols changed but does not resolve full type signatures, return types, or cross-file reference chains. The blast radius from graphify is accurate at the call-graph level, but the review agent lacks type-level detail about what changed in a function's contract (e.g. parameter types narrowed, return type widened). LSP integration (pyright) would address this.

---

## Review Quality

**No deterministic security scanning**
Security findings rely entirely on LLM reasoning. There is no rule-based scanning (e.g. Semgrep, CodeQL). Well-known vulnerability patterns that static analysis tools detect reliably may be missed or inconsistently surfaced.

**No organisation-specific rules**
The reviewer uses a general-purpose prompt. It has no knowledge of team conventions (e.g. "controllers must not call repositories directly", "all errors must raise AppException"). A `.pr-agent-rules.yml` file fetched from the repo root would allow teams to inject their own rules.

**No learning from past reviews**
Every review starts from zero. There is no memory of which past findings were accepted, ignored, or fixed. The agent will repeat findings the team has consciously dismissed, and has no signal to improve over time.

---

## Infrastructure

**No web UI**
Run history, findings over time, and per-PR details are only accessible via CLI commands (`pr-agent list`, `pr-agent status`, `pr-agent logs`) or by querying the SQLite database directly.

**SQLite limits concurrent writes**
SQLite is sufficient for single-user sequential use. If background workers or simultaneous review runs are introduced, SQLite's write-lock model becomes a bottleneck. A Postgres migration is a config-level change (only the connection string needs updating — the SQLAlchemy ORM layer is unchanged).
