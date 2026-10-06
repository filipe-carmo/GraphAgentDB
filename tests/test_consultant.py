import json

from graphagentdb.consultant import bootstrap, detect_stack
from graphagentdb.models import KnowledgeNode, NodeType


def test_detect_stack_reads_all_manifests(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"react": "^18"}, "devDependencies": {"@types/node": "*"}})
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["FastAPI>=0.1", "pydantic[email]"]\n'
        '[project.optional-dependencies]\ndev = ["pytest"]\n'
    )
    (tmp_path / "requirements.txt").write_text("# comment\nnumpy==2.0\n-e .\n")
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\n[dependencies]\nserde = "1"\n')

    assert detect_stack(tmp_path) == [
        "fastapi",
        "node",
        "numpy",
        "pydantic",
        "pytest",
        "react",
        "serde",
    ]


def test_bootstrap_writes_context_file(store, tmp_path):
    store.add_node(
        KnowledgeNode(
            id="practice_fastapi_deps",
            type=NodeType.BEST_PRACTICE,
            name="FastAPI dependency injection",
            description="Use Depends() for shared resources in fastapi apps.",
        )
    )
    project = tmp_path / "project"
    project.mkdir()
    (project / "requirements.txt").write_text("fastapi\n")

    state = bootstrap(store, str(project))

    assert state.error is None
    assert state.stack_keys == ["fastapi"]
    content = (project / "CLAUDE.md").read_text()
    assert "FastAPI dependency injection" in content
    assert (store.settings.exports_dir / "project.md").exists()


def test_bootstrap_missing_path_is_an_error(store, tmp_path):
    assert bootstrap(store, str(tmp_path / "missing")).error
