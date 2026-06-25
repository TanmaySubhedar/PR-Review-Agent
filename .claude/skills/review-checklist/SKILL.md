---
name: review-checklist
description: Use when the user asks to "review this PR", "run the review checklist", "check this diff", or wants a manual code review against this project's 7-category standard (security, errors, performance, logging, tests, readability, breaking changes) without waiting for the automated webhook pipeline. Applies the same checklist and evidence-discipline rules the backend's review_agent.py enforces server-side.
---

# Review Checklist

Apply this project's 7-category review checklist to a diff, file, or set of changes the user points at. This is the manual/ad-hoc counterpart to the automated checks in `backend/app/pipeline/review_agent.py` and `backend/app/pipeline/critic_agent.py` — same categories, same evidence bar, usable any time without a live webhook.

## The 7 categories

Walk every one explicitly, even to say "none found" — do not skip a category because nothing obvious jumped out.

- **security** — injection (SQL/command/template), hardcoded secrets or credentials, missing authn/authz checks on sensitive paths, unsafe deserialization, SSRF/path traversal from user-controlled input.
- **errors** (correctness) — logic errors, edge cases, null/undefined handling, exception handling, off-by-one, wrong comparisons.
- **performance** — N+1 queries or repeated I/O in a loop, unbounded result sets, blocking/sync calls inside async code paths, missing pagination/batching on new hot paths.
- **logging** — missing log statements on error/failure paths in changed code, secrets/PII written to logs, log levels that hide failures (e.g. errors logged at debug).
- **tests** — missing tests or incomplete coverage for the changed paths; if you can see the project's test suite, note whether an existing test already covers this or whether one should be added.
- **readability** (maintainability) — duplication, naming, complexity, dead code.
- **breaking changes** — signature changes (parameter count, async/sync flips), removed/renamed public symbols, changed return shapes that existing callers depend on.

## Evidence discipline (non-negotiable)

- Every finding must cite an exact file and line.
- The evidence must quote or precisely describe the actual code — never a vague claim.
- For security/performance findings specifically: name the exact user-controlled input or hot-path call, not just "this could be a security issue."
- Do not write a finding using hedge language ("may", "might", "could", "possibly", "potentially") as a substitute for identifying a real, traceable problem. If you can't describe a concrete input → code path → wrong behavior, downgrade the severity to `minor` or omit the finding.
- For concurrency/shared-state claims specifically: identify every function touching the shared state and state whether each one acquires the relevant lock/guard. Only raise a finding if you can name an access path that doesn't.

## Output format

One block per finding, in the same shape as `ReviewFinding` (`backend/app/schemas/review_finding.py`):

```
file: <path>
line: <line number>
dimension: <security|errors|performance|logging|tests|readability|breaking changes>
finding: <one sentence statement of the issue>
evidence: <the exact code/quote backing it>
severity: <info|minor|major|blocking>
```

`major`/`blocking` require the finding to describe a reproducible failure (specific input/scenario + what goes wrong), not just a risk category.

## When to use this vs. the automated pipeline

This skill is for: reviewing a diff *before* opening a PR, reviewing code that isn't going through GitHub at all, or demoing the checklist live without needing a webhook/network dependency. The automated pipeline (triggered by a real GitHub webhook) runs the equivalent logic server-side and additionally cross-references the blast-radius graph (callers/callees/test coverage) before publishing — this skill doesn't have that graph, so note explicitly when a finding would benefit from blast-radius context the skill doesn't have access to.
