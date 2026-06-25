# Design Document — PR Review Agent

---

## 1. Problem

Pull request reviews are becoming a bottleneck. As a codebase grows, so does the volume of code being written — and human review time does not scale with it. A reviewer reading a diff sees only the lines that changed, rarely the full blast radius: which callers break, which tests no longer cover the changed code path, or whether the change violates a layering rule that isn't enforced anywhere in the toolchain. Reviews get shallower as PR volume increases, and they vary dramatically depending on who reviews and how much time they have.

The specific problem this agent addresses: **a diff without its call graph is an incomplete document.** A 5-line change to `validate_token()` may break 12 callers across 4 services — none of which appear in the diff. Reviewers who don't know the codebase deeply miss this. Even reviewers who do know it can miss it under time pressure.


---

## 2. User

A team lead or backend engineer who needs a thorough first-pass review on every PR. They work in a Python, JavaScript, or TypeScript codebase. They have access to Azure OpenAI or plain OpenAI. They are comfortable with a CLI tool.

The agent is not intended to replace human review. It is intended to do the mechanical depth-first work — trace call chains, check test coverage, flag architectural violations — so that the human reviewer can focus on intent and judgement.

---

## 3. Main Flow

Eight phases run as a LangGraph workflow. Each phase is a node that writes into a shared `PRReviewState` TypedDict and reads from whatever upstream nodes wrote.

```
ingest
  │  Fetch PR metadata + file diffs from GitHub API.
  │  Clone/fetch the repo locally. Build FileDiff objects.
  ▼
symbols
  │  Tree-sitter AST parse on changed files.
  │  Identify which named symbols (functions, classes, methods)
  │  overlap the changed line ranges. Score risk level (low/medium/high).
  ▼
graphify  [agentic]
  │  LLM agent loop queries the graphify call-graph index
  │  iteratively. Decides which symbols need deeper traversal
  │  based on risk level and what it finds. Produces BlastRadius.
  │  Falls back to NetworkX BFS if graphify binary is absent.
  ▼
context
  │  Selects candidate context files from the blast radius output.
  │  Scores and ranks by relationship type and call distance.
  ▼
readers  [agentic dispatch]
  │  LLM decides which context files are worth reading and
  │  assigns each a targeted focus question. Reads selected
  │  files concurrently. Produces FileSummary per file.
  ▼
synthesizer
  │  Deterministic assembly of RepositoryContext from file
  │  summaries: affected components, services, tests, risk areas.
  ▼
reviewer
  │  Single LLM call. Generates findings across 5 dimensions:
  │  correctness, architecture, testing, maintainability, intent.
  │  Full context: diff, symbols, blast radius, repository context.
  ▼
critic  [agentic refinement]
  │  Validates each finding: evidence grounded, actionable,
  │  respects repo context. Filters below confidence threshold.
  │  Borderline findings get one strengthening attempt before
  │  final pass/fail decision. Stores ValidatedFinding list.
  ▼
publish decision
   User confirms (y/N). Findings posted as inline GitHub review
   comments + summary body. Run stored in local SQLite DB.
```

---

## 4. Why This Architecture

**LangGraph workflow with deterministic and agentic nodes.** Each node has a single responsibility and writes named keys into `PRReviewState`. Deterministic nodes handle ingestion, symbol extraction, context synthesis, and publishing, while agentic nodes handle graph traversal, context selection, reader dispatch, reviewer generation, and critic refinement. This keeps the pipeline testable in isolation and makes the execution order explicit and auditable.

**LiteLLM for all LLM calls.** Provider lock-in is a real risk for a tool that different teams will deploy against different LLM backends (Azure OpenAI, plain OpenAI, proxies, local models). LiteLLM provides one calling interface across all of them. Switching providers is a one-line config change. It also handles retry logic and rate-limit backoff consistently.

**Tree-sitter for symbol extraction, not regex or manual parsing.** Regex-based diff parsing cannot reliably identify which function a changed line belongs to. Tree-sitter produces a full concrete syntax tree; finding which named symbol contains a given line range is a single tree walk. It works on partial files and diff hunks without a build system or language server.

**Graphify as subprocess, not a service.** Graphify is invoked as a subprocess (`graphify update`, `graphify affected`) scoped to one review run. This is zero-infrastructure — no Docker service, no port management, no health checks. The subprocess lifecycle is exactly one review run. Phase 2 can upgrade to an HTTP sidecar without changing any calling code.

**Graph-guided retrieval, not embedding similarity.** The retrieval signal for which context files to read is call-graph proximity, not embedding cosine distance. A function that calls `validate_token()` is relevant to a change in `validate_token()` because of the call relationship, not because its source text happens to be semantically similar. Graph proximity is a more precise retrieval signal for this task.

**SQLite in Phase 1.** Single-user, single-process, zero configuration. The SQLAlchemy ORM layer means the migration to PostgreSQL in Phase 2 is a one-line connection string change.

---

## 5. What's Agentic

Three nodes in the pipeline exhibit genuine agentic behaviour — they use tool-calling loops where the LLM decides what to do next based on what it finds, rather than following a fixed script.

**Graphify node — blast radius exploration loop**
The LLM agent is given the list of changed symbols and the risk level. It has three tools: `get_callers(symbol, depth)`, `get_callees(symbol, depth)`, and `get_related(symbol, depth)`. The agent decides which symbols warrant deeper traversal (depth 3 for auth/payment/security, depth 2 for most others) and when it has "seen enough" to produce an accurate blast radius. For a low-risk cosmetic change, it may make 3 tool calls. For a high-risk auth change, it may make 15. The previous implementation made the same fixed number of calls for every symbol unconditionally.

**Readers node — intelligent file dispatch**
Before reading any context files, an LLM dispatch agent sees the full ranked candidate list and the blast radius. It decides which files are actually worth reading (skipping generated files, pure config, vendored code) and assigns each selected file a targeted focus question ("Does this file guard against null token values before calling authenticate()?"). Readers then read only selected files with their focus question, not a generic "summarize this file" instruction. This reduces both token cost and noise in the file summaries.

**Critic node — borderline finding refinement**
After the first validation pass, findings that are close to the confidence threshold — actionable, context-respecting, but underpowered — are returned to the reviewer with the critic's specific suggestion for what evidence would raise confidence. The reviewer produces a strengthened version. The critic re-evaluates. This happens at most 3 times per run total. It rescues valid findings that were initially underspecified rather than silently discarding them.

The core agent loop (`run_agent_loop` in `_llm.py`) is a reusable function: it takes tool schemas, handlers, a system prompt, and an initial message. It drives the tool-calling cycle until `finish_reason=stop` or `max_steps` is reached, returning the final response and a full trace of every tool call made.

---

## 6. What's RAG

The pipeline implements **graph-guided retrieval-augmented generation** — not classical embedding-based RAG, but the same three-step pattern: retrieve → augment → generate.

**Retrieve:** The blast radius computation (graphify phase) identifies which files are structurally relevant to the changed symbols via call-graph traversal. The context phase scores and ranks these files. The readers dispatch agent further filters to the highest-signal subset.

**Augment:** The readers phase reads each selected file and produces a `FileSummary` (purpose, relevance, risks). The synthesizer assembles these into a `RepositoryContext` object: affected components, affected services, affected tests, architecture constraints, risk areas.

**Generate:** The reviewer LLM call receives the full augmented context — diff, changed symbols, blast radius, and `RepositoryContext` — and generates findings against it. The critic similarly receives the finding plus `RepositoryContext` to validate whether the finding is consistent with the repo's actual structure.

The deliberate departure from classical RAG: retrieval is driven by **call-graph proximity**, not embedding similarity. A file is retrieved because it calls or is called by a changed symbol, not because its text is semantically similar to the diff. For code review, structural relevance is more precise than semantic similarity.

---

## 7. What Can Go Wrong

**Hallucinated file/line references.** The reviewer LLM may cite a line number that does not exist or a file that was not in the diff. The critic's `evidence_grounded` check (finding.file must be in known files, evidence must not be empty) catches the most obvious cases, but does not verify that the specific line number is correct.

**Blast radius explosion.** On large, highly-connected codebases, the graphify agent may make many tool calls and return a very large blast radius. The context phase scores and caps the candidate list, but if the blast radius is large, the readers phase may still try to read more files than the LLM can usefully process.

**Structured output schema rejections.** Azure OpenAI's strict structured output mode rejects schemas with `additionalProperties` (no `dict` fields) and requires all properties in `required` (no fields with defaults). This was encountered in production during development. Any new Pydantic model used as `response_format` must conform to these constraints.

**Graphify binary absent.** If `graphify` is not on PATH, the phase falls back to a NetworkX BFS over the locally cloned repo. The fallback is accurate for direct callers/callees but does not have graphify's cross-file import resolution quality.

**LLM context window overflow.** Very large diffs with many changed symbols and many context files can push the reviewer prompt toward token limits. There is currently no chunking or truncation strategy for oversized diffs.

**litellm async cleanup warnings.** The `GracefulThreadedWorker.__del__` in litellm GC-s queued async logging coroutines when the event loop closes between pipeline phases. This is suppressed via `warnings.filterwarnings` and `litellm.suppress_debug_info = True` in `_llm.py` — it is harmless but would otherwise pollute CLI output.

---

## 8. How Hallucination Was Reduced

Several independent layers work together:

**Structured output with evidence requirements.** Every `Finding` requires `file`, `line`, `evidence`, and `dimension`. The reviewer cannot produce a vague impression — it must cite specific evidence. Pydantic validation rejects responses that omit required fields.

**Heuristic pre-filter before LLM validation.** Before the critic LLM call, a deterministic check verifies that `finding.file` is in the set of known files (changed files + context files) and that `evidence` is non-empty. Findings that fail this check are discarded without spending an LLM call on them.

**Explicitly skeptical critic prompt.** The critic system prompt instructs the model to "judge it skeptically, not rubber-stamp it." It defines `actionable` strictly: vague findings ("improve error handling") fail; specific ones ("catch the KeyError from payload['sub'] on line 12") pass. The prompt explicitly says "do not default to a high confidence number."

**Confidence threshold as a hard filter.** Findings below `critic_confidence_threshold` (default 0.7) are stored in the local database but never posted. The threshold is configurable — teams can raise it on a new codebase and lower it once they've calibrated.

**Focus questions in file reading.** File readers receive a specific question for each file rather than a generic summary request. This keeps the file summary tightly scoped and reduces the chance of the synthesizer assembling irrelevant context that the reviewer then misuses.

**Refinement loop with structured feedback.** Borderline findings are not silently discarded — they are returned to the reviewer with the critic's specific objection. The reviewer must produce a more precisely evidenced version. A finding that survives this refinement is structurally more grounded than one that passed on the first pass.

---

## 9. What Was Not Built

**Webhook-triggered automation.** Every review is manually initiated. There is no event receiver, no job queue, and no background worker. This was a deliberate Phase 1 decision: webhooks require a publicly reachable server, Redis, and process management — infrastructure not worth adding until the review quality was validated on real PRs.

**Semgrep / CodeQL integration.** Security analysis relies entirely on LLM reasoning. Deterministic rule-based scanning was deferred to Phase 2 because it adds a binary dependency and a SARIF parsing layer. LLM security findings are lower precision than Semgrep for well-known vulnerability patterns.

**Organisation-specific rules.** The reviewer uses a general-purpose prompt. It cannot enforce "controllers must not call repositories directly" unless that rule is in the prompt. A `.pr-agent-rules.yml` file fetched from the repo root and injected at review time would address this but was not built.

**Historical feedback loop.** Every review starts fresh. There is no memory of which past findings were accepted, ignored, or fixed. The agent will repeat findings the team has dismissed, and has no signal to improve over time.

**Embedding-based retrieval.** A vector store for code chunks was considered and rejected in favour of graph-guided retrieval. Call-graph proximity is a more precise signal for this specific task. Embedding similarity could be added as a supplementary retrieval path, but was not needed for the current quality bar.

**Web UI.** Run history and findings are CLI-only. No dashboard, no trend graphs, no per-file finding history. SQLite stores everything; `prv list`, `status`, and `logs` expose it through the terminal.

---

## 10. Two-Week Improvement Plan

Ordered by impact-to-effort ratio. Each item is independent unless noted.

**Week 1**

*Day 1–2: Test on a variety of repos*
Run the agent against multiple repositories with different sizes, languages, dependency patterns, and architectural styles. Use this to calibrate review quality, confidence thresholds, and false-positive rate before expanding automation.

*Day 3–4: Post-merge graph refresh*
Update graphify’s graph after merge so the call graph reflects the latest repository state and future reviews use fresh structural data.

*Day 5: Concurrent auto-review support*
Enable the system to handle multiple PR reviews in parallel, with triggers that can run periodically or instantly via webhooks.

**Week 2**

*Day 1–2: Organisation policy injection*
Add a `load_org_rules` step before the reviewer that fetches `.pr-agent-rules.yml` from the repo root and injects the rules into the reviewer system prompt. The rules file is optional; the pipeline degrades gracefully if absent.

*Day 3–4: Semgrep security reviewer*
Run `semgrep --config=auto` against the changed files as a subprocess. Parse the results into `SecurityFinding` objects and pass them through the same critic confidence pipeline. High-confidence security hits can bypass the LLM critic entirely.

*Day 5: Historical finding store and calibration*
Add a `past_findings` table to the database and retrieve similar past findings for the same files using simple overlap matching. Then run the agent against real PRs to tune `critic_confidence_threshold` and the borderline refinement loop.

---

## 11. Summary of Phase 2

Phase 2 should focus on quality, freshness, and scale. The highest priority is testing on a variety of repos, followed by keeping the graph current after merges and enabling concurrent auto-review across periodic or webhook-triggered runs. After that, repo-specific policy injection, deterministic security scanning, and historical feedback loops can improve precision and reduce repeated noise.

---
