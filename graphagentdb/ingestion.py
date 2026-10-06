"""The Librarian: a LangGraph pipeline that ingests a URL or text into the knowledge store.

    fetch -> distill -> embed -> conflict_check -> commit

`conflict_check` compares each new concept with its nearest existing neighbour and decides
whether it is new, a duplicate (skipped) or an update (the old node is deprecated and linked
to the new one with a SUPERSEDES edge).
"""

import hashlib
import logging
from typing import Any

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from .extractor import KnowledgeExtractor, fetch_url_content
from .models import (
    ConflictResolution,
    ExtractedGraph,
    KnowledgeNode,
    NodeStatus,
    NodeType,
)
from .store import KnowledgeStore, node_text

logger = logging.getLogger(__name__)

CONFLICT_PROMPT = """
You are a knowledge conflict resolution engine. Compare a NEW extracted concept with an
EXISTING concept in the database.

NEW CONCEPT:
ID: {new_id}
Name: {new_name}
Description: {new_description}

EXISTING CONCEPT:
ID: {old_id}
Name: {old_name}
Description: {old_description}

Decide one of:
- "duplicate": the new concept is identical to, or a subset of, the existing one. Keep the existing node.
- "update": same entity, but the new concept has newer or more complete details. Replace the existing node.
- "new": despite the similarity they are separate entities. Insert the new concept as its own node.

Return a JSON object matching the schema.
"""


class HarvestState(BaseModel):
    url: str | None = None
    text: str | None = None
    source_title: str = "Raw Ingested Knowledge"
    source_hash: str | None = None
    distilled_graph: ExtractedGraph | None = None
    embeddings: dict[str, list[float]] = Field(default_factory=dict)
    conflict_decisions: dict[str, dict[str, Any]] = Field(default_factory=dict)
    committed_nodes: list[str] = Field(default_factory=list)
    status: str = "pending"
    error: str | None = None


def _offline_decision(node_name: str, node_description: str, text: str, existing: dict) -> dict:
    """Heuristic used when no LLM is available to arbitrate a near-duplicate."""
    if "update" in node_description.lower() or "critical update" in text.lower():
        return {"decision": "update", "reason": "Offline heuristic: 'update' keyword detected."}
    if node_name.lower().strip() == existing["name"].lower().strip():
        return {"decision": "duplicate", "reason": "Offline heuristic: names match exactly."}
    return {"decision": "update", "reason": "Offline heuristic: high similarity."}


def _resolve_id(node_id: str, decisions: dict[str, dict[str, Any]], source_hash: str) -> str:
    """Maps an extracted id to the id it was actually stored under."""
    decision = decisions.get(node_id, {})
    if decision.get("decision") == "duplicate" and decision.get("target_id"):
        return decision["target_id"]
    if decision.get("decision") == "update" and decision.get("target_id") == node_id:
        return f"{node_id}_{source_hash}"
    return node_id


def build_harvester(store: KnowledgeStore, extractor: KnowledgeExtractor | None = None):
    """Compiles the ingestion workflow bound to a store."""
    llm = store.llm
    extractor = extractor or KnowledgeExtractor(llm)
    threshold = store.settings.conflict_similarity_threshold
    cache_dir = store.settings.cache_dir

    def fetch(state: HarvestState) -> dict:
        if state.url:
            logger.info("Fetching %s", state.url)
            title, content = fetch_url_content(state.url)
        elif state.text:
            content = state.text
            title = "Text: " + state.text.strip()[:30].replace("\n", " ") + "..."
        else:
            return {"error": "Provide either a url or text to ingest."}

        if not content.strip():
            return {"error": "The ingested content is empty."}

        source_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / f"{source_hash}.txt").write_text(content, encoding="utf-8")
        except OSError:
            logger.warning("Could not cache raw content", exc_info=True)

        return {"text": content, "source_title": title, "source_hash": source_hash}

    def distill(state: HarvestState) -> dict:
        if state.error:
            return {}
        graph = extractor.extract(state.text or "")
        logger.info("Extracted %d nodes and %d edges", len(graph.nodes), len(graph.edges))
        return {"distilled_graph": graph}

    def embed(state: HarvestState) -> dict:
        if state.error or not state.distilled_graph:
            return {}
        return {
            "embeddings": {
                n.id: llm.embed(node_text(n.name, n.description))
                for n in state.distilled_graph.nodes
            }
        }

    def conflict_check(state: HarvestState) -> dict:
        if state.error or not state.distilled_graph:
            return {}
        decisions: dict[str, dict[str, Any]] = {}

        for node in state.distilled_graph.nodes:
            embedding = state.embeddings.get(node.id)
            hits = store.vectors.search(embedding, top_k=1) if embedding else []
            top_score = hits[0]["score"] if hits else 0.0
            if top_score < threshold:
                decisions[node.id] = {
                    "decision": "new",
                    "target_id": None,
                    "reason": f"No similar node found (top score {top_score:.2f}).",
                }
                continue

            existing = store.get_node(hits[0]["node_id"])
            if existing is None:
                decisions[node.id] = {
                    "decision": "new",
                    "target_id": None,
                    "reason": "Matched vector has no graph node.",
                }
                continue

            logger.info(
                "'%s' is similar to existing '%s' (score %.2f)",
                node.name,
                existing["name"],
                top_score,
            )
            if llm.gemini_available or store.settings.use_agent_harness:
                resolution = llm.generate_json(
                    CONFLICT_PROMPT.format(
                        new_id=node.id,
                        new_name=node.name,
                        new_description=node.description,
                        old_id=existing["id"],
                        old_name=existing["name"],
                        old_description=existing["description"],
                    ),
                    ConflictResolution,
                )
                if resolution is not None:
                    decision = {"decision": resolution.decision, "reason": resolution.reason}
                else:
                    # Refuse the write rather than risk a duplicate node.
                    decision = {"decision": "duplicate", "reason": "LLM arbitration failed."}
            else:
                decision = _offline_decision(
                    node.name, node.description, state.text or "", existing
                )
            decisions[node.id] = {**decision, "target_id": existing["id"]}
            logger.info("Decision for '%s': %s", node.name, decision["decision"])

        return {"conflict_decisions": decisions}

    def commit(state: HarvestState) -> dict:
        if state.error or not state.distilled_graph:
            return {}
        decisions = state.conflict_decisions
        source_hash = state.source_hash or ""
        committed = list(state.committed_nodes)

        for node in state.distilled_graph.nodes:
            info = decisions.get(node.id, {"decision": "new"})
            if info["decision"] == "duplicate":
                logger.info("Skipping duplicate '%s'", node.name)
                continue

            stored_id = _resolve_id(node.id, decisions, source_hash)
            try:
                node_type = NodeType(node.type)
            except ValueError:
                node_type = NodeType.CONCEPT
            store.add_node(
                KnowledgeNode(
                    id=stored_id,
                    type=node_type,
                    name=node.name,
                    description=node.description,
                    status=NodeStatus.ACTIVE,
                ),
                embedding=state.embeddings.get(node.id),
            )
            if info["decision"] == "update" and info.get("target_id"):
                store.deprecate_node(info["target_id"], stored_id, info.get("reason", ""))
            committed.append(stored_id)

        for edge in state.distilled_graph.edges:
            src = _resolve_id(edge.source_id, decisions, source_hash)
            tgt = _resolve_id(edge.target_id, decisions, source_hash)
            if store.get_node(src) and store.get_node(tgt):
                store.create_relation(src, tgt, edge.relation_type, edge.description)
            else:
                logger.info("Skipping edge %s -> %s: missing endpoint", src, tgt)

        return {"committed_nodes": committed, "status": "success"}

    workflow = StateGraph(HarvestState)
    workflow.add_node("fetch", fetch)
    workflow.add_node("distill", distill)
    workflow.add_node("embed", embed)
    workflow.add_node("conflict_check", conflict_check)
    workflow.add_node("commit", commit)
    workflow.set_entry_point("fetch")
    workflow.add_edge("fetch", "distill")
    workflow.add_edge("distill", "embed")
    workflow.add_edge("embed", "conflict_check")
    workflow.add_edge("conflict_check", "commit")
    workflow.add_edge("commit", END)
    return workflow.compile()


def ingest(store: KnowledgeStore, url: str | None = None, text: str | None = None) -> HarvestState:
    """Runs the ingestion workflow and returns the final state."""
    result = build_harvester(store).invoke(HarvestState(url=url, text=text))
    return HarvestState.model_validate(result)
