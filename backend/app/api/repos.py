import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone
from time import monotonic
from typing import Optional

import networkx as nx
from fastapi import APIRouter, Depends, HTTPException, Request
from github import Auth, Github
from pydantic import BaseModel
from sqlmodel import Session, select

from app.config import settings
from app.db import get_session
from app.llm.azure_client import complete_structured
from app.models.repository import Repository
from app.pipeline.blast_radius.graph_store import decompress_graph

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/repos", tags=["repos"])

# ── Rate limiting ─────────────────────────────────────────────────────────────

_rate_store: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT = 10
_RATE_WINDOW = 60.0


def _check_rate_limit(ip: str) -> None:
    now = monotonic()
    cutoff = now - _RATE_WINDOW
    _rate_store[ip] = [t for t in _rate_store[ip] if t > cutoff]
    if len(_rate_store[ip]) >= _RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many requests — please wait.")
    _rate_store[ip].append(now)


# ── Request / response schemas ────────────────────────────────────────────────

class RepoRegisterRequest(BaseModel):
    full_name: str
    clone_url: str
    default_branch: str = "main"


class RepoResponse(BaseModel):
    id: str
    full_name: str
    clone_url: str
    default_branch: str
    onboarding_status: str
    onboarding_error: Optional[str]
    graph_node_count: Optional[int]
    graph_edge_count: Optional[int]
    graph_truncated: bool
    created_at: datetime
    updated_at: datetime


class GraphNode(BaseModel):
    id: str
    kind: str
    file: Optional[str] = None
    name: Optional[str] = None
    symbol_type: Optional[str] = None
    start_line: Optional[int] = None


class GraphLink(BaseModel):
    source: str
    target: str
    kind: str


class GraphResponse(BaseModel):
    repo_id: str
    full_name: str
    node_count: int
    edge_count: int
    truncated: bool
    nodes: list[GraphNode]
    links: list[GraphLink]


class RepoChatRequest(BaseModel):
    message: str


class RepoChatResponse(BaseModel):
    response: str


# ── LLM schemas for 2-step chat ───────────────────────────────────────────────

class _FilePicker(BaseModel):
    files: list[str]
    reasoning: str


class _RepoAnswer(BaseModel):
    answer: str


# ── Chat prompts ──────────────────────────────────────────────────────────────

_PICKER_SYSTEM = """You are analyzing a code repository structure to identify the most relevant source files for a user's question.

You receive:
- A file→symbol index: each line is "filepath: symbol1, symbol2, ..." listing functions/classes in that file
- Import relationships between files
- The user's question

Select up to 4 file paths most likely to contain code that answers the question.

Critical rule: use SYMBOL NAMES as the primary signal — not just filenames.
A file called utils.py with symbols like authenticate_user, validate_password, generate_jwt
is authentication code even though the name gives no hint. Pick it.

Also consider import relationships: if routes.py imports auth_utils.py and the question
is about login, both are relevant.

Return exact file paths as they appear in the index. Return an empty list if nothing is relevant."""

_ANSWER_SYSTEM = """You are a senior software engineer explaining a codebase to a colleague.

You have:
- The repository's file and symbol graph (structure overview)
- The actual source code of the most relevant files

Answer the user's question concretely. Reference specific functions, classes, and logic.
Trace the full feature flow when asked about a feature (e.g. "the login flow starts in
login_endpoint() in routes.py, which calls authenticate_user() in utils.py, which...").
Be honest if the fetched files don't fully answer the question — say which other files
might hold the missing piece.
Use markdown for clarity."""

_MAX_FILES_TO_FETCH = 4
_MAX_FILE_CHARS = 10_000   # per file — truncate to keep within token budget
_GRAPH_INDEX_CAP = 30_000
_IMPORT_CAP = 5_000


# ── Graph context builders ────────────────────────────────────────────────────

def _build_graph_index(graph: nx.DiGraph) -> str:
    """Compact file → symbols map. Each line: 'filepath: sym1, sym2, ...'"""
    symbols_by_file: dict[str, list[str]] = defaultdict(list)
    for _, d in graph.nodes(data=True):
        if d.get("kind") == "symbol":
            f = d.get("file", "")
            name = d.get("name", "")
            stype = d.get("symbol_type", "")
            if f and name:
                label = f"{stype} {name}".strip() if stype else name
                symbols_by_file[f].append(label)

    modules = sorted(n for n, d in graph.nodes(data=True) if d.get("kind") == "module")
    lines = []
    for m in modules:
        syms = symbols_by_file.get(m, [])
        sym_str = ", ".join(syms[:10])
        lines.append(f"{m}: {sym_str}" if sym_str else m)
    return "\n".join(lines)


def _build_import_summary(graph: nx.DiGraph) -> str:
    lines = [
        f"{u} → {v}"
        for u, v, d in graph.edges(data=True)
        if d.get("kind") == "imports"
    ]
    return "\n".join(lines[:100])


# ── GitHub file fetch (sync PyGithub wrapped in executor) ─────────────────────

async def _fetch_file(full_name: str, file_path: str, branch: str) -> str:
    def _sync() -> str:
        try:
            gh = Github(auth=Auth.Token(settings.github_token)) if settings.github_token else Github()
            content = gh.get_repo(full_name).get_contents(file_path, ref=branch)
            if hasattr(content, "decoded_content"):
                return content.decoded_content.decode("utf-8", errors="replace")
            return f"[binary file — cannot display: {file_path}]"
        except Exception as exc:
            return f"[could not fetch {file_path}: {exc}]"

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_response(repo: Repository) -> RepoResponse:
    return RepoResponse(
        id=repo.id,
        full_name=repo.full_name,
        clone_url=repo.clone_url,
        default_branch=repo.default_branch,
        onboarding_status=repo.onboarding_status,
        onboarding_error=repo.onboarding_error,
        graph_node_count=repo.graph_node_count,
        graph_edge_count=repo.graph_edge_count,
        graph_truncated=repo.graph_truncated,
        created_at=repo.created_at,
        updated_at=repo.updated_at,
    )


_NODE_FIELDS = {"kind", "file", "name", "symbol_type", "start_line"}


# ── CRUD endpoints ────────────────────────────────────────────────────────────

@router.post("", status_code=201, response_model=RepoResponse)
async def register_repo(
    body: RepoRegisterRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> RepoResponse:
    existing = session.exec(
        select(Repository).where(Repository.full_name == body.full_name)
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Repo '{body.full_name}' is already registered. Use POST /{existing.id}/refresh to rebuild the graph.",
        )
    repo = Repository(
        full_name=body.full_name,
        clone_url=body.clone_url,
        default_branch=body.default_branch,
    )
    session.add(repo)
    session.commit()
    session.refresh(repo)

    queue: asyncio.Queue = request.app.state.onboarding_queue
    await queue.put(repo.id)
    logger.info("registered repo %s, enqueued onboarding", repo.full_name)
    return _to_response(repo)


@router.get("", response_model=list[RepoResponse])
def list_repos(session: Session = Depends(get_session)) -> list[RepoResponse]:
    repos = session.exec(
        select(Repository).order_by(Repository.created_at.desc())
    ).all()
    return [_to_response(r) for r in repos]


@router.get("/{repo_id}", response_model=RepoResponse)
def get_repo(repo_id: str, session: Session = Depends(get_session)) -> RepoResponse:
    repo = session.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="repo not found")
    return _to_response(repo)


@router.delete("/{repo_id}", status_code=204)
def delete_repo(repo_id: str, session: Session = Depends(get_session)) -> None:
    repo = session.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="repo not found")
    session.delete(repo)
    session.commit()


@router.post("/{repo_id}/refresh", response_model=RepoResponse)
async def refresh_repo(
    repo_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> RepoResponse:
    repo = session.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="repo not found")
    if repo.onboarding_status in ("cloning", "building_graph"):
        raise HTTPException(status_code=409, detail="onboarding already in progress")
    repo.onboarding_status = "pending"
    repo.graph_json = None
    repo.onboarding_error = None
    repo.updated_at = datetime.now(timezone.utc)
    session.add(repo)
    session.commit()
    session.refresh(repo)

    queue: asyncio.Queue = request.app.state.onboarding_queue
    await queue.put(repo.id)
    logger.info("re-queued onboarding for %s", repo.full_name)
    return _to_response(repo)


@router.get("/{repo_id}/graph", response_model=GraphResponse)
def get_repo_graph(
    repo_id: str,
    module_only: bool = False,
    session: Session = Depends(get_session),
) -> GraphResponse:
    repo = session.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="repo not found")
    if repo.onboarding_status != "ready" or repo.graph_json is None:
        raise HTTPException(
            status_code=409,
            detail=f"Graph not available yet — onboarding_status='{repo.onboarding_status}'",
        )
    graph = decompress_graph(repo.graph_json)

    if module_only:
        _base = graph
        graph = nx.subgraph_view(
            _base,
            filter_node=lambda n: _base.nodes[n].get("kind") == "module",
            filter_edge=lambda u, v: _base.edges[u, v].get("kind") == "imports",
        )

    nodes = [
        GraphNode(id=n, **{k: v for k, v in attrs.items() if k in _NODE_FIELDS})
        for n, attrs in graph.nodes(data=True)
    ]
    links = [
        GraphLink(source=u, target=v, kind=d.get("kind", "unknown"))
        for u, v, d in graph.edges(data=True)
    ]
    return GraphResponse(
        repo_id=repo.id,
        full_name=repo.full_name,
        node_count=graph.number_of_nodes(),
        edge_count=graph.number_of_edges(),
        truncated=repo.graph_truncated,
        nodes=nodes,
        links=links,
    )


# ── Repo chat endpoint ────────────────────────────────────────────────────────

@router.post("/{repo_id}/chat", response_model=RepoChatResponse)
async def repo_chat(
    repo_id: str,
    body: RepoChatRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> RepoChatResponse:
    ip = request.client.host if request.client else "unknown"
    _check_rate_limit(ip)

    repo = session.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="repo not found")
    if repo.onboarding_status != "ready" or repo.graph_json is None:
        raise HTTPException(
            status_code=409,
            detail="Graph not ready — wait for onboarding to complete before using chat.",
        )

    graph = decompress_graph(repo.graph_json)
    graph_index = _build_graph_index(graph)
    import_summary = _build_import_summary(graph)

    # ── Step 1: LLM picks the most relevant files ─────────────────────────────
    picker_prompt = (
        f"Repository: {repo.full_name}\n"
        f"Default branch: {repo.default_branch}\n\n"
        f"## File → Symbol Index\n{graph_index[:_GRAPH_INDEX_CAP]}\n\n"
        f"## Import Relationships\n{import_summary[:_IMPORT_CAP]}\n\n"
        f"## User Question\n{body.message}"
    )
    picker = await complete_structured(
        _FilePicker, _PICKER_SYSTEM, picker_prompt, temperature=0.1, max_tokens=512,
    )
    logger.info(
        "repo chat [%s]: picker selected %d file(s) for %r: %s",
        repo.full_name, len(picker.files), body.message[:60], picker.files,
    )

    # ── Step 2: Fetch file contents from GitHub ───────────────────────────────
    fetch_tasks = [
        _fetch_file(repo.full_name, fp, repo.default_branch)
        for fp in picker.files[:_MAX_FILES_TO_FETCH]
    ]
    raw_contents = await asyncio.gather(*fetch_tasks)

    file_sections: list[str] = []
    for fp, content in zip(picker.files[:_MAX_FILES_TO_FETCH], raw_contents):
        truncated = content[:_MAX_FILE_CHARS]
        if len(content) > _MAX_FILE_CHARS:
            truncated += f"\n... [file truncated at {_MAX_FILE_CHARS} chars]"
        file_sections.append(f"### {fp}\n```\n{truncated}\n```")

    files_block = (
        "\n\n".join(file_sections)
        if file_sections
        else "(No specific files identified — answering from repository structure only.)"
    )

    # ── Step 3: LLM answers with actual code ──────────────────────────────────
    answer_prompt = (
        f"Repository: {repo.full_name}\n\n"
        f"## Repository Structure\n{graph_index[:20_000]}\n\n"
        f"## Source Files\n{files_block}\n\n"
        f"## User Question\n{body.message}"
    )
    result = await complete_structured(
        _RepoAnswer, _ANSWER_SYSTEM, answer_prompt, max_tokens=1500, temperature=0.2,
    )
    return RepoChatResponse(response=result.answer)
