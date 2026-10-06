"""LanceDB vector index holding one embedding per knowledge node."""

import logging
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa

from .models import NodeStatus

logger = logging.getLogger(__name__)

TABLE_NAME = "vectors"


def _quote(value: str) -> str:
    """Quotes a string literal for a LanceDB SQL filter."""
    return "'" + value.replace("'", "''") + "'"


class VectorStore:
    def __init__(self, db_path: str | Path, embed_dim: int):
        db_path = Path(db_path)
        db_path.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(db_path))
        schema = pa.schema(
            [
                pa.field("chunk_id", pa.string()),
                pa.field("node_id", pa.string()),
                pa.field("text", pa.string()),
                pa.field("status", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), embed_dim)),
            ]
        )
        self.table = self.db.create_table(TABLE_NAME, schema=schema, exist_ok=True)

    def count(self) -> int:
        return self.table.count_rows()

    def add_vector(
        self,
        chunk_id: str,
        node_id: str,
        text: str,
        embedding: list[float],
        status: str = NodeStatus.ACTIVE.value,
    ) -> None:
        """Inserts a vector, replacing any existing row with the same chunk id."""
        self.table.delete(f"chunk_id = {_quote(chunk_id)}")
        self.table.add(
            [
                {
                    "chunk_id": chunk_id,
                    "node_id": node_id,
                    "text": text,
                    "status": status,
                    "vector": embedding,
                }
            ]
        )

    def set_status(self, node_id: str, status: str) -> None:
        self.table.update(where=f"node_id = {_quote(node_id)}", values={"status": status})

    def search(self, query_vector: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        """Cosine-similarity search over active vectors. Score is 1 - cosine distance."""
        if self.count() == 0:
            return []
        rows = (
            self.table.search(query_vector)
            .where(f"status = {_quote(NodeStatus.ACTIVE.value)}")
            .metric("cosine")
            .limit(top_k)
            .to_list()
        )
        return [
            {
                "chunk_id": r["chunk_id"],
                "node_id": r["node_id"],
                "text": r["text"],
                "score": float(1.0 - r.get("_distance", 1.0)),
            }
            for r in rows
        ]
