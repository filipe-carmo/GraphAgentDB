import os
import json
from typing import List, Dict, Any, Optional
import numpy as np
import lancedb
import pyarrow as pa
from google import genai
from google.genai.errors import APIError
from .settings import settings

DEFAULT_DB_DIR = settings.lancedb_path

class VectorStore:
    def __init__(self, db_path: str = None):
        if db_path is None:
            self.db_path = DEFAULT_DB_DIR
        else:
            # Backwards compatibility: if an SQLite .db path is passed,
            # translate it to a corresponding LanceDB folder path.
            if db_path.endswith(".db"):
                self.db_path = db_path.replace(".db", "_lance")
            else:
                self.db_path = db_path
                
        self._init_db()
        self.client = self._init_gemini_client()

    def _init_db(self):
        """Creates the vectors table in the LanceDB database if it doesn't exist."""
        dir_name = os.path.dirname(self.db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
            
        # Connect to serverless LanceDB database
        self.db = lancedb.connect(self.db_path)
        
        # Schema representing the vector elements (supporting status filtering)
        schema = pa.schema([
            pa.field("chunk_id", pa.string()),
            pa.field("node_id", pa.string()),
            pa.field("text", pa.string()),
            pa.field("status", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), settings.embed_dim)) # text-embedding-004 is 768-dim
        ])
        
        if "vectors" not in self.db.list_tables().tables:
            self.db.create_table("vectors", schema=schema)
        self.table = self.db.open_table("vectors")

    def _init_gemini_client(self) -> Optional[genai.Client]:
        """Initializes the Gemini client if the GEMINI_API_KEY environment variable is set."""
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            return genai.Client(api_key=api_key)
        return None

    def get_embedding(self, text: str) -> List[float]:
        """
        Generates a vector embedding for the input text using Gemini's text-embedding-004 model.
        Falls back to a deterministic semantic mockup if GEMINI_API_KEY is not available.
        """
        if self.client:
            try:
                response = self.client.models.embed_content(
                    model=settings.embed_model,
                    contents=text
                )
                if response.embeddings:
                    return response.embeddings[0].values
            except Exception as e:
                print(f"Gemini embedding generation failed: {e}. Falling back to fallback model.")
        
        # Fallback deterministic embedding mechanism (useful for testing or if no API key is provided)
        # Generates a 768-dimensional normalized mock vector based on the string hash
        return self._generate_fallback_embedding(text)

    def _generate_fallback_embedding(self, text: str, dimensions: int = None) -> List[float]:
        """Generates a deterministic pseudo-random unit vector based on the text hash."""
        if dimensions is None:
            dimensions = settings.embed_dim
        state = sum(ord(c) * (i + 1) for i, c in enumerate(text))
        rng = np.random.default_rng(state)
        vector = rng.standard_normal(dimensions)
        normalized = vector / np.linalg.norm(vector)
        return normalized.tolist()

    def add_vector(self, chunk_id: str, node_id: str, text: str, embedding: List[float], status: str = "active"):
        """Saves a chunk's text and its embedding vector associated with a parent Node."""
        # LanceDB allows deletion by primary identifier before appending to avoid duplication
        try:
            self.table.delete(f"chunk_id = '{chunk_id}'")
        except Exception:
            pass
            
        self.table.add([{
            "chunk_id": chunk_id,
            "node_id": node_id,
            "text": text,
            "status": status,
            "vector": embedding
        }])

    def search_vectors(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Performs a cosine similarity vector search against all stored chunks.
        Returns:
            List of matches, each containing node_id, chunk_id, text, and score.
        """
        if self.table.count_rows() == 0:
            return []
            
        query_vector = self.get_embedding(query)
        
        # Execute cosine similarity search in LanceDB (filtering for active status)
        results = (
            self.table.search(query_vector)
            .where("status = 'active'")
            .metric("cosine")
            .limit(top_k)
            .to_list()
        )
        
        formatted_results = []
        for r in results:
            # Cosine similarity = 1 - cosine distance
            dist = r.get("_distance", 1.0)
            score = 1.0 - dist
            formatted_results.append({
                "chunk_id": r["chunk_id"],
                "node_id": r["node_id"],
                "text": r["text"],
                "score": float(score)
            })
            
        return formatted_results
