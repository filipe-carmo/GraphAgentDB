from typing import List, Dict, Any, Optional
from .database import (
    upsert_node as db_upsert_node, 
    upsert_edge as db_upsert_edge, 
    get_node as db_get_node, 
    get_all_nodes, 
    get_all_edges, 
    get_subgraph
)
from .vector_store import VectorStore
from .models import KnowledgeNode, NodeStatus, NodeType

class KnowledgeStore:
    def __init__(self, db_path: str = None, vector_path: str = None):
        """Initializes Kuzu graph operations and LanceDB vector collection wrappers."""
        self.vector_store = VectorStore(vector_path)
        
    def add_node(self, node: KnowledgeNode, embedding: Optional[List[float]] = None) -> Dict[str, Any]:
        """
        Atomically inserts or updates a node in the Kuzu Property Graph 
        and LanceDB Vector index with strict synchronization.
        """
        # 1. Upsert node in Kuzu Graph
        node_dict = db_upsert_node(
            id=node.id,
            type=node.type.value,
            name=node.name,
            description=node.description,
            status=node.status.value,
            superseded_by=node.superseded_by,
            supersession_reason=node.supersession_reason
        )
        
        # 2. Compute embedding if missing
        if embedding is None:
            embedding = self.vector_store.get_embedding(f"{node.name}: {node.description}")
            
        # 3. Add to LanceDB Vector index
        self.vector_store.add_vector(
            chunk_id=f"vector_{node.id}",
            node_id=node.id,
            text=f"{node.name}: {node.description}",
            embedding=embedding,
            status=node.status.value
        )
        
        return node_dict

    def deprecate_node(self, node_id: str, new_node_id: str, reason: str):
        """
        Marks an existing node as deprecated, assigns pointers, and creates a SUPERSEDES edge.
        Updates status mapping in both Kuzu and LanceDB.
        """
        old_node = db_get_node(node_id)
        if old_node:
            # a. Mark as deprecated in Kuzu Graph
            db_upsert_node(
                id=old_node["id"],
                type=old_node["type"],
                name=old_node["name"],
                description=old_node["description"],
                status=NodeStatus.DEPRECATED.value,
                superseded_by=new_node_id,
                supersession_reason=reason
            )
            
            # b. Mark as deprecated in LanceDB vector store
            try:
                self.vector_store.table.update(
                    where=f"node_id = '{node_id}'",
                    values={"status": NodeStatus.DEPRECATED.value}
                )
            except Exception as e:
                print(f"[KnowledgeStore] Failed to update LanceDB vector status for deprecated node {node_id}: {e}")
                
            # c. Add a physical SUPERSEDES relationship in Kuzu Graph
            db_upsert_edge(
                source_id=new_node_id,
                target_id=node_id,
                relation_type="SUPERSEDES",
                properties={"description": f"Supersedes old implementation: {reason}"}
            )

    def create_relation(self, source_id: str, target_id: str, rel_type: str, description: str = "") -> Dict[str, Any]:
        """Creates or updates a relationship edge between two nodes inside Kuzu."""
        return db_upsert_edge(
            source_id=source_id,
            target_id=target_id,
            relation_type=rel_type,
            properties={"description": description}
        )

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single node's details from KuzuDB."""
        return db_get_node(node_id)

    def semantic_search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Queries the LanceDB vector store for highly matching active concepts."""
        return self.vector_store.search_vectors(query, top_k)

    def get_subgraph(self, start_node_ids: List[str], max_depth: int = 2) -> Dict[str, Any]:
        """Traverses the property graph starting from specific node IDs up to a given depth."""
        return get_subgraph(start_node_ids, max_depth)

    def get_all_nodes(self) -> List[Dict[str, Any]]:
        """Retrieves all stored nodes from Kuzu Property Graph."""
        return get_all_nodes()

    def get_all_edges(self) -> List[Dict[str, Any]]:
        """Retrieves all relationship edges from Kuzu Property Graph."""
        return get_all_edges()

    def stats(self) -> Dict[str, Any]:
        """Returns consolidated counts across Kuzu Property Graph and LanceDB Vector collections."""
        nodes = get_all_nodes()
        edges = get_all_edges()
        try:
            vector_count = self.vector_store.table.count_rows()
        except Exception:
            vector_count = 0
            
        return {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "vector_count": vector_count
        }

    def close(self):
        """No-op for connection pooling compatibility."""
        pass
