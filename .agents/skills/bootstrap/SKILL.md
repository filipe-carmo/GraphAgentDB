---
name: synapse-bootstrap
description: >
  Scans project directories recursively for manifest package dependencies (package.json, pyproject.toml, requirements.txt, Cargo.toml),
  queries active property subgraphs matching those stack keys, and generates developer laws root context (GEMINI.md).
---

# Synapse Bootstrap: Developer Context Generator

## Overview
The Bootstrap skill automates project directory scanning and compiles developercontext reports. It runs the Project Consultant LangGraph agent to detect the tech stack, query LanceDB + KuzuDB for active architectural rules, list deprecated code patterns linked by `SUPERSEDES` pointers, and bootstrap a root-level `GEMINI.md` file.

---

## Usage

### 1. Bootstrapping via Terminal CLI
Run the `bootstrap` command pointing to a local workspace path:
```powershell
$env:PYTHONIOENCODING="utf-8"
.venv\Scripts\python cli.py bootstrap "c:\Users\filip\GraphAgentDB"
```

### 2. Bootstrapping via API endpoint
Execute a POST request to `/api/consult/bootstrap` carrying the target project root path:
```json
{
  "project_path": "c:\\Users\\filip\\GraphAgentDB"
}
```

---

## Output Metrics
On success, the bootstrapping returns:
*   **Detected Stack Keys**: Array of libraries and packages scanned (e.g. `fastapi`, `lancedb`).
*   **Written Paths**: Array of context files created on disk.
*   **GEMINI.md**: Elegant root-level developer guidelines context compiled.
*   **Local Backup**: Report backup cached at `backend/exports/{project_name}.md`.
