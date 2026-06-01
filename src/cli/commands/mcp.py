"""MCP server management commands."""
import asyncio
import logging
from typing import Optional

import typer
from rich.table import Table
from rich.panel import Panel

from src.cli.utils import console

logger = logging.getLogger(__name__)


def register(parent: typer.Typer) -> None:
    mcp_app = typer.Typer(help="MCP server management")
    parent.add_typer(mcp_app, name="mcp")

    @mcp_app.command("list")
    def mcp_list_command():
        """List all MCP servers and their status."""
        asyncio.run(_mcp_list_async())

    @mcp_app.command("start")
    def mcp_start_command(
        server_name: str = typer.Argument(..., help="Server name"),
    ):
        """Start an MCP server."""
        asyncio.run(_mcp_start_async(server_name))

    @mcp_app.command("stop")
    def mcp_stop_command(
        server_name: str = typer.Argument(..., help="Server name"),
    ):
        """Stop an MCP server."""
        asyncio.run(_mcp_stop_async(server_name))

    @mcp_app.command("status")
    def mcp_status_command(
        server_name: str = typer.Argument(..., help="Server name"),
    ):
        """Get MCP server status."""
        asyncio.run(_mcp_status_async(server_name))

    @mcp_app.command("health")
    def mcp_health_command():
        """Check MCP health."""
        asyncio.run(_mcp_health_async())

    @mcp_app.command("reload")
    def mcp_reload_command():
        """Reload MCP configuration."""
        asyncio.run(_mcp_reload_async())


async def _mcp_list_async():
    from src.cli.client import ZensersClient

    client = ZensersClient()
    try:
        result = await client.mcp_list()
    except Exception as e:
        console.print(f"[red]Failed to list MCP servers: {e}[/red]")
        raise typer.Exit(1)
    finally:
        await client.close()

    servers = result.get("servers", [])
    if not servers:
        console.print("[yellow]No MCP servers configured[/yellow]")
        return

    table = Table(title=f"MCP Servers (total: {result.get('total', 0)}, running: {result.get('running_count', 0)})")
    table.add_column("Name", style="cyan")
    table.add_column("Transport", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Tools", justify="right")
    table.add_column("Latency", justify="right")
    table.add_column("Error")
    for s in servers:
        status_style = {"running": "green", "stopped": "dim", "error": "red", "starting": "yellow"}.get(s.get("status", ""), "white")
        table.add_row(
            s.get("name", ""),
            s.get("transport", ""),
            f"[{status_style}]{s.get('status', '')}[/{status_style}]",
            str(s.get("tools_count", 0)),
            f"{s.get('latency_ms', 0):.0f}ms" if s.get("latency_ms") else "-",
            s.get("error", "") or "",
        )
    console.print(table)


async def _mcp_start_async(server_name: str):
    from src.cli.client import ZensersClient

    client = ZensersClient()
    try:
        result = await client.mcp_start(server_name)
    except Exception as e:
        console.print(f"[red]Failed to start MCP server '{server_name}': {e}[/red]")
        raise typer.Exit(1)
    finally:
        await client.close()
    if result.get("success"):
        console.print(f"[green]✓ MCP server '{server_name}' started (status: {result.get('new_status', 'unknown')})[/green]")
    else:
        console.print(f"[red]Failed to start MCP server '{server_name}': {result.get('message', 'unknown error')}[/red]")
        raise typer.Exit(1)


async def _mcp_stop_async(server_name: str):
    from src.cli.client import ZensersClient

    client = ZensersClient()
    try:
        result = await client.mcp_stop(server_name)
    except Exception as e:
        console.print(f"[red]Failed to stop MCP server '{server_name}': {e}[/red]")
        raise typer.Exit(1)
    finally:
        await client.close()
    if result.get("success"):
        console.print(f"[green]✓ MCP server '{server_name}' stopped (status: {result.get('new_status', 'unknown')})[/green]")
    else:
        console.print(f"[red]Failed to stop MCP server '{server_name}': {result.get('message', 'unknown error')}[/red]")
        raise typer.Exit(1)


async def _mcp_status_async(server_name: str):
    from src.cli.client import ZensersClient

    client = ZensersClient()
    try:
        result = await client.mcp_status(server_name)
    except Exception as e:
        console.print(f"[red]Failed to get MCP server status: {e}[/red]")
        raise typer.Exit(1)
    finally:
        await client.close()
    console.print(Panel.fit(
        f"  Name: {result.get('name', '')}\n"
        f"  Transport: {result.get('transport', '')}\n"
        f"  Status: {result.get('status', '')}\n"
        f"  Description: {result.get('description', '')}\n"
        f"  Tools: {result.get('tools_count', 0)}\n"
        f"  Latency: {result.get('latency_ms', 0):.0f}ms\n"
        f"  Error: {result.get('error', 'none')}\n"
        f"  Tags: {', '.join(result.get('tags', []))}",
        title=f"MCP Server: {server_name}"
    ))


async def _mcp_health_async():
    from src.cli.client import ZensersClient

    client = ZensersClient()
    try:
        result = await client.mcp_health()
    except Exception as e:
        console.print(f"[red]MCP health check failed: {e}[/red]")
        raise typer.Exit(1)
    finally:
        await client.close()
    summary = result.get("summary", {})
    table = Table(title="MCP Health Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Total Servers", str(summary.get("total", 0)))
    table.add_row("Healthy", str(summary.get("healthy", 0)))
    table.add_row("Unhealthy", str(summary.get("unhealthy", 0)))
    console.print(table)


async def _mcp_reload_async():
    from src.cli.client import ZensersClient

    client = ZensersClient()
    try:
        result = await client.mcp_reload()
    except Exception as e:
        console.print(f"[red]Failed to reload MCP config: {e}[/red]")
        raise typer.Exit(1)
    finally:
        await client.close()
    if result.get("success"):
        console.print(f"[green]✓ MCP configuration reloaded ({result.get('servers_count', 0)} servers)[/green]")
    else:
        console.print(f"[red]MCP reload failed: {result.get('message', 'unknown error')}[/red]")
        raise typer.Exit(1)
