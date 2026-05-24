# 🔮 Agent Knowledge Synapse: Context & Hand-Off

This document serves as the developer hand-off context for the **Agent Knowledge Synapse** hybrid Property Graph + Vector database system. It outlines the architectural design, recent accomplishments, key findings, and planned future milestones to ensure seamless development continuation.

---

## 🚀 System & Project Overview

The **Agent Knowledge Synapse** is a local, high-performance, concept-first knowledge retrieval system designed to support advanced multi-agent systems and software engineering agents.

Unlike traditional document-centric RAG models, this system implements an **Agent-as-a-Graph** architecture. It splits raw ingested text into isolated, pure domain concepts (**Agents, Skills, Tools, Best Practices, Theories, and Concepts**), mapping them visually and semantically into:
1. **A Pure Property Graph Database (Kùzu DB)** queried via **openCypher** for structural relationships and graph traversals.
2. **A Separate LanceDB Vector Database** queried via **LanceDB** for concept-description similarity search.

These two stores are unified under a **Weighted Reciprocal Rank Fusion (wRRF)** ranking engine and synthesized into grounded responses using programmatic cascade loops through the **Antigravity 2.0 IDE Agent Harness (`agentapi`)**.

---

## 📁 Cleaned Codebase Architecture

All stray test database folders and obsolete mock-up files have been purged from the root. The repository is pristine:

```
c:\Users\filip\GraphAgentDB\
├── .agents/
│   ├── context/
│   │   ├── context.md                    # Developer hand-off guidelines (This file)
│   │   ├── implementation_plan.md        # The original implementation plan
│   │   └── resumed_integration_plan.md    # The newly executed integration blueprint
│   ├── agents/
│   │   ├── librarian.md                  # Librarian ingestion agent descriptor
│   │   └── consultant.md                 # Consultant bootstrapping agent descriptor
│   └── skills/
│       ├── ingestion/SKILL.md            # synapse-ingest skill
│       ├── bootstrap/SKILL.md            # synapse-bootstrap skill
│       └── search/SKILL.md               # synapse-search skill
├── backend/
│   ├── database.py       # Kùzu graph schemas, Cypher connections, and BFS expansions
│   ├── vector_store.py   # Embedding services, LanceDB connection, and fallbacks
│   ├── store.py          # Unified database facade class (KnowledgeStore)
│   ├── settings.py       # Pydantic settings loading backend/config.json
│   ├── config.json       # Central configurations and database paths
│   ├── models.py         # Rigid Pydantic node and document schemas
│   ├── harness.py        # Subprocess bridge executing Antigravity agentapi CLI commands
│   ├── extractor.py      # Scraping logic and structured prompts with concept constraints
│   ├── hybrid_search.py  # wRRF structural boosting, Cypher BFS, and synthesis cascades
│   ├── main.py           # FastAPI service routing, status endpoints, and vis-network formatting
│   ├── kuzu_db.db        # Core active Kùzu Property Graph file
│   └── vector_index_lance/ # Core active LanceDB Vector database directory
├── frontend/
│   ├── index.html        # Responsive glassmorphic visual console
│   ├── style.css         # Stylings, gradients, transitions, and vis-network color tokens
│   └── app.js            # Vis-network topology renderers and real-time inspector panels
├── requirements.txt      # Python dependencies (kuzu, lancedb, pyarrow, numpy, etc.)
├── cli.py                # Command-line interface tool (synapse check, stats, doctor, etc.)
├── test_backend.py       # PyUnit test suite checking core DB node and edge operations
├── test_ingestion.py     # PyUnit test checking Librarian ingestion agent conflict resolution
├── test_e2e.py           # E2E pipeline script validating chunking, mapping, and wRRF search
└── GEMINI.md             # Developer bootstrap laws (Root context descriptor)
```

---

## 💎 Key Accomplishments & Refinements

1. **Pure Property Graph DB Migration (Kùzu)**:
   - Migrated fully to a pure graph engine utilizing Kùzu (`backend/database.py`).
   - Defined table schemas: `Node` (primary node table) and 8 explicit relationship tables: `HAS_SKILL`, `HAS_TOOL`, `REQUIRES_TOOL`, `BASED_ON`, `REFERENCES`, `MENTIONS`, `IS_A`, and `SUPERSEDES`.
2. **LanceDB Integration (High Performance)**:
   - Replaced SQLite vector storage with serverless LanceDB (`backend/vector_store.py`) to manage high-dimensional float search.
3. **Atomic Dual-Store Facade**:
   - Created `backend/store.py` (`KnowledgeStore` facade) orchestrating transactional Kuzu and LanceDB operations, ensuring synchronized data.
4. **Harvester Ingest Sequence Fixed**:
   - Inverted the insert sequence inside the Ingestion Agent so the new active concept is written *before* the deprecation cascades, ensuring openCypher matches successfully when drawing `SUPERSEDES` edges.
5. **Diagnostics CLI (`synapse doctor`)**:
   - Implemented an observability checker inside `cli.py` to evaluate env health.
6. **Glassmorphic Fronted Upgrades**:
   - Added the Consultant Console tab selector and context bootstrapping code display.
   - Styled Vis-Network mapping to fade deprecated elements and highlight superseded pointers.

---

## ⚡ Developer Execution Commands

### Run Unit Tests
```powershell
.venv\Scripts\python -m unittest test_backend.py
.venv\Scripts\python -m unittest test_ingestion.py
```

### Run Observability doctor
```powershell
$env:PYTHONIOENCODING="utf-8"
.venv\Scripts\python cli.py doctor
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
