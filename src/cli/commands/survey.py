"""Survey commands (create/simulate/analyze)."""
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.cli.utils import console

logger = logging.getLogger(__name__)


def register(parent: typer.Typer) -> None:
    survey_app = typer.Typer(help="Survey (create/simulate/analyze)")
    parent.add_typer(survey_app, name="survey")

    @survey_app.command("create")
    def survey_create(
        title: str = typer.Argument(..., help="Survey title"),
        questions: str = typer.Option("", "--questions", "-q", help="Questions JSON file path"),
        description: str = typer.Option("", "--desc", "-d", help="Survey description"),
    ):
        """Create survey from JSON file."""
        asyncio.run(_survey_create_async(title, questions, description))

    @survey_app.command("list")
    def survey_list():
        """List all surveys."""
        asyncio.run(_survey_list_async())

    @survey_app.command("simulate")
    def survey_simulate(
        survey_id: str = typer.Argument(..., help="Survey ID"),
        count: int = typer.Option(50, "--count", "-c", help="Simulation sample count"),
        template: str = typer.Option("urban_white_collar", "--template", "-t", help="Persona template"),
        persona_type: str = typer.Option("consumer", "--type", "-p", help="Persona type (consumer/expert)"),
    ):
        """Run AI-simulated responses."""
        asyncio.run(_survey_simulate_async(survey_id, count, template, persona_type))

    @survey_app.command("status")
    def survey_status(
        survey_id: str = typer.Argument(..., help="Survey ID"),
    ):
        """Query simulation status."""
        asyncio.run(_survey_status_async(survey_id))

    @survey_app.command("results")
    def survey_results(
        survey_id: str = typer.Argument(..., help="Survey ID"),
        limit: int = typer.Option(100, "--limit", "-l", help="Max results to return"),
    ):
        """Get simulation results."""
        asyncio.run(_survey_results_async(survey_id, limit))

    @survey_app.command("analyze")
    def survey_analyze(
        survey_id: str = typer.Argument(..., help="Survey ID"),
        output: Optional[str] = typer.Option(None, "--output", "-o", help="Report output path"),
    ):
        """Generate analysis report."""
        asyncio.run(_survey_analyze_async(survey_id, output))

    @survey_app.command("templates")
    def survey_templates():
        """List available persona templates."""
        asyncio.run(_survey_templates_async())

    @survey_app.command("regions")
    def survey_regions():
        """List available region data."""
        asyncio.run(_survey_regions_async())


async def _survey_create_async(title: str, questions_path: str, description: str):
    """Create survey asynchronously."""
    if not questions_path:
        console.print("[red]Please specify questions file path: --questions questions.json[/red]")
        raise typer.Exit(1)

    path = Path(questions_path)
    if not path.exists():
        console.print(f"[red]File not found: {questions_path}[/red]")
        raise typer.Exit(1)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    qs = data if isinstance(data, list) else data.get("questions", [])
    from src.survey.client import SurveyClient

    client = SurveyClient(backend_type="ai_simulation")
    survey = await client.create_survey(title, qs, description)
    console.print(f"[green]✓ Survey created[/green]")
    console.print(f"  ID: {survey.survey_id}")
    console.print(f"  Title: {survey.title}")
    console.print(f"  Questions: {len(survey.questions)}")


async def _survey_list_async():
    """List surveys asynchronously."""
    from src.survey.task_manager import SurveyTaskManager

    tm = SurveyTaskManager()
    tasks = await tm.store.list_all() if hasattr(tm, "store") else []
    if not tasks:
        console.print("[dim]No surveys[/dim]")
        return
    table = Table(title="Survey List")
    table.add_column("ID", style="cyan")
    table.add_column("Title", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Collected")
    for t in tasks[:20]:
        sid = getattr(t, "survey_id", str(t.get("survey_id", "")))[:12]
        title = getattr(t, "title", t.get("topic", ""))[:30]
        st = getattr(t, "status", t.get("status", ""))
        st = st.value if hasattr(st, "value") else st
        cnt = getattr(t, "collected_count", t.get("collected_count", 0))
        table.add_row(sid, title, st, str(cnt))
    console.print(table)


async def _survey_simulate_async(survey_id: str, count: int, template: str, persona_type: str):
    """Execute simulation asynchronously."""
    from src.survey.models import Survey as SurveyModel
    from src.survey.engine.simulation_engine import SimulationExecutor
    from src.survey.engine.persona_models import PromptLevel

    survey = SurveyModel(survey_id=survey_id, title=template, questions=[])
    executor = SimulationExecutor(llm_skill=None, prompt_level=PromptLevel.ENHANCED, budget_limit=5.0)

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task("Simulating...", total=None)
        result = await executor.execute(
            survey=survey,
            template_name=template,
            persona_type=persona_type,
            target_count=count,
            survey_context=template,
        )

    console.print(f"[green]✓ Simulation complete[/green]")
    console.print(f"  Personas: {len(result['personas'])}")
    console.print(f"  Responses: {len(result['responses'])}")
    console.print(f"  Cost: ${result['cost_report']['total_cost']:.4f}")
    console.print(f"  Success: {result['success']}")


async def _survey_status_async(survey_id: str):
    """Query status asynchronously."""
    from src.survey.task_manager import SurveyTaskManager

    tm = SurveyTaskManager()
    task = await tm.get_task(f"task_{survey_id[:8]}")
    if not task:
        console.print(f"[red]Survey not found: {survey_id}[/red]")
        return
    st = task.status.value if hasattr(task.status, "value") else task.status
    table = Table(title=f"Survey Status: {survey_id[:12]}...")
    table.add_column("Item", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Status", st)
    table.add_row("Target Samples", str(task.target_count))
    table.add_row("Collected", str(task.collected_count))
    table.add_row("Valid", str(task.valid_count))
    console.print(table)


async def _survey_results_async(survey_id: str, limit: int):
    """Get results asynchronously."""
    from src.survey.client import SurveyClient
    from src.survey.task_manager import SurveyTaskManager

    tm = SurveyTaskManager()
    task = await tm.get_task(f"task_{survey_id[:8]}")
    if not task:
        console.print(f"[red]Survey not found: {survey_id}[/red]")
        return

    client = SurveyClient(backend_type="ai_simulation")
    responses = await client.get_results(task, limit=limit)

    console.print(f"[green]✓ {len(responses)} responses total[/green]")
    for r in responses[:10]:
        answers_display = ", ".join(
            f"{qid}: {a.answer_value}" for qid, a in list(r.answers.items())[:3]
        )
        console.print(f"  {r.respondent_id[:16]} | {answers_display}")
    if len(responses) > 10:
        console.print(f"  ... {len(responses)-10} more")


async def _survey_analyze_async(survey_id: str, output: Optional[str]):
    """Generate analysis report asynchronously."""
    from src.survey.client import SurveyClient
    from src.survey.task_manager import SurveyTaskManager
    from src.survey.models import Survey as SurveyModel
    from src.survey.analysis.report_builder import SurveyReportBuilder

    tm = SurveyTaskManager()
    task = await tm.get_task(f"task_{survey_id[:8]}")
    if not task:
        console.print(f"[red]Survey not found: {survey_id}[/red]")
        return

    client = SurveyClient(backend_type="ai_simulation")
    responses = await client.get_results(task, limit=1000)
    if not responses:
        console.print("[red]No data available, please run simulate first[/red]")
        return

    survey = SurveyModel(survey_id=survey_id, title=getattr(task, "title", "") or survey_id, questions=[])
    output_dir = os.path.join("output", "surveys", survey_id, "analysis")
    os.makedirs(output_dir, exist_ok=True)

    builder = SurveyReportBuilder()
    result = builder.build(survey=survey, responses=responses,
                           title=f"Survey Report - {survey_id}", output_dir=output_dir)

    report_path = output or os.path.join(output_dir, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(result["report"])
    console.print(f"[green]✓ Report generated: {report_path}[/green]")
    console.print(f"  Statistics: {result['statistics'].get('valid_responses', 0)} valid responses")
    console.print(f"  Charts: {list(result.get('charts', {}).keys())}")


async def _survey_templates_async():
    """List templates asynchronously."""
    from src.survey.engine.persona_templates import PersonaTemplateRegistry

    for ptype, label in [("consumer", "Consumer"), ("expert", "Expert")]:
        templates = PersonaTemplateRegistry.list_templates(ptype)
        table = Table(title=f"{label} Templates")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Description")
        for t in templates[:10]:
            table.add_row(t["id"], t.get("name", t["id"]), t.get("description", "")[:60])
        console.print(table)


async def _survey_regions_async():
    """List regions asynchronously."""
    from src.survey.engine.data import list_regions, load_region

    regions = list_regions()
    table = Table(title="Available Regions")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Dimensions")
    for rid in regions:
        try:
            data = load_region(rid)
            dims = [k for k in data.keys() if k != "meta"]
            table.add_row(rid, regions[rid], ", ".join(dims))
        except Exception:
            table.add_row(rid, regions[rid], "")
    console.print(table)
