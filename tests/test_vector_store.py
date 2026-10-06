from graphagentdb.llm import fallback_embedding
from graphagentdb.vector_store import VectorStore

DIM = 16


def _store(tmp_path):
    return VectorStore(tmp_path / "vectors.lance", embed_dim=DIM)


def test_search_on_empty_index_returns_nothing(tmp_path):
    assert _store(tmp_path).search(fallback_embedding("x", DIM)) == []


def test_identical_text_is_the_top_hit(tmp_path):
    store = _store(tmp_path)
    for node_id in ["alpha", "beta", "gamma"]:
        store.add_vector(f"vector_{node_id}", node_id, node_id, fallback_embedding(node_id, DIM))

    hits = store.search(fallback_embedding("beta", DIM), top_k=1)
    assert hits[0]["node_id"] == "beta"
    assert hits[0]["score"] > 0.99


def test_add_vector_replaces_same_chunk_id(tmp_path):
    store = _store(tmp_path)
    store.add_vector("vector_a", "a", "first", fallback_embedding("first", DIM))
    store.add_vector("vector_a", "a", "second", fallback_embedding("second", DIM))
    assert store.count() == 1
    assert store.search(fallback_embedding("second", DIM))[0]["text"] == "second"


def test_deprecated_vectors_are_excluded_from_search(tmp_path):
    store = _store(tmp_path)
    store.add_vector("vector_a", "a", "a", fallback_embedding("a", DIM))
    store.set_status("a", "deprecated")
    assert store.search(fallback_embedding("a", DIM)) == []


def test_ids_with_quotes_do_not_break_filters(tmp_path):
    store = _store(tmp_path)
    node_id = "o'reilly"
    store.add_vector(f"vector_{node_id}", node_id, "text", fallback_embedding("text", DIM))
    store.add_vector(f"vector_{node_id}", node_id, "text", fallback_embedding("text", DIM))
    store.set_status(node_id, "deprecated")
    assert store.count() == 1
