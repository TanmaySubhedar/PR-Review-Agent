# References

**This project was built from scratch. No starter template or boilerplate
repo was used.** The pipeline architecture, blast-radius engine, critic gate,
repo graph store, chatbot, and dashboard are all original code written for
this project.

## Dependencies (libraries, not templates)

Every dependency below is used unmodified as a library — "built" applies only
to this project's own code.

### Backend

| Name | Link | Used for | Status |
|---|---|---|---|
| FastAPI | https://fastapi.tiangolo.com/ | Backend web framework, webhook endpoint, REST API | dependency, unmodified |
| Uvicorn | https://www.uvicorn.org/ | ASGI server | dependency, unmodified |
| SQLModel | https://sqlmodel.tiangolo.com/ | ORM + persistence (`ReviewRun`, `Finding`, `PhaseLog`, `Repository`) | dependency, unmodified |
| Pydantic / pydantic-settings | https://docs.pydantic.dev/ | Data contracts between pipeline phases, `.env` config loading | dependency, unmodified |
| litellm | https://github.com/BerriAI/litellm | LLM abstraction layer — single `acompletion()` call works for Azure OpenAI and direct OpenAI; handles retry logic | dependency, unmodified |
| PyGithub | https://pygithub.readthedocs.io/ | GitHub REST API client (diffs, reviews, repo contents for chatbot) | dependency, unmodified |
| tree-sitter, tree-sitter-python, tree-sitter-javascript, tree-sitter-typescript | https://tree-sitter.github.io/tree-sitter/ | Source parsing for diff analysis and the blast-radius call graph | dependency, unmodified |
| networkx | https://networkx.org/ | The blast-radius call/import graph — build, traverse, serialize to node-link JSON | dependency, unmodified |
| httpx | https://www.python-httpx.org/ | HTTP client (transitive, used by litellm/PyGithub) | dependency, unmodified |
| pytest, pytest-asyncio | https://docs.pytest.org/ | Test suite | dependency, unmodified |

### Frontend

| Name | Link | Used for | Status |
|---|---|---|---|
| React | https://react.dev/ | Frontend dashboard | dependency, unmodified |
| Vite | https://vitejs.dev/ | Frontend build tool / dev server | dependency, unmodified |
| react-router-dom | https://reactrouter.com/ | Dashboard routing (list/detail/graph pages) | dependency, unmodified |
| @xyflow/react | https://reactflow.dev/ | Interactive graph visualization (React Flow nodes, edges, controls, minimap) | dependency, unmodified |
| @dagrejs/dagre | https://github.com/dagrejs/dagre | Automatic top-down graph layout (positions nodes before React Flow renders) | dependency, unmodified |

### Deployment

| Name | Link | Used for | Status |
|---|---|---|---|
| Docker / Docker Compose | https://docs.docker.com/ | Container build + orchestration | dependency, unmodified |
| nginx | https://nginx.org/ | Serve compiled React bundle; reverse proxy `/api/*` to backend with `proxy_read_timeout 120s` | dependency, unmodified |

## Conceptual inspirations (not code, not dependencies)

- **Graphify** ([safishamsi/graphify](https://github.com/safishamsi/graphify),
  [graphifylabs.ai](https://graphifylabs.ai/)) — a real open-source tool that
  builds a Tree-sitter + NetworkX codebase knowledge graph entirely locally,
  surfacing blast-radius-style queries (who calls this, what's the god-node).
  This project's blast-radius engine (`backend/app/pipeline/blast_radius/`)
  was inspired by that approach but is an independent implementation scoped
  specifically to this pipeline's caller/callee/test/doc queries — no code
  was copied or adapted from it.

## This project

| Name | Link | Status |
|---|---|---|
| Sentinel PR — PR Review Agent (this repo) | https://github.com/TanmaySubhedar/PR-Review-Agent | built |
