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
    updates the Kuzu Property Graph, computes embeddings, and indexes them in the local Vector DB.
    """
    extractor = KnowledgeExtractor()
    vector_store = VectorStore()
    
    source_title = "Raw Ingested Knowledge"
    content_text = ""
    
    # 1. Fetch content if URL is provided
    if payload.url:
        print(f"Scraping content from URL: {payload.url}")
        source_title, content_text = extractor.fetch_url_content(payload.url)
    elif payload.text:
        content_text = payload.text
        source_title = "Text chunk: " + payload.text[:30].replace("\n", " ") + "..."
    else:
        raise HTTPException(status_code=400, detail="Either 'url' or 'text' must be provided in the payload.")
        
    if not content_text.strip():
        raise HTTPException(status_code=400, detail="The ingested text content is empty.")
        
    try:
        # 2. Extract Graph nodes and edges using Antigravity Harness (Gemini fallback)
        print(f"Extracting knowledge entities and relationships for: {source_title}")
        extracted_graph = extractor.extract_graph_from_text(content_text, source_title)
        
        # 3. Store and index Extracted Entities (Nodes) directly
        for node in extracted_graph.nodes:
            upsert_node(
                id=node.id,
                type=node.type,
                name=node.name,
                description=node.description
            )
            
            # Compute embedding on the concept name + description directly
            node_concept_text = f"{node.name}: {node.description}"
            embedding = vector_store.get_embedding(node_concept_text)
            vector_store.add_vector(
                chunk_id=f"vector_{node.id}",
                node_id=node.id,
                text=node_concept_text,
                embedding=embedding
            )
            
        # 4. Store Extracted Relationships (Edges) into Kuzu Property Graph
        for edge in extracted_graph.edges:
            try:
                upsert_edge(
                    source_id=edge.source_id,
                    target_id=edge.target_id,
                    relation_type=edge.relation_type,
                    properties={"description": edge.description}
                )
            except Exception as edge_err:
                print(f"Skipping edge {edge.source_id} -> {edge.target_id} due to integrity: {edge_err}")
                
        return {
            "message": "Knowledge successfully ingested and indexed.",
            "source_node_id": None,
            "title": source_title,
            "nodes_extracted": len(extracted_graph.nodes),
            "edges_extracted": len(extracted_graph.edges),
            "vector_chunks_created": len(extracted_graph.nodes)
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

@app.get("/api/graph")
def get_graph():
    """
    Returns the complete list of nodes and edges in the database.
    Format compatible with frontend vis-network.js.
    """
    try:
        nodes = get_all_nodes()
        edges = get_all_edges()
        
        formatted_nodes = []
        for n in nodes:
            formatted_nodes.append({
                "id": n["id"],
                "label": n["name"],
                "group": n["type"],
                "title": f"<b>{n['name']}</b> ({n['type'].upper()})<br>{n['description'] or ''}",
                "description": n["description"]
            })
            
        formatted_edges = []
        for e in edges:
            formatted_edges.append({
                "id": e["id"],
                "from": e["source_id"],
                "to": e["target_id"],
                "label": e["relation_type"],
                "title": e["properties"].get("description", "")
            })
            
        return {
            "nodes": formatted_nodes,
            "edges": formatted_edges
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph retrieval failed: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
