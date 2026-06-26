# Demo Script — 7 minutes

## Pre-flight checklist (do before going on stage)

- [ ] Backend running: `cd backend && .venv\Scripts\activate && uvicorn app.main:app --port 8001`
- [ ] Frontend running: `cd frontend && npm run dev` → `http://localhost:5173`
- [ ] `.env` at repo root populated with real Azure OpenAI credentials
- [ ] `cd backend && pytest` passes (confirms nothing is broken right before presenting)
- [ ] Have a real or fixture diff ready for the live-demo step (the
      `backend/tests/fixtures/sample_repo/` files work without any network
      dependency beyond Azure OpenAI)

## 0:00–1:00 — Problem and user

Open the dashboard (`http://localhost:5173`). Read the tagline. State the
problem in one breath: PR reviews are slow and miss cross-file blast
radius; this agent reads a PR the moment it opens and traces what it
actually touches before a human looks at it.

## 1:00–3:00 — Architecture

Walk the flow diagram in `ARCHITECTURE.md`: webhook → ingestion → diff
analysis → blast radius → context retrieval → synthesis → review → critic
→ publish. Point at the dashboard's phase timeline component on a real
past run to show the same 7 phases as live status, not just a diagram.
Name the one thing that makes this more than "call an LLM on a diff": the
blast-radius graph (who calls this, is it tested) computed before the LLM
ever sees the change.

## 3:00–5:00 — Live demo (the two Skills)

1. Trigger the **`local-pipeline-demo`** skill against the fixture diff -
   no live webhook, no tunnel, no network dependency beyond Azure OpenAI.
   Show findings printing in the terminal, then show the same run
   appearing in the dashboard.
2. Trigger the **`review-checklist`** skill against a small snippet live -
   show it walking all 7 categories (security, errors, performance,
   logging, tests, readability, breaking changes) explicitly, including
   saying "none found" for categories with nothing to flag.

## 5:00–6:00 — AI usage

Summarize `AI_USAGE.md`'s headline numbers: ~90% AI-written code under
continuous human direction, every architecture fork a human decision, the
`/code-review` pass that caught 10 real bugs (test suite went from 39 to
48 tests as a direct result) - own that the review-and-fix cycle is part
of how this was actually built, not a gap to hide.

## 6:00–7:00 — Limitations and next steps

Pick 2-3 from `LIMITATIONS.md` (language coverage, no retry/resumability,
no stable finding fingerprint across re-reviews) and the headline of
`DESIGN.md`'s 2-week plan (fingerprinting, more language grammars,
multi-repo dashboard). Close on: this reviews real PRs today, posts real
GitHub comments, and was validated against a live, previously-unseen repo
- not just a local demo.
