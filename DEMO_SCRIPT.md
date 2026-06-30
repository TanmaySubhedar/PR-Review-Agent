# Demo Script — 7 minutes

## Pre-flight checklist (do before going on stage)

- [ ] Docker stack running: `docker compose -f deployment/docker-compose.yml up -d`
- [ ] Dashboard open: `http://localhost:5173`
- [ ] At least one repo registered and `onboarding_status: ready` at `http://localhost:5173/repos`
- [ ] smee client running: `npx smee-client --url https://smee.io/<channel> --target http://localhost:8001/webhooks/github`
- [ ] Have a real or fixture diff ready for the checklist skill demo
- [ ] GitHub webhook configured and showing green deliveries
- [ ] `cd backend && pytest` passes — confirms nothing is broken right before presenting

---

## 0:00–1:00 — Problem and user

Open the dashboard (`http://localhost:5173`). State the problem in one breath:

> PR reviews are slow and miss cross-file blast radius. A developer merges a
> change to a core function — 9 other components call it, none of the callers
> are updated, and two are missing test coverage. A human reviewer who only
> looks at the diff misses all of that. This agent reads a PR the moment it
> opens, traces the full call graph before the LLM ever sees the code, and
> posts a grounded review — not a noisy bot that flags everything, but one
> that only posts what it can back with concrete evidence.

---

## 1:00–3:00 — Architecture + agent/RAG flow

Walk through the two main flows:

**PR Review pipeline** (7 phases):
1. Webhook arrives → ingestion (diff + commits fetched from GitHub)
2. Diff analysis — Tree-sitter parses old/new source, detects signature
   changes, scores risk deterministically (no LLM yet)
3. Blast radius — builds a full call graph of the cloned repo, finds all
   callers/callees/tests for changed symbols
4. Context retrieval — reads the top N blast-radius files in parallel (one
   LLM call per file)
5. Synthesis — pure aggregation: affected components, risk areas
6. Review agent — one LLM call with diff + graph context → findings across
   7 categories (security, errors, performance, logging, tests, readability,
   breaking changes) + "What changed" summary + suggested PR description
7. Critic — deterministic gate first (no LLM), then one LLM call per finding
   judging actionability and repo-context consistency — survivors post to GitHub

Point at the phase timeline on a real past run in the dashboard to show the
7 phases as live status, not just a diagram.

**Repo chatbot** (separate two-step flow):
- Repo is registered → cloned → Tree-sitter builds call graph → persisted
  as gzip+base64 in SQLite
- User opens graph at `/repos/{id}/graph` — React Flow renders it with dagre
  layout, custom hover tooltips showing full paths
- User clicks a node → question pre-fills the chatbot
- Chatbot: LLM 1 reads graph index (file names + all symbol names) and picks
  up to 4 relevant files; actual source is fetched from GitHub API; LLM 2
  answers grounded in the real code

Name the key design point: **deterministic risk-scoring before any LLM call**
— the graph traversal and Tree-sitter analysis happen first, so the LLM gets
grounded context, not a raw diff to guess about.

---

## 3:00–5:00 — Live demo

**1. Repo graph + chatbot** (~1 min):
- Navigate to `http://localhost:5173/repos` → click **View Graph** on a ready repo
- Show the React Flow graph rendering — nodes are files and symbols, edges are
  imports and calls; hover over a node to see the full path tooltip
- Click a node (e.g. a core module) — the chatbot opens pre-filled
- Ask the question live: show the two-step LLM chain completing and returning
  an answer grounded in the real source code

**2. `review-checklist` skill** (~1 min):
- In Claude Code, type `/review-checklist` and point it at a small diff or snippet
- Show it walking all 7 categories explicitly — security, errors, performance,
  logging, tests, readability, breaking changes — including saying "none found"
  for categories with nothing to flag
- Emphasize: same evidence discipline as the automated pipeline — no finding
  without a concrete file + line + quoted code

**3. Live PR review result** (~1 min):
- Show a recent review posted to GitHub
- Point out the **"What changed"** section: opening sentence naming the features
  introduced, then a per-file bullet list
- Point out the **"Issues found"** section with severity icons (🔴🟠🟡⚪) — bugs
  visible at a glance without hunting inline comments
- Expand the **Blast-radius warnings** section (collapsed by default)
- Click through to an inline comment on a specific line

---

## 5:00–6:00 — AI usage

Summarize `AI_USAGE.md`'s headline numbers:

- ~90% AI-written code under continuous human direction
- Every architecture fork a human decision: smee.io over ngrok after a real
  routing bug, litellm over direct Azure client for provider flexibility,
  `asyncio.Queue` for sequential review ordering
- Three custom Skills authored: `review-checklist`, `local-pipeline-demo`,
  `onboard` (live guided setup walk for new users)
- `/code-review` pass caught 10 real bugs — test suite grew from 39 to 48
  tests as a direct result
- Real infrastructure bugs found and fixed: nginx timeout, wrong `full_name`
  format in DB, React Flow `nodeTypes` prop missing

Own that the review-and-fix cycle is part of how this was actually built, not
a gap to hide.

---

## 6:00–7:00 — Limitations and next steps

Pick 2-3 from `LIMITATIONS.md`:

- **Language coverage** — Tree-sitter understands Python/JS/TS/TSX; other
  languages still get reviewed from the raw diff, just without call-graph context
- **One global critic threshold** — no per-dimension calibration yet; security
  findings get the same confidence bar as maintainability findings
- **Chatbot degrades on very large repos** — graph index is capped, so the
  file picker may miss relevant code in large monorepos

Two-week plan (`DESIGN.md`): per-dimension thresholds, more language grammars
(Go, Java), basic dashboard auth before running against a real org's repos.

Close on: this reviews real PRs today, posts real GitHub comments, was
validated against a live previously-unseen repo — not just a local demo.
