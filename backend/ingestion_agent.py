import os
import hashlib
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END
from google import genai
from google.genai import types

from .store import KnowledgeStore
from .models import KnowledgeNode, NodeType, NodeStatus
from .extractor import KnowledgeExtractor, ExtractedGraph, ExtractedNode, ExtractedEdge

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")

class HarvestState(BaseModel):
    url: Optional[str] = None
    text: Optional[str] = None
    source_title: str = "Raw Ingested Knowledge"
    source_hash: Optional[str] = None
    distilled_graph: Optional[ExtractedGraph] = None
    embeddings: Dict[str, List[float]] = Field(default_factory=dict)
    conflict_decisions: Dict[str, Dict[str, Any]] = Field(default_factory=dict) # node_id -> decision info
    committed_nodes: List[str] = Field(default_factory=list)
    status: str = "pending"
    error: Optional[str] = None

class ConflictResolution(BaseModel):
    decision: str = Field(description="Must be exactly one of: 'new', 'update', 'duplicate'")
    target_id: Optional[str] = Field(None, description="The node_id of the matching existing concept if decision is 'update' or 'duplicate', else null.")
    reason: str = Field(description="Brief, professional explanation of the decision based on concept matching.")

def fetch_node(state: HarvestState) -> dict:
    """Crawls a URL or takes raw text, computes a unique hash, and caches the raw content."""
    extractor = KnowledgeExtractor()
    content_text = ""
    source_title = state.source_title
    error = None
    source_hash = None
    
    if state.url:
        print(f"[Librarian] Crawling URL: {state.url}")
        source_title, content_text = extractor.fetch_url_content(state.url)
    elif state.text:
        content_text = state.text
        source_title = "Text chunk: " + state.text[:30].replace("\n", " ") + "..."
    else:
        error = "Neither 'url' nor 'text' was provided in the HarvestState."
        return {"error": error}
        
    if not content_text.strip():
        error = "Ingested text content is completely empty."
        return {"error": error}
        
    # Calculate unique hash of the clean body text
    source_hash = hashlib.sha256(content_text.encode("utf-8")).hexdigest()[:16]
    
    # Cache the raw content on disk
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        cache_file = os.path.join(CACHE_DIR, f"{source_hash}.txt")
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(content_text)
        print(f"[Librarian] Cached raw content successfully at {cache_file}")
    except Exception as e:
        print(f"[Librarian] Failed to cache raw content: {e}")
        
    return {
        "text": content_text,
        "source_title": source_title,
        "source_hash": source_hash,
        "error": error
    }

def distill_node(state: HarvestState) -> dict:
    """Uses Gemini structured output in KnowledgeExtractor to extract pure concept nodes and relations."""
    if state.error:
        return {}
        
    print(f"[Librarian] Extracting graph concepts for: '{state.source_title}'")
    extractor = KnowledgeExtractor()
    distilled_graph = None
    error = None
    try:
        distilled = extractor.extract_graph_from_text(state.text, state.source_title)
        distilled_graph = distilled
        print(f"[Librarian] Extracted {len(distilled.nodes)} nodes and {len(distilled.edges)} edges.")
    except Exception as e:
        error = f"Distillation extraction failed: {str(e)}"
        
    return {
        "distilled_graph": distilled_graph,
        "error": error
    }

def embed_node(state: HarvestState) -> dict:
    """Computes vector embeddings for each extracted concept node's description."""
    if state.error or not state.distilled_graph:
        return {}
        
    print("[Librarian] Generating embeddings for extracted concepts...")
    store = KnowledgeStore()
    embeddings = {}
    
    for node in state.distilled_graph.nodes:
        concept_text = f"{node.name}: {node.description}"
        try:
            emb = store.vector_store.get_embedding(concept_text)
            embeddings[node.id] = emb
        except Exception as e:
            print(f"[Librarian] Embedding generation failed for {node.id}: {e}")
            embeddings[node.id] = store.vector_store._generate_fallback_embedding(concept_text)
            
    return {"embeddings": embeddings}

def conflict_check_node(state: HarvestState) -> dict:
    """Checks for conceptual duplicates or updates by comparing embeddings in LanceDB."""
    if state.error or not state.distilled_graph:
        return {}
        
    print("[Librarian] Running LanceDB semantic lookup for conflict detection...")
    store = KnowledgeStore()
    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key) if api_key else None
    conflict_decisions = {}
    
    for node in state.distilled_graph.nodes:
        emb = state.embeddings.get(node.id)
        if not emb:
            conflict_decisions[node.id] = {"decision": "new", "target_id": None, "reason": "No embedding available."}
            continue
            
        # Semantic search in LanceDB
        hits = store.semantic_search(f"{node.name}: {node.description}", top_k=1)
        
        if not hits or hits[0]["score"] < 0.85:
            # No matching concept found, mark as new
            conflict_decisions[node.id] = {
                "decision": "new",
                "target_id": None,
                "reason": f"No highly similar conceptual node found in DB (top score: {hits[0]['score'] if hits else 0.0:.2f})."
            }
            continue
            
        # Highly matching concept candidate found!
        target_hit = hits[0]
        target_id = target_hit["node_id"]
        
        # Retrieve full target node description from Kuzu
        existing_node = store.get_node(target_id)
        if not existing_node:
            conflict_decisions[node.id] = {"decision": "new", "target_id": None, "reason": "Target node not found in Graph."}
            continue
            
        print(f"[Librarian] Similarity match found: New concept '{node.name}' matches existing concept '{existing_node['name']}' (score: {target_hit['score']:.2f})")
        
        if client:
            # Let Gemini decide if duplicate, update, or distinct new concept
            prompt = f"""
            You are a technical knowledge conflict resolution engine.
            Compare the following NEW extracted concept with an EXISTING concept in the database.
            
            NEW CONCEPT:
            ID: {node.id}
            Name: {node.name}
            Description: {node.description}
            
            EXISTING CONCEPT:
            ID: {existing_node['id']}
            Name: {existing_node['name']}
            Description: {existing_node['description']}
            
            Decide if:
            1. 'duplicate': The new concept is identical or a subset of the existing concept. We should reject the write and keep the existing node.
            2. 'update': The new concept describes the same entity but contains updated, superior, or more comprehensive technical details. We should deprecate the existing node and replace it with the new node.
            3. 'new': Despite naming similarities, they represent completely separate entities or paradigms. We should insert the new concept as a distinct new node.
            
            You MUST return a valid JSON object matching the schema.
            """
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ConflictResolution,
                        temperature=0.1
                    )
                )
                resolution = ConflictResolution.model_validate_json(response.text)
                conflict_decisions[node.id] = {
                    "decision": resolution.decision,
                    "target_id": resolution.target_id or existing_node['id'],
                    "reason": resolution.reason
                }
                print(f"[Librarian] Conflict Decision for '{node.name}': {resolution.decision.upper()} - {resolution.reason}")
            except Exception as e:
                print(f"[Librarian] Gemini conflict resolution call failed: {e}. Falling back to default 'duplicate' to prevent duplicate writes.")
                conflict_decisions[node.id] = {
                    "decision": "duplicate",
                    "target_id": existing_node['id'],
                    "reason": "Structured LLM call failed. Defaulting to duplicate safety."
                }
        else:
            # Fallback offline decision: if names are nearly identical, mark as duplicate
            if "update" in node.description.lower() or (state.text and "critical update" in state.text.lower()):
                conflict_decisions[node.id] = {
                    "decision": "update",
                    "target_id": existing_node['id'],
                    "reason": "Deterministic fallback: 'update' keyword detected in text."
                }
            elif node.name.lower().strip() == existing_node["name"].lower().strip():
                conflict_decisions[node.id] = {
                    "decision": "duplicate",
                    "target_id": existing_node['id'],
                    "reason": "Deterministic fallback: Concept names match exactly."
                }
            else:
                conflict_decisions[node.id] = {
                    "decision": "update",
                    "target_id": existing_node['id'],
                    "reason": "Deterministic fallback: High similarity. Defaulting to update."
                }
                
    print(f"[Librarian DEBUG] conflict_decisions to return: {conflict_decisions}")
    return {"conflict_decisions": conflict_decisions}

def commit_node(state: HarvestState) -> dict:
    """Performs atomic database insertions, marking supersedes and deprecating old nodes if necessary."""
    if state.error or not state.distilled_graph:
        return {}
        
    print(f"[Librarian DEBUG] state.conflict_decisions inside commit: {state.conflict_decisions}")
    print("[Librarian] Committing extracted concepts and relations to the databases...")
    store = KnowledgeStore()
    committed_nodes = list(state.committed_nodes)
    
    # 1. Insert/Update Nodes
    for node in state.distilled_graph.nodes:
        decision_info = state.conflict_decisions.get(node.id, {"decision": "new"})
        decision = decision_info.get("decision", "new")
        target_id = decision_info.get("target_id")
        reason = decision_info.get("reason", "")
        
        if decision == "duplicate":
            print(f"[Librarian] Skipping duplicate node: '{node.name}' (duplicate of '{target_id}')")
            continue
            
        original_new_id = node.id
        if decision == "update" and target_id and node.id == target_id:
            # Suffix the new node ID with the source text hash to avoid ID collision on update
            node.id = f"{node.id}_{state.source_hash}"
            print(f"[Librarian] Suffixing new updated node ID to avoid collision: {node.id}")
            
        # Save new node in storage facade first so it exists in DB before deprecate/supersede links are created
        try:
            ntype = NodeType(node.type)
        except Exception:
            ntype = NodeType.CONCEPT
            
        k_node = KnowledgeNode(
            id=node.id,
            type=ntype,
            name=node.name,
            description=node.description,
            status=NodeStatus.ACTIVE
        )
        
        emb = state.embeddings.get(original_new_id)
        store.add_node(node=k_node, embedding=emb)

        if decision == "update" and target_id:
            print(f"[Librarian] Updating existing node '{target_id}' -> Deprecating it in favor of new node '{node.id}'")
            store.deprecate_node(node_id=target_id, new_node_id=node.id, reason=reason)
            
        committed_nodes.append(node.id)
        
    # 2. Insert Extracted Relationships (Edges)
    for edge in state.distilled_graph.edges:
        src_id = edge.source_id
        tgt_id = edge.target_id
        
        src_decision = state.conflict_decisions.get(src_id, {"decision": "new"})
        tgt_decision = state.conflict_decisions.get(tgt_id, {"decision": "new"})
        
        if src_decision.get("decision") == "duplicate" and src_decision.get("target_id"):
            src_id = src_decision["target_id"]
        elif src_decision.get("decision") == "update" and src_decision.get("target_id") == src_id:
            src_id = f"{src_id}_{state.source_hash}"
            
        if tgt_decision.get("decision") == "duplicate" and tgt_decision.get("target_id"):
            tgt_id = tgt_decision["target_id"]
        elif tgt_decision.get("decision") == "update" and tgt_decision.get("target_id") == tgt_id:
            tgt_id = f"{tgt_id}_{state.source_hash}"
            
        # Verify that both endpoints exist in storage facade
        src_node = store.get_node(src_id)
        tgt_node = store.get_node(tgt_id)
        
        if src_node and tgt_node:
            try:
                store.create_relation(
                    source_id=src_id,
                    target_id=tgt_id,
                    rel_type=edge.relation_type,
                    description=edge.description
                )
            except Exception as edge_err:
                print(f"[Librarian] Skipping edge {src_id} -> {tgt_id} due to: {edge_err}")
        else:
            print(f"[Librarian] Skipping edge connection {src_id} -> {tgt_id} because one of the endpoints is missing.")
            
    return {
        "committed_nodes": committed_nodes,
        "status": "success",
        "error": state.error
    }

# Compile LangGraph State Graph
workflow = StateGraph(HarvestState)
workflow.add_node("fetch", fetch_node)
workflow.add_node("distill", distill_node)
workflow.add_node("embed", embed_node)
workflow.add_node("conflict_check", conflict_check_node)
workflow.add_node("commit", commit_node)

workflow.set_entry_point("fetch")
workflow.add_edge("fetch", "distill")
workflow.add_edge("distill", "embed")
workflow.add_edge("embed", "conflict_check")
workflow.add_edge("conflict_check", "commit")
workflow.add_edge("commit", END)

harvester = workflow.compile()
