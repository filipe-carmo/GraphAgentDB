import os
import re
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END

from .store import KnowledgeStore

class ConsultState(BaseModel):
    project_path: str = "."
    stack_keys: List[str] = Field(default_factory=list)
    active_nodes: List[Dict[str, Any]] = Field(default_factory=list)
    markdown_output: str = ""
    written_paths: List[str] = Field(default_factory=list)
    status: str = "pending"
    error: Optional[str] = None

def detect_stack(project_dir: Path) -> List[str]:
    """Scans local manifests recursively for package names to identify the technology stack."""
    stack = set()
    
    # 1. Node.js dependencies
    pkg = project_dir / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            deps = data.get("dependencies", {})
            deps.update(data.get("devDependencies", {}))
            for k in deps:
                clean_k = k.lower().lstrip("@").split("/")[-1]
                stack.add(clean_k)
        except Exception:
            pass
            
    # 2. Python dependencies
    pyproj = project_dir / "pyproject.toml"
    if pyproj.exists():
        try:
            text = pyproj.read_text(encoding="utf-8")
            # Extract standard dependency names using simple regex
            matches = re.findall(r'["\']([\w\-]+)["\']', text)
            for m in matches:
                if m.replace("-", "").isalnum():
                    stack.add(m.lower())
        except Exception:
            pass
            
    req = project_dir / "requirements.txt"
    if req.exists():
        try:
            for line in req.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    pkg_name = re.split(r'[>=<!]', line)[0].strip().lower()
                    if pkg_name:
                        stack.add(pkg_name)
        except Exception:
            pass
            
    # 3. Rust dependencies
    cargo = project_dir / "Cargo.toml"
    if cargo.exists():
        try:
            for line in cargo.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.strip().startswith("["):
                    name = line.split("=")[0].strip().strip('"').lower()
                    if name:
                        stack.add(name)
        except Exception:
            pass
            
    return sorted(list(stack))

def detect_stack_node(state: ConsultState) -> dict:
    """Scans the repository path and registers stack keys."""
    print(f"[Consultant] Scanning project stack dependencies at: '{state.project_path}'")
    proj_path = Path(state.project_path)
    if not proj_path.exists():
        return {"error": f"Target project path does not exist: {state.project_path}"}
        
    stack_keys = detect_stack(proj_path)
    print(f"[Consultant] Detected technology stack: {stack_keys}")
    return {"stack_keys": stack_keys}

def query_graph_node(state: ConsultState) -> dict:
    """Uses LanceDB hybrid search to find nodes related to the stack, then fetches active Kuzu subgraphs."""
    if state.error:
        return {}
        
    store = KnowledgeStore()
    if not state.stack_keys:
        # Fallback if no specific tech stack found: fetch all active nodes to make context grounded
        print("[Consultant] No stack keys detected. Defaulting to general active knowledge.")
        nodes = store.get_all_nodes()
        active = [n for n in nodes if n["status"] == "active"]
        return {"active_nodes": active}
        
    print("[Consultant] Querying graph + vectors for stack-relevant developer rules...")
    matched_node_ids = set()
    
    # Semantic search matches for each detected package/tech key
    for key in state.stack_keys:
        hits = store.semantic_search(key, top_k=2)
        for h in hits:
            # We want high confidence semantic matches
            if h["score"] > 0.65:
                matched_node_ids.add(h["node_id"])
                
    if not matched_node_ids:
        # Final fallback: search descriptions for matching keys
        all_nodes = store.get_all_nodes()
        for node in all_nodes:
            node_desc = node.get("description", "").lower()
            node_name = node.get("name", "").lower()
            for key in state.stack_keys:
                if key in node_desc or key in node_name:
                    if node["status"] == "active":
                        matched_node_ids.add(node["id"])
                        
    # Fetch active subgraph around matched nodes up to depth 2
    subgraph = store.get_subgraph(list(matched_node_ids), max_depth=2)
    active_subgraph_nodes = [n for n in subgraph["nodes"] if n["status"] == "active"]
    
    print(f"[Consultant] Retrieved {len(active_subgraph_nodes)} active developer concepts.")
    return {"active_nodes": active_subgraph_nodes}

GLOBAL_TEMPLATE = """# 🔮 Agent Knowledge Synapse — Project Context
<!-- Generated by Agent Knowledge Synapse. Run `synapse bootstrap` to refresh. -->

This document establishes the conceptual developer context for the project **{project_name}**. It provides guidelines, architectural best practices, and details active versus deprecated developer patterns.

---

## 🛠️ Detected Technology Stack
{stack_list}

---

## 📜 Active Architectural Principles & Guidelines
{guidelines_section}

---

## ⚠️ Deprecated & Superseded Patterns (DO NOT USE)
{deprecated_section}

---

## ⚡ Meta
*   **Context Generated**: {timestamp} UTC
*   **Active Rules Compiled**: {node_count} nodes
"""

def format_guidelines(nodes: List[Dict[str, Any]]) -> str:
    if not nodes:
        return "_No active architecture principles found matching the detected tech stack._"
    
    lines = []
    for n in nodes:
        lines.append(f"### 🏷️ {n['name']} (`{n['type'].upper()}`)")
        lines.append(f"> ID: `{n['id']}`")
        lines.append("")
        lines.append(n["description"])
        lines.append("")
    return "\n".join(lines)

def format_deprecated(project_path: str) -> str:
    # Query database for deprecated nodes
    store = KnowledgeStore()
    all_nodes = store.get_all_nodes()
    deprecated_nodes = [n for n in all_nodes if n["status"] == "deprecated"]
    
    if not deprecated_nodes:
        return "_No deprecated architectural patterns documented._"
        
    lines = []
    for n in deprecated_nodes:
        replacement = n.get("superseded_by", "N/A")
        reason = n.get("supersession_reason", "Updated paradigm.")
        lines.append(f"*   **{n['name']}** (ID: `{n['id']}`) — *DEPRECATED*.")
        lines.append(f"    *   *Superseded By*: `{replacement}`")
        lines.append(f"    *   *Reason*: {reason}")
    return "\n".join(lines)

def generate_markdown_node(state: ConsultState) -> dict:
    """Compiles the retrieved concepts into a formatted markdown structure."""
    if state.error:
        return {}
        
    proj_name = Path(state.project_path).resolve().name or "Workspace"
    stack_list = "\n".join(f"*   `{k}`" for k in state.stack_keys) if state.stack_keys else "_No standard stack manifests detected._"
    
    guidelines = format_guidelines(state.active_nodes)
    deprecated = format_deprecated(state.project_path)
    
    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).isoformat()
    
    md = GLOBAL_TEMPLATE.format(
        project_name=proj_name,
        stack_list=stack_list,
        guidelines_section=guidelines,
        deprecated_section=deprecated,
        timestamp=timestamp,
        node_count=len(state.active_nodes)
    )
    
    return {"markdown_output": md}

def write_files_node(state: ConsultState) -> dict:
    """Writes the GEMINI.md context file to the target path and creates a local backup."""
    if state.error or not state.markdown_output:
        return {}
        
    proj_path = Path(state.project_path)
    written_paths = []
    
    # 1. Write project-level GEMINI.md
    try:
        main_file = proj_path / "GEMINI.md"
        main_file.write_text(state.markdown_output, encoding="utf-8")
        written_paths.append(str(main_file))
        print(f"[Consultant] Successfully generated developer context at {main_file}")
    except Exception as e:
        return {"error": f"Failed to write GEMINI.md in project path: {e}"}
        
    # 2. Write local backup in exports/
    try:
        exports_dir = Path(__file__).parent / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        backup_file = exports_dir / f"{proj_path.resolve().name}.md"
        backup_file.write_text(state.markdown_output, encoding="utf-8")
        written_paths.append(str(backup_file))
        print(f"[Consultant] Backed up project context report at {backup_file}")
    except Exception as e:
        print(f"[Consultant] Failed to write backup context report: {e}")
        
    return {
        "written_paths": written_paths,
        "status": "success"
    }

# Compile Consultant Graph
consult_workflow = StateGraph(ConsultState)
consult_workflow.add_node("detect_stack", detect_stack_node)
consult_workflow.add_node("query_graph", query_graph_node)
consult_workflow.add_node("generate_markdown", generate_markdown_node)
consult_workflow.add_node("write_files", write_files_node)

consult_workflow.set_entry_point("detect_stack")
consult_workflow.add_edge("detect_stack", "query_graph")
consult_workflow.add_edge("query_graph", "generate_markdown")
consult_workflow.add_edge("generate_markdown", "write_files")
consult_workflow.add_edge("write_files", END)

consultant = consult_workflow.compile()
