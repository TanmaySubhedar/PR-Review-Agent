# AI Usage Log

Honest record of how AI was used to build this project, updated as work
progressed rather than reconstructed from nothing at the end.

## Tools used

- **Claude Code** (terminal agent) - the primary tool for the entire
  project: backend implementation, frontend implementation, debugging real
  infrastructure issues (GitHub PAT permissions, webhook delivery, an
  ngrok routing bug), the code-review pass, and all documentation in this
  repo including this file.

## Skills authored

- **`review-checklist`** (`.claude/skills/review-checklist/SKILL.md`) -
  applies this project's 7-category review standard (security, errors,
  performance, logging, tests, readability, breaking changes) to any diff
  on demand, mirroring the automated pipeline's own checks.
- **`local-pipeline-demo`** (`.claude/skills/local-pipeline-demo/SKILL.md`)
  - runs the full review pipeline against a local fixture diff with no
    live webhook/tunnel dependency, for development and live demos.

Both authored for this submission; both intended to be triggered live
during the demo (see `DEMO_SCRIPT.md`).

## Subagents / slash commands used

- **`/code-review` (high effort)** - run once against the full set of
  uncommitted pipeline changes. Spawned 8 parallel finder agents
  (correctness x3, reuse, simplification, efficiency, altitude) plus
  independent 1-vote verifier agents per candidate finding. Surfaced 16
  deduped candidates; 10 were kept after verification and all 10 were
  fixed in a follow-up pass (see "Bugs introduced/fixed" below).
- **Plan-mode subagent (`Plan` type)** - used twice: once to design the
  initial 8-milestone backend+frontend architecture before any code was
  written, and once to design this workshop-compliance retrofit plan.
  Both plans were reviewed and explicitly approved before execution.

## AI-generated vs. human-written

Nearly all literal code and documentation text was AI-generated (Claude
Code), but under continuous human direction:

- Every architectural fork was a human decision, not an AI default:
  Python vs. other backend, React+Vite frontend, GitHub webhook (not a
  CLI or polling) as the trigger, smee.io over ngrok after a real routing
  bug, local Docker over Azure for deployment, security/performance/logging
  as new dimensions rather than folding them into existing ones.
- Real infrastructure debugging (GitHub fine-grained PAT permission scopes,
  diagnosing why ngrok served a stale/wrong app, webhook-per-repo vs.
  token-per-repo confusion) was driven by the human reading actual API
  responses and logs and directing the next diagnostic step.
- The human reviewed and explicitly approved every plan before
  implementation (plan mode was used twice), and explicitly chose to run
  the `/code-review` pass and to fix all 10 findings it surfaced.

## Files accepted / rejected

- Several proposed actions were explicitly rejected and redirected by the
  human during the session: a broad process-kill attempt (denied, replaced
  with a narrower verified-PID approach), starting an ngrok tunnel
  autonomously (denied - exposing a local service is a user decision), and
  one mid-flight PR close/reopen action (interrupted and redirected to a
  manual step instead).
- No generated code files were rejected wholesale; corrections were at the
  level of "fix this specific bug" rather than "discard this file."

## Bugs introduced / fixed

The `/code-review` pass against the AI-written pipeline code found 10 real
bugs, all subsequently fixed in the same session:

- A symbol-name collision bug in the signature-change detector that could
  silently miss a real async/sync breaking change.
- A truthy-check bug (`if line` instead of `if line is not None`) that
  dropped line `0` from a posted summary.
- An async-detection false positive reachable via a decorator-line comment
  (fixed by switching from regex-over-text to reading Tree-sitter's actual
  parse-tree node).
- An unhandled validation error path, an unbounded re-review prompt-growth
  risk, a lossy risk-score bucketing round-trip, a duplicated hedge-word
  list across two files, a redundant Tree-sitter re-parse, and a missing
  `LIMIT 1` on a database query.

All 10 were fixed and covered by new regression tests in the same pass
(test suite grew from 39 to 48 passing tests as a direct result).

## Final estimate: AI vs. human

**Code/docs text: ~90% AI-written. Direction, review, and every
non-trivial decision: human.** The AI did the typing and the first draft
of every design choice presented as options; the human chose between
options, caught real infrastructure problems no amount of code review
would have found (a live ngrok routing bug, GitHub permission scoping),
and was the one who decided to spend a full review-and-fix cycle on code
quality before calling this submission done.
