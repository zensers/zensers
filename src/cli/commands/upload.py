"""File upload commands."""
import asyncio
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from src.cli.utils import console

logger = logging.getLogger(__name__)


def register(parent: typer.Typer) -> None:
    upload_app = typer.Typer(help="File upload management")
    parent.add_typer(upload_app, name="upload")

    @upload_app.command("file")
    def upload_file_command(
        path: str = typer.Argument(..., help="File path to upload"),
        session_id: Optional[str] = typer.Option(None, "--session-id", "-s", help="Session ID to attach file to"),
    ):
        """Upload file to server."""
        asyncio.run(_upload_file_async(path, session_id))

    @upload_app.command("delete")
    def delete_file_command(
        file_id: str = typer.Argument(..., help="File ID to delete"),
    ):
        """Delete uploaded file."""
        asyncio.run(_delete_file_async(file_id))


async def _upload_file_async(path: str, session_id: Optional[str]):
    from src.cli.client import ZensersClient

    file_path = Path(path)
    if not file_path.exists():
        console.print(f"[red]File not found: {path}[/red]")
        raise typer.Exit(1)
    if not file_path.is_file():
        console.print(f"[red]Not a file: {path}[/red]")
        raise typer.Exit(1)
    client = ZensersClient()
    try:
        result = await client.upload_file(path, session_id)
    except Exception as e:
        console.print(f"[red]Upload failed: {e}[/red]")
        raise typer.Exit(1)
    finally:
        await client.close()
    files = result.get("files", [])
    table = Table(title="Upload Results")
    table.add_column("File ID", style="cyan")
    table.add_column("Filename", style="green")
    table.add_column("Size", justify="right")
    table.add_column("Type")
    for f in files:
        table.add_row(f.get("id", ""), f.get("filename", ""), f"{f.get('size', 0):,}", f.get("type", ""))
    console.print(table)


async def _delete_file_async(file_id: str):
    from src.cli.client import ZensersClient

    client = ZensersClient()
    try:
        result = await client.delete_file(file_id)
    except Exception as e:
        console.print(f"[red]Failed to delete file: {e}[/red]")
        raise typer.Exit(1)
    finally:
        await client.close()
    removed = result.get("removed", 0)
    console.print(f"[green]✓ Deleted {removed} file(s) (ID: {file_id})[/green]")
