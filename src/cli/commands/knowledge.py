"""Knowledge bank management commands."""
import asyncio
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.cli.utils import console

logger = logging.getLogger(__name__)


def register(parent: typer.Typer) -> None:
    knowledge_app = typer.Typer(help="Knowledge Bank Management")
    parent.add_typer(knowledge_app, name="knowledge")

    @knowledge_app.command("summary")
    def knowledge_summary(
        user_id: str = typer.Option("default", "--user-id", "-u", help="User ID"),
        db_path: Optional[str] = typer.Option(None, "--db-path", help="Database path"),
    ):
        """Show knowledge bank summary."""
        from src.core.memory.knowledge_bank import UserKnowledgeBank

        bank = UserKnowledgeBank(user_id, db_path=db_path)
        stats = bank.get_knowledge_stats()

        table = Table(title="Knowledge Bank Statistics")
        table.add_column("Item", style="cyan")
        table.add_column("Count", style="green")

        table.add_row("Entity Count", str(stats.get("entity_count", 0)))
        table.add_row("Relation Count", str(stats.get("relation_count", 0)))
        table.add_row("Data Point Count", str(stats.get("data_point_count", 0)))
        table.add_row("Insight Count", str(stats.get("insight_count", 0)))

        console.print(table)
        bank.close()

    @knowledge_app.command("search")
    def knowledge_search(
        query: str = typer.Argument(..., help="Search keywords"),
        user_id: str = typer.Option("default", "--user-id", "-u", help="User ID"),
        db_path: Optional[str] = typer.Option(None, "--db-path", help="Database path"),
        limit: int = typer.Option(10, "--limit", "-l", help="Result limit"),
    ):
        """Search knowledge bank."""
        from src.core.memory.knowledge_bank import UserKnowledgeBank

        bank = UserKnowledgeBank(user_id, db_path=db_path)
        results = bank.search_all(query, limit=limit)

        if results.get("entities"):
            console.print("\n[bold]Entities:[/bold]")
            for entity in results["entities"]:
                console.print(f"  - {entity.get('name', 'N/A')} ({entity.get('entity_type', 'N/A')})")

        if results.get("relations"):
            console.print("\n[bold]Relations:[/bold]")
            for relation in results["relations"]:
                console.print(f"  - {relation.get('context', 'N/A')}")

        if results.get("data_points"):
            console.print("\n[bold]Data Points:[/bold]")
            for data in results["data_points"]:
                console.print(f"  - {data.get('metric_name', 'N/A')}: {data.get('metric_value', 'N/A')}")

        bank.close()

    @knowledge_app.command("export")
    def knowledge_export(
        user_id: str = typer.Option("default", "--user-id", "-u", help="User ID"),
        db_path: Optional[str] = typer.Option(None, "--db-path", help="Database path"),
        output: str = typer.Option("knowledge_export.json", "--output", "-o", help="Output file path"),
    ):
        """Export knowledge bank data."""
        from src.core.memory.knowledge_bank import UserKnowledgeBank

        bank = UserKnowledgeBank(user_id, db_path=db_path)
        bank.export_to_json(output)
        console.print(f"[green]Knowledge exported to: {output}[/green]")
        bank.close()

    @knowledge_app.command("import")
    def knowledge_import(
        path: str = typer.Argument(..., help="File or directory path"),
        user_id: str = typer.Option("default", "--user-id", "-u", help="User ID"),
        db_path: Optional[str] = typer.Option(None, "--db-path", help="Database path"),
        auto_extract: bool = typer.Option(True, "--auto-extract/--no-auto-extract", help="Auto-extract knowledge"),
        recursive: bool = typer.Option(True, "--recursive/--no-recursive", help="Recursive subdirectories"),
    ):
        """Import file or directory into knowledge base."""
        asyncio.run(_knowledge_import_async(path, user_id, db_path, auto_extract, recursive))

    @knowledge_app.command("compile")
    def knowledge_compile(
        research_id: str = typer.Argument(..., help="Research ID or file path"),
        user_id: str = typer.Option("default", "--user-id", "-u", help="User ID"),
        db_path: Optional[str] = typer.Option(None, "--db-path", help="Database path"),
    ):
        """Compile research report into structured knowledge."""
        asyncio.run(_knowledge_compile_async(research_id, user_id, db_path))

    @knowledge_app.command("contradictions")
    def knowledge_contradictions(
        user_id: str = typer.Option("default", "--user-id", "-u", help="User ID"),
        db_path: Optional[str] = typer.Option(None, "--db-path", help="Database path"),
        resolve: Optional[str] = typer.Option(None, "--resolve", help="Contradiction ID to resolve"),
        note: str = typer.Option("", "--note", help="Resolution note"),
    ):
        """Detect and manage knowledge contradictions."""
        asyncio.run(_knowledge_contradictions_async(user_id, db_path, resolve, note))

    @knowledge_app.command("backlinks")
    def knowledge_backlinks(
        user_id: str = typer.Option("default", "--user-id", "-u", help="User ID"),
        db_path: Optional[str] = typer.Option(None, "--db-path", help="Database path"),
    ):
        """Update knowledge page backlink references."""
        asyncio.run(_knowledge_backlinks_async(user_id, db_path))


async def _knowledge_import_async(
    path: str,
    user_id: str,
    db_path: Optional[str],
    auto_extract: bool,
    recursive: bool
):
    """Execute knowledge import asynchronously."""
    from src.core.memory.knowledge_bank import UserKnowledgeBank

    bank = UserKnowledgeBank(user_id, db_path=db_path)

    input_path = Path(path)

    if input_path.is_file():
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Importing file: {path}...", total=None)
            result = bank.import_file(str(input_path), auto_extract=auto_extract)

        if result.status == "success":
            console.print(f"[green][OK] Import successful: {path}[/green]")
            console.print(f"  Knowledge pages created: {result.pages_created}")
            console.print(f"  Entities extracted: {result.entities_extracted}")
        elif result.status == "skipped":
            console.print(f"[yellow]Skipped: {result.error_message}[/yellow]")
        else:
            console.print(f"[red][FAIL] Import failed: {result.error_message}[/red]")

    elif input_path.is_dir():
        console.print(f"[bold]Batch importing directory: {path}[/bold]")

        results = bank.import_directory(
            str(input_path),
            auto_extract=auto_extract,
            recursive=recursive
        )

        success_count = sum(1 for r in results if r.status == "success")
        partial_count = sum(1 for r in results if r.status == "partial")
        failed_count = sum(1 for r in results if r.status == "failed")
        skipped_count = sum(1 for r in results if r.status == "skipped")

        table = Table(title="Import Results")
        table.add_column("Status", style="cyan")
        table.add_column("Count", style="green")

        table.add_row("Success", str(success_count))
        table.add_row("Partial Success", str(partial_count))
        table.add_row("Failed", str(failed_count))
        table.add_row("Skipped", str(skipped_count))

        console.print(table)

    else:
        console.print(f"[red]Path does not exist: {path}[/red]")

    bank.close()


async def _knowledge_compile_async(
    research_id: str,
    user_id: str,
    db_path: Optional[str]
):
    """Execute knowledge compilation asynchronously."""
    from src.core.memory.knowledge_bank import UserKnowledgeBank

    bank = UserKnowledgeBank(user_id, db_path=db_path)

    input_path = Path(research_id)

    if input_path.exists() and input_path.is_file():
        content = input_path.read_text(encoding='utf-8')
        source_info = {
            "title": input_path.stem,
            "type": "file",
            "path": str(input_path)
        }
    else:
        console.print(f"[red]Research ID not found or invalid file path: {research_id}[/red]")
        bank.close()
        return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Compiling knowledge...", total=None)
        knowledge = bank.compile_research(content, source_info)
        bank.save_compiled_knowledge(knowledge)

    stats = knowledge.get_stats()

    table = Table(title="Compilation Results")
    table.add_column("Type", style="cyan")
    table.add_column("Count", style="green")

    table.add_row("Concept Pages", str(stats["concepts"]))
    table.add_row("Entity Pages", str(stats["entities"]))
    table.add_row("Relation Pages", str(stats["relations"]))
    table.add_row("Total", str(stats["total"]))

    console.print(table)
    bank.close()


async def _knowledge_contradictions_async(
    user_id: str,
    db_path: Optional[str],
    resolve: Optional[str],
    note: str
):
    """Execute contradiction detection asynchronously."""
    from src.core.memory.knowledge_bank import UserKnowledgeBank

    bank = UserKnowledgeBank(user_id, db_path=db_path)

    if resolve:
        bank.resolve_contradiction(resolve, "resolved", note)
        console.print(f"[green]Contradiction resolved: {resolve}[/green]")
    else:
        contradictions = bank.detect_contradictions()
        stats = bank.get_contradiction_stats()

        table = Table(title="Contradiction Statistics")
        table.add_column("Status", style="cyan")
        table.add_column("Count", style="green")

        table.add_row("Pending", str(stats.get("pending", 0)))
        table.add_row("Resolved", str(stats.get("resolved", 0)))
        table.add_row("Ignored", str(stats.get("ignored", 0)))
        table.add_row("Total", str(stats.get("total", 0)))

        console.print(table)

        pending = [c for c in contradictions if c.resolution_status.value == "pending"]
        if pending:
            console.print(f"\n[bold]Pending Contradictions ({len(pending)}):[/bold]")
            for c in pending[:10]:
                console.print(f"  ID: {c.contradiction_id}")
                console.print(f"  Entity: {c.entity_name}, Attribute: {c.attribute}")
                console.print(f"  Value 1: {c.value_1} (Source: {c.source_1})")
                console.print(f"  Value 2: {c.value_2} (Source: {c.source_2})")
                console.print("")

    bank.close()


async def _knowledge_backlinks_async(
    user_id: str,
    db_path: Optional[str]
):
    """Update backlink references asynchronously."""
    from src.core.memory.knowledge_bank import UserKnowledgeBank

    bank = UserKnowledgeBank(user_id, db_path=db_path)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Updating backlink references...", total=None)
        bank.compiler.backlink_system.update_backlinks()

    console.print("[green][OK] Backlink references updated[/green]")
    bank.close()
