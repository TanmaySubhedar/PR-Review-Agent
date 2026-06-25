# data/

This project's sample data lives alongside the tests that exercise it,
rather than being duplicated here (moving it would break the test suite's
import paths):

- [`backend/tests/fixtures/sample_repo/`](../backend/tests/fixtures/sample_repo/)
  - a small real repo (Python files with genuine call relationships across
    `auth/`, `admin/`, `tests/`, `docs/`) used to validate the blast-radius
    engine end to end.
- [`backend/tests/fixtures/sample_webhook_payload.json`](../backend/tests/fixtures/sample_webhook_payload.json)
  - a realistic `pull_request.opened` GitHub webhook payload, used to test
    signature verification and ingestion without a live webhook.

Both are referenced directly by `backend/tests/test_blast_radius.py`,
`test_diff_analysis.py`, and `test_pipeline_e2e.py`.
