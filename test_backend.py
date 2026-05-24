import os
import unittest
import shutil
import gc
from backend.database import init_db, upsert_node, upsert_edge, get_node, get_all_nodes, get_all_edges, get_subgraph, _database
from backend.vector_store import VectorStore

class TestAgentKnowledgeKuzuDB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db = "test_kuzu_db.db"
        if os.path.exists(cls.test_db):
            try:
                os.remove(cls.test_db)
            except:
                pass
            
        # Reset cached database connection in database.py
        import backend.database
        backend.database._database = None
        
        init_db(cls.test_db)

    @classmethod
    def tearDownClass(cls):
        # Explicitly close the cached connection in database.py if active
        import backend.database
        backend.database._database = None
        
        # Run garbage collector to release active file handles
        gc.collect()
        
        # Clean up database directory
        if os.path.exists(cls.test_db):
            try:
                os.remove(cls.test_db)
            except:
                pass

    def test_01_node_upsert(self):
        # Create an Agent node in Kuzu
        node = upsert_node(
            id="agent_alpha",
            type="agent",
            name="Alpha Agent",
            description="Alpha agent capable of writing python scripts.",
            db_path=self.test_db
        )
        self.assertEqual(node["id"], "agent_alpha")
        self.assertEqual(node["type"], "agent")
        
        # Verify it exists in Kuzu DB
        db_node = get_node("agent_alpha", db_path=self.test_db)
        self.assertIsNotNone(db_node)
        self.assertEqual(db_node["name"], "Alpha Agent")
        self.assertEqual(db_node["description"], "Alpha agent capable of writing python scripts.")

    def test_02_edge_upsert(self):
        # Create a Tool node first
        upsert_node(
            id="tool_python",
            type="tool",
            name="Python Interpreter",
            description="Runs standard python code locally.",
            db_path=self.test_db
        )
        
        # Connect Agent to Tool in Kuzu
        edge = upsert_edge(
            source_id="agent_alpha",
            target_id="tool_python",
            relation_type="HAS_TOOL",
            properties={"description": "Alpha Agent uses Python Interpreter tool."},
            db_path=self.test_db
        )
        
        self.assertEqual(edge["source_id"], "agent_alpha")
        self.assertEqual(edge["target_id"], "tool_python")
        self.assertEqual(edge["relation_type"], "HAS_TOOL")
        
        # Verify edge exists in Kuzu
        edges = get_all_edges(db_path=self.test_db)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["relation_type"], "HAS_TOOL")

    def test_03_subgraph_traversal(self):
        # Fetch subgraph around agent_alpha
        subgraph = get_subgraph(["agent_alpha"], max_depth=1, db_path=self.test_db)
        self.assertEqual(len(subgraph["nodes"]), 2) # agent_alpha + tool_python
        self.assertEqual(len(subgraph["edges"]), 1)
        
        node_ids = [n["id"] for n in subgraph["nodes"]]
        self.assertIn("agent_alpha", node_ids)
        self.assertIn("tool_python", node_ids)

    def test_04_vector_store(self):
        # Initialize a vector index using same DB file context (it uses standard sqlite internally for embeddings)
        vector_db = "test_vectors.db"
        if os.path.exists(vector_db):
            os.remove(vector_db)
            
        store = VectorStore(vector_db)
        
        # Test mock embedding generation
        emb1 = store.get_embedding("Run python scripts in a sandboxed environment")
        self.assertEqual(len(emb1), 768)
        
        # Add vector chunk linked to tool_python
        store.add_vector(
            chunk_id="chunk_python_0",
            node_id="tool_python",
            text="Run python scripts in a sandboxed environment with stdout and stderr output capture",
            embedding=emb1
        )
        
        # Perform similarity search
        hits = store.search_vectors("how do i execute python code?", top_k=1)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["node_id"], "tool_python")
        self.assertGreater(hits[0]["score"], 0.0)
        
        # Clean up vector database
        if os.path.exists(vector_db):
            try:
                os.remove(vector_db)
            except PermissionError:
                pass

if __name__ == "__main__":
    unittest.main()
