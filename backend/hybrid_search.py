import os
from typing import List, Dict, Any, Optional, Set
from google import genai
from .database import get_node, get_subgraph
from .vector_store import VectorStore
from .harness import call_harness_agent

class HybridSearchEngine:
    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self.db_path = db_path + "_kuzu.db"
            self.vector_store = VectorStore(db_path + "_vectors.db")
        else:
            self.db_path = os.path.join(os.path.dirname(__file__), "kuzu_db.db")
            self.vector_store = VectorStore(os.path.join(os.path.dirname(__file__), "vector_index.db"))
            
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None

    def search(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """
        Executes a hybrid search:
        1. Performs vector search on chunked document embeddings.
        2. Gathers primary matched nodes from the vector hits.
        3. Dynamically traverses the Kuzu property graph to assemble the connected subgraph.
        4. Applies a Weighted Reciprocal Rank Fusion (wRRF) style structural boosting mechanism.
        5. Synthesizes a grounded answer using the Antigravity 2.0 Harness (or fallback clients).
        """
        # Step 1: Vector similarity search
        vector_hits = self.vector_store.search_vectors(query, top_k=top_k)
        if not vector_hits:
            return {
                "answer": "No matching knowledge could be found in the database. Please ingest some URLs or prompts first.",
                "subgraph": {"nodes": [], "edges": []},
                "sources": []
            }

        # Step 2: Fetch primary node IDs from vector hits
        primary_node_ids = list(set(hit["node_id"] for hit in vector_hits))
        
        # Step 3: Graph Traversal - fetch neighbor subgraph from Kuzu Graph
        subgraph = get_subgraph(primary_node_ids, max_depth=2, db_path=self.db_path)
        
        # Step 4: wRRF / Structural Boosting (Agent-as-a-Graph style)
        node_scores = {}
        for hit in vector_hits:
            node_id = hit["node_id"]
            node_scores[node_id] = max(node_scores.get(node_id, 0), hit["score"])

        for edge in subgraph["edges"]:
            src = edge["source_id"]
            tgt = edge["target_id"]
            rel = edge["relation_type"]
            
            if rel == "HAS_TOOL" and tgt in node_scores:
                boost = node_scores[tgt] * 0.5
                node_scores[src] = node_scores.get(src, 0) + boost
            elif rel == "HAS_SKILL" and tgt in node_scores:
                boost = node_scores[tgt] * 0.4
                node_scores[src] = node_scores.get(src, 0) + boost
            elif rel == "REQUIRES_TOOL" and src in node_scores:
                boost = node_scores[src] * 0.3
                node_scores[tgt] = node_scores.get(tgt, 0) + boost

        # Append hybrid scores and sort nodes
        for node in subgraph["nodes"]:
            node["hybrid_score"] = round(node_scores.get(node["id"], 0.1), 3)
            
        subgraph["nodes"] = sorted(subgraph["nodes"], key=lambda x: x.get("hybrid_score", 0), reverse=True)

        # Step 5: Synthesize grounded response
        answer = self._synthesize_response(query, subgraph, vector_hits)

        return {
            "answer": answer,
            "subgraph": subgraph,
            "sources": vector_hits
        }

    def _synthesize_response(self, query: str, subgraph: Dict[str, Any], vector_hits: List[Dict[str, Any]]) -> str:
        """
        Synthesizes the final answer. Prioritizes the Antigravity Harness,
        falling back to direct Gemini APIs or a local offline compiler.
        """
        # Format context strings
        nodes_context = []
        for n in subgraph["nodes"]:
            nodes_context.append(f"- [{n['type'].upper()}] {n['name']} (ID: {n['id']}): {n['description']} [Score: {n.get('hybrid_score', 0)}]")
            
        edges_context = []
        for e in subgraph["edges"]:
            edges_context.append(f"- {e['source_id']} --({e['relation_type']})--> {e['target_id']}: {e['properties'].get('description', '')}")

        chunks_context = []
        for i, hit in enumerate(vector_hits):
            chunks_context.append(f"Concept Snippet {i+1} (Node: {hit['node_id']}, Sim: {round(hit['score'], 2)}):\n\"{hit['text']}\"")
 
        prompt = f"""
        You are a highly capable agent reasoning system that answers questions based on a local Property Graph and Vector database.
        Synthesize a detailed, expert-level response to the user's query using the retrieved entities, relationships, and concept text snippets.
        
        User Query: "{query}"
        
        RETIRIEVED AGENT KNOWLEDGE GRAPH:
        Entities (Sorted by relevance):
        {chr(10).join(nodes_context[:10])}
        
        Relationships:
        {chr(10).join(edges_context[:15])}
        
        RELEVANT CONCEPT SNIPPETS:
        ---
        {chr(10).join(chunks_context[:5])}
        ---
        
        Instructions:
        1. Base your answer directly on the retrieved entities, skills, tools, and best practices.
        2. Highlight how the tools and skills connect back to their parent agents based on the knowledge graph connections.
        3. Maintain a professional, technical, and objective tone.
        """
        
        # 1. Attempt synthesis via Antigravity 2.0 IDE Harness (agentapi)
        print("[Search Engine] Attempting response synthesis via IDE Harness (agentapi)...")
        harness_response = call_harness_agent(prompt)
        if harness_response:
            print("[Search Engine] Successfully synthesized response using IDE Harness.")
            return harness_response
 
        # 2. Fallback to Direct Gemini API
        if self.client:
            print("[Search Engine] Falling back to direct Gemini 2.5 API for response synthesis...")
            try:
                response = self.client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt
                )
                return response.text
            except Exception as e:
                print(f"[Search Engine] Direct Gemini API synthesis failed: {e}.")
 
        # 3. Double-fallback to Local Compiled synthesis
        print("[Search Engine] Falling back to local offline grounded synthesis compiler.")
        return self._compile_fallback_response(query, subgraph, vector_hits)
 
    def _compile_fallback_response(self, query: str, subgraph: Dict[str, Any], vector_hits: List[Dict[str, Any]]) -> str:
        """Grounded compilation of the retrieved context in case the model is unreachable."""
        ans = f"### Hybrid Search Results for: \"{query}\"\n\n"
        ans += "*(Note: Direct LLM/Harness bridge is offline. This is a grounded compilation of retrieved DB entities.)*\n\n"
        
        ans += "#### 🏷️ Top Retrieved Entities:\n"
        for n in subgraph["nodes"][:5]:
            ans += f"- **{n['name']}** (`{n['type']}`): {n['description']} *(Relevance: {n.get('hybrid_score', 0)})*\n"
            
        if subgraph["edges"]:
            ans += "\n#### 🕸️ Key Relationships in Subgraph:\n"
            for e in subgraph["edges"][:5]:
                src_node = next((n for n in subgraph["nodes"] if n["id"] == e["source_id"]), None)
                tgt_node = next((n for n in subgraph["nodes"] if n["id"] == e["target_id"]), None)
                src_name = src_node["name"] if src_node else e["source_id"]
                tgt_name = tgt_node["name"] if tgt_node else e["target_id"]
                ans += f"- **{src_name}** --[`{e['relation_type']}`]--> **{tgt_name}**\n"
                
        ans += "\n#### 📄 Primary Concept Snippet:\n"
        if vector_hits:
            ans += f"> \"{vector_hits[0]['text'][:400]}...\"\n"
            
        return ans
