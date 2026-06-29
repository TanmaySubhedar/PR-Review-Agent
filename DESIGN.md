# Design

Ten required questions, answered honestly against the actual implementation.

## 1. What problem does this solve?

Human PR review is inconsistent and slow, and even careful reviewers rarely
trace the full blast radius of a change — who else calls this function,
does anything else rely on its old behavior, is it actually covered by a
test. A quick glance at a diff misses exactly the kind of cross-file
breakage that causes incidents. This project automates the first pass: it
reads a PR the moment it's opened, traces what the change actually touches
across the whole repository, and posts a grounded review before a human
even opens the diff. Beyond PR review, it also builds and persists a
call-graph diagram per registered repo and provides an LLM chatbot that
answers questions grounded in the actual source code.

## 2. Who is the user?

Engineering teams with a GitHub repo who want an automated, high-precision
first-pass review — not a noisy bot that comments on everything, but one
that's deliberately gated to only post findings it can back with concrete
evidence (see Q8). Also: developers who want to explore a codebase visually
(the graph view) or ask natural-language questions about specific files and
functions (the repo chatbot).

## 3. What is the main flow?

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full, exact trace. Summary:
a GitHub webhook fires on PR open/update → the backend fetches the diff and
shallow-clones the PR head → Tree-sitter-based diff analysis scores risk and
detects breaking signature changes → a blast-radius graph of the whole repo
is built to find callers/callees/tests/docs of the changed symbols →
relevant files are read in parallel by an LLM → that's synthesized into one
repository context object → a review agent produces findings grounded in the
diff + that context → a critic agent gates each finding (deterministically
and via a second LLM call) before anything is allowed to publish → surviving
findings are posted back to the PR as a GitHub review with a structured
"What changed" section (features introduced + per-file bullets) and an
"Issues found" section with severity icons.

Separately: users register repositories through the UI → the system clones
the repo, builds a full NetworkX call graph with Tree-sitter, compresses and
persists it → a React Flow visualization renders it interactively → clicking
any node pre-fills the repo chatbot → the chatbot runs a two-step LLM chain
(file picker, then answer grounded in real source fetched via GitHub API).

## 4. Why this architecture?

Four deliberate choices:

- **Phase separation.** Each of the 7 pipeline phases is a pure function
  with a typed input/output (`backend/app/schemas/`), independently
  unit-testable with mocked LLM calls. This is why the project has 48+
  passing tests covering real logic, not smoke tests.
- **Deterministic risk-scoring before any LLM call.** Risk level
  (`diff_analysis.py`) is computed from Tree-sitter facts (sensitive paths,
  signature changes, blast-radius fan-in, test coverage) — not asked of an
  LLM. This keeps the signal reproducible and gives every downstream LLM
  call grounded context instead of a raw diff to guess about.
- **Critic as a separate call from generation.** The agent that writes a
  finding never grades its own homework. A second, independent LLM call
  judges each finding's actionability and repo-context consistency, on top
  of a deterministic evidence-grounding gate that runs first and needs no
  LLM at all (see Q8).
- **Persistent graph store.** The per-repo call graph is built once on
  onboarding and stored compressed (gzip+base64) in SQLite, not rebuilt on
  every PR run. This lets the graph visualization and chatbot work instantly
  without re-parsing the repo each time.

## 5. What's agentic about it?

The PR pipeline autonomously: decides which files in the repo matter to this
specific change (blast-radius ranking, not a fixed list), retrieves and reads
them, synthesizes that into context, generates findings grounded in that
context, critiques and gates its own output, and acts on the result (posts
a real GitHub review) — all from one trigger event, with no per-step human
approval. The re-review feature gives it memory of what it said on a previous
push to the same PR (via stable per-finding fingerprints).

The repo chatbot is a separate two-step agentic flow: given a user question,
an LLM file-picker analyzes the graph index (file paths + all symbol names)
and selects up to 4 most-relevant files — using symbol names as the primary
signal so a file named `utils.py` containing `authenticate_user()` is
correctly identified as auth code. Those files are then fetched from GitHub
via the API, and a second LLM call answers the question grounded in the
real source. The chatbot runs both steps every time with no caching, so
answers always reflect the current code.

## 6. What's RAG (if anything)?

Honestly: none in the PR pipeline. Context selection (phase 3) is
deterministic graph traversal over a Tree-sitter-built call/import graph,
ranked by a fixed formula (call distance, test coverage, same-module), plus
targeted per-file LLM reads of whatever that traversal surfaces. There's no
embedding model, no vector store, no semantic similarity search anywhere in
the PR review pipeline. We considered it and chose graph traversal instead,
because "what's structurally connected to this changed function" is a
better-defined, more precise question than "what's semantically similar to
this diff" for this specific task.

The repo chatbot does something RAG-adjacent — it selects source files by
having an LLM read a structured index (filenames + all symbol names) and
pick relevant ones — but it uses LLM reasoning over structured metadata
rather than embedding similarity, and fetches the actual source files rather
than pre-chunked passages.

## 7. What can go wrong?

See [LIMITATIONS.md](LIMITATIONS.md) for the full list. Headline risks:
Tree-sitter only understands Python/JS/TS/TSX, so other languages get a
weaker, ungrounded review; blast-radius graph is rebuilt per PR run (cached
only for the graph view, not during review); the critic threshold is one
global cutoff, not tuned per dimension; the repo chatbot accuracy degrades
for very large repos because the graph index is capped; and there's no
dashboard authentication.

## 8. How was hallucination reduced?

Four concrete, real mechanisms in the code, not just a system-prompt request
to "be accurate":

1. **Deterministic evidence-grounding gate** (`critic_agent.py::_heuristic_evidence_check`)
   — discards any finding citing a file/line that doesn't actually appear in
   the diff or the read context, before any LLM judges it at all.
2. **Hedge-word severity cap** (`HEDGE_WORDS` regex,
   `critic_agent.py::_cap_severity_if_hedged`) — a `major`/`blocking`
   finding whose own text hedges ("may", "could", "might lead to") gets
   force-capped to `minor`, deterministically, independent of whether the
   LLM followed its own instruction not to do this.
3. **Concrete-trace prompt requirement** — the review agent's system prompt
   requires naming an exact access path before raising a concurrency/shared-
   state finding, and requires a reproducible input→code-path→failure for
   any `major`/`blocking` severity, not a risk category.
4. **Independent second critic call** — a finding's `actionable` and
   `respects_repo_context` judgment comes from a separate LLM invocation that
   never saw how the finding was generated, reducing the chance the same blind
   spot produces and approves the same hallucination.

For the repo chatbot: hallucination is reduced by fetching the actual source
file content via GitHub API and passing it verbatim to the answer LLM —
the model reads real code, not recalled paraphrases of it.

## 9. What wasn't built?

No RAG/vector retrieval (see Q6), no multi-repo or cross-PR awareness beyond
same-PR re-review, no per-dimension critic confidence thresholds, no
dashboard authentication (fine for demo/internal use; not production-ready),
no auto-fix capability (the agent reviews and comments; it never modifies
code or resolves merge conflicts — auto-applying a generated fix without a
human in the loop is a materially higher-risk feature class than reviewing),
no multi-tenant support, and no PM/Linear integration.

Private repo support is partial: the PR pipeline authenticates cloning via
`GITHUB_TOKEN`, and the chatbot fetches files via PyGithub with that same
token — but there's no UI for injecting credentials per-repo, so all repos
must be accessible with the single configured token.

## 10. Two-week improvement plan

**Week 1:** add more Tree-sitter grammars (Go, Java) to widen language
coverage; add per-dimension critic confidence thresholds (security findings
should have a different bar than maintainability ones) calibrated from the
eval dataset; add retry/idempotency at the phase level so a transient LLM
failure doesn't fail the entire run.

**Week 2:** a multi-repo dashboard view showing risk trends across all
registered repos; basic authentication on the dashboard before running this
against anything beyond a demo/internal repo; swap the PAT for GitHub App
installation auth (no personal token tied to one account); add the chatbot's
conversation history to the graph-index context so follow-up questions
maintain coherence across turns.
