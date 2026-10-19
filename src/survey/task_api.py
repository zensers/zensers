"""Survey REST API endpoints."""
import asyncio
import logging
import uuid
from datetime import datetime
import os
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/surveys", tags=["surveys"])


class QuestionSchema(BaseModel):
    text: str
    type: str = "single_choice"
    options: Optional[List[str]] = None
    required: bool = True
    description: Optional[str] = None


class CreateSurveyRequest(BaseModel):
    title: str
    description: str = ""
    questions: List[QuestionSchema]


class DistributeRequest(BaseModel):
    target_count: int = 200
    template: str = "一线白领"
    persona_type: str = "consumer"
    backend: str = "ai_simulation"


class SimulateRequest(BaseModel):
    target_count: int = 50
    template: str = "一线白领"
    persona_type: str = "consumer"


class SurveySummary(BaseModel):
    survey_id: str
    title: str
    status: str
    question_count: int
    response_count: int
    created_at: str


_client = None
_task_manager = None
_surveys: Dict[str, Any] = {}
_survey_tasks: Dict[str, Any] = {}
_simulation_results: Dict[str, Dict[str, Any]] = {}
_persistence = None


def _get_persistence():
    global _persistence
    if _persistence is None:
        from .persistence import SurveyPersistence
        _persistence = SurveyPersistence()
    return _persistence


async def _get_stored_survey(survey_id: str):
    survey = _surveys.get(survey_id)
    if survey is None:
        survey = await asyncio.to_thread(_get_persistence().get_survey, survey_id)
        if survey is not None:
            _surveys[survey_id] = survey
    return survey


async def _get_stored_run(survey_id: str):
    run = _simulation_results.get(survey_id)
    if run is None:
        run = await asyncio.to_thread(_get_persistence().get_run, survey_id)
        if run is not None:
            _simulation_results[survey_id] = run
    return run


def _get_client():
    global _client
    if _client is None:
        from .backends.factory import BackendFactory
        BackendFactory.clear_instances()
        from .client import SurveyClient
        _client = SurveyClient(backend_type="ai_simulation")
    return _client


def _get_task_manager():
    global _task_manager
    if _task_manager is None:
        from .task_manager import SurveyTaskManager
        _task_manager = SurveyTaskManager()
    return _task_manager


@router.post("", response_model=Dict)
async def create_survey(req: CreateSurveyRequest):
    client = _get_client()
    questions = [
        {"id": f"q_{i+1}", "text": q.text, "type": q.type,
         "options": q.options or [], "required": q.required,
         "description": q.description}
        for i, q in enumerate(req.questions)]
    survey = await client.create_survey(req.title, questions, req.description)
    _surveys[survey.survey_id] = survey
    await asyncio.to_thread(_get_persistence().save_survey, survey)
    return {"survey_id": survey.survey_id, "title": survey.title,
            "question_count": len(survey.questions)}


@router.get("", response_model=List[SurveySummary])
async def list_surveys():
    tm = _get_task_manager()
    tasks = await tm.store.list_all() if hasattr(tm, 'store') else []
    summaries = []
    known_ids = set()
    persisted_surveys = await asyncio.to_thread(_get_persistence().list_surveys)
    surveys = {survey.survey_id: survey for survey in persisted_surveys}
    surveys.update(_surveys)
    for survey_id, survey in surveys.items():
        _surveys[survey_id] = survey
        run = await _get_stored_run(survey_id) or {}
        responses = run.get("responses", [])
        summaries.append(SurveySummary(
            survey_id=survey_id, title=survey.title,
            status=run.get("status", "draft"),
            question_count=len(survey.questions), response_count=len(responses),
            created_at=str(survey.created_at)))
        known_ids.add(survey_id)
    for task in tasks[:100]:
        if isinstance(task, dict):
            sid = task.get('survey_id', '')
            title = task.get('title', task.get('topic', ''))
            status = task.get('status', '')
            count = task.get('collected_count', 0)
            created = task.get('created_at', '')
        else:
            sid = getattr(task, 'survey_id', '')
            title = getattr(task, 'title', getattr(task, 'topic', ''))
            status = getattr(task, 'status', '')
            count = getattr(task, 'collected_count', 0)
            created = getattr(task, 'created_at', '')
        if hasattr(status, 'value'):
            status = status.value
        if sid in known_ids:
            # A persisted survey and its distribution task share survey_id.
            # Merge the task counters instead of returning duplicate rows.
            existing = next(item for item in summaries if item.survey_id == sid)
            if existing.status in ("", "draft") and status:
                existing.status = status
            existing.response_count = max(existing.response_count, count)
            continue
        summaries.append(SurveySummary(
            survey_id=sid, title=title, status=status,
            question_count=0, response_count=count, created_at=str(created)))
        known_ids.add(sid)
    return summaries


@router.get("/regions", response_model=Dict)
async def list_survey_regions():
    from .engine.data import list_regions, load_region
    regions = list_regions()
    details = {}
    for rid in regions:
        try:
            data = load_region(rid)
            meta = data.get("meta", {})
            details[rid] = {"name": meta.get("name_en", rid),
                            "source": meta.get("source_en", ""),
                            "source_url": meta.get("source_url", ""),
                            "dimensions": [k for k in data.keys() if k != "meta"]}
        except Exception:
            details[rid] = {"name": rid}
    return {"regions": details}


@router.get("/templates", response_model=Dict)
async def list_templates():
    from .engine.persona_templates import PersonaTemplateRegistry
    consumers = PersonaTemplateRegistry.list_templates("consumer")
    experts = PersonaTemplateRegistry.list_templates("expert")
    return {
        "consumer_templates": [{"id": t["id"], "name": t.get("name", t["id"]),
                                "description": t.get("description", "")} for t in consumers],
        "expert_templates": [{"id": t["id"], "name": t.get("name", t["id"]),
                               "description": t.get("description", "")} for t in experts]}


@router.get("/{survey_id}", response_model=Dict)
async def get_survey(survey_id: str):
    survey = await _get_stored_survey(survey_id)
    if survey:
        run = await _get_stored_run(survey_id) or {}
        return {"survey_id": survey_id, "title": survey.title,
                "description": survey.description,
                "questions": [q.to_dict() for q in survey.questions],
                "status": run.get("status", "draft"),
                "question_count": len(survey.questions),
                "collected_count": len(run.get("responses", []))}
    tm = _get_task_manager()
    task = await tm.get_task(f"task_{survey_id[:8]}")
    if not task:
        raise HTTPException(status_code=404, detail="Survey not found")
    status = task.status.value if hasattr(task.status, 'value') else task.status
    return {"survey_id": survey_id, "status": status,
            "target_count": task.target_count,
            "collected_count": task.collected_count}


@router.post("/{survey_id}/distribute", response_model=Dict)
async def distribute_survey(survey_id: str, req: DistributeRequest):
    client = _get_client()
    survey = await _get_stored_survey(survey_id)
    if survey is None:
        raise HTTPException(status_code=404, detail="Survey not found")
    task = await client.distribute(survey, target_count=req.target_count)
    _survey_tasks[survey_id] = task
    status = task.status.value if hasattr(task.status, 'value') else task.status
    return {"task_id": task.task_id, "survey_id": survey_id,
            "status": status, "target_count": task.target_count}


@router.post("/{survey_id}/simulate", response_model=Dict)
async def simulate_survey(survey_id: str, req: SimulateRequest):
    from .engine.simulation_engine import SimulationExecutor
    from .engine.persona_models import PromptLevel
    survey = await _get_stored_survey(survey_id)
    if survey is None:
        raise HTTPException(status_code=404, detail="Survey not found")
    # Keep the run referentially valid even for surveys created by legacy
    # callers that populated the in-memory registry directly.
    await asyncio.to_thread(_get_persistence().save_survey, survey)
    run_id = f"sim_{uuid.uuid4().hex[:12]}"
    started_at = datetime.now().isoformat()
    running_run = {
        "run_id": run_id,
        "status": "running",
        "target_count": req.target_count,
        "responses": [],
        "personas": [],
        "result": {},
        "started_at": started_at,
    }
    _simulation_results[survey_id] = running_run
    await asyncio.to_thread(_get_persistence().save_run, survey_id, running_run)
    executor = SimulationExecutor(prompt_level=PromptLevel.ENHANCED, budget_limit=5.0)
    try:
        result = await executor.execute(survey=survey, template_name=req.template,
                                         persona_type=req.persona_type,
                                         target_count=req.target_count,
                                         survey_context=req.template)
    except Exception as exc:
        failed_run = {
            "status": "failed",
            "target_count": req.target_count,
            "responses": [],
            "personas": [],
            "result": {"success": False, "error": str(exc)},
            "run_id": run_id,
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(),
            "error_message": str(exc),
        }
        _simulation_results[survey_id] = failed_run
        await asyncio.to_thread(_get_persistence().save_run, survey_id, failed_run)
        raise
    _simulation_results[survey_id] = {
        "status": "completed" if result.get("success") else "failed",
        "responses": result.get("responses", []),
        "personas": result.get("personas", []),
        "result": result,
        "run_id": run_id,
        "target_count": req.target_count,
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(),
    }
    await asyncio.to_thread(
        _get_persistence().save_run, survey_id, _simulation_results[survey_id]
    )
    return {"task_id": result["task_id"], "persona_count": len(result["personas"]),
            "response_count": len(result["responses"]),
            "cost": result["cost_report"]["total_cost"],
            "success": result["success"]}


@router.get("/{survey_id}/status", response_model=Dict)
async def get_status(survey_id: str):
    run = await _get_stored_run(survey_id)
    if run:
        count = len(run.get("responses", []))
        return {"survey_id": survey_id, "status": run["status"],
                "collected": count, "target": run.get("target_count", count),
                "valid": count}
    if await _get_stored_survey(survey_id) is not None and survey_id not in _survey_tasks:
        return {"survey_id": survey_id, "status": "draft", "collected": 0,
                "target": 0, "valid": 0}
    tm = _get_task_manager()
    task = await tm.get_task(f"task_{survey_id[:8]}")
    if not task:
        raise HTTPException(status_code=404, detail="Survey not found")
    status = task.status.value if hasattr(task.status, 'value') else task.status
    return {"survey_id": survey_id, "status": status,
            "collected": task.collected_count,
            "target": task.target_count, "valid": task.valid_count}


@router.get("/{survey_id}/results", response_model=Dict)
async def get_results(survey_id: str, limit: int = 100):
    run = await _get_stored_run(survey_id)
    if run:
        responses = run.get("responses", [])[:limit]
        return {"survey_id": survey_id, "total": len(run.get("responses", [])),
                "valid": len(responses),
                "responses": [r.to_dict() for r in responses]}
    client = _get_client()
    tm = _get_task_manager()
    task = await tm.get_task(f"task_{survey_id[:8]}")
    if not task:
        raise HTTPException(status_code=404, detail="Survey task not found")
    try:
        responses = await client.get_results(task, limit=limit)
        return {"survey_id": survey_id, "total": task.collected_count,
                "valid": task.valid_count,
                "responses": [r.to_dict() for r in responses[:limit]]}
    except Exception as e:
        logger.warning(f"Failed to get results: {e}")
        return {"survey_id": survey_id, "total": task.collected_count, "responses": []}


@router.get("/{survey_id}/runs", response_model=Dict)
async def get_simulation_runs(survey_id: str, limit: int = 50):
    """Return simulation history summaries without loading full response data."""
    if await _get_stored_survey(survey_id) is None:
        raise HTTPException(status_code=404, detail="Survey not found")
    return {
        "survey_id": survey_id,
        "runs": await asyncio.to_thread(
            _get_persistence().list_run_summaries, survey_id, limit
        ),
    }


@router.get("/{survey_id}/analysis", response_model=Dict)
async def get_analysis(survey_id: str):
    from .analysis.report_builder import SurveyReportBuilder
    from .models import Survey as SurveyModel
    run = await _get_stored_run(survey_id)
    if run and run.get("responses"):
        survey = await _get_stored_survey(survey_id)
        builder = SurveyReportBuilder()
        result = builder.build(
            survey=survey, responses=run["responses"],
            title=f"Survey Report - {survey_id}",
            output_dir=os.path.join("output", "surveys", survey_id, "analysis"),
        )
        return {"survey_id": survey_id, "status": "completed",
                "report": result["report"], "statistics": result["statistics"],
                "sentiment": result.get("sentiment", {}),
                "wordcloud": result.get("wordcloud", {}),
                "cross_tabulations": result.get("cross_tabulations", []),
                "generated_at": result["generated_at"]}
    tm = _get_task_manager()
    client = _get_client()
    task = await tm.get_task(f"task_{survey_id[:8]}")
    if not task:
        raise HTTPException(status_code=404, detail="Survey not found")
    responses = await client.get_results(task, limit=1000)
    if not responses:
        return {"survey_id": survey_id, "report": "No data yet, run simulation first", "status": "no_data"}
    survey = SurveyModel(survey_id=survey_id, title=getattr(task, 'title', '') or task.survey_id, questions=[])
    output_dir = os.path.join("output", "surveys", survey_id, "analysis")
    os.makedirs(output_dir, exist_ok=True)
    builder = SurveyReportBuilder()
    result = builder.build(survey=survey, responses=responses, title=f"Survey Report - {survey_id}", output_dir=output_dir)
    return {"survey_id": survey_id, "status": "completed", "report": result["report"],
            "statistics": result["statistics"], "sentiment": result.get("sentiment", {}),
            "wordcloud": result.get("wordcloud", {}),
            "cross_tabulations": result.get("cross_tabulations", []),
            "generated_at": result["generated_at"]}
