"""Document generation and management commands."""
import asyncio
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table
from rich.panel import Panel

from src.cli.utils import console

logger = logging.getLogger(__name__)


def register(parent: typer.Typer) -> None:
    doc_app = typer.Typer(help="Document generation and management")
    parent.add_typer(doc_app, name="document")

    @doc_app.command("generate")
    def doc_generate(
        task_id: str = typer.Argument(..., help="Task ID"),
        format: str = typer.Option("docx", "--format", "-f", help="Output format: docx, pdf, html"),
        template: str = typer.Option("consulting", "--template", "-t", help="Template: consulting, academic, business, minimal"),
    ):
        """Generate document for completed research."""
        asyncio.run(_doc_generate_async(task_id, format, template))

    @doc_app.command("versions")
    def doc_versions(
        task_id: str = typer.Argument(..., help="Task ID"),
        format: str = typer.Option("docx", "--format", "-f", help="Document format"),
    ):
        """List document versions."""
        asyncio.run(_doc_versions_async(task_id, format))

    @doc_app.command("rollback")
    def doc_rollback(
        task_id: str = typer.Argument(..., help="Task ID"),
        format: str = typer.Option("docx", "--format", "-f", help="Document format"),
        target_version: str = typer.Option(..., "--version", "-v", help="Target version (e.g. v3)"),
    ):
        """Rollback to a previous version."""
        asyncio.run(_doc_rollback_async(task_id, format, target_version))

    @doc_app.command("preview")
    def doc_preview(
        task_id: str = typer.Argument(..., help="Task ID"),
        format: str = typer.Option("png", "--format", "-f", help="Preview format: png, jpg, pdf"),
        version_id: Optional[str] = typer.Option(None, "--version", "-v", help="Version ID"),
        output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
    ):
        """Get document preview image."""
        asyncio.run(_doc_preview_async(task_id, version_id, format, output))

    @doc_app.command("adjust")
    def doc_adjust(
        task_id: str = typer.Argument(..., help="Task ID"),
        adjustment_type: str = typer.Option("GLOBAL", "--type", "-t", help="Adjustment type: GLOBAL, PAGE, SECTION, ELEMENT"),
        target: Optional[str] = typer.Option(None, "--target", help="Target element/section for SECTION/ELEMENT type"),
        changes: Optional[str] = typer.Option(None, "--changes", "-c", help="JSON-encoded changes"),
    ):
        """Adjust document layout or content."""
        import json
        parsed_changes = None
        if changes:
            try:
                parsed_changes = json.loads(changes)
            except json.JSONDecodeError:
                console.print("[red]Invalid JSON for --changes[/red]")
                raise typer.Exit(1)
        asyncio.run(_doc_adjust_async(task_id, adjustment_type, target, parsed_changes))

    @doc_app.command("revisions")
    def doc_revisions(
        task_id: str = typer.Argument(..., help="Task ID"),
    ):
        """List revision history."""
        asyncio.run(_doc_revisions_async(task_id))

    @doc_app.command("export")
    def doc_export(
        task_id: str = typer.Argument(..., help="Task ID"),
        format: str = typer.Option("docx", "--format", "-f", help="Output format: docx, pdf, html"),
        version_id: str = typer.Option("latest", "--version", "-v", help="Version ID (default: latest)"),
        output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
    ):
        """Export document as file."""
        asyncio.run(_doc_export_async(task_id, format, version_id, output))

    @doc_app.command("revision")
    def doc_revision(
        task_id: str = typer.Argument(..., help="Task ID"),
        revision_type: str = typer.Option("minor", "--type", "-t", help="Revision type: minor, section, phase, full"),
        user_feedback: str = typer.Option("", "--feedback", "-f", help="User feedback for revision"),
        section_id: Optional[str] = typer.Option(None, "--section-id", help="Section ID"),
        section_title: Optional[str] = typer.Option(None, "--section-title", help="Section title"),
        keywords: Optional[str] = typer.Option(None, "--keywords", "-k", help="Comma-separated keywords"),
        target_content: Optional[str] = typer.Option(None, "--target-content", help="Target content"),
    ):
        """Request document revision."""
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else None
        asyncio.run(_doc_revision_async(task_id, revision_type, user_feedback, section_id, section_title, kw_list, target_content))


async def _doc_generate_async(task_id: str, format: str, template: str):
    from src.cli.client import ZensersClient

    client = ZensersClient()
    try:
        result = await client.document_generate(task_id, format, template)
    except Exception as e:
        console.print(f"[red]Failed to generate document: {e}[/red]")
        raise typer.Exit(1)
    finally:
        await client.close()
    console.print(f"[green][OK] Document generation started[/green]")
    if result.get("task_id"):
        console.print(f"  Task ID: {result['task_id']}")
    if result.get("document_path"):
        console.print(f"  Path: {result['document_path']}")


async def _doc_versions_async(task_id: str, format: str):
    from src.cli.client import ZensersClient

    client = ZensersClient()
    try:
        result = await client.document_versions(task_id, format)
    except Exception as e:
        console.print(f"[red]Failed to list versions: {e}[/red]")
        raise typer.Exit(1)
    finally:
        await client.close()
    versions = result.get("versions", [])
    if not versions:
        console.print("[yellow]No versions found[/yellow]")
        return
    table = Table(title=f"Versions for {task_id}")
    table.add_column("Version", style="cyan")
    table.add_column("Created At")
    table.add_column("Size")
    for v in versions:
        table.add_row(v.get("version_id", ""), v.get("created_at", ""), v.get("size", ""))
    console.print(table)


async def _doc_rollback_async(task_id: str, format: str, target_version: str):
    from src.cli.client import ZensersClient

    client = ZensersClient()
    try:
        result = await client.document_rollback(task_id, format, target_version)
    except Exception as e:
        console.print(f"[red]Failed to rollback: {e}[/red]")
        raise typer.Exit(1)
    finally:
        await client.close()
    console.print(f"[green][OK] Rolled back to {target_version}[/green]")
    if result.get("new_version"):
        console.print(f"  New version: {result['new_version']}")


async def _doc_preview_async(task_id: str, version_id: Optional[str], format: str, output: Optional[str]):
    from src.cli.client import ZensersClient

    client = ZensersClient()
    try:
        content = await client.document_preview(task_id, version_id, format)
    except Exception as e:
        console.print(f"[red]Failed to get preview: {e}[/red]")
        raise typer.Exit(1)
    finally:
        await client.close()
    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(content)
        console.print(f"[green]Preview saved: {out_path} ({len(content)} bytes)[/green]")
    else:
        console.print(f"[green]Preview received: {len(content)} bytes[/green]")
        console.print("[dim]Use --output to save to file[/dim]")


async def _doc_adjust_async(task_id: str, adjustment_type: str, target: Optional[str], changes: Optional[dict]):
    from src.cli.client import ZensersClient

    client = ZensersClient()
    try:
        result = await client.document_adjust(task_id, adjustment_type, target, changes)
    except Exception as e:
        console.print(f"[red]Failed to adjust document: {e}[/red]")
        raise typer.Exit(1)
    finally:
        await client.close()
    console.print(f"[green][OK] Document adjusted[/green]")
    if result.get("message"):
        console.print(f"  {result['message']}")


async def _doc_revisions_async(task_id: str):
    from src.cli.client import ZensersClient

    client = ZensersClient()
    try:
        result = await client.document_revisions(task_id)
    except Exception as e:
        console.print(f"[red]Failed to get revision history: {e}[/red]")
        raise typer.Exit(1)
    finally:
        await client.close()
    revisions = result.get("revisions", [])
    if not revisions:
        console.print("[yellow]No revisions found[/yellow]")
        return
    table = Table(title=f"Revision History: {task_id}")
    table.add_column("ID", style="cyan")
    table.add_column("Type")
    table.add_column("Status", style="yellow")
    table.add_column("Created At")
    for r in revisions:
        table.add_row(r.get("id", ""), r.get("type", ""), r.get("status", ""), r.get("created_at", ""))
    console.print(table)


async def _doc_export_async(task_id: str, format: str, version_id: str, output: Optional[str]):
    from src.cli.client import ZensersClient

    client = ZensersClient()
    try:
        content, content_type = await client.document_export(task_id, version_id, format)
    except FileNotFoundError:
        console.print(f"[red]Document not found for task {task_id}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Failed to export document: {e}[/red]")
        raise typer.Exit(1)
    finally:
        await client.close()

    ext = {"docx": ".docx", "pdf": ".pdf", "html": ".html", "pptx": ".pptx"}.get(format, ".bin")
    out_path = Path(output) if output else Path(f"{task_id}_export{ext}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(content)
    console.print(f"[green]Exported: {out_path} ({len(content)} bytes)[/green]")


async def _doc_revision_async(
    task_id: str,
    revision_type: str,
    user_feedback: str,
    section_id: Optional[str],
    section_title: Optional[str],
    keywords: Optional[list],
    target_content: Optional[str],
):
    from src.cli.client import ZensersClient

    client = ZensersClient()
    try:
        result = await client.document_revision(
            task_id, revision_type, user_feedback,
            section_id=section_id, section_title=section_title,
            keywords=keywords, target_content=target_content,
        )
    except Exception as e:
        console.print(f"[red]Failed to submit revision: {e}[/red]")
        raise typer.Exit(1)
    finally:
        await client.close()
    if result.get("success"):
        console.print(f"[green][OK] Revision submitted[/green]")
        if result.get("revision_id"):
            console.print(f"  Revision ID: {result['revision_id']}")
    else:
        console.print(f"[red]Revision failed: {result.get('error', 'unknown error')}[/red]")
        raise typer.Exit(1)
