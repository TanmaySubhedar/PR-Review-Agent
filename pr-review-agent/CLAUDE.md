# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working directory

All commands below assume you are inside `pr-review-agent/` (the Python package root, not the repo root).

## Commands

```bash
# Install in editable mode with dev dependencies
pip install -e .[dev]

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_config.py -v

# Run a single test by name
pytest tests/test_db.py::test_finding_crud -v

# Run the CLI (after install)
prv --help
prv setup
prv review owner/repo 42

# Run as a module (without installing)
python -m pr_review_agent --help
```

## Architecture

The package is a Typer CLI that drives an 8-phase sequential pipeline. There is no web server or webhook handler — everything is initiated from `prv review`.

### Pipeline (`graph/`)

`graph/graph.py:run_pipeline()` is the single entry point. It iterates `_PHASES` — a list of `(phase_name, node_fn)` pairs — threading a `PRReviewState` TypedDict through each node:

```
ingest → symbols → graphify → context → readers → synthesizer → reviewer → critic
```

Each node lives in `graph/nodes/<name>.py` and exposes a single `run(state) -> PRReviewState` function that returns `{**state, <new_keys>}`. Nodes never mutate state in place.

`PRReviewState` is defined in `graph/state.py` as a `TypedDict(total=False)`. All keys are optional at the type level; nodes assume upstream keys are present.

### LLM calls (`_llm.py`)

All LLM calls go through `complete_structured(schema, system_prompt, user_prompt)`. It uses `chat.completions.parse()` with a Pydantic schema as `response_format`. The client is an `lru_cache` singleton — Azure OpenAI when `azure_openai_endpoint` is set, plain OpenAI otherwise. Never call the OpenAI SDK directly from nodes; always use `complete_structured`.

### Symbol extraction (`graph/nodes/symbols.py`)

Tree-sitter parses Python/JS/TS/TSX source files. There are two symbol representations:
- `_RawSymbol` — internal dataclass with `start_byte`/`end_byte` (needed for call-site matching within the same file)
- `Symbol` — public Pydantic domain model written to state; has no byte offsets

`extract_raw_symbols()` is used internally by the graphify node to build the call graph. `extract_symbols()` is the public wrapper that returns `list[Symbol]`.

### Blast radius (`graph/nodes/graphify.py`)

Builds a NetworkX `DiGraph` over all source files in the cloned repo. Node kinds: `"module"` (file) and `"symbol"` (function/class/method). Edge kinds: `"contains"`, `"calls"`, `"imports"`. BFS over this graph produces callers, callees, and related components for each changed symbol. `tools/graphify_mcp.py` is currently a stub (`is_available()` returns `False`).

### Configuration (`config.py`)

`settings` is a module-level singleton created at import time. Config priority: `~/.prv/config.toml` → `PR_AGENT_*` environment variables. `save_settings(dict)` merges values into the TOML file. Tests that need a clean config should `patch("pr_review_agent.config._CONFIG_FILE", ...)`.

### Persistence (`db.py`)

`engine` is a module-level SQLAlchemy engine pointing at `~/.prv/runs.db`. Tests that need an isolated DB should `patch("pr_review_agent.db.engine", create_engine("sqlite:///:memory:"))`. The three SQLModel tables — `RunRecord`, `FindingRecord`, `PhaseLog` — have explicit `__tablename__` values to avoid SQLModel auto-naming surprises with foreign keys.

`get_session()` returns a plain `Session` (not a context manager); callers are responsible for `.commit()` and `.close()` or use it as `with get_session() as s:`.

### Models (`models/`)

- `models/config.py` — `Settings` Pydantic model; fields map 1-to-1 with config.toml keys
- `models/domain.py` — all pipeline domain types (`PRMetadata`, `FileDiff`, `DiffHunk`, `Symbol`, `BlastRadius`, `FileSummary`, `Finding`, `ValidatedFinding`, etc.)
- `models/db.py` — SQLModel ORM tables (`RunRecord`, `FindingRecord`, `PhaseLog`)

Keep domain models and DB models in separate files — they serve different purposes.

### Prompts (`prompts/`)

Each LLM-backed node has a corresponding prompt module. The reviewer and critic prompts are the most complex. `reviewer.build_prompts()` accepts flat state keys (not a single object) and returns `(system_str, user_str)`. Do not inline prompt strings in nodes.

## Key conventions

- `asyncio.run()` is called at the top of each node's `run()` to drive async LLM calls. Do not make `run()` itself async — the pipeline loop in `graph.py` is synchronous.
- New fields added to `PRReviewState` must use `total=False` semantics (optional). Nodes read with `.get()` and write by spreading: `{**state, "new_key": value}`.
- The `tests/fixtures/` directory is excluded from pytest collection (`addopts = "--ignore=tests/fixtures"` in pyproject.toml).
- `test_smoke_imports.py` imports every module in the package — if a new module is added, add it to the `MODULES` list there.
