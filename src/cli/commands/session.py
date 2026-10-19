"""Session area commands — the core of CLI session management."""
import asyncio
import logging
from pathlib import Path
from typing import Optional, List

import typer
from rich.table import Table

from src.cli.utils import console

logger = logging.getLogger(__name__)


def register(parent: typer.Typer) -> None:
    session_app = typer.Typer(help="Session area (start/attach/history/list)")

    @session_app.command("start")
    def session_start(
        requirement: str = typer.Argument(..., help="Research requirement or topic"),
        user_id: str = typer.Option("default", "--user-id", "-u", help="User ID"),
        interactive: bool = typer.Option(True, "--interactive/--no-interactive", "-i/-n", help="Enter interactive dialog after start"),
    ):
        """Start a new session and optionally enter interactive dialog."""
        asyncio.run(_session_start(requirement, user_id, interactive))

    @session_app.command("attach")
    def session_attach(
        session_id: str = typer.Argument(..., help="Session ID to attach to"),
    ):
        """Attach to an existing session and enter interactive dialog."""
        asyncio.run(_session_attach(session_id))

    @session_app.command("list")
    def session_list():
        """List all sessions."""
        asyncio.run(_session_list())

    @session_app.command("show")
    def session_show(
        session_id: str = typer.Argument(..., help="Session ID"),
    ):
        """Show session details."""
        asyncio.run(_session_show(session_id))

    @session_app.command("history")
    def session_history(
        session_id: str = typer.Argument(..., help="Session ID"),
        limit: int = typer.Option(50, "--limit", "-l", help="Max messages to show"),
    ):
        """View conversation history for a session."""
        asyncio.run(_session_history(session_id, limit))

    @session_app.command("modify")
    def session_modify(
        session_id: str = typer.Argument(..., help="Session ID"),
        aspects: str = typer.Option("", "--aspects", "-a", help="New sections, comma-separated"),
        topic: Optional[str] = typer.Option(None, "--topic", "-t", help="New topic"),
    ):
        """Modify research requirements in a session."""
        aspects_list = [a.strip() for a in aspects.split(",") if a.strip()] if aspects else []
        if not aspects_list and not topic:
            console.print("[red]Please specify --aspects or --topic[/red]")
            raise typer.Exit(1)
        asyncio.run(_session_modify(session_id, aspects_list, topic))

    @session_app.command("confirm")
    def session_confirm(
        session_id: str = typer.Argument(..., help="Session ID"),
        format: str = typer.Option("docx", "--format", "-f", help="Output format: docx, pdf, pptx"),
        output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
    ):
        """Confirm HTML preview and generate final document."""
        asyncio.run(_session_confirm(session_id, format, output))

    @session_app.command("revise")
    def session_revise(
        session_id: str = typer.Argument(..., help="Session ID"),
        aspects: str = typer.Option("", "--aspects", "-a", help="Sections to revise, comma-separated"),
    ):
        """Partially revise specified sections."""
        aspects_list = [a.strip() for a in aspects.split(",") if a.strip()] if aspects else []
        if not aspects_list:
            console.print("[red]Please specify sections to revise[/red]")
            raise typer.Exit(1)
        asyncio.run(_session_revise(session_id, aspects_list))

    @session_app.command("delete")
    def session_delete(
        session_id: str = typer.Argument(..., help="Session ID"),
        force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    ):
        """Delete a session and its data."""
        asyncio.run(_session_delete(session_id, force))

    parent.add_typer(session_app, name="session")


async def _session_start(requirement: str, user_id: str, interactive: bool):
    """Start a new session via API and optionally enter REPL."""
    from src.cli.client import ZensersClient, ZensersError

    try:
        async with ZensersClient() as client:
            result = await client.research_start(requirement, user_id=user_id)
    except ZensersError as e:
        console.print(f"[red]Failed to start session: {e.message}[/red]")
        raise typer.Exit(1)

    session_id = result.get("session_id", "")
    if not session_id:
        console.print(f"[red]No session ID returned[/red]")
        raise typer.Exit(1)

    console.print(f"[green][OK] Session started: {session_id}[/green]")

    response = result.get("response", result.get("message", ""))
    if response:
        from rich.markdown import Markdown
        console.print(f"[bold blue]Assistant:[/bold blue]")
        console.print(Markdown(str(response)[:2000]))

    if interactive:
        from src.cli.repl import SessionREPL
        repl = SessionREPL(session_id)
        await repl.run()
    else:
        console.print(f"[dim]Use 'session attach {session_id}' to enter interactive dialog[/dim]")


async def _session_attach(session_id: str):
    """Attach to existing session and enter REPL."""
    from src.cli.client import ZensersClient, ZensersError

    try:
        async with ZensersClient() as client:
            result = await client.research_status(session_id)
    except ZensersError as e:
        console.print(f"[red]Session not found: {e.message}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Attaching to session: {session_id}[/green]")
    console.print(f"  Status: {result.get('status', 'unknown')}")

    from src.cli.repl import SessionREPL
    repl = SessionREPL(session_id)
    await repl.run()


async def _session_list():
    """List all sessions."""
    from src.cli.client import ZensersClient, ZensersError

    try:
        async with ZensersClient() as client:
            result = await client.research_sessions(limit=50)
    except ZensersError as e:
        console.print(f"[red]Failed to list sessions: {e.message}[/red]")
        raise typer.Exit(1)

    sessions = result.get("sessions", [])
    if not sessions:
        console.print("[yellow]No sessions[/yellow]")
        return

    table = Table(title="Sessions")
    table.add_column("Session ID", style="cyan")
    table.add_column("Topic", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Created At", style="dim")
    for s in sessions[:20]:
        table.add_row(
            s.get("session_id", s.get("task_id", "N/A"))[:16],
            (s.get("topic", "") or s.get("user_input", ""))[:30],
            s.get("status", "unknown"),
            s.get("created_at", "")[:19],
        )
    console.print(table)


async def _session_show(session_id: str):
    """Show session details."""
    from src.cli.client import ZensersClient, ZensersError

    try:
        async with ZensersClient() as client:
            result = await client.research_detail(session_id)
    except ZensersError as e:
        console.print(f"[red]Session not found: {e.message}[/red]")
        return

    console.print(f"\n[bold]Session: {session_id}[/bold]")
    console.print(f"  Status: {result.get('status', 'N/A')}")
    console.print(f"  Topic: {result.get('topic', 'N/A')}")
    console.print(f"  Created: {result.get('created_at', 'N/A')}")
    console.print(f"  Mode: {result.get('mode', 'N/A')}")
    if result.get("sections"):
        console.print(f"  Sections: {', '.join(result['sections'][:5])}{'...' if len(result['sections']) > 5 else ''}")


async def _session_history(session_id: str, limit: int):
    """View conversation history."""
    from src.cli.client import ZensersClient, ZensersError

    try:
        async with ZensersClient() as client:
            result = await client.research_messages(session_id, limit=limit)
    except ZensersError as e:
        console.print(f"[red]Failed to load history: {e.message}[/red]")
        return

    messages = result.get("messages", [])
    if not messages:
        console.print("[dim]No conversation history[/dim]")
        return

    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        timestamp = msg.get("timestamp", "")
        role_style = {"user": "green", "assistant": "blue"}.get(role, "white")
        role_label = {"user": "You", "assistant": "Assistant"}.get(role, role)
        console.print(f"[{role_style}]{role_label}[/{role_style}] [dim]{timestamp}[/dim]")
        console.print(f"  {str(content)[:200]}")
        console.print("")

    if result.get("has_more"):
        console.print(f"[dim]... {result['total'] - len(messages)} more messages. Use --limit to see more.[/dim]")


async def _session_modify(session_id: str, aspects: List[str], topic: Optional[str]):
    """Modify research requirements."""
    from src.cli.client import ZensersClient, ZensersError

    try:
        async with ZensersClient() as client:
            result = await client.research_modify(session_id, aspects, topic)
    except ZensersError as e:
        console.print(f"[red]Modify failed: {e.message}[/red]")
        return

    if result.get("status") == "requirements_updated":
        plan = result.get("plan", {})
        console.print("[green][OK] Requirements updated[/green]")
        console.print(f"  Topic: {plan.get('topic', 'N/A')}")
        console.print(f"  Sections: {', '.join(plan.get('sections', []))}")
        console.print(f"\n[dim]Use 'session attach {session_id}' to continue[/dim]")
    else:
        console.print(f"[red]Modify failed: {result.get('error', 'unknown')}[/red]")


async def _session_confirm(session_id: str, format: str, output: Optional[str]):
    """Confirm and generate document via API."""
    from src.cli.client import ZensersClient, ZensersError

    console.print(f"[cyan]Confirming session {session_id} and generating {format} document...[/cyan]")

    try:
        async with ZensersClient() as client:
            result = await client.document_generate(session_id, output_format=format)
    except ZensersError as e:
        console.print(f"[red]Confirm/generate failed: {e.message}[/red]")
        raise typer.Exit(1)

    if result.get("success") or result.get("status") in ("completed", "generating"):
        document_path = result.get("document_path") or result.get("output_path")
        if document_path:
            console.print(f"[green][OK] Document generated: {document_path}[/green]")
            if output and document_path:
                import shutil
                src_path = Path(document_path)
                dst_path = Path(output)
                if src_path.exists():
                    dst_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_path, dst_path)
                    console.print(f"  Copied to: {dst_path}")
        else:
            console.print(f"[green][OK] Document generation started. {result.get('message', '')}[/green]")
    else:
        console.print(f"[red][FAIL] Document generation failed: {result.get('error', result.get('message', 'Unknown error'))}[/red]")
        raise typer.Exit(1)


async def _session_revise(session_id: str, aspects: List[str]):
    """Revise sections via API."""
    from src.cli.client import ZensersClient, ZensersError

    console.print(f"[yellow]Revising sections {aspects}...[/yellow]")

    try:
        async with ZensersClient() as client:
            result = await client.research_revise(session_id, aspects)
    except ZensersError as e:
        console.print(f"[red]Revision failed: {e.message}[/red]")
        return

    status = result.get("status", "")
    if status in ("completed", "revising", "revision_submitted"):
        console.print(f"[green][OK] Revision submitted. Status: {status}[/green]")
    else:
        console.print(f"[red]Revision failed: {result.get('error', status or 'unknown')}[/red]")


async def _session_delete(session_id: str, force: bool):
    """Delete a session via API."""
    if not force:
        console.print(f"[yellow]Are you sure you want to delete session {session_id}? Use --force to confirm.[/yellow]")
        return

    from src.cli.client import ZensersClient, ZensersError

    try:
        async with ZensersClient() as client:
            await client.research_cancel(session_id)
    except ZensersError as e:
        console.print(f"[red]Delete failed: {e.message}[/red]")
        raise typer.Exit(1)

    console.print(f"[green][OK] Session deleted: {session_id}[/green]")
