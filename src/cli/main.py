"""Zensers CLI - Command Line Interface.

Provides research task submission, status query, report download and other functions.
"""

import asyncio
import json
import logging
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from src.cli.utils import console, setup_cli_logging, set_api_base_url, get_api_base_url
from src.cli.commands import session, task, knowledge, survey, mcp, llm, prompt, document, upload

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="zensers",
    help="Zensers - Automated Industry Research System",
    no_args_is_help=True,
)

# Register all subcommand groups
session.register(app)
task.register(app)
knowledge.register(app)
survey.register(app)
mcp.register(app)
llm.register(app)
prompt.register(app)
document.register(app)
upload.register(app)


@app.callback()
def global_options(
    api_url: Optional[str] = typer.Option(None, "--api-url", envvar="ZENSERS_API_URL", help="API server base URL"),
    no_color: bool = typer.Option(False, "--no-color", help="Disable colored output"),
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
):
    """Zensers - Automated Industry Research System."""
    if api_url:
        set_api_base_url(api_url)
    if no_color:
        console.no_color = True
    if json_output:
        from src.cli.utils import set_output_json
        set_output_json(True)


# ===== Top-level command: research =====

@app.command()
def research(
    requirement: str = typer.Argument(..., help="Research requirement description"),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
    format: str = typer.Option(
        "docx", "--format", "-f", help="Output format: docx, pdf, html, markdown"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show verbose logs"
    ),
    interactive: bool = typer.Option(
        True, "--interactive/--no-interactive", "-i/-n", help="Enable interactive mode"
    ),
    # === Custom options ===
    aspects: Optional[str] = typer.Option(
        None, "--aspects", "-a", help="Custom sections, comma-separated: market size,competitive landscape,industry chain"
    ),
    framework: Optional[str] = typer.Option(
        None, "--framework", "--fw", help="Research framework: detailed/standard/brief"
    ),
    template: Optional[str] = typer.Option(
        None, "--template", "-t", help="Output template: research_report(default)/default"
    ),
    output_type: Optional[str] = typer.Option(
        None, "--type", "--output-type", help="Report type: industry_report/company_research/market_brief"
    ),
    language: Optional[str] = typer.Option(
        None, "--language", "-l", help="Language: zh/en/ja/ko"
    ),
):
    """Submit research requirement and generate report."""
    if verbose:
        setup_cli_logging(verbose=True)

    if language:
        try:
            from src.core.i18n import set_language, Language
            set_language(Language(language))
            logger.info(f"CLI language set to: {language}")
        except Exception:
            logger.warning(f"Unsupported language: {language}")

    asyncio.run(_research_async(
        requirement, output, format, verbose, interactive,
        aspects=aspects.split(",") if aspects else None,
        framework=framework, template=template, output_type=output_type,
    ))


async def _research_async(
    requirement: str,
    output: Optional[str],
    format: str,
    verbose: bool,
    interactive: bool,
    aspects: Optional[List[str]] = None,
    framework: Optional[str] = None,
    template: Optional[str] = None,
    output_type: Optional[str] = None,
):
    """Execute research task via API."""
    from src.cli.client import ZensersClient, ZensersError

    console.print(Panel.fit(
        f"[bold blue]Zensers[/bold blue] - Starting Research Task\n"
        f"[dim]Requirement: {requirement[:50]}{'...' if len(requirement) > 50 else ''}[/dim]"
    ))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Submitting research task...", total=None)

        try:
            async with ZensersClient() as client:
                if template:
                    start_result = await client.research_quick_start(
                        user_input=requirement,
                        template_id=template,
                        auto_confirm=not interactive,
                        custom_params={"aspects": aspects, "framework": framework, "output_type": output_type} if any([aspects, framework, output_type]) else None,
                    )
                else:
                    start_result = await client.research_start(user_input=requirement)

                session_id = start_result.get("session_id") or start_result.get("task_id")
                if not session_id:
                    console.print(f"[red]Failed to start research: no session_id returned[/red]")
                    raise typer.Exit(1)

                progress.update(task, description=f"Session {session_id[:12]} created")

                if not interactive:
                    if start_result.get("mode") == "chat" or start_result.get("status") is None:
                        console.print(f"\n[green][OK] Research session started: {session_id}[/green]")
                        response = start_result.get("response", start_result.get("message", ""))
                        if response:
                            from rich.markdown import Markdown
                            console.print(f"[bold blue]Assistant:[/bold blue]")
                            console.print(Markdown(str(response)[:2000]))
                        console.print(f"\n[dim]Session is in dialogue mode. Use --interactive to continue, or:[/dim]")
                        console.print(f"[dim]  python -m src.cli.main session attach {session_id}[/dim]")
                        progress.update(task, description="Session created (non-interactive)")
                        return
                    while True:
                        status_result = await client.research_status(session_id)
                        status = status_result.get("status", "unknown")
                        progress.update(task, description=f"Task {session_id[:12]} - {status}")
                        if status in ("completed", "failed", "cancelled"):
                            result = status_result
                            result["task_id"] = session_id
                            break
                        await asyncio.sleep(2)
                    progress.update(task, description="Research complete")
                    _print_research_result(result, output)
                    return

                result = start_result
                result.setdefault("session_id", session_id)
                progress.update(task, description="Session ready for interactive dialogue")

        except ZensersError as e:
            logger.error(f"Research execution failed: {e.message}", exc_info=True)
            console.print(f"[red]Research execution failed: {e.message}[/red]")
            raise typer.Exit(1)

    if interactive and result.get("session_id"):
        from src.cli.repl import SessionREPL
        console.print(f"[green][OK] Session started: {result['session_id']}[/green]")
        response = result.get("response", result.get("message", ""))
        if response:
            from rich.markdown import Markdown
            console.print(f"[bold blue]Assistant:[/bold blue]")
            console.print(Markdown(str(response)[:2000]))
        repl = SessionREPL(result["session_id"])
        await repl.run()


def _print_research_result(result: dict, output: Optional[str]):
    status = result.get("status", "unknown")
    if status == "completed":
        console.print("\n[green][OK] Research task completed![/green]")

        table = Table(title="Report Information")
        table.add_column("Item", style="cyan")
        table.add_column("Content", style="green")

        table.add_row("Task ID", result.get("task_id", "N/A"))
        table.add_row("Topic", result.get("topic", "N/A"))
        table.add_row("Status", status)
        table.add_row("Output Path", str(result.get("output_path", "N/A")))
        agents = result.get("agents_used", [])
        table.add_row("Used Agents", ", ".join(agents) if isinstance(agents, list) else str(agents))

        console.print(table)

        document_path = result.get("document_path")
        if output and document_path:
            src_path = Path(document_path)
            dst_path = Path(output)
            if src_path.exists():
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, dst_path)
                console.print(f"\n[green]Report saved: {output}[/green]")
            else:
                console.print(f"\n[yellow]Warning: Document path does not exist {document_path}[/yellow]")
        elif output and not document_path:
            console.print(f"\n[yellow]Warning: Research complete but no document generated, cannot save to {output}[/yellow]")

        if document_path:
            console.print(f"\n[green]Report generated: {document_path}[/green]")
        console.print("[dim]Use python -m src.cli.main session list to view historical tasks[/dim]")
        console.print("[dim]Use python -m src.cli.main session attach <session_id> to enter session REPL[/dim]")

    else:
        console.print(f"\n[red]Research failed: {status}[/red]")
        raise typer.Exit(1)


# ===== Top-level command: status =====

@app.command()
def status(
    task_id: Optional[str] = typer.Argument(None, help="Task ID"),
    watch: bool = typer.Option(False, "--watch", "-w", help="Continuously monitor status"),
):
    """Query research task status."""
    if task_id:
        asyncio.run(_get_task_status_remote(task_id, watch))
    else:
        asyncio.run(_list_active_tasks_remote())


async def _get_task_status_remote(task_id: str, watch: bool):
    from src.cli.client import ZensersClient, ZensersError
    async with ZensersClient() as client:
        if watch:
            console.print(f"[dim]Monitoring task {task_id} (press Ctrl+C to stop)...[/dim]\n")
            try:
                while True:
                    result = await client.research_status(task_id)
                    console.print(f"[dim]Status: {result.get('status', 'unknown')}[/dim]")
                    if result.get("status") in ("completed", "failed", "cancelled"):
                        break
                    await asyncio.sleep(2)
            except KeyboardInterrupt:
                console.print("\n[dim]Monitoring stopped[/dim]")
        else:
            try:
                result = await client.research_status(task_id)
            except ZensersError as e:
                console.print(f"[red]Failed to get task status: {e.message}[/red]")
                raise typer.Exit(1)
            console.print(f"Status: {result.get('status', 'unknown')}")
            if result.get("topic"):
                console.print(f"Topic: {result['topic']}")
            if result.get("progress"):
                console.print(f"Progress: {result['progress']}")


async def _list_active_tasks_remote():
    from src.cli.client import ZensersClient, ZensersError
    try:
        async with ZensersClient() as client:
            result = await client.research_sessions(limit=50)
    except ZensersError as e:
        console.print(f"[red]Failed to list active tasks: {e.message}[/red]")
        raise typer.Exit(1)

    sessions = result.get("sessions", [])
    active = [s for s in sessions if s.get("status") in ("analyzing", "reporting", "paused")]
    if not active:
        console.print("[dim]No active tasks[/dim]")
        return

    table = Table(title=f"Active Tasks ({len(active)} total)")
    table.add_column("Task ID", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Topic", style="yellow")
    table.add_column("Created At", style="dim")
    for s in active:
        # Persisted sessions may contain explicit null values.  ``dict.get``
        # does not apply its default to null, so normalize before slicing.
        task_id = str(s.get("task_id") or "N/A")
        status = str(s.get("status") or "unknown")
        topic = str(s.get("topic") or "")
        created_at = str(s.get("created_at") or "")
        table.add_row(task_id[:12], status, topic[:30], created_at[:19])
    console.print(table)


# ===== Top-level command: download =====

@app.command()
def download(
    task_id: str = typer.Argument(..., help="Task ID"),
    output: str = typer.Option(..., "--output", "-o", help="Output file path"),
    format: str = typer.Option(
        "markdown", "--format", "-f",
        help="Format is auto-detected from Content-Type header; kept for backward compatibility."
    ),
):
    """Download research report."""
    asyncio.run(_download_report(task_id, output, format))


async def _download_report(task_id: str, output: str, format: str):
    from src.cli.client import ZensersClient, ZensersError
    try:
        async with ZensersClient() as client:
            content, content_type = await client.download(task_id)
    except FileNotFoundError:
        console.print(f"[red]Report not found: {task_id}[/red]")
        raise typer.Exit(1)
    except ZensersError as e:
        console.print(f"[red]Download failed: {e.message}[/red]")
        raise typer.Exit(1)

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)
    console.print(f"[green]Report downloaded: {output_path} ({len(content)} bytes)[/green]")


# ===== Top-level command: config =====

@app.command()
def config(
    show: bool = typer.Option(False, "--show", help="Show current configuration"),
    reset: bool = typer.Option(False, "--reset", help="Reset to default configuration"),
    set_key: Optional[str] = typer.Option(None, "--set", help="Set config key=value (e.g. --set default_output_format=docx)"),
):
    """Manage CLI configuration."""
    from src.cli.utils import CLIConfig

    if set_key:
        if "=" not in set_key:
            console.print("[red]Invalid format. Use: --set key=value[/red]")
            raise typer.Exit(1)
        key, value = set_key.split("=", 1)
        cfg = CLIConfig.load()
        if key not in CLIConfig.__dataclass_fields__:
            console.print(f"[red]Unknown config key: {key}[/red]")
            console.print(f"[dim]Available keys: {', '.join(CLIConfig.__dataclass_fields__.keys())}[/dim]")
            raise typer.Exit(1)
        setattr(cfg, key, value)
        cfg.save()
        console.print(f"[green]Set {key} = {value}[/green]")
    elif show:
        cfg = CLIConfig.load()
        console.print_json(json.dumps(asdict(cfg)))
    elif reset:
        cfg = CLIConfig()
        cfg.save()
        console.print("[green]Configuration reset to defaults[/green]")
    else:
        console.print("[dim]Use --show to view config, --reset to reset, or --set key=value to update[/dim]")


# ===== Top-level command: version =====

@app.command()
def version():
    """Show version information."""
    from src.core.version import get_local_version, get_build_date
    ver = get_local_version()
    build_date = get_build_date()
    console.print(Panel.fit(
        f"[bold blue]Zensers[/bold blue]\n"
        f"[dim]Version: {ver}[/dim]\n"
        f"[dim]Build: {build_date}[/dim]\n"
        f"[dim]Automated Industry Research System[/dim]"
    ))


# ===== Top-level command: changelog =====

@app.command()
def changelog(
    format: str = typer.Option("text", "--format", "-f", help="Output format: text, json"),
    max_lines: int = typer.Option(50, "--max-lines", "-n", help="Max lines to display"),
):
    """Show system changelog."""
    asyncio.run(_changelog_async(format, max_lines))


async def _changelog_async(format: str, max_lines: int):
    from src.cli.client import ZensersClient, ZensersError
    try:
        async with ZensersClient() as client:
            result = await client.changelog(format, max_lines)
    except ZensersError as e:
        console.print(f"[red]Failed to fetch changelog: {e.message}[/red]")
        raise typer.Exit(1)
    content = result.get("changelog", "")
    if isinstance(content, list):
        for entry in content:
            console.print(Panel.fit(entry.get("body", ""), title=entry.get("header", "")))
    else:
        console.print(Panel.fit(str(content)[:4000], title="Changelog"))


# ===== Entry point =====

def main():
    """CLI entry point."""
    setup_cli_logging(verbose=False)
    api_url = get_api_base_url()
    set_api_base_url(api_url)
    app()


if __name__ == "__main__":
    main()
