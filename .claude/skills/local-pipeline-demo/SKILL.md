---
name: local-pipeline-demo
description: Use when the user asks to "run the pipeline locally", "demo the review pipeline without a webhook", "trigger a local diff review", or wants to exercise the full PR-review pipeline (backend/app/pipeline/orchestrator.py's run_review_pipeline) against a sample diff without a live GitHub webhook, network tunnel, or real PR. Useful for development, debugging, and live demos where webhook/network dependency would be risky.
---

# Local Pipeline Demo

`run_review_pipeline()` in `backend/app/pipeline/orchestrator.py` is already fully decoupled from GitHub webhooks — it takes a `list[FileDiff]`, a `workspace_root: Path`, and a `github_client`. This skill drives it directly, the same way `backend/tests/test_pipeline_e2e.py` does, so the entire pipeline (diff analysis → blast radius → context retrieval → synthesis → review → critic → publish) can be exercised with no live webhook, no ngrok/smee tunnel, and no real GitHub PR.

## Steps

1. Confirm the backend venv is set up and real Azure OpenAI credentials are in `.env` at the repo root — this is **not** mocked like the test suite; it makes real LLM calls.
2. Use `backend/tests/fixtures/sample_repo/` as the workspace (or point at any other local repo checkout) and either reuse the inline `PATCH`/`FileDiff` fixtures from `backend/tests/test_pipeline_e2e.py` or construct a new `FileDiff` for whatever diff is being demoed.
3. Write a small throwaway async script (or run inline via `python -c`) that:
   - Builds a minimal `PREvent` (see `backend/app/schemas/pr_event.py` for required fields - title/description/repo_full_name/pr_number/clone_url/etc, dummy values are fine for a local run).
   - Builds one or more `FileDiff` objects (`backend/app/pipeline/diff_analysis.py`) with the patch text and old/new source bytes for the change being demoed.
   - Uses a `FakeGitHubClient` with a no-op `create_review()` (same shape as the one in `test_pipeline_e2e.py`) if you don't want to actually post to GitHub, or a real `PATGitHubClient` if you do.
   - Calls `await run_review_pipeline(review_run_id, pr_event, file_diffs, workspace_root, github_client)`.
   - Prints `result.diff_analysis.risk_level`, `result.findings`, and `result.scored_findings`.
4. Run it from the `backend/` directory with the venv activated: `python <script>.py`.
5. Optionally, to show it in the dashboard too: have the backend (`uvicorn app.main:app --port 8001`) and frontend (`npm run dev`) running, and either call the same code path through a manually-POSTed webhook payload (see `README.md`'s testing section) or extend the script to also write a `ReviewRun`/`Finding` row via the models in `backend/app/models/` so it shows up at `http://localhost:5173`.

## Why this exists

The demo format requires "triggering a custom Skill on stage." A live webhook depends on GitHub, a tunnel (ngrok/smee.io), and network availability — all real failure points mid-demo. This skill gives a one-command, deterministic way to show the exact same pipeline code path succeeding, independent of any of that.
