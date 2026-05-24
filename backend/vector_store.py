import os
import json
import sqlite3
from typing import List, Dict, Any, Optional
import numpy as np
from google import genai
from google.genai.errors import APIError

DB_FILE = os.path.join(os.path.dirname(__file__), "vector_index.db")

class VectorStore:
    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        self._init_db()
        self.client = self._init_gemini_client()

    def _init_db(self):
        """Creates the vectors table in the SQLite database if it doesn't exist."""
        dir_name = os.path.dirname(self.db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS vectors (
                chunk_id TEXT PRIMARY KEY,
                node_id TEXT NOT NULL,
                text TEXT NOT NULL,
                embedding TEXT NOT NULL -- JSON serialized list of floats
            );
            """)
            conn.commit()

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
                    model="text-embedding-004",
                    contents=text
                )
                if response.embeddings:
                    return response.embeddings[0].values
            except Exception as e:
                print(f"Gemini embedding generation failed: {e}. Falling back to fallback model.")
        
        # Fallback deterministic embedding mechanism (useful for testing or if no API key is provided)
        # Generates a 768-dimensional normalized mock vector based on the string hash
        return self._generate_fallback_embedding(text)

    def _generate_fallback_embedding(self, text: str, dimensions: int = 768) -> List[float]:
        """Generates a deterministic pseudo-random unit vector based on the text hash."""
        state = sum(ord(c) * (i + 1) for i, c in enumerate(text))
        rng = np.random.default_rng(state)
        vector = rng.standard_normal(dimensions)
        normalized = vector / np.linalg.norm(vector)
        return normalized.tolist()

    def add_vector(self, chunk_id: str, node_id: str, text: str, embedding: List[float]):
        """Saves a chunk's text and its embedding vector associated with a parent Node."""
        embedding_str = json.dumps(embedding)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO vectors (chunk_id, node_id, text, embedding)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chunk_id) DO UPDATE SET
                node_id = excluded.node_id,
                text = excluded.text,
                embedding = excluded.embedding;
            """, (chunk_id, node_id, text, embedding_str))
            conn.commit()

    def search_vectors(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Performs a cosine similarity vector search against all stored chunks.
        Returns:
            List of matches, each containing node_id, chunk_id, text, and score.
        """
        query_vector = self.get_embedding(query)
        
        # Fetch all stored vectors
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT chunk_id, node_id, text, embedding FROM vectors")
            rows = cursor.fetchall()
            
        if not rows:
            return []
            
        chunk_ids = []
        node_ids = []
        texts = []
        embeddings = []
        
        for r in rows:
            chunk_ids.append(r["chunk_id"])
            node_ids.append(r["node_id"])
            texts.append(r["text"])
            embeddings.append(json.loads(r["embedding"]))
            
        # Convert lists to NumPy arrays for vectorized cosine similarity
        embedding_matrix = np.array(embeddings) # shape: (num_vectors, dim)
        query_arr = np.array(query_vector)     # shape: (dim,)
        
        # Cosine similarity formula: dot(A, B) / (norm(A) * norm(B))
        # Since we normalize query and stored vectors, it's just matrix multiplication!
        norms_matrix = np.linalg.norm(embedding_matrix, axis=1)
        norm_query = np.linalg.norm(query_arr)
        
        # Prevent divide-by-zero
        norms_matrix[norms_matrix == 0] = 1e-10
        if norm_query == 0:
            norm_query = 1e-10
            
        scores = np.dot(embedding_matrix, query_arr) / (norms_matrix * norm_query)
        
        # Get top K indices
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            results.append({
                "chunk_id": chunk_ids[idx],
                "node_id": node_ids[idx],
                "text": texts[idx],
                "score": float(scores[idx])
            })
            
        return results
