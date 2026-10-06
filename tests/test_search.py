from graphagentdb.models import KnowledgeNode, NodeType
from graphagentdb.search import HybridSearchEngine, score_subgraph

NODES = [
    (
        "agent_orchestrator",
        NodeType.AGENT,
        "Orchestrator Agent",
        "Reasoning controller managing subagents.",
    ),
    (
        "skill_planning",
        NodeType.SKILL,
        "Multi-Step Planning",
        "Decomposes goals into atomic tasks.",
    ),
    (
        "tool_assigner",
        NodeType.TOOL,
        "Task Assigner Tool",
        "Dispatches subtasks to subagent queues.",
    ),
    ("tool_monitor", NodeType.TOOL, "Status Monitor Tool", "Polls subagent health in real time."),
]
EDGES = [
    ("agent_orchestrator", "skill_planning", "HAS_SKILL"),
    ("agent_orchestrator", "tool_assigner", "HAS_TOOL"),
    ("agent_orchestrator", "tool_monitor", "HAS_TOOL"),
    ("skill_planning", "tool_assigner", "REQUIRES_TOOL"),
]


def _load(store):
    for node_id, node_type, name, description in NODES:
        store.add_node(
            KnowledgeNode(id=node_id, type=node_type, name=name, description=description)
        )
    for src, tgt, rel in EDGES:
        store.create_relation(src, tgt, rel)


def _edge(src, tgt, rel):
    return {"source_id": src, "target_id": tgt, "relation_type": rel}


def test_score_propagates_along_weighted_relations():
    scores = score_subgraph(
        [{"node_id": "tool", "score": 0.8}, {"node_id": "skill", "score": 0.5}],
        [
            _edge("agent", "tool", "HAS_TOOL"),
            _edge("skill", "other", "REQUIRES_TOOL"),
            _edge("x", "tool", "MENTIONS"),
        ],
    )
    assert scores["agent"] == 0.8 * 0.5
    assert scores["other"] == 0.5 * 0.3
    assert "x" not in scores


def test_search_on_empty_store(store):
    result = HybridSearchEngine(store).search("anything")
    assert result["sources"] == []
    assert result["subgraph"] == {"nodes": [], "edges": []}


def test_search_expands_matches_through_the_graph(store):
    _load(store)
    # Offline embeddings only match identical text, so query with a tool's exact node text.
    result = HybridSearchEngine(store).search(
        "Status Monitor Tool: Polls subagent health in real time.", top_k=1
    )
    ids = [n["id"] for n in result["subgraph"]["nodes"]]

    assert result["sources"][0]["node_id"] == "tool_monitor"
    assert set(ids) == {n[0] for n in NODES}  # neighbours pulled in by graph traversal
    assert ids[0] == "tool_monitor"
    scores = {n["id"]: n["hybrid_score"] for n in result["subgraph"]["nodes"]}
    assert scores["agent_orchestrator"] > scores["skill_planning"]  # boosted via HAS_TOOL
    assert "Status Monitor Tool" in result["answer"]
