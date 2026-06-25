# Limitations

Honest, known gaps - not an exhaustive risk register, but everything here
is real and traceable to the code, not speculative.

## Language coverage

Tree-sitter-based diff analysis and the blast-radius engine only
understand **Python, JavaScript, TypeScript, and TSX**
(`backend/app/pipeline/treesitter_support.py`). A PR touching any other
language still gets reviewed (the review agent sees the raw diff text
regardless), but without symbol-level risk scoring, blast-radius context,
or signature-change detection - the review is meaningfully weaker for
those files.

## No retry or resumability

`runner.execute_review_run()` runs the entire 7-phase pipeline in one
straight-line pass per webhook event. Any exception anywhere - a flaky
Azure OpenAI call, a git clone failure, a transient GitHub API error -
fails the whole run (`ReviewRun.status = "failed"`). There's no
checkpointing and no automatic retry; a new push (a `synchronize` event)
is the only way to get another attempt.

## No stable identity for findings across re-reviews

The re-review comparison (`runner._fetch_previous_findings`) pulls the
most recent prior run's published findings as plain text and asks the LLM
to classify each as resolved/still-present/unrelated against the current
diff. There's no fingerprint or hash identifying "this is the same finding"
across runs - matching relies entirely on the LLM reading prose. Paraphrased
wording or line-number drift from an unrelated earlier hunk could break
the comparison. The list is capped at 15 findings (highest-confidence
first) to bound prompt growth, but isn't deduplicated against the new
run's findings beyond what the LLM does itself.

## Single repo/PR per webhook event

Each webhook event is processed independently; there's no cross-PR or
cross-repo awareness beyond the same-PR re-review lookup above. Two PRs on
the same repo touching the same function don't know about each other.

## One global critic confidence threshold

`CRITIC_CONFIDENCE_THRESHOLD` (default 0.7) gates every finding regardless
of dimension. The newly added `security`/`performance`/`logging`
dimensions inherit this untuned - there's no per-dimension calibration
based on how that dimension's findings actually perform in practice yet.

## Blast-radius graph is rebuilt from scratch every run

There's no caching of the parsed call graph across runs targeting the same
base commit. Fine at current scale (a single repo, periodic PRs); a real
cost on a large monorepo reviewed frequently. `BlastRadius.graph_truncated`
is set and surfaced in `risk_areas` when a configured file cap
(`BLAST_RADIUS_MAX_FILES`) kicks in, so the system at least flags when its
own analysis was partial - it doesn't make the analysis faster.

## Local development requires a webhook tunnel

GitHub can't reach `localhost`. Running this against a real PR locally
needs ngrok or smee.io relaying the webhook to your machine - a real setup
cost documented in `README.md`. (We hit a real ngrok routing bug doing
this - see `README.md`'s troubleshooting section - and switched to
smee.io, which is purpose-built for this and avoided the issue entirely.)

## No dashboard authentication

The React dashboard and the `/api/reviews/*` endpoints have no auth layer.
Fine for local/demo use; not production-ready as shipped.

## No RAG / vector retrieval

Context selection (phase 3) is deterministic graph traversal (the
blast-radius call graph) plus targeted per-file LLM reads, ranked by a
fixed scoring formula - not embedding-based retrieval over a vector store.
There is no RAG component in this project; see `DESIGN.md`'s answer to
"what's RAG" for why that's a deliberate choice, not an oversight.

## No auto-fix

The agent only reviews and comments - it never modifies code, never
commits a fix, and never resolves merge conflicts. See `DESIGN.md` for the
reasoning (auto-applying an LLM-generated fix without a human in the loop
is a meaningfully higher-risk feature class than reviewing).
