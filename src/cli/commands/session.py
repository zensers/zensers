"""Session management commands."""
import asyncio
import json
import logging
from pathlib import Path
from typing import Optional, List

import typer
from rich.table import Table
from rich.panel import Panel

from src.cli.utils import console, get_api_base_url

logger = logging.getLogger(__name__)


def register(parent: typer.Typer) -> None:
    session_app = typer.Typer(help="Session management (resume/revise/query/confirm generation)")

    @session_app.command("list")
    def session_list():
        """List all historical sessions"""
        asyncio.run(_session_list())

    @session_app.command("show")
    def session_show(task_id: str = typer.Argument(..., help="Task ID")):
        """View session details"""
        asyncio.run(_session_show(task_id))

    @session_app.command("resume")
    def session_resume(task_id: str = typer.Argument(..., help="Task ID")):
        """Resume interrupted session"""
        asyncio.run(_session_resume(task_id))

    @session_app.command("pause")
    def session_pause(task_id: str = typer.Argument(..., help="Task ID")):
        """Pause research task"""
        asyncio.run(_session_pause(task_id))

    @session_app.command("cancel")
    def session_cancel(task_id: str = typer.Argument(..., help="Task ID")):
        """Cancel research task"""
        asyncio.run(_session_cancel(task_id))

    @session_app.command("status")
    def session_status(task_id: str = typer.Argument(..., help="Task ID")):
        """View task status (progress, current phase, etc.)"""
        asyncio.run(_session_status(task_id))

    @session_app.command("modify")
    def session_modify(
        task_id: str = typer.Argument(..., help="Task ID"),
        aspects: str = typer.Option("", "--aspects", "-a", help="New sections, comma-separated"),
        topic: Optional[str] = typer.Option(None, "--topic", "-t", help="New topic (optional)"),
    ):
        """Modify research requirements (add new sections while paused)"""
        aspects_list = [a.strip() for a in aspects.split(",") if a.strip()] if aspects else []
        if not aspects_list:
            console.print("[red]Please specify new sections, e.g.: --aspects policy_analysis,financial_analysis[/red]")
            raise typer.Exit(1)
        asyncio.run(_session_modify(task_id, aspects_list, topic))

    @session_app.command("confirm")
    def session_confirm(
        task_id: str = typer.Argument(..., help="Task ID"),
        format: str = typer.Option("docx", "--format", "-f", help="Output format: docx, pdf, pptx"),
        output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
    ):
        """Confirm HTML preview and generate final document"""
        asyncio.run(_session_confirm(task_id, format, output))

    @session_app.command("revise")
    def session_revise(
        task_id: str = typer.Argument(..., help="Task ID"),
        aspects: str = typer.Option("", "--aspects", "-a", help="Sections to revise, comma-separated"),
    ):
        """Partially revise specified sections"""
        aspects_list = [a.strip() for a in aspects.split(",") if a.strip()] if aspects else []
        if not aspects_list:
            console.print("[red]Please specify sections to revise, e.g.: --aspects \"market size,competitive landscape\"[/red]")
            raise typer.Exit(1)
        asyncio.run(_session_revise(task_id, aspects_list))

    parent.add_typer(session_app, name="session")


async def _session_list():
    """List all historical sessions"""
    from src.core.task_persistence import TaskPersistenceManager

    tp = TaskPersistenceManager()
    tasks = tp.recover_all_tasks()

    if not tasks:
        console.print("[yellow]No historical sessions[/yellow]")
        return

    table = Table(title="Historical Sessions")
    table.add_column("Task ID", style="cyan")
    table.add_column("Topic", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Created At")
    table.add_column("Progress")

    for t in sorted(tasks, key=lambda x: x.created_at, reverse=True)[:20]:
        status = t.status.state.value if t.status else "unknown"
        progress = f"{t.status.progress*100:.0f}%" if t.status and t.status.progress else "-"
        topic = t.input_data.get("topic", "")[:30] if t.input_data else ""
        table.add_row(t.task_id, topic, status, t.created_at[:19], progress)

    console.print(table)


async def _session_show(task_id: str):
    """Show session details"""
    from src.core.task_persistence import TaskPersistenceManager
    from src.core.storage import ResearchResultStore

    tp = TaskPersistenceManager()
    task = tp.load_task(task_id)
    if not task:
        console.print(f"[red]Task not found: {task_id}[/red]")
        return

    console.print(f"\n[bold]Task: {task_id}[/bold]")
    console.print(f"  Type: {task.task_type}")
    console.print(f"  Status: {task.status.state.value if task.status else 'N/A'}")
    console.print(f"  Created: {task.created_at[:19]}")
    console.print(f"  Updated: {task.updated_at[:19]}")
    console.print(f"  Topic: {task.input_data.get('topic', 'N/A')}")
    console.print(f"  Aspects: {task.input_data.get('aspects', [])}")

    es = task.execution_state
    if es.get("completed_agents"):
        console.print(f"  Completed agents: {len(es['completed_agents'])}")
    if es.get("completed_phases"):
        console.print(f"  Completed phases: {', '.join(es['completed_phases'])}")
    if es.get("failed_agents"):
        console.print(f"  Failed agents: {len(es['failed_agents'])}")

    store = ResearchResultStore(storage_path="data")
    data = store.load_result(task_id)
    if data:
        console.print(f"  Collected data points: {len(data.get('data_points', []))}")
        console.print(f"  Collected sources: {len(data.get('sources', []))}")


async def _session_resume(task_id: str):
    """Resume interrupted session"""
    from src.core.orchestrator import ResearchOrchestrator

    console.print(f"[yellow]Resuming task: {task_id}...[/yellow]")
    orchestrator = ResearchOrchestrator()
    try:
        result = await orchestrator.resume(task_id)
        if result.status == "completed":
            console.print(f"[green]Resume successful! Report: {result.output_path}[/green]")
        else:
            console.print(f"[red]Resume failed: {result.status}[/red]")
    except Exception as e:
        console.print(f"[red]Resume failed: {e}[/red]")


async def _session_pause(task_id: str):
    """Pause research task"""
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{get_api_base_url()}/api/v1/research/{task_id}/pause", timeout=10)
            result = r.json()
            if result.get("status") == "paused":
                console.print(f"[green]✓ Task paused: {task_id}[/green]")
            else:
                console.print(f"[yellow]Pause result: {result.get('message', 'unknown')}[/yellow]")
    except Exception as e:
        console.print(f"[red]Pause failed: {e}[/red]")


async def _session_cancel(task_id: str):
    """Cancel research task"""
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{get_api_base_url()}/api/v1/research/{task_id}/cancel", timeout=10)
            result = r.json()
            if result.get("status") == "cancelled":
                console.print(f"[green]✓ Task cancelled: {task_id}[/green]")
            else:
                console.print(f"[yellow]Cancel result: {result.get('message', 'unknown')}[/yellow]")
    except Exception as e:
        console.print(f"[red]Cancel failed: {e}[/red]")


async def _session_status(task_id: str):
    """View task status"""
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{get_api_base_url()}/api/v1/research/{task_id}/status", timeout=10)
            result = r.json()
            console.print(f"\n[bold]Task: {task_id}[/bold]")
            console.print(f"  Status: {result.get('status', 'unknown')}")
            console.print(f"  Progress: {result.get('progress', 0) * 100:.0f}%")
            if result.get('current_phase'):
                console.print(f"  Current Phase: {result['current_phase']}")
            if result.get('phases'):
                console.print(f"  Phases:")
                for p in result['phases']:
                    status_icon = {"completed": "✅", "running": "⏳", "pending": "⬜", "error": "❌"}.get(p.get('status', ''), '⬜')
                    console.print(f"    {status_icon} {p.get('name', 'unknown')} ({p.get('progress', 0)*100:.0f}%)")
    except Exception as e:
        console.print(f"[red]Status query failed: {e}[/red]")


async def _session_modify(task_id: str, aspects: List[str], topic: Optional[str] = None):
    """Modify research requirements"""
    import httpx
    try:
        data = {"task_id": task_id, "aspects": json.dumps(aspects, ensure_ascii=False)}
        if topic:
            data["topic"] = topic
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{get_api_base_url()}/api/v1/research/{task_id}/modify", data=data, timeout=30)
            result = r.json()
            if result.get("status") == "requirements_updated":
                plan = result.get("plan", {})
                console.print(f"[green]✓ Requirements updated[/green]")
                console.print(f"  Topic: {plan.get('topic', 'N/A')}")
                console.print(f"  Sections: {', '.join(plan.get('sections', []))}")
                console.print(f"\n[dim]Use 'session resume {task_id}' to resume research[/dim]")
            else:
                console.print(f"[red]Modify failed: {result.get('error', 'unknown')}[/red]")
    except Exception as e:
        console.print(f"[red]Modify failed: {e}[/red]")


async def _session_revise(task_id: str, aspects: List[str]):
    """Partially revise specified sections"""
    from src.core.orchestrator import ResearchOrchestrator

    if not aspects:
        console.print("[red]Please specify sections to revise, e.g.: --aspects \"market size,competitive landscape\"[/red]")
        return

    console.print(f"[yellow]Revising sections {aspects}...[/yellow]")
    orchestrator = ResearchOrchestrator()
    try:
        result = await orchestrator.revise(task_id, aspects)
        if result.status == "completed":
            console.print(f"[green]Revision complete! Report: {result.output_path}[/green]")
        else:
            console.print(f"[red]Revision failed: {result.status}[/red]")
    except Exception as e:
        console.print(f"[red]Revision failed: {e}[/red]")


async def _session_confirm(
    task_id: str,
    format: str,
    output: Optional[str],
):
    """Confirm HTML preview and generate final document"""
    from src.core.orchestrator import ResearchOrchestrator as Orchestrator

    console.print(f"[cyan]Confirming task {task_id} and generating {format} document...[/cyan]")

    orchestrator = Orchestrator()

    try:
        result = await orchestrator.generate_document_later(
            task_id=task_id,
            output_format=format,
        )

        if result.get("success"):
            document_path = result.get("document_path") or result.get("output_path")
            if document_path:
                console.print(f"[green]✓ Document generated successfully![/green]")
                console.print(f"  Document path: {document_path}")

                if output and document_path:
                    import shutil
                    from pathlib import Path
                    src_path = Path(document_path)
                    dst_path = Path(output)
                    if src_path.exists():
                        shutil.copy2(src_path, dst_path)
                        console.print(f"  Copied to: {dst_path}")
            else:
                console.print(f"[yellow]Document generated successfully, but path not returned[/yellow]")
        else:
            error = result.get("error", "Unknown error")
            console.print(f"[red]✗ Document generation failed: {error}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]✗ Document generation failed: {e}[/red]")
        raise typer.Exit(1)
