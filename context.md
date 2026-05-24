# 🔮 Agent Knowledge Synapse: Context & Hand-Off

This document serves as the developer hand-off context for the **Agent Knowledge Synapse** hybrid Property Graph + Vector database system. It outlines the architectural design, recent accomplishments, key findings, and planned future milestones to ensure seamless development continuation.

---

## 🚀 System & Project Overview

The **Agent Knowledge Synapse** is a local, high-performance, concept-first knowledge retrieval system designed to support advanced multi-agent systems and software engineering agents.

Unlike traditional document-centric RAG models, this system implements an **Agent-as-a-Graph** architecture. It splits raw ingested text into isolated, pure domain concepts (**Agents, Skills, Tools, Best Practices, Theories, and Concepts**), mapping them visually and semantically into:
1. **A Pure Property Graph Database (Kùzu DB)** queried via **openCypher** for structural relationships and graph traversals.
2. **A Separate SQLite Vector Database** queried via **NumPy** for concept-description similarity search.

These two stores are unified under a **Weighted Reciprocal Rank Fusion (wRRF)** ranking engine and synthesized into grounded responses using programmatic cascade loops through the **Antigravity 2.0 IDE Agent Harness (`agentapi`)**.

---

## 📁 Cleaned Codebase Architecture

All stray test database folders and obsolete mock-up files have been purged from the root. The repository is pristine:

```
c:\Users\filip\GraphAgentDB\
├── backend/
│   ├── database.py       # Kùzu graph schemas, Cypher connections, and BFS expansions
│   ├── vector_store.py   # Embedding services, SQLite index, and NumPy cosine similarities
│   ├── harness.py        # Subprocess bridge executing Antigravity agentapi CLI commands
│   ├── extractor.py      # Scraping logic and structured prompts with concept constraints
│   ├── hybrid_search.py  # wRRF structural boosting, Cypher BFS, and synthesis cascades
│   ├── main.py           # FastAPI service routing, status endpoints, and vis-network formatting
│   ├── kuzu_db.db        # Core active Kùzu Property Graph file
│   └── vector_index.db   # Core active SQLite Vector index file
├── frontend/
│   ├── index.html        # Responsive glassmorphic visual console
│   ├── style.css         # Stylings, gradients, transitions, and vis-network color tokens
│   └── app.js            # Vis-network topology renderers and real-time inspector panels
├── requirements.txt      # Python dependencies (kuzu, numpy, beautifulsoup4, requests, etc.)
├── test_backend.py       # PyUnit test suite checking core DB node and edge operations
├── test_e2e.py           # E2E pipeline script validating chunking, mapping, and wRRF search
└── context.md            # Developer hand-off guidelines (This file)
```

---

## 💎 Key Accomplishments & Pivots

1. **Pure Property Graph DB Migration (Kùzu)**:
   - Migrated fully to a pure graph engine utilizing Kùzu (`backend/database.py`).
   - Defined table schemas: `Node` (primary node table) and 7 explicit relationship tables: `HAS_SKILL`, `HAS_TOOL`, `REQUIRES_TOOL`, `BASED_ON`, `REFERENCES`, `MENTIONS`, `IS_A`.
   - Traversed connections cleanly using Cypher queries and multi-depth BFS expansions in Python.
2. **Double-DB Segregation (Concurrent Safety)**:
   - Isolated SQLite (`vector_index.db`) and Kùzu (`kuzu_db.db`) databases into separate files, preventing disk file locks and ensuring safe, concurrent execution.
3. **Pure Conceptual Isolation (No Origin Metadata)**:
   - Overhauled standard LLM extractions (`backend/extractor.py`) to prevent document metadata, URLs, page titles, or page references from polluting the graph.
   - Refined the deterministic offline builder to extract clean, pure concepts (e.g. SOLID, Design Patterns, OOP) and connect them directly.
   - Standardized visual labels and Synthesis outputs to refer to **"Concept Snippets"** and **"Concept Definitions"** instead of "Source Chunks".
4. **Ingestion of lp-foundations (Software Design Course)**:
   - Crawled and successfully indexed concepts from `DareData/lp-foundations` on Software Design, including **SOLID Principles, Unit Testing, Factory Pattern, Adapter Pattern, Strategy Pattern, and Command Pattern**.
   - Verified that concept queries retrieve pure concept networks and map their topological pathways beautifully.

---

## 💡 Technical Gotchas & Cypher constraints in Kùzu

When continuing development on Kùzu and openCypher integrations, be mindful of these architectural rules:
*   **Database File Format**: In Kùzu `v0.11.0+`, the database path must represent a **file** (`backend/kuzu_db.db`), not a directory.
*   **No MERGE Support**: Kùzu does not support the Cypher `MERGE` clause. Node/Edge updates must run sequential check-and-insert blocks in Python.
*   **Parameter Passing Constraints**: Kùzu's parser throws exceptions if Cypher parameters are bound inside inline maps or relationship `SET` clauses (e.g. `SET r.description = $desc`). Instead, string-escape literals directly within the Cypher command (e.g. `SET r.description = '{desc_escaped}'`).
*   **No Wildcard Relationship Label Resolvers**: Wildcard relationships inside Cypher `MATCH (a)-[r]->(b)` will not resolve label metadata natively via `r._LABEL` or `TYPE(r)`. The only bulletproof method is to query relationships table-by-table (`-[r:HAS_TOOL]->`).

---

## 🔮 Future Developments & Next Steps

When continuing development, prioritize the following enhancements:

### 1. Dynamic User-Prompted Custom Edge Definitions
*   Currently, the relationship types are strictly bounded to the 7 predefined schemas in `backend/database.py`. 
*   *Plan*: Allow the system to automatically and dynamically alter Kùzu node/edge schemas (`ALTER TABLE ADD ...`) when the LLM extracts a novel, custom relationship type, providing unlimited topological flexibility.

### 2. Multi-threaded Folder Batch Ingest
*   Implement a command-line script or FastAPI endpoint `/api/ingest/directory` that reads a whole folder of Markdown files or source files recursively, strips comments, and feeds them into the extraction engine concurrently.

### 3. Server-Sent Events (SSE) Response Streaming
*   Modify `backend/main.py` and `backend/hybrid_search.py` to stream grounded responses token-by-token using `EventSource` in `frontend/app.js` instead of blocking on long Harness/LLM API calls.

### 4. Graph Topology Group Filtering
*   Update `frontend/app.js` and `frontend/index.html` to add toggles that hide or show specific entity groups (e.g., only show `tool` and `agent` nodes, or hide `theoretical_knowledge`) to make large-scale maps easily navigable.

### 5. Scale Vector Search with FAISS or sqlite-vec
*   As the database grows past thousands of nodes, transition from simple in-memory NumPy vectorized cosine similarity to **sqlite-vec** (SQLite native vector extension) or **FAISS** to keep retrieval times sub-millisecond.

---

## ⚡ Developer Execution Commands

### Run Unit Tests
```powershell
.venv\Scripts\python -m unittest test_backend.py
```

### Run End-to-End Ingest & Query Pipelines
```powershell
$env:PYTHONIOENCODING="utf-8"
.venv\Scripts\python test_e2e.py
```

### Spin Up FastAPI Backend
```powershell
.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```
