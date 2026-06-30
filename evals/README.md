# evals/

This project's evaluation harness is the backend test suite, not a
separate framework - the mocked-LLM end-to-end test functionally *is* an
eval:

- [`backend/tests/test_pipeline_e2e.py`](../backend/tests/test_pipeline_e2e.py)
  - runs the full 7-phase pipeline against the fixture repo with mocked LLM
    responses and a fake GitHub client, asserting that a grounded finding
    publishes inline while a hallucinated one is caught and discarded by
    the critic gate. This is the project's core correctness eval.
- [`backend/tests/test_review_agent.py`](../backend/tests/test_review_agent.py)
  - asserts the review prompt's structure and re-review behavior.
- [`backend/tests/test_critic_agent.py`](../backend/tests/test_critic_agent.py)
  - asserts the critic's deterministic gates (evidence-grounding, hedge-word
    severity capping) independent of the LLM call.

Run them all with `cd backend && pytest`.
