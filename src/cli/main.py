"""Zensers CLI - Command Line Interface.

Provides research task submission, status query, report download and other functions.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from src.cli.utils import console, setup_cli_logging, set_api_base_url, get_api_base_url
from src.cli.commands import session, knowledge, chat, survey, mcp, llm, prompt, document, upload

sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="zensers",
    help="Zensers - Automated Industry Research System",
    no_args_is_help=True,
)

# Register all subcommand groups
session.register(app)
knowledge.register(app)
chat.register(app)
survey.register(app)
mcp.register(app)
llm.register(app)
prompt.register(app)
document.register(app)
upload.register(app)


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
    """Execute research task asynchronously."""
    from src.core.orchestrator import ResearchOrchestrator as Orchestrator

    console.print(Panel.fit(
        f"[bold blue]Zensers[/bold blue] - Starting Research Task\n"
        f"[dim]Requirement: {requirement[:50]}{'...' if len(requirement) > 50 else ''}[/dim]"
    ))

    async def interaction_callback(step_data: dict) -> dict:
        """CLI interactive callback, using up/down arrow to select + enter to confirm"""
        try:
            import questionary
        except ImportError:
            console.print("[red]Interactive mode requires questionary library. Run: pip install questionary[/red]")
            raise typer.Exit(1)

        step_type = step_data.get("step", "unknown")
        next_step = step_data.get("next_step", "")
        step_type_str = str(step_type)

        console.print(f"\n[bold yellow]>>> Interaction Step: {step_type}[/bold yellow]")

        options = step_data.get("options", [])
        instruction = step_data.get("instruction", step_data.get("message", "Please select:"))

        if options:
            console.print(f"\n[cyan]{instruction}[/cyan]")

            choices = []
            for opt in options:
                if isinstance(opt, dict):
                    label = opt.get("label", opt.get("value", str(opt)))
                    desc = opt.get("desc", opt.get("description", ""))
                    if desc:
                        choices.append(f"{label} - {desc}")
                    else:
                        choices.append(label)
                else:
                    choices.append(str(opt))

            selected = await questionary.select(
                "Please select:",
                choices=choices,
                style=questionary.Style([
                    ('selected', 'fg:green bold'),
                    ('pointer', 'fg:green bold'),
                    ('question', 'fg:cyan bold'),
                ])
            ).ask_async()

            if selected is None:
                return {"confirmed": False, "cancelled": True}

            selected_idx = choices.index(selected)
            if selected_idx < len(options) and isinstance(options[selected_idx], dict):
                selected_value = options[selected_idx].get("value", selected)
            else:
                selected_value = selected

            if next_step == "select_output_type":
                return {"output_type": selected_value}
            elif next_step == "select_template":
                return {"template_id": selected_value}
            else:
                return {"selected": selected_value, "answer": selected_value}

        framework_options = step_data.get("framework_options", [])
        if framework_options:
            console.print(f"\n[cyan]{instruction}[/cyan]")

            choices = []
            for fw in framework_options:
                name = fw.get("name", fw.get("id", "Unknown option"))
                desc = fw.get("description", "")
                pages = fw.get("estimated_pages", "")
                sections = fw.get("section_names", [])

                choice_text = f"{name} - {desc}"
                if pages:
                    choice_text += f" ({pages})"
                choices.append(choice_text)

                if sections:
                    console.print(f"  [dim]{name} includes: {', '.join(sections[:5])}{'...' if len(sections) > 5 else ''}[/dim]")

            selected = await questionary.select(
                "Please select research framework:",
                choices=choices,
            ).ask_async()

            if selected is None:
                return {"confirmed": False}

            selected_idx = choices.index(selected)
            if selected_idx < len(framework_options):
                framework_id = framework_options[selected_idx].get("id", "standard")
            else:
                framework_id = "standard"

            return {"framework_id": framework_id}

        sections_detail = step_data.get("sections_detail", [])
        if sections_detail:
            console.print(f"\n[cyan]{instruction}[/cyan]")

            console.print(f"\n[bold]Research Section List:[/bold]")
            for i, section in enumerate(sections_detail, 1):
                name = section.get("name", section.get("id", "Unknown section"))
                content = section.get("content", "Content to be confirmed")
                console.print(f"  [green]{i}. {name}[/green]")
                console.print(f"     [dim]Research content: {content}[/dim]")

            action = await questionary.select(
                "\nPlease confirm section content:",
                choices=[
                    "Confirm, proceed to next step",
                    "Need to adjust sections",
                    "Go back to previous step (re-select framework)",
                    "Cancel research",
                ],
            ).ask_async()

            if action == "Confirm, proceed to next step":
                return {"confirmed": True}
            elif action == "Need to adjust sections":
                section_names = [s.get("name", s.get("id", "")) for s in sections_detail]
                kept_sections = await questionary.checkbox(
                    "Please select sections to keep (space to select, enter to confirm, ESC to cancel):",
                    choices=section_names,
                ).ask_async()

                if kept_sections is None:
                    return await interaction_callback(step_data)

                kept_sections = [s for s in kept_sections if s in section_names]
                if not kept_sections:
                    kept_sections = section_names

                adjustments = []
                for s in sections_detail:
                    name = s.get("name", s.get("id", ""))
                    adjustments.append({
                        "id": s.get("id", name),
                        "keep": name in kept_sections
                    })
                return {"confirmed": True, "adjustments": adjustments}
            elif action == "Go back to previous step (re-select framework)":
                return {"go_back": True}
            else:
                return {"confirmed": False}

        parameters = step_data.get("parameters", {})
        if parameters:
            console.print(f"\n[cyan]{instruction}[/cyan]")

            result = {}

            param_list = []
            if isinstance(parameters, dict):
                param_list = parameters.get("parameters", [])
                if not param_list:
                    for legacy_key in ("region", "time_range", "depth"):
                        legacy_param = parameters.get(legacy_key)
                        if isinstance(legacy_param, dict):
                            param_list.append({
                                "id": legacy_key,
                                "type": "select",
                                "label": legacy_param.get("label", legacy_key),
                                "default": legacy_param.get("default", ""),
                                "options": [
                                    {"value": o, "label": o}
                                    for o in legacy_param.get("options", [])
                                ],
                            })
            elif isinstance(parameters, list):
                param_list = parameters

            for param in param_list:
                param_id = param.get("id", "")
                param_type = param.get("type", "select")
                param_label = param.get("label", param_id)
                param_default = param.get("default")
                param_options = param.get("options", [])
                param_required = param.get("required", False)
                param_placeholder = param.get("placeholder", "")

                if param_type == "text":
                    prompt_text = f"{param_label}:"
                    if param_placeholder:
                        prompt_text += f" ({param_placeholder})"
                    value = await questionary.text(
                        prompt_text,
                        default=str(param_default) if param_default else "",
                    ).ask_async()
                    if value:
                        result[param_id] = value
                    elif param_default:
                        result[param_id] = param_default

                elif param_type in ("select",):
                    option_labels = [opt.get("label", opt.get("value", "")) for opt in param_options]
                    if len(option_labels) > 1 or param_required:
                        selected = await questionary.select(
                            param_label,
                            choices=option_labels,
                        ).ask_async()
                        if selected:
                            selected_idx = option_labels.index(selected)
                            result[param_id] = param_options[selected_idx].get("value", selected)
                        else:
                            result[param_id] = param_default
                    else:
                        result[param_id] = param_default

                elif param_type == "multi_select":
                    option_labels = [opt.get("label", opt.get("value", "")) for opt in param_options]
                    selected = await questionary.checkbox(
                        f"{param_label} (space to select, enter to confirm):",
                        choices=option_labels,
                    ).ask_async()
                    if selected:
                        selected_values = []
                        for sel in selected:
                            idx = option_labels.index(sel)
                            selected_values.append(param_options[idx].get("value", sel))
                        result[param_id] = selected_values
                    else:
                        result[param_id] = param_default if param_default else []

                elif param_type == "date":
                    value = await questionary.text(
                        f"{param_label} (YYYY-MM-DD):",
                        default=str(param_default) if param_default else "",
                    ).ask_async()
                    result[param_id] = value or param_default

                else:
                    value = await questionary.text(
                        f"{param_label}:",
                        default=str(param_default) if param_default else "",
                    ).ask_async()
                    result[param_id] = value or param_default

            return result

        summary = step_data.get("summary", {})
        if summary or step_data.get("next_step") == "confirm_research":
            console.print(f"\n[cyan]{instruction}[/cyan]")

            if summary:
                console.print(f"  [bold]Research Topic:[/bold] {summary.get('topic', 'N/A')}")
                console.print(f"  [bold]Report Type:[/bold] {summary.get('output_type', 'N/A')}")
                console.print(f"  [bold]Region:[/bold] {summary.get('region', 'N/A')}")
                console.print(f"  [bold]Time Range:[/bold] {summary.get('time_range', 'N/A')}")
                console.print(f"  [bold]Sections:[/bold] {', '.join(summary.get('sections', []))}")

            action = await questionary.select(
                "Confirm to start research?",
                choices=["Confirm and start", "Cancel"],
            ).ask_async()

            return {"confirmed": action == "Confirm and start"}

        if step_type_str == "preview":
            preview_url = step_data.get("preview_url", "")
            actions = step_data.get("actions", ["confirm", "revise", "cancel"])

            console.print(f"\n[cyan]{instruction}[/cyan]")
            if preview_url:
                console.print(f"  [dim]Preview file: {preview_url}[/dim]")

            action_choices = []
            action_map = {}
            if "confirm" in actions:
                action_choices.append("Confirm and finalize")
                action_map["Confirm and finalize"] = "confirm"
            if "revise" in actions:
                action_choices.append("Needs revision")
                action_map["Needs revision"] = "revise"
            if "cancel" in actions:
                action_choices.append("Cancel")
                action_map["Cancel"] = "cancel"

            if not action_choices:
                action_choices = ["Confirm and finalize", "Needs revision", "Cancel"]
                action_map = {"Confirm and finalize": "confirm", "Needs revision": "revise", "Cancel": "cancel"}

            selected = await questionary.select(
                "Please select action:",
                choices=action_choices,
            ).ask_async()

            action_value = action_map.get(selected, "confirm")

            if action_value == "revise":
                revision_input = await questionary.text(
                    "Please enter revision suggestion (e.g., add market size data):",
                ).ask_async()
                return {
                    "action": "revise",
                    "adjustment": revision_input or "Please improve content quality",
                }

            return {"action": action_value}

        console.print(f"[dim]Step data: {step_data}[/dim]")

        action = await questionary.select(
            "Please select action:",
            choices=["Continue", "Cancel"],
        ).ask_async()

        return {"confirmed": action == "Continue"}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Initializing research system...", total=None)
        orchestrator = Orchestrator()
        progress.update(task, description="System ready")

        progress.update(task, description="Executing research workflow...")
        try:
            result = await orchestrator.research(
                requirement,
                output_dir=output,
                interaction_mode=interactive,
                interaction_callback=interaction_callback if interactive else None,
                output_type=output_type,
                custom_aspects=aspects,
                framework=framework,
                template_name=template,
                output_format=format,
            )
            progress.update(task, description="Research complete")
        except Exception as e:
            logger.error(f"Research execution failed: {e}", exc_info=True)
            console.print(f"[red]Research execution failed: {e}[/red]")
            raise typer.Exit(1)

    if result.status == "completed":
        console.print("\n[green]✓ Research task completed![/green]")

        table = Table(title="Report Information")
        table.add_column("Item", style="cyan")
        table.add_column("Content", style="green")

        table.add_row("Task ID", result.task_id)
        table.add_row("Topic", result.topic)
        table.add_row("Status", result.status)
        table.add_row("Output Path", str(result.output_path))
        table.add_row("Used Agents", ", ".join(result.agents_used))

        console.print(table)

        if output and result.document_path:
            import shutil
            src_path = Path(result.document_path)
            dst_path = Path(output)
            if src_path.exists():
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, dst_path)
                console.print(f"\n[green]Report saved: {output}[/green]")
            else:
                console.print(f"\n[yellow]Warning: Document path does not exist {result.document_path}[/yellow]")
        elif output and not result.document_path:
            console.print(f"\n[yellow]Warning: Research complete but no document generated, cannot save to {output}[/yellow]")

        if result.document_path:
            console.print(f"\n[green]Report generated: {result.document_path}[/green]")
        console.print("[dim]Use python -m src.cli.main session list to view historical tasks[/dim]")
        console.print("[dim]Use python -m src.cli.main session resume <task_id> to resume task[/dim]")
        console.print("[dim]Web UI for conversational interaction will be available later[/dim]")

    else:
        console.print(f"\n[red]Research failed: {result.status}[/red]")
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
    """Get task status via HTTP API delegation."""
    import httpx
    if watch:
        console.print(f"[dim]Monitoring task {task_id} (press Ctrl+C to stop)...[/dim]\n")
        try:
            while True:
                async with httpx.AsyncClient() as client:
                    base = get_api_base_url()
                    r = await client.get(f"{base}/api/v1/research/{task_id}/status", timeout=10)
                    r.raise_for_status()
                    result = r.json()
                    console.print(f"[dim]Status: {result.get('status', 'unknown')}[/dim]")
                    if result.get("status") in ("completed", "failed", "cancelled"):
                        break
                await asyncio.sleep(2)
        except KeyboardInterrupt:
            console.print("\n[dim]Monitoring stopped[/dim]")
    else:
        async with httpx.AsyncClient() as client:
            base = get_api_base_url()
            r = await client.get(f"{base}/api/v1/research/{task_id}/status", timeout=10)
            r.raise_for_status()
            result = r.json()
            console.print(f"Status: {result.get('status', 'unknown')}")
            if result.get("topic"):
                console.print(f"Topic: {result['topic']}")
            if result.get("progress"):
                console.print(f"Progress: {result['progress']}")


async def _list_active_tasks_remote():
    """List active tasks via HTTP API."""
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            base = get_api_base_url()
            r = await client.get(f"{base}/api/v1/research/sessions", params={"limit": 50})
            r.raise_for_status()
            result = r.json()
    except httpx.ConnectError:
        console.print("[red]Connection refused: server not running[/red]")
        raise typer.Exit(1)
    except httpx.TimeoutException:
        console.print("[red]Request timed out[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Failed to list active tasks: {e}[/red]")
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
        table.add_row(s.get("task_id", "N/A")[:12], s.get("status", "unknown"), s.get("topic", "")[:30], s.get("created_at", "")[:19])
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
    """Download report via HTTP API."""
    import httpx
    content = None
    try:
        async with httpx.AsyncClient() as client:
            url = f"{get_api_base_url()}/api/v1/download/{task_id}"
            r = await client.get(url, timeout=60)
            if r.status_code == 404:
                console.print(f"[red]Report not found: {task_id}[/red]")
                raise typer.Exit(1)
            if r.status_code != 200:
                console.print(f"[red]Download failed: HTTP {r.status_code} - {r.text}[/red]")
                raise typer.Exit(1)
            content = r.content
    except httpx.RequestError as e:
        console.print(f"[red]Download failed (network): {e}[/red]")
        raise typer.Exit(1)

    if content is None:
        console.print("[red]Download failed: no content received[/red]")
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
):
    """Manage CLI configuration."""
    config_path = Path.home() / ".zensers" / "config.json"

    if show:
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            console.print_json(json.dumps(config))
        else:
            console.print("[dim]Configuration file not yet created[/dim]")

    elif reset:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        default_config = {
            "default_output_format": "markdown",
            "auto_save_reports": True,
            "max_concurrent_tasks": 3,
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2)
        console.print("[green]Configuration reset to defaults[/green]")


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
    from src.cli.client import ZensersClient

    client = ZensersClient()
    try:
        result = await client.changelog(format, max_lines)
    except Exception as e:
        console.print(f"[red]Failed to fetch changelog: {e}[/red]")
        raise typer.Exit(1)
    finally:
        await client.close()
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
