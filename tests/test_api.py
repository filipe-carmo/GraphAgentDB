import pytest
from fastapi.testclient import TestClient

from graphagentdb.api import create_app


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def test_status(client):
    body = client.get("/api/status").json()
    assert body["status"] == "online"
    assert body["node_count"] == 0
    assert body["llm_active"] is False


def test_ingest_search_and_graph(client):
    response = client.post(
        "/api/ingest", json={"text": "design_patterns like the strategy pattern"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["nodes_extracted"] == 2

    graph = client.get("/api/graph").json()
    assert {n["id"] for n in graph["nodes"]} == {"concept_strategy", "concept_design_patterns"}
    assert graph["edges"][0]["label"] == "IS_A"

    search = client.post("/api/search", json={"query": "strategy"}).json()
    assert search["sources"]
    assert search["answer"]


def test_ingest_requires_url_or_text(client):
    assert client.post("/api/ingest", json={}).status_code == 422


def test_graph_can_hide_deprecated_nodes(client):
    client.post("/api/ingest", json={"text": "The factory pattern creates objects."})
    client.post("/api/ingest", json={"text": "CRITICAL UPDATE: the factory pattern, modernised."})

    full = client.get("/api/graph").json()
    active = client.get("/api/graph", params={"show_deprecated": False}).json()
    assert len(full["nodes"]) == 2
    assert any(e["label"] == "SUPERSEDES" for e in full["edges"])
    assert len(active["nodes"]) == 1
    assert active["edges"] == []


def test_ui_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "<html" in response.text.lower()
