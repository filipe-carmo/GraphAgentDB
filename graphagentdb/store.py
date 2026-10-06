"""`KnowledgeStore` keeps the property graph and the vector index in sync."""

import logging
from typing import Any

from .config import Settings
from .graph_store import GraphStore
from .llm import LLMClient
from .models import KnowledgeNode, NodeStatus, RelationType
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


def node_text(name: str, description: str) -> str:
    """The text that gets embedded for a node."""
    return f"{name}: {description}"


class KnowledgeStore:
    def __init__(self, settings: Settings, llm: LLMClient | None = None):
        self.settings = settings
        self.llm = llm or LLMClient(settings)
        self.graph = GraphStore(settings.kuzu_path)
        self.vectors = VectorStore(settings.lancedb_path, settings.embed_dim)

    def add_node(self, node: KnowledgeNode, embedding: list[float] | None = None) -> dict[str, Any]:
        """Writes the node to the graph and its embedding to the vector index."""
        stored = self.graph.upsert_node(
            id=node.id,
            type=node.type.value,
            name=node.name,
            description=node.description,
            status=node.status.value,
            superseded_by=node.superseded_by,
            supersession_reason=node.supersession_reason,
        )
        text = node_text(node.name, node.description)
        self.vectors.add_vector(
            chunk_id=f"vector_{node.id}",
            node_id=node.id,
            text=text,
            embedding=embedding if embedding is not None else self.llm.embed(text),
            status=node.status.value,
        )
        return stored

    def deprecate_node(self, node_id: str, new_node_id: str, reason: str) -> None:
        """Marks `node_id` as deprecated and links it to its replacement with a SUPERSEDES edge."""
        old = self.graph.get_node(node_id)
        if old is None:
            logger.warning("Cannot deprecate missing node %s", node_id)
            return
        self.graph.upsert_node(
            id=old["id"],
            type=old["type"],
            name=old["name"],
            description=old["description"],
            status=NodeStatus.DEPRECATED.value,
            superseded_by=new_node_id,
            supersession_reason=reason,
        )
        self.vectors.set_status(node_id, NodeStatus.DEPRECATED.value)
        self.graph.upsert_edge(
            new_node_id,
            node_id,
            RelationType.SUPERSEDES.value,
            f"Supersedes old implementation: {reason}",
        )

    def create_relation(
        self, source_id: str, target_id: str, rel_type: str, description: str = ""
    ) -> dict[str, Any]:
        return self.graph.upsert_edge(source_id, target_id, rel_type, description)

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return self.graph.get_node(node_id)

    def get_all_nodes(self) -> list[dict[str, Any]]:
        return self.graph.get_all_nodes()

    def get_all_edges(self) -> list[dict[str, Any]]:
        return self.graph.get_all_edges()

    def get_subgraph(self, start_node_ids: list[str], max_depth: int = 2) -> dict[str, Any]:
        return self.graph.get_subgraph(start_node_ids, max_depth)

    def semantic_search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        return self.vectors.search(self.llm.embed(query), top_k)

    def stats(self) -> dict[str, int]:
        return {
            "node_count": len(self.graph.get_all_nodes()),
            "edge_count": len(self.graph.get_all_edges()),
            "vector_count": self.vectors.count(),
        }

    def close(self) -> None:
        self.graph.close()
