"""Kùzu property-graph storage: one `Node` table plus one relationship table per relation type."""

import logging
from pathlib import Path
from typing import Any

import kuzu

from .models import NodeStatus, RelationType

logger = logging.getLogger(__name__)

RELATION_TYPES: list[str] = [r.value for r in RelationType]

_NODE_COLUMNS = (
    "n.id, n.type, n.name, n.description, n.status, n.superseded_by, n.supersession_reason"
)


def _row_to_node(row: list[Any]) -> dict[str, Any]:
    return {
        "id": row[0],
        "type": row[1],
        "name": row[2],
        "description": row[3] or "",
        "status": row[4] or NodeStatus.ACTIVE.value,
        "superseded_by": row[5] or "",
        "supersession_reason": row[6] or "",
    }


def _edge(source_id: str, target_id: str, relation_type: str, description: str) -> dict[str, Any]:
    return {
        "id": f"{source_id}_{relation_type}_{target_id}",
        "source_id": source_id,
        "target_id": target_id,
        "relation_type": relation_type,
        "properties": {"description": description or ""},
    }


class GraphStore:
    """Owns a single embedded Kùzu database. Create one per process and per path."""

    def __init__(self, db_path: str | Path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = kuzu.Database(str(db_path))
        self._conn = kuzu.Connection(self._db)
        self._init_schema()

    def _query(self, query: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
        result = self._conn.execute(query, params or {})
        rows = []
        while result.has_next():
            rows.append(result.get_next())
        return rows

    def _init_schema(self) -> None:
        existing = {row[0] for row in self._query("CALL show_tables() RETURN name")}
        if "Node" not in existing:
            logger.info("Creating Kùzu Node table")
            self._conn.execute(
                """
                CREATE NODE TABLE Node (
                    id STRING,
                    type STRING,
                    name STRING,
                    description STRING,
                    status STRING,
                    superseded_by STRING,
                    supersession_reason STRING,
                    PRIMARY KEY (id)
                )
                """
            )
        for rel in RELATION_TYPES:
            if rel not in existing:
                logger.info("Creating Kùzu relationship table %s", rel)
                self._conn.execute(
                    f"CREATE REL TABLE {rel} (FROM Node TO Node, description STRING)"
                )

    def upsert_node(
        self,
        id: str,
        type: str,
        name: str,
        description: str = "",
        status: str = NodeStatus.ACTIVE.value,
        superseded_by: str = "",
        supersession_reason: str = "",
    ) -> dict[str, Any]:
        """Creates the node, or overwrites every property of an existing node with the same id."""
        params = {
            "id": id,
            "type": type,
            "name": name,
            "description": description or "",
            "status": status,
            "superseded_by": superseded_by or "",
            "supersession_reason": supersession_reason or "",
        }
        self._conn.execute(
            """
            MERGE (n:Node {id: $id})
            SET n.type = $type,
                n.name = $name,
                n.description = $description,
                n.status = $status,
                n.superseded_by = $superseded_by,
                n.supersession_reason = $supersession_reason
            """,
            params,
        )
        return params

    def upsert_edge(
        self, source_id: str, target_id: str, relation_type: str, description: str = ""
    ) -> dict[str, Any]:
        """Creates an edge if it does not exist yet. Unknown relation types become REFERENCES."""
        if relation_type not in RELATION_TYPES:
            relation_type = RelationType.REFERENCES.value
        params = {"src": source_id, "tgt": target_id, "description": description or ""}
        # Relation types can't be query parameters, but they come from the fixed list above.
        exists = self._query(
            f"MATCH (a:Node {{id: $src}})-[r:{relation_type}]->(b:Node {{id: $tgt}}) RETURN count(r)",
            {"src": source_id, "tgt": target_id},
        )
        if not exists[0][0]:
            self._conn.execute(
                f"""
                MATCH (a:Node {{id: $src}}), (b:Node {{id: $tgt}})
                CREATE (a)-[r:{relation_type} {{description: $description}}]->(b)
                """,
                params,
            )
        return _edge(source_id, target_id, relation_type, description)

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        rows = self._query(f"MATCH (n:Node {{id: $id}}) RETURN {_NODE_COLUMNS}", {"id": node_id})
        return _row_to_node(rows[0]) if rows else None

    def get_nodes(self, node_ids: list[str]) -> list[dict[str, Any]]:
        if not node_ids:
            return []
        rows = self._query(
            f"MATCH (n:Node) WHERE n.id IN $ids RETURN {_NODE_COLUMNS}", {"ids": list(node_ids)}
        )
        return [_row_to_node(r) for r in rows]

    def get_all_nodes(self) -> list[dict[str, Any]]:
        return [_row_to_node(r) for r in self._query(f"MATCH (n:Node) RETURN {_NODE_COLUMNS}")]

    def get_all_edges(self) -> list[dict[str, Any]]:
        edges = []
        for rel in RELATION_TYPES:
            for src, tgt, desc in self._query(
                f"MATCH (a:Node)-[r:{rel}]->(b:Node) RETURN a.id, b.id, r.description"
            ):
                edges.append(_edge(src, tgt, rel, desc))
        return edges

    def get_subgraph(self, start_node_ids: list[str], max_depth: int = 2) -> dict[str, Any]:
        """Breadth-first expansion (in either edge direction) from the seed nodes up to `max_depth` hops."""
        visited: set[str] = set()
        edges: dict[str, dict[str, Any]] = {}
        frontier = set(start_node_ids)

        for depth in range(max_depth + 1):
            if not frontier:
                break
            visited |= frontier
            if depth == max_depth:
                break
            next_frontier: set[str] = set()
            for rel in RELATION_TYPES:
                rows = self._query(
                    f"""
                    MATCH (a:Node)-[r:{rel}]->(b:Node)
                    WHERE a.id IN $ids OR b.id IN $ids
                    RETURN a.id, b.id, r.description
                    """,
                    {"ids": list(frontier)},
                )
                for src, tgt, desc in rows:
                    edge = _edge(src, tgt, rel, desc)
                    edges[edge["id"]] = edge
                    next_frontier |= {src, tgt} - visited
            frontier = next_frontier

        return {"nodes": self.get_nodes(sorted(visited)), "edges": list(edges.values())}

    def close(self) -> None:
        self._conn.close()
        self._db.close()
