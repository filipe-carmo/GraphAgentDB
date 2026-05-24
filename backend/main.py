import os
import uvicorn
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from .database import init_db, upsert_node, upsert_edge, get_all_nodes, get_all_edges
from .extractor import KnowledgeExtractor
from .vector_store import VectorStore
from .hybrid_search import HybridSearchEngine

app = FastAPI(
    title="Agent Knowledge Graph & Vector DB (Agent-as-a-Graph)",
    description="A hybrid local RAG system modeling agents, tools, skills, and best practices."
)

# Enable CORS for rich browser interaction
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic schemas for request validations
class IngestRequest(BaseModel):
    url: Optional[str] = Field(None, description="The URL to scrape and ingest.")
    text: Optional[str] = Field(None, description="Raw text content to ingest.")

class SearchRequest(BaseModel):
    query: str = Field(..., description="The query to search the knowledge graph.")
    top_k: int = Field(5, description="Number of vector chunks to match.")

@app.on_event("startup")
def startup_event():
    """Initializes the Kuzu property graph database schema at startup."""
    try:
        init_db()
        print("Agent Kuzu Property Graph Database initialized successfully.")
    except Exception as e:
        print(f"Startup schema initialization error: {e}")

@app.get("/api/status")
def get_status():
    """Returns the API service and database status."""
    try:
        nodes = get_all_nodes()
        edges = get_all_edges()
        return {
            "status": "online",
            "node_count": len(nodes),
            "edge_count": len(edges),
            "database_file": "backend/kuzu_db",
            "gemini_api_active": bool(os.environ.get("GEMINI_API_KEY"))
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database status error: {str(e)}")

@app.post("/api/ingest")
def ingest_knowledge(payload: IngestRequest):
    """
    Crawls a URL or takes raw text, parses it, extracts structured Agent/Skill/Tool/Theory nodes,
    updates Kuzu Property Graph and LanceDB, runs conflict/deduplication checks, and maps links via
    the stateful Librarian LangGraph workflow.
    """
    from .ingestion_agent import harvester, HarvestState
    
    try:
        state = HarvestState(
            url=payload.url,
            text=payload.text
        )
        result_state = harvester.invoke(state)
        
        if result_state.error:
            raise HTTPException(status_code=500, detail=f"Ingestion failed: {result_state.error}")
            
        return {
            "message": "Knowledge successfully ingested and indexed via Librarian agent.",
            "source_node_id": None,
            "title": result_state.source_title,
            "nodes_extracted": len(result_state.distilled_graph.nodes) if result_state.distilled_graph else 0,
            "edges_extracted": len(result_state.distilled_graph.edges) if result_state.distilled_graph else 0,
            "vector_chunks_created": len(result_state.committed_nodes)
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

@app.post("/api/search")
def search_knowledge(payload: SearchRequest):
    """
    Performs a hybrid search combining vector search, Kuzu graph traversal,
    wRRF score fusion, and grounded Harness agent text synthesis.
    """
    try:
        engine = HybridSearchEngine()
        results = engine.search(payload.query, payload.top_k)
        return results
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

class BootstrapRequest(BaseModel):
    project_path: str = Field(..., description="The repository directory path to bootstrap.")

@app.post("/api/consult/bootstrap")
def bootstrap_project(payload: BootstrapRequest):
    """
    Executes the Consultant LangGraph workflow to scan local manifests,
    retrieve active developer rules, and compile/generate the GEMINI.md file.
    """
    from .consultant_agent import consultant, ConsultState
    
    try:
        state = ConsultState(project_path=payload.project_path)
        result = consultant.invoke(state.model_dump())
        
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result.get("error"))
            
        return {
            "message": "Project context bootstrapped successfully.",
            "stack_keys": result.get("stack_keys", []),
            "written_paths": result.get("written_paths", []),
            "markdown_output": result.get("markdown_output", "")
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/graph")
def get_graph(show_deprecated: bool = True):
    """
    Returns the complete list of nodes and edges in the database.
    Format compatible with frontend vis-network.js.
    """
    try:
        nodes = get_all_nodes()
        edges = get_all_edges()
        
        if not show_deprecated:
            # Filter out deprecated nodes
            deprecated_ids = {n["id"] for n in nodes if n.get("status") == "deprecated"}
            nodes = [n for n in nodes if n.get("status") != "deprecated"]
            edges = [e for e in edges if e["source_id"] not in deprecated_ids and e["target_id"] not in deprecated_ids]
            
        formatted_nodes = []
        for n in nodes:
            status_tag = " [DEPRECATED]" if n.get("status") == "deprecated" else ""
            node_desc = n.get("description", "") or ""
            if n.get("status") == "deprecated":
                node_desc = f"<b>Superseded By:</b> {n.get('superseded_by', 'N/A')}<br><b>Reason:</b> {n.get('supersession_reason', '')}<br><br>{node_desc}"
                
            node_entry = {
                "id": n["id"],
                "label": n["name"] + status_tag,
                "group": n["type"],
                "title": f"<b>{n['name']}</b> ({n['type'].upper()}){status_tag}<br>{node_desc}",
                "description": n.get("description", ""),
                "status": n.get("status", "active")
            }
            
            # Style deprecated nodes distinctly for frontend Vis-Network
            if n.get("status") == "deprecated":
                node_entry.update({
                    "color": {
                        "background": "#2d3748",
                        "border": "#4a5568",
                        "highlight": {"background": "#4a5568", "border": "#718096"}
                    },
                    "font": {"color": "#718096"},
                    "borderWidth": 2,
                    "borderWidthSelected": 3,
                    "opacity": 0.5
                })
            formatted_nodes.append(node_entry)
            
        formatted_edges = []
        for e in edges:
            edge_entry = {
                "id": e["id"],
                "from": e["source_id"],
                "to": e["target_id"],
                "label": e["relation_type"],
                "title": e["properties"].get("description", ""),
                "relation_type": e["relation_type"]
            }
            
            # Style SUPERSEDES relationships as dashed red arrows
            if e["relation_type"] == "SUPERSEDES":
                edge_entry.update({
                    "color": {"color": "#ef4444", "highlight": "#f87171"},
                    "dashes": True,
                    "width": 2
                })
            formatted_edges.append(edge_entry)
            
        return {
            "nodes": formatted_nodes,
            "edges": formatted_edges
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph retrieval failed: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
