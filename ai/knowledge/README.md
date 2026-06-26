# ai/knowledge/

What an autonomous coding agent (or a new contributor) needs to know to
work in this repo productively. For the full picture, start with
[ARCHITECTURE.md](../../ARCHITECTURE.md) - this file is just the gotchas
that aren't obvious from reading the code top-to-bottom.

## Gotchas

- **`.env` lives at the repo root**, not in `backend/`. `backend/app/config.py`
  resolves it via `Path(__file__).resolve().parents[2]` - two directories
  above `app/config.py`. Putting `.env` inside `backend/` silently does
  nothing; settings fall back to defaults.
- **Editing `.env` does not take effect on a running process.** `Settings`
  is loaded once into a module-level singleton at import time. Changing
  `GITHUB_TOKEN` or any other value requires restarting `uvicorn`.
- **Webhooks are per-repo, not per-token.** Granting a PAT access to a new
  repo does *not* make GitHub send it webhook events - a webhook must be
  separately configured on that repo's Settings -> Webhooks page (or via
  the API, which needs the token's `Webhooks: Read and write` permission).
- **Tree-sitter coverage is Python/JS/TS/TSX only** (`app/pipeline/treesitter_support.py`).
  Other languages produce empty `changed_symbols`/blast-radius results - the
  review agent still runs on the raw diff, just without repository-context
  grounding.
- **GitHub's review `position` field is not the file's line number** - it's
  the 1-indexed offset within that file's unified-diff patch text. See
  `app/github/diff_positions.py` for the mapping, and don't try to anchor a
  comment on a line that isn't inside a diff hunk (it will be rejected
  inline - the critic gate downgrades these to summary-only automatically).
- **The blast-radius graph is rebuilt from scratch on every review run** -
  there's no caching of the parsed call graph across runs targeting the
  same base commit. Fine for the current scale; a real cost on large repos
  reviewed frequently (see `LIMITATIONS.md`).
