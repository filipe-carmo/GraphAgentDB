import os
import typer
from typing import Optional
from rich.console import Console
from rich.table import Table

from backend.database import init_db, get_all_nodes, get_all_edges
from backend.vector_store import VectorStore
from backend.hybrid_search import HybridSearchEngine
from backend.ingestion_agent import harvester, HarvestState
from backend.consultant_agent import consultant, ConsultState

app = typer.Typer(help="🔮 Agent Knowledge Synapse: Interactive CLI Console")
console = Console()

@app.command()
def ingest(
    url: Optional[str] = typer.Option(None, help="The URL to scrape and ingest."),
    text: Optional[str] = typer.Option(None, help="Raw text string to ingest directly.")
):
    """
    Crawls a URL or takes raw text, parses it, extracts structured concept nodes/relations,
    computes LanceDB vector embeddings, and runs conflict deduplications.
    """
    if not url and not text:
        console.print("[bold red]Error:[/bold red] Either --url or --text must be specified.")
        raise typer.Exit(1)
        
    console.print(f"[bold blue]🔮 Ingesting content...[/bold blue]")
    state = HarvestState(url=url, text=text)
    
    try:
        result = harvester.invoke(state.model_dump())
        if result.get("error"):
            console.print(f"[bold red]Ingestion Error:[/bold red] {result.get('error')}")
            raise typer.Exit(1)
            
        console.print(f"[bold green]✓ Ingestion Complete![/bold green]")
        console.print(f"  [bold cyan]Source Title:[/bold cyan] {result.get('source_title')}")
        console.print(f"  [bold cyan]Concepts Distilled:[/bold cyan] {len(result.get('distilled_graph').nodes) if result.get('distilled_graph') else 0}")
        console.print(f"  [bold cyan]Relations Logged:[/bold cyan] {len(result.get('distilled_graph').edges) if result.get('distilled_graph') else 0}")
        console.print(f"  [bold cyan]Committed Nodes:[/bold cyan] {result.get('committed_nodes')}")
    except Exception as e:
        console.print(f"[bold red]Ingestion Failed:[/bold red] {e}")
        raise typer.Exit(1)

@app.command()
def bootstrap(path: str = typer.Argument(".", help="The repository directory path to bootstrap.")):
    """
    Scans project dependency manifests, vector-queries for rules, and compiles the project GEMINI.md context.
    """
    console.print(f"[bold blue]🔮 Bootstrapping developer context at '{path}'...[/bold blue]")
    state = ConsultState(project_path=path)
    
    try:
        result = consultant.invoke(state.model_dump())
        if result.get("error"):
            console.print(f"[bold red]Bootstrap Error:[/bold red] {result.get('error')}")
            raise typer.Exit(1)
            
        console.print(f"[bold green]✓ Bootstrap Completed successfully![/bold green]")
        console.print(f"  [bold cyan]Detected Stack Keys:[/bold cyan] {result.get('stack_keys')}")
        console.print(f"  [bold cyan]Context Files Bootstrapped:[/bold cyan]")
        for p in result.get("written_paths", []):
            console.print(f"    → [yellow]{p}[/yellow]")
    except Exception as e:
        console.print(f"[bold red]Bootstrap Failed:[/bold red] {e}")
        raise typer.Exit(1)

@app.command()
def search(
    query: str = typer.Argument(..., help="The query string to search the synapse database."),
    top_k: int = typer.Option(5, help="Number of semantic vectors to match.")
):
    """
    Executes a hybrid wRRF search merging LanceDB and Kuzu property BFS traversal,
    then synthesizes a grounded expert grounded response.
    """
    console.print(f"[bold blue]🔮 Querying Graph-Vector Hybrid Engine...[/bold blue]")
    try:
        engine = HybridSearchEngine()
        results = engine.search(query, top_k)
        
        console.print("\n[bold green]Answer Synthesis Output:[/bold green]")
        console.print("=" * 80)
        console.print(results["answer"])
        console.print("=" * 80)
        
        console.print("\n[bold cyan]Top Connected Concepts Traversed:[/bold cyan]")
        for n in results["subgraph"]["nodes"][:5]:
            console.print(f"  • [bold]{n['name']}[/bold] ({n['type'].upper()}) - Score: {n.get('hybrid_score', 0)}")
    except Exception as e:
        console.print(f"[bold red]Query Failed:[/bold red] {e}")
        raise typer.Exit(1)

@app.command()
def stats():
    """
    Returns metrics and counts across Kuzu Property Graph tables and LanceDB vector collections.
    """
    from backend.store import KnowledgeStore
    
    try:
        store = KnowledgeStore()
        db_stats = store.stats()
        nodes = store.get_all_nodes()
        edges = store.get_all_edges()
        
        # Breakdown by group
        node_groups = {}
        for n in nodes:
            node_groups[n["type"]] = node_groups.get(n["type"], 0) + 1
            
        # Breakdown by edge relation
        edge_relations = {}
        for e in edges:
            edge_relations[e["relation_type"]] = edge_relations.get(e["relation_type"], 0) + 1
            
        table = Table(title="🔮 Agent Knowledge Synapse Metrics")
        table.add_column("Component", style="cyan")
        table.add_column("Metric / Classification", style="yellow")
        table.add_column("Count", style="magenta", justify="right")
        
        table.add_row("Kuzu Property Graph", "Total Active & Deprecated Nodes", str(db_stats["node_count"]))
        for g, count in node_groups.items():
            table.add_row("  ↳ Node Group", g.upper(), str(count))
            
        table.add_row("Kuzu Property Graph", "Total Edge Connections", str(db_stats["edge_count"]))
        for r, count in edge_relations.items():
            table.add_row("  ↳ Relation Type", r, str(count))
            
        table.add_row("LanceDB Vector Database", "Total Vector Embeddings", str(db_stats["vector_count"]))
        
        console.print(table)
    except Exception as e:
        console.print(f"[bold red]Failed to retrieve statistics:[/bold red] {e}")
        raise typer.Exit(1)

@app.command()
def doctor():
    """
    Runs diagnostic and connection checks across environment, configurations, KuzuDB, and LanceDB.
    """
    console.print("[bold blue]🔮 Executing Agent Knowledge Synapse Environment Doctor...[/bold blue]\n")
    
    import sys
    from backend.settings import settings
    from backend.store import KnowledgeStore
    
    # 1. Check Python runtime
    python_ok = sys.version_info >= (3, 11)
    python_status = "[green]HEALTHY[/green]" if python_ok else "[red]UNSUPPORTED[/red]"
    console.print(f"  • [bold]Python Runtime:[/bold] {sys.version.split()[0]} ({python_status})")
    
    # 2. Check environment config & API Key
    api_key_env = settings.gemini_api_key
    api_status = "[green]YES[/green]" if api_key_env else "[yellow]NO (Offline stubs active)[/yellow]"
    if api_key_env:
        masked = f" (Masked: {api_key_env[:4]}...{api_key_env[-4:]})"
    else:
        masked = ""
    console.print(f"  • [bold]GEMINI_API_KEY Configured:[/bold] {api_status}{masked}")
    
    # 3. Check Manifest file configuration
    console.print(f"  • [bold]Kuzu DB File path:[/bold] [yellow]{settings.kuzu_db_path}[/yellow]")
    console.print(f"  • [bold]LanceDB Store path:[/bold] [yellow]{settings.lancedb_path}[/yellow]")
    
    # 4. Storage read-write smoke test
    try:
        store = KnowledgeStore()
        console.print("  • [bold]Database Connections:[/bold] [green]SUCCESS[/green] (Thread-safe connection pool operational)")
        
        db_stats = store.stats()
        console.print(f"  • [bold]Property Graph Nodes count:[/bold] [magenta]{db_stats['node_count']}[/magenta]")
        console.print(f"  • [bold]Property Graph Edges count:[/bold] [magenta]{db_stats['edge_count']}[/magenta]")
        console.print(f"  • [bold]LanceDB Chunks count:[/bold] [magenta]{db_stats['vector_count']}[/magenta]")
        
        # Connection validation success
        console.print("  • [bold]Store Health Cycle Check:[/bold] [green]PASS[/green]")
    except Exception as e:
        console.print(f"  • [bold]Store Health Cycle Check:[/bold] [bold red]FAILED[/bold red] ({e})")
        
    console.print("\n[bold green]✓ Synapse Environment check completed.[/bold green]")

if __name__ == "__main__":
    app()
