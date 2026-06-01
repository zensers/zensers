"""Survey REST API endpoints."""
import logging
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


class SurveySummary(BaseModel):
    survey_id: str
    title: str
    status: str
    question_count: int
    response_count: int
    created_at: str


_client = None
_task_manager = None


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
    return {"survey_id": survey.survey_id, "title": survey.title,
            "question_count": len(survey.questions)}


@router.get("", response_model=List[SurveySummary])
async def list_surveys():
    tm = _get_task_manager()
    tasks = await tm.store.list_all() if hasattr(tm, 'store') else []
    summaries = []
    for task in tasks[:100]:
        sid = getattr(task, 'survey_id', str(task.get('survey_id', '')))
        title = getattr(task, 'title', str(task.get('topic', '')))
        status = getattr(task, 'status', str(task.get('status', '')))
        if hasattr(status, 'value'):
            status = status.value
        count = getattr(task, 'collected_count', int(task.get('collected_count', 0)))
        created = str(getattr(task, 'created_at', task.get('created_at', '')))
        summaries.append(SurveySummary(
            survey_id=sid, title=title, status=status,
            question_count=0, response_count=count, created_at=created))
    return summaries


@router.get("/{survey_id}", response_model=Dict)
async def get_survey(survey_id: str):
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
    import asyncio
    from .models import Survey
    from .stores import SurveyTaskStore
    client = _get_client()
    store = SurveyTaskStore()
    task = await asyncio.to_thread(store.get, f"task_{survey_id[:8]}")
    if task and task.get("questions"):
        questions = task["questions"]
    else:
        questions = []
    survey = Survey(survey_id=survey_id, title=req.template, questions=questions)
    config_type = type('Config', (), {'target_count': req.target_count,
                                       'sampling_spec': {'template': req.template,
                                                          'persona_type': req.persona_type}})()
    task = await client.distribute(survey, target_count=req.target_count)
    status = task.status.value if hasattr(task.status, 'value') else task.status
    return {"task_id": task.task_id, "survey_id": survey_id,
            "status": status, "target_count": task.target_count}


@router.post("/{survey_id}/simulate", response_model=Dict)
async def simulate_survey(survey_id: str, target_count: int = 50,
                          template: str = "一线白领",
                          persona_type: str = "consumer"):
    import asyncio
    from ..engine.simulation_engine import SimulationExecutor
    from ..engine.persona_models import PromptLevel
    from ..models import Survey as SurveyModel
    from ..stores import SurveyTaskStore
    from src.skills.registry import get_skill_registry
    store = SurveyTaskStore()
    task = await asyncio.to_thread(store.get, f"task_{survey_id[:8]}")
    if task and task.get("questions"):
        questions = task["questions"]
    else:
        questions = []
    survey = SurveyModel(survey_id=survey_id, title=template, questions=questions)
    reg = get_skill_registry()
    llm_skill = reg.get("llm_skill")
    executor = SimulationExecutor(llm_skill=llm_skill, prompt_level=PromptLevel.ENHANCED, budget_limit=5.0)
    result = await executor.execute(survey=survey, template_name=template,
                                     persona_type=persona_type,
                                     target_count=target_count,
                                     survey_context=template)
    return {"task_id": result["task_id"], "persona_count": len(result["personas"]),
            "response_count": len(result["responses"]),
            "cost": result["cost_report"]["total_cost"],
            "success": result["success"]}


@router.get("/{survey_id}/status", response_model=Dict)
async def get_status(survey_id: str):
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


@router.get("/{survey_id}/analysis", response_model=Dict)
async def get_analysis(survey_id: str):
    from ..analysis.report_builder import SurveyReportBuilder
    from ..models import Survey as SurveyModel
    tm = _get_task_manager()
    client = _get_client()
    task = await tm.get_task(f"task_{survey_id[:8]}")
    if not task:
        raise HTTPException(status_code=404, detail="Survey not found")
    responses = await client.get_results(task, limit=1000)
    if not responses:
        return {"survey_id": survey_id, "report": "No data yet, run simulation first", "status": "no_data"}
    survey = SurveyModel(survey_id=survey_id, title=getattr(task, 'title', '') or task.survey_id, questions=[])
    import os
    output_dir = os.path.join("output", "surveys", survey_id, "analysis")
    os.makedirs(output_dir, exist_ok=True)
    builder = SurveyReportBuilder()
    result = builder.build(survey=survey, responses=responses, title=f"Survey Report - {survey_id}", output_dir=output_dir)
    return {"survey_id": survey_id, "status": "completed", "report": result["report"],
            "statistics": result["statistics"], "sentiment": result.get("sentiment", {}),
            "wordcloud": result.get("wordcloud", {}),
            "cross_tabulations": result.get("cross_tabulations", []),
            "generated_at": result["generated_at"]}


@router.get("/regions", response_model=Dict)
async def list_survey_regions():
    from ..engine.data import list_regions, load_region
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
    from ..engine.persona_templates import PersonaTemplateRegistry
    consumers = PersonaTemplateRegistry.list_templates("consumer")
    experts = PersonaTemplateRegistry.list_templates("expert")
    return {
        "consumer_templates": [{"id": t["id"], "name": t.get("name", t["id"]),
                                "description": t.get("description", "")} for t in consumers],
        "expert_templates": [{"id": t["id"], "name": t.get("name", t["id"]),
                              "description": t.get("description", "")} for t in experts]}
