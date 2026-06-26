# ai/memory/

Honestly: this project has no persistent agent-memory module. The only
cross-run state that exists is the previous-findings lookup in
[`backend/app/pipeline/runner.py`](../../backend/app/pipeline/runner.py)'s
`_fetch_previous_findings()` - a plain database query against the most
recent prior review run on the same PR, not a memory system in any
agentic sense (no embeddings, no semantic recall, no persistent identity
for a finding across runs beyond that single lookup).

This folder is kept (per the required project structure) rather than
populated with an invented memory layer that doesn't exist in the code.
See [LIMITATIONS.md](../../LIMITATIONS.md) for what a real memory/fingerprint
system for this project would need to look like.
