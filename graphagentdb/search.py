"""Hybrid retrieval: vector search finds seed concepts, graph traversal adds their neighbourhood,
and relation-aware score propagation re-ranks the result before an LLM writes the answer."""

import logging
from typing import Any

from .store import KnowledgeStore

logger = logging.getLogger(__name__)

# How much of a matched node's score flows along each relation type.
# direction "to_source": an agent that HAS_TOOL a matching tool is boosted.
# direction "to_target": a tool REQUIRED by a matching skill is boosted.
RELATION_BOOSTS: dict[str, tuple[float, str]] = {
    "HAS_TOOL": (0.5, "to_source"),
    "HAS_SKILL": (0.4, "to_source"),
    "REQUIRES_TOOL": (0.3, "to_target"),
}
DEFAULT_SCORE = 0.1

ANSWER_PROMPT = """
You answer questions from a local knowledge graph of agents, skills, tools and best practices.
Write a detailed, expert answer to the user's query using the retrieved entities, relationships
and concept snippets below.

User query: "{query}"

ENTITIES (most relevant first):
{nodes}

RELATIONSHIPS:
{edges}

CONCEPT SNIPPETS:
---
{snippets}
---

Instructions:
1. Base the answer on the retrieved entities, skills, tools and best practices.
2. Explain how tools and skills connect back to their parent agents through the graph.
3. Keep a professional, technical and objective tone.
"""


def score_subgraph(
    vector_hits: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> dict[str, float]:
    """Starts from the vector similarity of each hit and propagates it along weighted relations."""
    scores: dict[str, float] = {}
    for hit in vector_hits:
        scores[hit["node_id"]] = max(scores.get(hit["node_id"], 0.0), hit["score"])

    for edge in edges:
        rule = RELATION_BOOSTS.get(edge["relation_type"])
        if rule is None:
            continue
        weight, direction = rule
        src, tgt = edge["source_id"], edge["target_id"]
        if direction == "to_source" and tgt in scores:
            scores[src] = scores.get(src, 0.0) + scores[tgt] * weight
        elif direction == "to_target" and src in scores:
            scores[tgt] = scores.get(tgt, 0.0) + scores[src] * weight
    return scores


class HybridSearchEngine:
    def __init__(self, store: KnowledgeStore):
        self.store = store

    def search(self, query: str, top_k: int = 5) -> dict[str, Any]:
        vector_hits = self.store.semantic_search(query, top_k=top_k)
        if not vector_hits:
            return {
                "answer": "No matching knowledge found. Ingest some URLs or text first.",
                "subgraph": {"nodes": [], "edges": []},
                "sources": [],
            }

        seed_ids = list(dict.fromkeys(hit["node_id"] for hit in vector_hits))
        subgraph = self.store.get_subgraph(seed_ids, max_depth=2)

        scores = score_subgraph(vector_hits, subgraph["edges"])
        for node in subgraph["nodes"]:
            node["hybrid_score"] = round(scores.get(node["id"], DEFAULT_SCORE), 3)
        subgraph["nodes"].sort(key=lambda n: n["hybrid_score"], reverse=True)

        return {
            "answer": self._synthesize(query, subgraph, vector_hits),
            "subgraph": subgraph,
            "sources": vector_hits,
        }

    def _synthesize(
        self, query: str, subgraph: dict[str, Any], vector_hits: list[dict[str, Any]]
    ) -> str:
        nodes = [
            f"- [{n['type'].upper()}] {n['name']} (ID: {n['id']}): {n['description']} "
            f"[Score: {n['hybrid_score']}]"
            for n in subgraph["nodes"][:10]
        ]
        edges = [
            f"- {e['source_id']} --({e['relation_type']})--> {e['target_id']}: "
            f"{e['properties'].get('description', '')}"
            for e in subgraph["edges"][:15]
        ]
        snippets = [
            f'Snippet {i + 1} (node: {h["node_id"]}, similarity: {h["score"]:.2f}):\n"{h["text"]}"'
            for i, h in enumerate(vector_hits[:5])
        ]
        prompt = ANSWER_PROMPT.format(
            query=query,
            nodes="\n".join(nodes),
            edges="\n".join(edges),
            snippets="\n".join(snippets),
        )
        answer = self.store.llm.generate(prompt)
        if answer:
            return answer
        logger.info("No LLM available, compiling an offline answer")
        return compile_offline_answer(query, subgraph, vector_hits)


def compile_offline_answer(
    query: str, subgraph: dict[str, Any], vector_hits: list[dict[str, Any]]
) -> str:
    """A grounded Markdown summary of the retrieved context, used when no LLM is reachable."""
    names = {n["id"]: n["name"] for n in subgraph["nodes"]}
    lines = [
        f'### Hybrid search results for: "{query}"',
        "",
        "*(No LLM is configured, so this is a compilation of the retrieved graph context.)*",
        "",
        "#### Top entities",
    ]
    lines += [
        f"- **{n['name']}** (`{n['type']}`): {n['description']} *(relevance {n['hybrid_score']})*"
        for n in subgraph["nodes"][:5]
    ]
    if subgraph["edges"]:
        lines += ["", "#### Key relationships"]
        lines += [
            f"- **{names.get(e['source_id'], e['source_id'])}** --[`{e['relation_type']}`]--> "
            f"**{names.get(e['target_id'], e['target_id'])}**"
            for e in subgraph["edges"][:5]
        ]
    if vector_hits:
        lines += ["", "#### Best matching snippet", f'> "{vector_hits[0]["text"][:400]}"']
    return "\n".join(lines) + "\n"
