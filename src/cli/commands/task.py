"""Task control commands (pause/cancel/status)."""
import asyncio
import logging
from typing import Optional

import typer
from rich.table import Table

from src.cli.utils import console

logger = logging.getLogger(__name__)


def register(parent: typer.Typer) -> None:
    task_app = typer.Typer(help="Task control (pause/cancel/status)")
    parent.add_typer(task_app, name="task")

    @task_app.command("pause")
    def task_pause(task_id: str = typer.Argument(..., help="Task ID")):
        """Pause a running research task."""
        asyncio.run(_task_pause(task_id))

    @task_app.command("cancel")
    def task_cancel(task_id: str = typer.Argument(..., help="Task ID")):
        """Cancel a research task."""
        asyncio.run(_task_cancel(task_id))

    @task_app.command("status")
    def task_status(task_id: str = typer.Argument(..., help="Task ID")):
        """View task status and progress."""
        asyncio.run(_task_status(task_id))


async def _task_pause(task_id: str):
    from src.cli.client import ZensersClient, ZensersError
    try:
        async with ZensersClient() as client:
            result = await client.research_pause(task_id)
    except ZensersError as e:
        console.print(f"[red]Pause failed: {e.message}[/red]")
        return
    if result.get("status") == "paused":
        console.print(f"[green][OK] Task paused: {task_id}[/green]")
    else:
        console.print(f"[yellow]Pause result: {result.get('message', 'unknown')}[/yellow]")


async def _task_cancel(task_id: str):
    from src.cli.client import ZensersClient, ZensersError
    try:
        async with ZensersClient() as client:
            result = await client.research_cancel(task_id)
    except ZensersError as e:
        console.print(f"[red]Cancel failed: {e.message}[/red]")
        return
    if result.get("status") == "cancelled":
        console.print(f"[green][OK] Task cancelled: {task_id}[/green]")
    else:
        console.print(f"[yellow]Cancel result: {result.get('message', 'unknown')}[/yellow]")


async def _task_status(task_id: str):
    from src.cli.client import ZensersClient, ZensersError
    try:
        async with ZensersClient() as client:
            result = await client.research_status(task_id)
    except ZensersError as e:
        console.print(f"[red]Status query failed: {e.message}[/red]")
        return
    console.print(f"\n[bold]Task: {task_id}[/bold]")
    console.print(f"  Status: {result.get('status', 'unknown')}")
    console.print(f"  Progress: {result.get('progress', 0) * 100:.0f}%")
    if result.get('current_phase'):
        console.print(f"  Current Phase: {result['current_phase']}")
    if result.get('phases'):
        console.print("  Phases:")
        for p in result['phases']:
            status_icon = {"completed": "✅", "running": "⏳", "pending": "⬜", "error": "❌"}.get(p.get('status', ''), '⬜')
            console.print(f"    {status_icon} {p.get('name', 'unknown')} ({p.get('progress', 0)*100:.0f}%)")
