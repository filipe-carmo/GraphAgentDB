import pytest

from graphagentdb.graph_store import GraphStore


@pytest.fixture
def graph(tmp_path):
    g = GraphStore(tmp_path / "graph.kuzu")
    yield g
    g.close()


def _seed(graph):
    graph.upsert_node("agent_alpha", "agent", "Alpha Agent", "Writes python scripts.")
    graph.upsert_node("tool_python", "tool", "Python Interpreter", "Runs python code locally.")
    graph.upsert_node("practice_tests", "best_practice", "Write Tests", "Test the scripts.")
    graph.upsert_edge("agent_alpha", "tool_python", "HAS_TOOL", "Alpha uses the interpreter.")
    graph.upsert_edge("tool_python", "practice_tests", "BASED_ON", "")


def test_upsert_node_creates_then_updates(graph):
    graph.upsert_node("agent_alpha", "agent", "Alpha Agent", "First description.")
    graph.upsert_node("agent_alpha", "agent", "Alpha Agent", "Second description.")

    nodes = graph.get_all_nodes()
    assert len(nodes) == 1
    assert nodes[0]["description"] == "Second description."
    assert nodes[0]["status"] == "active"
    assert nodes[0]["superseded_by"] == ""


def test_get_missing_node_returns_none(graph):
    assert graph.get_node("nope") is None


def test_upsert_edge_is_idempotent(graph):
    _seed(graph)
    graph.upsert_edge("agent_alpha", "tool_python", "HAS_TOOL", "Duplicate write.")

    edges = graph.get_all_edges()
    has_tool = [e for e in edges if e["relation_type"] == "HAS_TOOL"]
    assert len(has_tool) == 1
    assert has_tool[0]["properties"]["description"] == "Alpha uses the interpreter."


def test_unknown_relation_falls_back_to_references(graph):
    _seed(graph)
    edge = graph.upsert_edge("agent_alpha", "practice_tests", "LIKES", "")
    assert edge["relation_type"] == "REFERENCES"


def test_edge_description_with_quotes_is_stored_verbatim(graph):
    _seed(graph)
    text = 'It\'s a "quoted" description; DROP TABLE Node;'
    graph.upsert_edge("agent_alpha", "practice_tests", "REFERENCES", text)
    edge = next(e for e in graph.get_all_edges() if e["relation_type"] == "REFERENCES")
    assert edge["properties"]["description"] == text


@pytest.mark.parametrize(
    ("depth", "expected_nodes", "expected_edges"),
    [(0, {"agent_alpha"}, 0), (1, {"agent_alpha", "tool_python"}, 1), (2, None, 2)],
)
def test_subgraph_depth(graph, depth, expected_nodes, expected_edges):
    _seed(graph)
    subgraph = graph.get_subgraph(["agent_alpha"], max_depth=depth)
    ids = {n["id"] for n in subgraph["nodes"]}
    assert ids == (expected_nodes or {"agent_alpha", "tool_python", "practice_tests"})
    assert len(subgraph["edges"]) == expected_edges


def test_subgraph_traverses_edges_in_both_directions(graph):
    _seed(graph)
    subgraph = graph.get_subgraph(["practice_tests"], max_depth=1)
    assert {n["id"] for n in subgraph["nodes"]} == {"practice_tests", "tool_python"}
