import os
import unittest
import shutil
import gc
from backend.database import init_db, get_node, get_all_nodes, get_all_edges
from backend.vector_store import VectorStore
from backend.ingestion_agent import harvester, HarvestState

class TestLibrarianIngestionAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db = "test_ingest_db.db"
        cls.kuzu_path = cls.test_db + "_kuzu.db"
        cls.vector_path = cls.test_db + "_vectors_lance"
        
        # Clean up files if they exist
        for path in [cls.kuzu_path, cls.vector_path]:
            if os.path.exists(path):
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                except Exception:
                    pass
                    
        # Reset cached database connection in database.py
        import backend.database
        backend.database._database = None
        
        # Initialize Kuzu schema
        init_db(cls.kuzu_path)
        
        # Temporarily mock the environment database paths
        import backend.database
        backend.database.DB_FILE = cls.kuzu_path
        
        import backend.vector_store
        backend.vector_store.DEFAULT_DB_DIR = cls.vector_path

        from backend.settings import settings
        settings.kuzu_db_path = cls.kuzu_path
        settings.lancedb_path = cls.vector_path

    @classmethod
    def tearDownClass(cls):
        import backend.database
        backend.database._database = None
        gc.collect()
        
        for path in [cls.kuzu_path, cls.vector_path]:
            if os.path.exists(path):
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                except Exception:
                    pass

    def test_01_first_ingest(self):
        # First-time ingestion of a new software concept
        text = """
        The Factory Pattern is a creational design pattern that provides an interface for creating objects in a superclass,
        but allows subclasses to alter the type of objects that will be created. It helps decouple instantiation logic.
        """
        state = HarvestState(text=text, source_title="Factory Pattern Article")
        result = harvester.invoke(state.model_dump()) # Invoke with dictionary or state model_dump
        
        self.assertIsNone(result.get("error"))
        self.assertEqual(result.get("status"), "success")
        self.assertGreater(len(result.get("committed_nodes", [])), 0)
        
        # Verify the node exists and is active in Kuzu Graph
        node_id = result.get("committed_nodes")[0]
        node = get_node(node_id, db_path=self.kuzu_path)
        self.assertIsNotNone(node)
        self.assertEqual(node["status"], "active")
        self.assertEqual(node["superseded_by"], "")
        
        # Verify it exists in LanceDB vector store
        store = VectorStore(self.vector_path)
        self.assertEqual(store.table.count_rows(), len(result.get("committed_nodes")))

    def test_02_duplicate_ingest(self):
        # Try ingesting the exact same content again (Deduplication Check)
        text = """
        The Factory Pattern is a creational design pattern that provides an interface for creating objects in a superclass,
        but allows subclasses to alter the type of objects that will be created. It helps decouple instantiation logic.
        """
        state = HarvestState(text=text, source_title="Duplicate Factory Pattern Article")
        result = harvester.invoke(state.model_dump())
        
        self.assertIsNone(result.get("error"))
        print("\nDEBUG test_02 result:", result)
        # Should detect as duplicate and avoid writing new nodes
        for nid, decision_info in result.get("conflict_decisions", {}).items():
            self.assertEqual(decision_info["decision"], "duplicate")
            
        self.assertEqual(len(result.get("committed_nodes", [])), 0)

    def test_03_supersedes_update_ingest(self):
        # Ingest an updated version of the same concept (Supersession/Update Check)
        
        # Let's fetch the original node ID
        nodes = get_all_nodes(db_path=self.kuzu_path)
        factory_node = next(n for n in nodes if "factory" in n["id"])
        old_node_id = factory_node["id"]
        
        # Trigger an update ingestion by using a highly similar description but superior details with critical update keyword
        text = """
        The Factory Pattern is a creational design pattern providing a standard interface for object creation.
        CRITICAL UPDATE: In modern Python development, the Factory Pattern is best implemented using classmethods
        or protocols instead of abstract classes, which reduces boilerplate code and improves dynamic type checking.
        """
        state = HarvestState(text=text, source_title="Modern Factory Pattern Guide")
        result = harvester.invoke(state.model_dump())
        
        self.assertIsNone(result.get("error"))
        print("\nDEBUG test_03 result:", result)
        self.assertEqual(result.get("status"), "success")
        
        # Check if the old node was deprecated and superseded by a new one
        updated_old_node = get_node(old_node_id, db_path=self.kuzu_path)
        self.assertEqual(updated_old_node["status"], "deprecated")
        self.assertNotEqual(updated_old_node["superseded_by"], "")
        
        new_node_id = updated_old_node["superseded_by"]
        new_node = get_node(new_node_id, db_path=self.kuzu_path)
        self.assertIsNotNone(new_node)
        self.assertEqual(new_node["status"], "active")
        
        # Verify a SUPERSEDES edge exists between them
        edges = get_all_edges(db_path=self.kuzu_path)
        supersedes_edge = next((e for e in edges if e["relation_type"] == "SUPERSEDES" and e["source_id"] == new_node_id and e["target_id"] == old_node_id), None)
        self.assertIsNotNone(supersedes_edge)

if __name__ == "__main__":
    unittest.main()
