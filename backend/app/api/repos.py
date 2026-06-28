import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.models.repository import Repository
from app.pipeline.blast_radius.graph_store import decompress_graph

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/repos", tags=["repos"])


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


# ── Endpoints ─────────────────────────────────────────────────────────────────

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
        import networkx as nx
        _base = graph  # capture the full DiGraph before reassigning the name
        graph = nx.subgraph_view(
            _base,
            filter_node=lambda n: _base.nodes[n].get("kind") == "module",
            filter_edge=lambda u, v: _base.edges[u, v].get("kind") == "imports",
        )

    nodes = [
        GraphNode(
            id=n,
            **{k: v for k, v in attrs.items() if k in _NODE_FIELDS},
        )
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
