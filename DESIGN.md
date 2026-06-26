# Design

Ten required questions, answered honestly against the actual implementation.

## 1. What problem does this solve?

Human PR review is inconsistent and slow, and even careful reviewers rarely
trace the full blast radius of a change - who else calls this function,
does anything else rely on its old behavior, is it actually covered by a
test. A quick glance at a diff misses exactly the kind of cross-file
breakage that causes incidents. This project automates the first pass: it
reads a PR the moment it's opened, traces what the change actually
touches across the whole repository, and posts a grounded review before a
human even opens the diff.

## 2. Who is the user?

Engineering teams with a GitHub repo who want an automated, high-precision
first-pass review - not a noisy bot that comments on everything, but one
that's deliberately gated to only post findings it can back with concrete
evidence (see Q8).

## 3. What is the main flow?

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full, exact trace
(file-by-file, function-by-function). Summary: a GitHub webhook fires on
PR open/update → the backend fetches the diff and shallow-clones the PR
head → Tree-sitter-based diff analysis scores risk and detects breaking
signature changes → a blast-radius graph of the whole repo is built to
find callers/callees/tests/docs of the changed symbols → relevant files
are read in parallel by an LLM → that's synthesized into one repository
context object → a review agent produces findings grounded in the diff +
that context → a critic agent gates each finding (deterministically and
via a second LLM call) before anything is allowed to publish → surviving
findings are posted back to the PR as a GitHub review.

## 4. Why this architecture?

Three deliberate choices:

- **Phase separation.** Each of the 7 phases is a pure function with a
  typed input/output (`backend/app/schemas/`), independently unit-testable
  with mocked LLM calls. This is why the project has 48+ passing tests
  covering real logic, not just smoke tests.
- **Deterministic risk-scoring before any LLM call.** Risk level
  (`diff_analysis.py`) is computed from Tree-sitter facts (sensitive paths,
  signature changes, blast-radius fan-in, test coverage) - not asked of an
  LLM. This keeps the signal reproducible and gives every downstream LLM
  call grounded context instead of a raw diff to guess about.
- **Critic as a separate call from generation.** The agent that writes a
  finding never grades its own homework. A second, independent LLM call
  judges each finding's actionability and repo-context consistency, on top
  of a deterministic evidence-grounding gate that runs first and needs no
  LLM at all (see Q8).

## 5. What's agentic about it?

The system autonomously: decides which files in the repo matter to this
specific change (blast-radius ranking, not a fixed list), retrieves and
reads them, synthesizes that into context, generates findings grounded in
that context, critiques and gates its own output, and acts on the result
(posts a real GitHub review) - all from one trigger event, with no
per-step human approval. The re-review feature additionally gives it
memory of what it said on a previous push to the same PR.

## 6. What's RAG (if anything)?

Honestly: none. Context selection (phase 3) is deterministic graph
traversal over a Tree-sitter-built call/import graph, ranked by a fixed
formula (call distance, test coverage, same-module), plus targeted
per-file LLM reads of whatever that traversal surfaces. There's no
embedding model, no vector store, no semantic similarity search anywhere
in this pipeline. We considered it and chose graph traversal instead,
because "what's structurally connected to this changed function" is a
better-defined, more precise question than "what's semantically similar
to this diff" for this specific task.

## 7. What can go wrong?

See [LIMITATIONS.md](LIMITATIONS.md) for the full list. Headline risks:
Tree-sitter only understands Python/JS/TS/TSX, so other languages get a
weaker, ungrounded review; there's no retry/resumability, so a transient
failure (a flaky LLM call, a clone error) fails the whole run; the critic
threshold is one global cutoff, not tuned per dimension; and re-review
comparison across pushes relies on an LLM reading prose with no stable
finding identity.

## 8. How was hallucination reduced?

Four concrete, real mechanisms in the code, not just a system-prompt
request to "be accurate":

1. **Deterministic evidence-grounding gate** (`critic_agent.py::_heuristic_evidence_check`)
   - discards any finding citing a file/line that doesn't actually appear
   in the diff or the read context, before any LLM judges it at all.
2. **Hedge-word severity cap** (`HEDGE_WORDS` regex,
   `critic_agent.py::_cap_severity_if_hedged`) - a `major`/`blocking`
   finding whose own text hedges ("may", "could", "might lead to") gets
   force-capped to `minor`, deterministically, independent of whether the
   LLM followed its own instruction not to do this.
3. **Concrete-trace prompt requirement** - the review agent's system
   prompt requires naming an exact access path before raising a
   concurrency/shared-state finding, and requires a reproducible
   input→code-path→failure for any `major`/`blocking` severity, not a risk
   category.
4. **Independent second critic call** - a finding's `actionable` and
   `respects_repo_context` judgment comes from a separate LLM invocation
   that never saw how the finding was generated, reducing the chance the
   same blind spot produces and approves the same hallucination.

## 9. What wasn't built?

No RAG/vector retrieval (see Q6), no multi-repo or multi-tenant support, no
retry/checkpointing across pipeline failures, no stable fingerprinting of
findings across re-review runs, no PM/Linear integration, no dashboard
authentication, and - deliberately - no auto-fix capability (the agent
reviews and comments; it never modifies code or resolves merge conflicts,
since auto-applying a generated fix without a human in the loop is a
materially higher-risk feature than reviewing).

## 10. Two-week improvement plan

**Week 1:** add more Tree-sitter grammars (Go, Java) to widen language
coverage; add a stable per-finding fingerprint (hash of file + dimension +
normalized symbol) so re-review comparison stops relying purely on LLM
prose-matching; add retry/idempotency to the runner so a transient failure
doesn't fail the whole run.

**Week 2:** a multi-repo dashboard view; per-dimension critic confidence
thresholds instead of one global cutoff; swap the PAT for GitHub App
installation auth (no personal token tied to one account); basic
authentication on the dashboard before this could run against anything
beyond a demo/internal repo.
