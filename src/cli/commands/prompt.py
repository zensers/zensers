"""Prompt management commands."""
import asyncio
import json
import logging
from typing import Optional, Dict, Any

import typer
from rich.table import Table

from src.cli.utils import console

logger = logging.getLogger(__name__)


def register(parent: typer.Typer) -> None:
    prompt_app = typer.Typer(help="Prompt management")
    parent.add_typer(prompt_app, name="prompt")

    @prompt_app.command("list")
    def prompt_list_command(
        category: Optional[str] = typer.Argument(None, help="Category name (omit to list categories)"),
    ):
        """List prompts or categories."""
        asyncio.run(_prompt_list_async(category))

    @prompt_app.command("show")
    def prompt_show_command(
        category: str = typer.Argument(..., help="Category name"),
        name: str = typer.Argument(..., help="Prompt name"),
    ):
        """Show prompt content."""
        asyncio.run(_prompt_show_async(category, name))

    @prompt_app.command("render")
    def prompt_render_command(
        category: str = typer.Argument(..., help="Category name"),
        name: str = typer.Argument(..., help="Prompt name"),
        variables: str = typer.Option("{}", "--vars", "-v", help="JSON-encoded variables"),
    ):
        """Render a prompt with variables."""
        try:
            parsed_vars: Dict[str, Any] = json.loads(variables) if variables else {}
        except json.JSONDecodeError:
            console.print("[red]Invalid JSON for --vars[/red]")
            raise typer.Exit(1)
        asyncio.run(_prompt_render_async(category, name, parsed_vars))


async def _prompt_list_async(category: Optional[str] = None):
    from src.cli.client import ZensersClient

    client = ZensersClient()
    try:
        if category:
            prompts = await client.prompt_list(category)
            if not prompts:
                console.print(f"[yellow]No prompts found in category '{category}'[/yellow]")
                return
            table = Table(title=f"Prompts in '{category}'")
            table.add_column("Name", style="cyan")
            table.add_column("Path")
            table.add_column("Has Frontmatter")
            table.add_column("Size (bytes)", justify="right")
            for p in prompts:
                table.add_row(p.get("name", ""), p.get("path", ""), str(p.get("has_frontmatter", False)), str(p.get("size_bytes", 0)))
            console.print(table)
        else:
            categories = await client.prompt_categories()
            if not categories:
                console.print("[yellow]No prompt categories found[/yellow]")
                return
            table = Table(title="Prompt Categories")
            table.add_column("Category", style="cyan")
            for cat in categories:
                table.add_row(cat)
            console.print(table)
    except Exception as e:
        console.print(f"[red]Failed to list prompts: {e}[/red]")
        raise typer.Exit(1)
    finally:
        await client.close()


async def _prompt_show_async(category: str, name: str):
    from src.cli.client import ZensersClient
    from rich.panel import Panel

    client = ZensersClient()
    try:
        result = await client.prompt_get(category, name)
    except Exception as e:
        console.print(f"[red]Failed to get prompt: {e}[/red]")
        raise typer.Exit(1)
    finally:
        await client.close()
    content = result.get("content", "")
    console.print(Panel.fit(
        str(content)[:4000],
        title=f"Prompt: {category}/{name}",
        border_style="cyan"
    ))
    if len(str(content)) > 4000:
        console.print(f"[dim]... truncated, total {result.get('length', len(content))} chars[/dim]")


async def _prompt_render_async(category: str, name: str, variables: Dict[str, Any]):
    from src.cli.client import ZensersClient
    from rich.panel import Panel

    client = ZensersClient()
    try:
        result = await client.prompt_render(category, name, variables)
    except Exception as e:
        console.print(f"[red]Failed to render prompt: {e}[/red]")
        raise typer.Exit(1)
    finally:
        await client.close()
    rendered = result.get("rendered", result.get("content", ""))
    console.print(Panel.fit(
        str(rendered)[:4000],
        title=f"Rendered: {category}/{name}",
        border_style="green"
    ))
    if len(str(rendered)) > 4000:
        console.print(f"[dim]... truncated, total {result.get('length', len(rendered))} chars[/dim]")
