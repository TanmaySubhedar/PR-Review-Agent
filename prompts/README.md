# prompts/

The system prompts that drive the two LLM-calling phases of the pipeline -
the review agent and the critic agent - live here as plain text, loaded by
the code at runtime rather than hardcoded as Python string literals:

- `review_agent_system.md` - phase 5 (review). Defines the 7 review
  dimensions, the evidence-discipline rules, and the re-review comparison
  instructions.
- `critic_agent_system.md` - phase 6 (critic). Defines the skepticism rules
  the critic LLM call applies before a finding is allowed to publish.

Loaded by `backend/app/pipeline/review_agent.py` and
`backend/app/pipeline/critic_agent.py` respectively.
