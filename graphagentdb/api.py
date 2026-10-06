"""FastAPI app exposing ingestion, hybrid search, the graph view and project bootstrap.

The web UI in `static/` is served from `/`.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from . import __version__
from .config import Settings, get_settings
from .consultant import bootstrap
from .ingestion import ingest
from .models import NodeStatus, RelationType
from .search import HybridSearchEngine
from .store import KnowledgeStore

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

DEPRECATED_NODE_STYLE = {
    "color": {
        "background": "#2d3748",
        "border": "#4a5568",
        "highlight": {"background": "#4a5568", "border": "#718096"},
    },
    "font": {"color": "#718096"},
    "borderWidth": 2,
    "borderWidthSelected": 3,
    "opacity": 0.5,
}
SUPERSEDES_EDGE_STYLE = {
    "color": {"color": "#ef4444", "highlight": "#f87171"},
    "dashes": True,
    "width": 2,
}


class IngestRequest(BaseModel):
    url: str | None = Field(None, description="A web page to scrape and ingest.")
    text: str | None = Field(None, description="Raw text to ingest.")

    @model_validator(mode="after")
    def _one_source(self) -> "IngestRequest":
        if not (self.url or self.text):
            raise ValueError("Provide either 'url' or 'text'.")
        return self


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=50)


class BootstrapRequest(BaseModel):
    project_path: str = Field(..., description="Directory of the project to bootstrap.")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.store = KnowledgeStore(settings)
        logger.info("Knowledge store ready at %s", settings.data_dir.resolve())
        yield
        app.state.store.close()

    app = FastAPI(
        title="GraphAgentDB",
        description="Hybrid graph + vector knowledge base for agents, skills, tools and best practices.",
        version=__version__,
        lifespan=lifespan,
    )
    # The UI can also be opened straight from disk (file://), which needs CORS.
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )

    def get_store(request: Request) -> KnowledgeStore:
        return request.app.state.store

    @app.get("/api/status")
    def status(store: KnowledgeStore = Depends(get_store)) -> dict[str, Any]:
        return {
            "status": "online",
            **store.stats(),
            "data_dir": str(settings.data_dir),
            "gemini_api_active": store.llm.gemini_available,
        }

    @app.post("/api/ingest")
    def ingest_knowledge(
        payload: IngestRequest, store: KnowledgeStore = Depends(get_store)
    ) -> dict[str, Any]:
        state = ingest(store, url=payload.url, text=payload.text)
        if state.error:
            raise HTTPException(status_code=422, detail=state.error)
        graph = state.distilled_graph
        return {
            "message": "Knowledge ingested and indexed.",
            "title": state.source_title,
            "nodes_extracted": len(graph.nodes) if graph else 0,
            "edges_extracted": len(graph.edges) if graph else 0,
            "committed_nodes": state.committed_nodes,
            "vector_chunks_created": len(state.committed_nodes),
        }

    @app.post("/api/search")
    def search(
        payload: SearchRequest, store: KnowledgeStore = Depends(get_store)
    ) -> dict[str, Any]:
        return HybridSearchEngine(store).search(payload.query, payload.top_k)

    @app.post("/api/consult/bootstrap")
    def bootstrap_project(
        payload: BootstrapRequest, store: KnowledgeStore = Depends(get_store)
    ) -> dict[str, Any]:
        state = bootstrap(store, payload.project_path)
        if state.error:
            raise HTTPException(status_code=422, detail=state.error)
        return {
            "message": "Project context bootstrapped.",
            "stack_keys": state.stack_keys,
            "written_paths": state.written_paths,
            "markdown_output": state.markdown_output,
        }

    @app.get("/api/graph")
    def graph(
        show_deprecated: bool = True, store: KnowledgeStore = Depends(get_store)
    ) -> dict[str, Any]:
        """The whole graph, formatted for vis-network."""
        nodes = store.get_all_nodes()
        edges = store.get_all_edges()
        if not show_deprecated:
            hidden = {n["id"] for n in nodes if n["status"] == NodeStatus.DEPRECATED.value}
            nodes = [n for n in nodes if n["id"] not in hidden]
            edges = [e for e in edges if not {e["source_id"], e["target_id"]} & hidden]
        return {
            "nodes": [_format_node(n) for n in nodes],
            "edges": [_format_edge(e) for e in edges],
        }

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")

    return app


def _format_node(n: dict[str, Any]) -> dict[str, Any]:
    deprecated = n["status"] == NodeStatus.DEPRECATED.value
    tag = " [DEPRECATED]" if deprecated else ""
    detail = n["description"]
    if deprecated:
        detail = (
            f"<b>Superseded By:</b> {n['superseded_by'] or 'N/A'}<br>"
            f"<b>Reason:</b> {n['supersession_reason']}<br><br>{detail}"
        )
    entry = {
        "id": n["id"],
        "label": n["name"] + tag,
        "group": n["type"],
        "title": f"<b>{n['name']}</b> ({n['type'].upper()}){tag}<br>{detail}",
        "description": n["description"],
        "status": n["status"],
    }
    if deprecated:
        entry.update(DEPRECATED_NODE_STYLE)
    return entry


def _format_edge(e: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "id": e["id"],
        "from": e["source_id"],
        "to": e["target_id"],
        "label": e["relation_type"],
        "title": e["properties"]["description"],
        "relation_type": e["relation_type"],
    }
    if e["relation_type"] == RelationType.SUPERSEDES.value:
        entry.update(SUPERSEDES_EDGE_STYLE)
    return entry
