from unittest.mock import patch

import requests

from graphagentdb.extractor import fallback_graph, fetch_url_content
from graphagentdb.llm import strip_code_fences
from graphagentdb.models import ExtractedEdge, ExtractedNode


def test_strip_code_fences():
    assert strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert strip_code_fences('{"a": 1}') == '{"a": 1}'


def test_extracted_ids_are_normalized():
    node = ExtractedNode(id="  Graph_RAG ", type="concept", name="n", description="d")
    edge = ExtractedEdge(source_id="A", target_id="B ", relation_type="IS_A", description="")
    assert node.id == "graph_rag"
    assert (edge.source_id, edge.target_id) == ("a", "b")


def test_fallback_graph_without_keywords_returns_a_default_node():
    graph = fallback_graph("nothing relevant here")
    assert [n.id for n in graph.nodes] == ["concept_software_design"]
    assert graph.edges == []


def test_fetch_url_extracts_title_and_visible_text():
    html = (
        "<html><head><title> Page </title><script>bad()</script></head>"
        "<body><nav>menu</nav><p>Hello   world</p></body></html>"
    )
    response = requests.Response()
    response.status_code = 200
    response._content = html.encode()
    with patch("graphagentdb.extractor.requests.get", return_value=response):
        title, text = fetch_url_content("https://example.com")
    assert title == "Page"
    assert text == "Hello\nworld"


def test_fetch_url_failure_returns_empty_body():
    with patch("graphagentdb.extractor.requests.get", side_effect=requests.ConnectionError("down")):
        title, text = fetch_url_content("https://example.com/page")
    assert title == "example.com/page"
    assert text == ""
