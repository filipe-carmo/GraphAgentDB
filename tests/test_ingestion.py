from graphagentdb.ingestion import ingest

FACTORY_TEXT = """
The Factory Pattern is a creational design pattern that provides an interface for creating
objects in a superclass, but allows subclasses to alter the type of objects that will be created.
"""

FACTORY_UPDATE_TEXT = """
The Factory Pattern is a creational design pattern providing a standard interface for object creation.
CRITICAL UPDATE: In modern Python, the Factory Pattern is best implemented using classmethods
or protocols instead of abstract classes.
"""


def test_first_ingest_writes_graph_and_vectors(store):
    state = ingest(store, text=FACTORY_TEXT)

    assert state.error is None
    assert state.status == "success"
    assert state.committed_nodes
    node = store.get_node(state.committed_nodes[0])
    assert node["status"] == "active"
    assert store.vectors.count() == len(state.committed_nodes)


def test_reingesting_same_text_is_a_duplicate(store):
    ingest(store, text=FACTORY_TEXT)
    state = ingest(store, text=FACTORY_TEXT)

    assert state.error is None
    assert state.committed_nodes == []
    assert {d["decision"] for d in state.conflict_decisions.values()} == {"duplicate"}


def test_update_supersedes_the_old_node(store):
    first = ingest(store, text=FACTORY_TEXT)
    old_id = first.committed_nodes[0]

    state = ingest(store, text=FACTORY_UPDATE_TEXT)
    assert state.error is None

    old = store.get_node(old_id)
    assert old["status"] == "deprecated"
    new = store.get_node(old["superseded_by"])
    assert new["status"] == "active"
    assert any(
        e["relation_type"] == "SUPERSEDES"
        and e["source_id"] == new["id"]
        and e["target_id"] == old_id
        for e in store.get_all_edges()
    )
    # The deprecated node no longer shows up in vector search.
    assert all(h["node_id"] != old_id for h in store.semantic_search(old["name"], top_k=10))


def test_extracted_edges_are_committed(store):
    state = ingest(store, text="design_patterns: the factory and strategy patterns, and solid")
    assert state.error is None
    relations = {
        (e["source_id"], e["relation_type"], e["target_id"]) for e in store.get_all_edges()
    }
    assert ("concept_factory", "IS_A", "concept_design_patterns") in relations
    assert ("concept_design_patterns", "BASED_ON", "concept_solid") in relations


def test_empty_input_is_an_error(store):
    assert ingest(store).error
    assert ingest(store, text="   ").error
