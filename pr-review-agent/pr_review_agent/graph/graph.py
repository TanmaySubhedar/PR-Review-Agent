"""Pipeline graph: sequential execution of all review nodes with phase callbacks."""

import uuid
from dataclasses import dataclass
from typing import Callable

from pr_review_agent.graph.nodes import (
    context,
    critic,
    graphify,
    ingest,
    readers,
    reviewer,
    symbols,
    synthesizer,
)
from pr_review_agent.graph.state import PRReviewState
from pr_review_agent.models.domain import Finding

PhaseCallback = Callable[[str, str], None]           # (phase_name, "running"|"done"|"failed")
PhaseDoneCallback = Callable[[str, PRReviewState], None]  # (phase_name, state_after)


@dataclass
class PipelineResult:
    state: PRReviewState
    review_run_id: str


def _noop(phase: str, status: str) -> None:
    return None


def _noop_done(phase: str, state: PRReviewState) -> None:
    return None


_PHASES = [
    ("ingest", ingest.run),
    ("symbols", symbols.run),
    ("graphify", graphify.run),
    ("context", context.run),
    ("readers", readers.run),
    ("synthesizer", synthesizer.run),
    ("reviewer", reviewer.run),
    ("critic", critic.run),
]


def run_pipeline(
    repo_full_name: str,
    pr_number: int,
    on_phase: PhaseCallback = _noop,
    on_phase_done: PhaseDoneCallback = _noop_done,
    previous_findings: list[Finding] | None = None,
) -> PipelineResult:
    run_id = str(uuid.uuid4())
    state: PRReviewState = {
        "repo_full_name": repo_full_name,
        "pr_number": pr_number,
        "review_run_id": run_id,
        "previous_findings": previous_findings,
        "phase_status": {},
        "error": None,
    }

    for phase_name, node_fn in _PHASES:
        on_phase(phase_name, "running")
        state = node_fn(state)
        on_phase(phase_name, "done")
        on_phase_done(phase_name, state)

    return PipelineResult(state=state, review_run_id=run_id)
