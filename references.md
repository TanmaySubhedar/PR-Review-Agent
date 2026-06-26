# References

External codebases, tools, and resources referenced or integrated in this project.

---

## External Tools

### graphify
- **Repo:** https://github.com/safishamsi/graphify *(internal — update URL if public)*
- **What it does:** Builds a call-graph index from a source tree (`graphify update`) and answers affected-symbol queries (`graphify affected <symbol>`). The output is a JSON graph stored under `<repo>/graphify-out/graph.json`.
- **How it's used:** The `graphify` pipeline phase calls the binary as a subprocess via `pr_review_agent/tools/graphify_mcp.py`. An agentic LLM loop queries the index iteratively (`get_callers`, `get_callees`, `get_related`) to compute blast radius for changed symbols. When the binary is absent, the phase falls back to a NetworkX-based graph built from tree-sitter AST analysis.
- **Interface files:** `pr_review_agent/tools/graphify_mcp.py`, `pr_review_agent/graph/nodes/graphify.py`

---

## Key Libraries

These are pip dependencies that shape the architecture (beyond standard utility packages):

| Library | Purpose |
|---|---|
| [tree-sitter](https://tree-sitter.github.io/tree-sitter/) + language grammars | AST parsing for Python, JS, TS — used in the `symbols` node and the NetworkX blast-radius fallback |
| [networkx](https://networkx.org/) | Graph data structure and BFS traversal for the fallback blast-radius computation |
| [litellm](https://github.com/BerriAI/litellm) | Provider-agnostic LLM wrapper — routes calls to Azure OpenAI or plain OpenAI through a single interface |
| [SQLModel](https://sqlmodel.tiangolo.com/) | ORM layer for the local SQLite run history database |
| [PyGithub](https://github.com/PyGithub/PyGithub) | GitHub API client — PR metadata fetch and review comment posting |
