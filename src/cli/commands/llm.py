"""LLM configuration and model commands."""
import asyncio
import logging
from typing import Optional

import typer
from rich.table import Table
from rich.panel import Panel

from src.cli.utils import console

logger = logging.getLogger(__name__)


def register(parent: typer.Typer) -> None:
    llm_app = typer.Typer(help="LLM configuration and models")
    parent.add_typer(llm_app, name="llm")

    @llm_app.command("models")
    def llm_models_command(
        provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Filter by provider"),
    ):
        """List available LLM models."""
        asyncio.run(_llm_models_async(provider))

    @llm_app.command("config")
    def llm_config_command():
        """Show current LLM configuration."""
        asyncio.run(_llm_config_async())

    @llm_app.command("health")
    def llm_health_command():
        """Check LLM connectivity."""
        asyncio.run(_llm_health_async())

    @llm_app.command("set-config")
    def llm_set_config_command(
        provider: Optional[str] = typer.Option(None, "--provider", "-p", help="LLM provider"),
        model: Optional[str] = typer.Option(None, "--model", "-m", help="Model name"),
        api_key: Optional[str] = typer.Option(None, "--api-key", "-k", help="API key"),
        api_endpoint: Optional[str] = typer.Option(None, "--api-endpoint", "-e", help="API endpoint URL"),
        temperature: Optional[float] = typer.Option(None, "--temperature", "-t", help="Temperature"),
        max_tokens: Optional[int] = typer.Option(None, "--max-tokens", help="Max tokens"),
    ):
        """Update LLM configuration."""
        if not any([provider, model, api_key, api_endpoint, temperature is not None, max_tokens is not None]):
            console.print("[red]Please specify at least one config option[/red]")
            raise typer.Exit(1)
        asyncio.run(_llm_set_config_async(provider, model, api_key, api_endpoint, temperature, max_tokens))

    @llm_app.command("reset-config")
    def llm_reset_config_command():
        """Reset LLM configuration to defaults."""
        asyncio.run(_llm_reset_config_async())


async def _llm_models_async(provider: Optional[str] = None):
    from src.cli.client import ZensersClient, ZensersError
    try:
        async with ZensersClient() as client:
            result = await client.llm_models()
    except ZensersError as e:
        console.print(f"[red]Failed to list LLM models: {e.message}[/red]")
        raise typer.Exit(1)
    providers = result.get("providers", [])
    models = result.get("models", [])

    ptable = Table(title="Supported Providers")
    ptable.add_column("ID", style="cyan")
    ptable.add_column("Name", style="green")
    ptable.add_column("Default Endpoint")
    for p in providers:
        if provider and p["id"] != provider:
            continue
        ptable.add_row(p["id"], p["name"], p.get("default_endpoint", ""))
    console.print(ptable)

    mtable = Table(title="Available Models")
    mtable.add_column("ID", style="cyan")
    mtable.add_column("Name", style="green")
    mtable.add_column("Provider")
    mtable.add_column("Max Tokens", justify="right")
    for m in models:
        if provider and m["provider"] != provider:
            continue
        mtable.add_row(m["id"], m["name"], m["provider"], f"{m.get('max_tokens', 0):,}")
    console.print(mtable)


async def _llm_config_async():
    from src.cli.client import ZensersClient, ZensersError
    try:
        async with ZensersClient() as client:
            result = await client.llm_config()
    except ZensersError as e:
        console.print(f"[red]Failed to get LLM config: {e.message}[/red]")
        raise typer.Exit(1)
    console.print(Panel.fit(
        f"  Provider: {result.get('provider', 'N/A')}\n"
        f"  Model: {result.get('model', 'N/A')}\n"
        f"  API Endpoint: {result.get('apiEndpoint', 'N/A')}\n"
        f"  Temperature: {result.get('temperature', 'N/A')}\n"
        f"  Max Tokens: {result.get('maxTokens', 'N/A')}\n"
        f"  Has API Key: {result.get('hasApiKey', False)}",
        title="LLM Configuration"
    ))


async def _llm_health_async():
    from src.cli.client import ZensersClient, ZensersError
    try:
        async with ZensersClient() as client:
            result = await client.llm_health()
    except ZensersError as e:
        console.print(f"[red]LLM health check failed: {e.message}[/red]")
        raise typer.Exit(1)
    reachable = result.get("reachable", False)
    status_style = "green" if reachable else "red"
    table = Table(title="LLM Health")
    table.add_column("Check", style="cyan")
    table.add_column("Result", style=status_style)
    table.add_row("Model", result.get("model", "N/A"))
    table.add_row("Has API Key", str(result.get("has_key", False)))
    table.add_row("Reachable", f"[{status_style}]{reachable}[/{status_style}]")
    if result.get("error"):
        table.add_row("Error", result["error"])
    console.print(table)


async def _llm_set_config_async(provider, model, api_key, api_endpoint, temperature, max_tokens):
    from src.cli.client import ZensersClient, ZensersError
    try:
        async with ZensersClient() as client:
            result = await client.llm_set_config(provider, model, api_key, api_endpoint, temperature, max_tokens)
    except ZensersError as e:
        console.print(f"[red]Failed to set LLM config: {e.message}[/red]")
        raise typer.Exit(1)
    console.print("[green][OK] LLM configuration updated[/green]")


async def _llm_reset_config_async():
    from src.cli.client import ZensersClient, ZensersError
    try:
        async with ZensersClient() as client:
            result = await client.llm_reset_config()
    except ZensersError as e:
        console.print(f"[red]Failed to reset LLM config: {e.message}[/red]")
        raise typer.Exit(1)
    console.print("[green][OK] LLM configuration reset to defaults[/green]")
