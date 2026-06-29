# AI Usage Log

Honest record of how AI was used to build this project, updated as work
progressed rather than reconstructed from nothing at the end.

## Tools used

- **Claude Code** (terminal + VS Code extension agent) — the primary tool
  for the entire project: backend implementation, frontend implementation,
  debugging real infrastructure issues (GitHub PAT permissions, webhook
  delivery, Docker nginx timeout, wrong `full_name` format in DB), the
  code-review pass, and all documentation in this repo including this file.

## Skills authored

Three custom Skills, all committed and demoed live:

- **`review-checklist`** (`.claude/skills/review-checklist/SKILL.md`) —
  applies this project's 7-category review standard (security, errors,
  performance, logging, tests, readability, breaking changes) to any diff
  on demand, mirroring the automated pipeline's own checks. Same evidence
  discipline rules — findings without a concrete trace don't pass.

- **`local-pipeline-demo`** (`.claude/skills/local-pipeline-demo/SKILL.md`)
  — runs the full 7-phase review pipeline against a local fixture diff with
  no live webhook/tunnel/network dependency beyond Azure OpenAI. Used for
  development and live demos when a real PR isn't available.

- **`onboard`** (`.claude/skills/onboard/SKILL.md`) — guided 8-step setup
  walk: prerequisites check, GitHub PAT creation, smee.io channel, webhook
  registration, `.env` validation (never displays secret values), Docker
  stack launch with health check, smee relay start, and first repository
  registration. Includes OS detection (Windows/macOS/Linux) and per-step
  recovery instructions for every known failure mode. Backed by four Python
  check scripts (`check_prereqs.py`, `check_env.py`, `check_stack.py`,
  `generate_secret.py`).

## Subagents / slash commands used

- **`/code-review` (high effort)** — run once against the full set of
  uncommitted pipeline changes. Spawned 8 parallel finder agents
  (correctness ×3, reuse, simplification, efficiency, altitude) plus
  independent 1-vote verifier agents per candidate finding. Surfaced 16
  deduped candidates; 10 were kept after verification and all 10 were fixed
  in a follow-up pass (see "Bugs introduced/fixed" below).
- **Plan-mode subagent (`Plan` type)** — used twice: once to design the
  initial 8-milestone backend+frontend architecture before any code was
  written, and once to design the multi-repo onboarding + sequential queue
  feature plan. Both plans were reviewed and explicitly approved before
  execution.

## AI-generated vs. human-written

Nearly all literal code and documentation text was AI-generated (Claude Code),
but under continuous human direction:

- Every architectural fork was a human decision, not an AI default:
  Python vs. other backend, React+Vite frontend, GitHub webhook (not a CLI
  or polling) as the trigger, smee.io over ngrok after a real routing bug,
  local Docker over Azure for deployment, Tree-sitter + NetworkX for the
  call graph, `asyncio.Queue` for the sequential PR review queue, litellm
  as the LLM abstraction layer (replacing a direct Azure client).
- Real infrastructure debugging (GitHub fine-grained PAT permission scopes,
  diagnosing why ngrok served a stale/wrong app, wrong `full_name` format
  stored in DB causing PyGithub `NotFound`, nginx default 60 s timeout
  cutting off two-LLM-call chains) was driven by the human reading actual
  API responses and logs and directing the next diagnostic step.
- The human reviewed and explicitly approved every plan before implementation
  (plan mode used twice), explicitly chose to run the `/code-review` pass and
  fix all 10 findings, and directed the graph visualization, chatbot, and
  review comment format improvements.

## Files accepted / rejected

- Several proposed actions were explicitly rejected and redirected: a broad
  process-kill attempt (denied, replaced with a narrower verified-PID
  approach), starting an ngrok tunnel autonomously (denied — exposing a local
  service is a user decision), a mid-flight PR close/reopen action
  (interrupted and redirected to a manual step).
- No generated code files were rejected wholesale; corrections were at the
  level of "fix this specific bug" or "this section is wrong, redo it."

## Bugs introduced / fixed

**From the `/code-review` pass** (10 real bugs, all fixed):
- A symbol-name collision bug in the signature-change detector that could
  silently miss a real async/sync breaking change.
- A truthy-check bug (`if line` instead of `if line is not None`) that
  dropped line 0 from a posted summary.
- An async-detection false positive reachable via a decorator-line comment
  (fixed by switching from regex-over-text to Tree-sitter's parse-tree node).
- An unhandled validation error path, an unbounded re-review prompt-growth
  risk, a lossy risk-score bucketing round-trip, a duplicated hedge-word list
  across two files, a redundant Tree-sitter re-parse, a missing `LIMIT 1` on
  a DB query, and a missing fingerprint uniqueness check.

Test suite grew from 39 to 48 passing tests as a direct result.

**From subsequent development (found during integration testing):**
- `full_name` register form accepted bare `TanmaySubhedar` (without repo
  name), causing PyGithub `NotFound` on every file fetch — fixed by adding
  `owner/repo` regex validation on the frontend form.
- React Flow custom node type declared but not passed as `nodeTypes` prop —
  TypeScript caught it via `tsc --noEmit`; fixed by passing `nodeTypes={NODE_TYPES}`.
- Module graph nodes showed full path as label when `file` attribute is null
  — fixed by splitting `n.id` (which IS the file path for module nodes).
- `change_summary` LLM output was a vague single sentence — fixed by
  rewriting the prompt to require a features-introduced block + per-file
  bullet list, and passing `max_tokens=6000` to give it room to produce it.
- nginx 60 s default read timeout was cutting off two sequential LLM calls
  (total 30–60 s) — fixed by adding `proxy_read_timeout 120s`.

## Final estimate: AI vs. human

**Code/docs text: ~90% AI-written. Direction, review, and every non-trivial
decision: human.** The AI did the typing and the first draft of every design
choice presented as options; the human chose between options, caught real
infrastructure problems no amount of code review would have found (a live
ngrok routing bug, GitHub permission scoping, Docker volume + DB state
interaction), and was the one who decided to spend a full review-and-fix
cycle on code quality before calling this done.
