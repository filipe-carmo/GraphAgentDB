"""Command-line interface: `graphagentdb ingest | search | bootstrap | stats | doctor | serve`."""

import logging
import sys
from collections import Counter
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from .config import get_settings
from .store import KnowledgeStore

app = typer.Typer(
    help="GraphAgentDB: a hybrid graph + vector knowledge base.", no_args_is_help=True
)
console = Console()


@app.callback()
def main(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show debug logs.")] = False,
):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )


def _open_store() -> KnowledgeStore:
    return KnowledgeStore(get_settings())


@app.command()
def ingest(
    url: Annotated[str | None, typer.Option(help="A web page to scrape and ingest.")] = None,
    text: Annotated[str | None, typer.Option(help="Raw text to ingest.")] = None,
):
    """Extract concepts from a URL or text and add them to the graph and vector index."""
    from .ingestion import ingest as run_ingest

    if not url and not text:
        console.print("[bold red]Error:[/bold red] pass --url or --text.")
        raise typer.Exit(1)

    state = run_ingest(_open_store(), url=url, text=text)
    if state.error:
        console.print(f"[bold red]Ingestion failed:[/bold red] {state.error}")
        raise typer.Exit(1)

    graph = state.distilled_graph
    console.print("[bold green]Ingestion complete[/bold green]")
    console.print(f"  Source: {state.source_title}")
    console.print(f"  Concepts extracted: {len(graph.nodes) if graph else 0}")
    console.print(f"  Relations extracted: {len(graph.edges) if graph else 0}")
    console.print(f"  Committed nodes: {state.committed_nodes}")


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="The question to answer.")],
    top_k: Annotated[
        int, typer.Option(help="Number of vector matches to seed the graph with.")
    ] = 5,
):
    """Answer a question with hybrid vector + graph retrieval."""
    from .search import HybridSearchEngine

    results = HybridSearchEngine(_open_store()).search(query, top_k)
    console.rule("Answer")
    console.print(results["answer"])
    console.rule()
    console.print("[bold cyan]Top connected concepts:[/bold cyan]")
    for n in results["subgraph"]["nodes"][:5]:
        console.print(
            f"  • [bold]{n['name']}[/bold] ({n['type'].upper()}) score {n['hybrid_score']}"
        )


@app.command()
def bootstrap(path: Annotated[str, typer.Argument(help="Project directory to bootstrap.")] = "."):
    """Write a context file for a project, listing the practices that apply to its stack."""
    from .consultant import bootstrap as run_bootstrap

    state = run_bootstrap(_open_store(), path)
    if state.error:
        console.print(f"[bold red]Bootstrap failed:[/bold red] {state.error}")
        raise typer.Exit(1)
    console.print("[bold green]Bootstrap complete[/bold green]")
    console.print(f"  Detected stack: {state.stack_keys}")
    for written in state.written_paths:
        console.print(f"  → [yellow]{written}[/yellow]")


@app.command()
def stats():
    """Show node, edge and vector counts."""
    store = _open_store()
    totals = store.stats()
    table = Table(title="GraphAgentDB")
    table.add_column("Component", style="cyan")
    table.add_column("Metric", style="yellow")
    table.add_column("Count", style="magenta", justify="right")

    table.add_row("Graph", "Nodes (active + deprecated)", str(totals["node_count"]))
    for node_type, count in Counter(n["type"] for n in store.get_all_nodes()).items():
        table.add_row("", f"↳ {node_type}", str(count))
    table.add_row("Graph", "Edges", str(totals["edge_count"]))
    for relation, count in Counter(e["relation_type"] for e in store.get_all_edges()).items():
        table.add_row("", f"↳ {relation}", str(count))
    table.add_row("Vector index", "Embeddings", str(totals["vector_count"]))
    console.print(table)


@app.command()
def doctor():
    """Check the Python version, configuration and database connections."""
    settings = get_settings()
    py_ok = sys.version_info >= (3, 11)
    console.print(
        f"  • Python {sys.version.split()[0]}: "
        + ("[green]OK[/green]" if py_ok else "[red]needs 3.11+[/red]")
    )
    console.print(
        "  • GEMINI_API_KEY: "
        + (
            "[green]set[/green]"
            if settings.gemini_api_key
            else "[yellow]not set (offline mode)[/yellow]"
        )
    )
    console.print(f"  • Agent harness: {'enabled' if settings.use_agent_harness else 'disabled'}")
    console.print(f"  • Data directory: [yellow]{settings.data_dir.resolve()}[/yellow]")
    try:
        totals = _open_store().stats()
    except Exception as exc:
        console.print(f"  • Storage: [bold red]FAILED[/bold red] ({exc})")
        raise typer.Exit(1) from exc
    console.print(
        f"  • Storage: [green]OK[/green] ({totals['node_count']} nodes, "
        f"{totals['edge_count']} edges, {totals['vector_count']} vectors)"
    )


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Interface to bind.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to listen on.")] = 8000,
):
    """Run the API and web UI."""
    import uvicorn

    from .api import create_app

    console.print(f"Serving GraphAgentDB on http://{host}:{port}")
    uvicorn.run(create_app(), host=host, port=port)
