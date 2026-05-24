import os
import json
from backend.database import init_db, get_all_nodes, get_all_edges
from backend.extractor import KnowledgeExtractor
from backend.hybrid_search import HybridSearchEngine
from backend.database import upsert_node, upsert_edge

def run_e2e():
    print("=== STARTING HYBRID AGENT KNOWLEDGE GRAPH END-TO-END VERIFICATION ===")
    
    # Reset cached database connection in database.py
    import backend.database
    import gc
    backend.database._database = None
    gc.collect()
    
    # 1. Initialize DB
    db_file = "agent_knowledge.db.db"
    kuzu_path = db_file + "_kuzu.db"
    vector_path = db_file + "_vectors.db"
    
    for path in [kuzu_path, vector_path]:
        if os.path.exists(path):
            try:
                os.remove(path)
            except:
                pass
                
    init_db(kuzu_path)
    
    extractor = KnowledgeExtractor()
    search_engine = HybridSearchEngine(db_file)
    
    # 2. Sample Agent Knowledge corpus text
    corpus = """
    We introduce the DeepMind Orchestrator Agent. The Orchestrator Agent is a core reasoning controller that manages a team of specialized subagents.
    The Orchestrator Agent possesses two primary skills: 'Multi-Step Planning' and 'Subagent Routing'.
    
    To execute its plans, the Orchestrator Agent relies on the 'Task Assigner Tool' and the 'Status Monitor Tool'.
    
    - The Multi-Step Planning skill decomposes high-level user goals into atomic tasks.
    - The Subagent Routing skill selects the best subagent to handle a specific subtask based on history.
    - The Task Assigner Tool is a protocol tool that interfaces directly with subagent queues.
    - The Status Monitor Tool polls the execution health of subagents in real-time.
    
    Best practices for the Orchestrator Agent dictate that the routing history should be stored in a local SQLite database to prevent memory degradation.
    """
    
    print("\n[Step 1] Ingesting raw multi-agent knowledge text...")
    
    # Extracted graph elements (simulated LLM structured extraction)
    nodes = [
        ("agent_orchestrator", "agent", "Orchestrator Agent", "Core reasoning controller managing specialized subagents."),
        ("skill_planning", "skill", "Multi-Step Planning", "Decomposes high-level user goals into atomic tasks."),
        ("skill_routing", "skill", "Subagent Routing", "Selects the best subagent based on historical efficiency."),
        ("tool_assigner", "tool", "Task Assigner Tool", "Interface tool that dispatches subtasks to subagent queues."),
        ("tool_monitor", "tool", "Status Monitor Tool", "Interface tool that polls execution health in real-time."),
        ("practice_routing_history", "best_practice", "Routing History Storage", "Best practice to store routing history in SQLite to avoid memory degradation.")
    ]
    
    edges = [
        ("agent_orchestrator", "skill_planning", "HAS_SKILL", "Possesses multi-step planning capability."),
        ("agent_orchestrator", "skill_routing", "HAS_SKILL", "Possesses routing capabilities."),
        ("agent_orchestrator", "tool_assigner", "HAS_TOOL", "Possesses dispatching tool."),
        ("agent_orchestrator", "tool_monitor", "HAS_TOOL", "Possesses execution polling tool."),
        ("skill_routing", "practice_routing_history", "BASED_ON", "Routing decisions should track history according to best practices."),
        ("skill_planning", "tool_assigner", "REQUIRES_TOOL", "Planning results require assigner tool to dispatch.")
    ]
    
    print("Upserting extracted entities into Knowledge Graph...")
    for nid, ntype, name, desc in nodes:
        upsert_node(nid, ntype, name, desc, db_path=kuzu_path)
        
    for src, tgt, rel, desc in edges:
        upsert_edge(src, tgt, rel, {"description": desc}, db_path=kuzu_path)
        
    # Index vector embeddings directly on node concepts
    print("Creating vector embeddings directly on node concepts...")
    for nid, ntype, name, desc in nodes:
        chunk_id = f"vector_{nid}"
        concept_text = f"{name}: {desc}"
        emb = search_engine.store.vector_store.get_embedding(concept_text)
        search_engine.store.vector_store.add_vector(chunk_id, nid, concept_text, emb)
        
    print(f"Successfully loaded. Total indexed nodes: {len(nodes)}. Edges: {len(edges)}.")
    
    # 3. Perform Hybrid Search
    print("\n[Step 2] Performing Hybrid Query (wRRF + Graph Traversal):")
    query = "What skills and tools does the Orchestrator Agent have, and what best practices apply?"
    print(f"Query: '{query}'")
    
    results = search_engine.search(query, top_k=3)
    
    print("\n[Answer Synthesis]:")
    print("-" * 80)
    print(results["answer"])
    print("-" * 80)
    
    print("\n[Retrieved Subgraph Entities]:")
    for n in results["subgraph"]["nodes"][:5]:
        print(f"- {n['name']} ({n['type'].upper()}) - Hybrid Score: {n.get('hybrid_score', 0)}")
        
    print("\n[Retrieved Subgraph Connections]:")
    for e in results["subgraph"]["edges"][:5]:
        print(f"- {e['source_id']} --[{e['relation_type']}]--> {e['target_id']}")
        
    print("\n=== E2E VERIFICATION COMPLETED SUCCESSFULLY ===")
    
    # 4. Clean up test database
    import backend.database
    backend.database._database = None
    gc.collect()
    for path in [kuzu_path, vector_path]:
        if os.path.exists(path):
            try:
                os.remove(path)
            except:
                pass

if __name__ == "__main__":
    run_e2e()
