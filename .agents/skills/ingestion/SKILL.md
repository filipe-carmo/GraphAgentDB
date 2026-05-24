---
name: synapse-ingest
description: >
  Scrapes technical URLs or direct markdown/raw text, distills concepts and relationships,
  resolves conflicts via semantic vector lookups, and persistently writes to KuzuDB + LanceDB.
---

# Synapse Ingestion: Crawler and harvester Ingestion

## Overview
The Ingestion skill ingests technical web pages or raw documentation strings into the **Agent Knowledge Synapse** hybrid database system. It runs the stateful Librarian LangGraph agent to extract isolated concepts, avoid duplicate concept insertions, and auto-link newer paradigm overrides using openCypher `SUPERSEDES` relationship edges.

---

## Usage

### 1. Ingesting via Terminal CLI
Run the `ingest` command using `cli.py` with environment unicode formatting:
```powershell
$env:PYTHONIOENCODING="utf-8"
.venv\Scripts\python cli.py ingest --url "https://microsoft.github.io/graphrag/"
```

Options:
*   `--url <str>`: The URL scraper path to download, cache, and harvest.
*   `--text <str>`: A direct block of markdown or documentation text to ingest.

### 2. Ingesting via API endpoint
Execute a POST request to `/api/ingest` with request body:
```json
{
  "url": "https://microsoft.github.io/graphrag/",
  "text": null
}
```

---

## Output Metrics
On success, the ingestion returns:
*   **Concepts Distilled**: The number of category concepts extracted.
*   **Relations Logged**: Predefined relationship connections discovered.
*   **Committed Nodes**: Array of final concept IDs added to KuzuDB + LanceDB.
*   **Cache File**: Saved clean raw content cached at `backend/cache/{source_hash}.txt`.
