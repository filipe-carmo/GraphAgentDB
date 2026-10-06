"""Loads a small demo graph so the UI has something to show without an API key.

python examples/seed_demo.py
graphagentdb serve
"""

from graphagentdb.config import get_settings
from graphagentdb.ingestion import ingest
from graphagentdb.models import KnowledgeNode, NodeType
from graphagentdb.store import KnowledgeStore

NODES = [
    (
        "agent_orchestrator",
        NodeType.AGENT,
        "Orchestrator Agent",
        "Core reasoning controller that manages a team of specialized subagents.",
    ),
    (
        "skill_planning",
        NodeType.SKILL,
        "Multi-Step Planning",
        "Decomposes high-level user goals into atomic tasks.",
    ),
    (
        "skill_routing",
        NodeType.SKILL,
        "Subagent Routing",
        "Selects the best subagent for a subtask based on past performance.",
    ),
    (
        "tool_assigner",
        NodeType.TOOL,
        "Task Assigner Tool",
        "Dispatches subtasks to subagent queues.",
    ),
    (
        "tool_monitor",
        NodeType.TOOL,
        "Status Monitor Tool",
        "Polls the execution health of subagents in real time.",
    ),
    (
        "practice_routing_history",
        NodeType.BEST_PRACTICE,
        "Persist Routing History",
        "Store routing history in a local database to avoid memory degradation.",
    ),
]

EDGES = [
    ("agent_orchestrator", "skill_planning", "HAS_SKILL", "Plans multi-step work."),
    ("agent_orchestrator", "skill_routing", "HAS_SKILL", "Routes subtasks."),
    ("agent_orchestrator", "tool_assigner", "HAS_TOOL", "Dispatches work."),
    ("agent_orchestrator", "tool_monitor", "HAS_TOOL", "Monitors subagents."),
    (
        "skill_routing",
        "practice_routing_history",
        "BASED_ON",
        "Routing relies on recorded history.",
    ),
    (
        "skill_planning",
        "tool_assigner",
        "REQUIRES_TOOL",
        "Plans are executed through the assigner.",
    ),
]

TEXTS = [
    "Design_patterns such as the factory, adapter, strategy and command patterns build on SOLID, "
    "and clean_code depends on SOLID too.",
    "CRITICAL UPDATE: the factory pattern is best written with classmethods or protocols.",
]


def main() -> None:
    store = KnowledgeStore(get_settings())
    for node_id, node_type, name, description in NODES:
        store.add_node(
            KnowledgeNode(id=node_id, type=node_type, name=name, description=description)
        )
    for src, tgt, rel, description in EDGES:
        store.create_relation(src, tgt, rel, description)
    for text in TEXTS:
        ingest(store, text=text)
    print(store.stats())


if __name__ == "__main__":
    main()
