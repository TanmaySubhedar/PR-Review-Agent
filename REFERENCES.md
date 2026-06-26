# References

**This project was built from scratch. No starter template or boilerplate
repo was used.** The pipeline architecture, blast-radius engine, critic
gate, and dashboard are all original code written for this project.

## Dependencies (libraries, not templates)

Every dependency below is used unmodified as a library - "built" applies
only to this project's own code.

| Name | Link | Used for | Status |
|---|---|---|---|
| FastAPI | https://fastapi.tiangolo.com/ | Backend web framework, webhook endpoint, REST API | dependency, unmodified |
| Uvicorn | https://www.uvicorn.org/ | ASGI server | dependency, unmodified |
| SQLModel | https://sqlmodel.tiangolo.com/ | ORM + persistence (`ReviewRun`, `Finding`, `PhaseLog`) | dependency, unmodified |
| Pydantic / pydantic-settings | https://docs.pydantic.dev/ | Data contracts between pipeline phases, `.env` config loading | dependency, unmodified |
| PyGithub | https://pygithub.readthedocs.io/ | GitHub REST API client (diffs, reviews, repo contents) | dependency, unmodified |
| openai (Azure client) | https://github.com/openai/openai-python | Azure OpenAI calls (review agent, critic, context readers) | dependency, unmodified |
| tree-sitter, tree-sitter-python, tree-sitter-javascript, tree-sitter-typescript | https://tree-sitter.github.io/tree-sitter/ | Source parsing for diff analysis and the blast-radius call graph | dependency, unmodified |
| networkx | https://networkx.org/ | The blast-radius call/import graph data structure and traversal | dependency, unmodified |
| httpx | https://www.python-httpx.org/ | HTTP client (transitive, used by openai/PyGithub) | dependency, unmodified |
| React | https://react.dev/ | Frontend dashboard | dependency, unmodified |
| Vite | https://vitejs.dev/ | Frontend build tool / dev server | dependency, unmodified |
| react-router-dom | https://reactrouter.com/ | Dashboard routing (list/detail pages) | dependency, unmodified |
| pytest, pytest-asyncio | https://docs.pytest.org/ | Test suite | dependency, unmodified |

## Conceptual inspirations (not code, not dependencies)

- **Graphify** ([safishamsi/graphify](https://github.com/safishamsi/graphify),
  [graphifylabs.ai](https://graphifylabs.ai/)) - a real open-source tool that
  builds a Tree-sitter + NetworkX codebase knowledge graph entirely locally,
  surfacing blast-radius-style queries (who calls this, what's the god-node).
  This project's blast-radius engine (`backend/app/pipeline/blast_radius/`)
  was inspired by that approach but is an independent implementation scoped
  specifically to this pipeline's caller/callee/test/doc queries - no code
  was copied or adapted from it.

## This project

| Name | Link | Status |
|---|---|---|
| PR Analyzer (this repo) | https://github.com/TanmaySubhedar/PR-Review-Agent | built |
