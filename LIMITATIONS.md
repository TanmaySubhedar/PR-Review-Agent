# Limitations

Honest, known gaps — not an exhaustive risk register, but everything here
is real and traceable to the code, not speculative.

## Language coverage

Tree-sitter-based diff analysis and the blast-radius engine only understand
**Python, JavaScript, TypeScript, and TSX**
(`backend/app/pipeline/treesitter_support.py`). A PR touching any other
language still gets reviewed (the review agent sees the raw diff text
regardless), but without symbol-level risk scoring, blast-radius context,
or signature-change detection — the review is meaningfully weaker for those
files. The repo graph visualization is also limited to the same four
languages.

## No retry or resumability

~~`runner.execute_review_run()` runs the entire 7-phase pipeline in one
straight-line pass per webhook event. Any exception anywhere — a flaky
Azure OpenAI call, a git clone failure, a transient GitHub API error —
fails the whole run. There's no checkpointing and no automatic retry.~~

**Resolved.** `complete_structured()` (the single LLM call site used by
every pipeline phase) now retries up to 3× on transient errors
(`RateLimitError`, `APIConnectionError`, `ServiceUnavailableError`,
`InternalServerError`, `BadGatewayError`) with 1.5 s exponential backoff
(waits: 1.5 s → 3 s → 6 s). Git clone and GitHub API failures still fail
the run — phase-level checkpointing remains a future improvement.

## No stable identity for findings across re-reviews

~~The re-review comparison pulls prior published findings as plain text and
asks the LLM to classify each as resolved/still-present/unrelated. There's
no fingerprint identifying "this is the same finding" across runs —
matching relied entirely on the LLM reading prose.~~

**Resolved.** Each `Finding` row now stores a `fingerprint`: the first 16
hex chars of `sha256(file | dimension | normalised_finding_text)`. Line
number is deliberately excluded so the fingerprint survives line drift.
On re-review, previous findings are labelled `[fp:xxxx]` in the prompt and
the LLM is required to return a structured `PreviousFindingStatus` verdict
(`resolved` / `still_present` / `unrelated`) per fingerprint — replacing
prose-matching with a verifiable, code-level ID.

## Single repo/PR per webhook event

Each webhook event is processed independently; there's no cross-PR or
cross-repo awareness beyond the same-PR re-review lookup above. Two PRs on
the same repo touching the same function don't know about each other.

## One global critic confidence threshold

`CRITIC_CONFIDENCE_THRESHOLD` (default 0.7) gates every finding regardless
of dimension. The `security`/`performance`/`logging` dimensions inherit this
untuned — there's no per-dimension calibration based on how that dimension's
findings actually perform in practice yet.

## Blast-radius graph rebuilt per PR run

The call graph used during PR review (`blast_radius/engine.py`) is rebuilt
from the cloned repo head on every run — it is not the same as the
persisted graph stored for the graph visualization. Fine at current scale;
a real cost on a large monorepo reviewed frequently. `BlastRadius.graph_truncated`
is set and surfaced in `risk_areas` when the configured file cap kicks in.

## Repo chatbot accuracy degrades on large repos

The two-step chatbot (file picker → answer) works well for repos up to a few
hundred files. For very large repos the graph index sent to the picker LLM
is capped (`_GRAPH_INDEX_CAP = 30_000 chars`), and the file content sent to
the answer LLM is capped per file (`_MAX_FILE_CHARS = 10_000`). Files beyond
these caps are either excluded from consideration or truncated, so answers
about code in those portions of the repo may be incomplete or miss the
relevant context. The chatbot always notes when a file "could not be
retrieved" but doesn't explain whether it was excluded by the cap vs. a
network error.

## Docker fresh volume requires repo re-registration

The SQLite database lives in a Docker named volume (`backend-data`). If the
volume is wiped (`docker compose down -v`), all registered repos, their
graphs, and all review history are deleted. Users must re-register repos
through the UI. The `full_name` must be in `owner/repo` format — the form
validates this, but repos registered before this validation was added may
have incorrect format stored and will fail chatbot file fetches.

## Local development requires a webhook tunnel

GitHub can't reach `localhost`. Running this against a real PR locally needs
smee.io relaying the webhook to your machine — a real setup cost documented
in `README.md`. (We hit a real ngrok routing bug during development and
switched to smee.io, which is purpose-built for this and avoided the issue.)

## No dashboard authentication

The React dashboard and the `/api/reviews/*` endpoints have no auth layer.
Fine for local/demo use; not production-ready as shipped.

## No RAG / vector retrieval

Context selection (phase 3) is deterministic graph traversal (the
blast-radius call graph) plus targeted per-file LLM reads, ranked by a
fixed scoring formula — not embedding-based retrieval over a vector store.
There is no RAG component in this project; see `DESIGN.md`'s answer to
"what's RAG" for why that's a deliberate choice, not an oversight.

## No auto-fix

The agent only reviews and comments — it never modifies code, never commits
a fix, and never resolves merge conflicts. See `DESIGN.md` for the reasoning
(auto-applying an LLM-generated fix without a human in the loop is a
meaningfully higher-risk feature class than reviewing).

## Single GITHUB_TOKEN for all repos

All repos registered in the system must be accessible with the single
`GITHUB_TOKEN` configured in `.env`. There's no per-repo credential
management, so private repos in different orgs or under different accounts
aren't supported without changing the token globally.
