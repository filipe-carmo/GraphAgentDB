---
name: synapse-search
description: >
  Performs hybrid search querying LanceDB vectors, dynamically traversing KuzuDB property graph neighbor nodes,
  applying wRRF structural boosting, and compiling grounded answer text.
---

# Synapse Search: Hybrid RAG Graph + Vector Search

## Overview
The Search skill executes a hybrid wRRF (Weighted Reciprocal Rank Fusion) and Cypher BFS traversal query. It identifies seed concepts using LanceDB vector similarity, queries KuzuDB openCypher for connected skills, tools, and practices, applies structural scoring boosts based on relationships (e.g. `HAS_SKILL`, `HAS_TOOL`), and synthesizes expert responses via Antigravity Harness or offline grounded compilers.

---

## Usage

### 1. Searching via Terminal CLI
Run the `search` command querying Synapse databases:
```powershell
$env:PYTHONIOENCODING="utf-8"
.venv\Scripts\python cli.py search "What skills does the Orchestrator Agent have?" --top-k 5
```

### 2. Searching via API endpoint
Execute a POST request to `/api/search` with search query parameters:
```json
{
  "query": "What skills does the Orchestrator Agent have?",
  "top_k": 5
}
```

---

## Output Structure
On query execution, search returns:
*   **Synthesized Answer**: Expert-level grounded text answer describing graph relationships.
*   **Retrieved Subgraph**: Array of connected nodes and relationship edges traversed.
*   **Source Snippets**: Bounded vector matching text passages and similarity percentages.
