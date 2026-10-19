from datetime import datetime

import pytest

from src.survey.models import Answer, Question, QuestionType, Survey, SurveyResponse
from src.survey.engine.persona_models import PersonaType, PersonaV2
from src.survey.services.mvp_pipeline import SurveySimulationPipeline
from src.agents.fixed_agents.survey_integration_agent import SurveyIntegrationAgent
from src.survey.client import SurveyClient
from src.survey.task_manager import SurveyTaskManager
from src.survey import task_api
from src.survey.persistence import SurveyPersistence


@pytest.fixture(autouse=True)
def isolated_survey_api_persistence(monkeypatch, tmp_path):
    monkeypatch.setattr(
        task_api,
        "_persistence",
        SurveyPersistence(db_path=str(tmp_path / "surveys.db")),
    )
    task_api._surveys.clear()
    task_api._survey_tasks.clear()
    task_api._simulation_results.clear()


def make_survey() -> Survey:
    return Survey(
        survey_id="survey_mvp_001",
        title="MVP survey",
        questions=[
            Question(
                question_id="q1",
                text="Would you recommend it?",
                question_type=QuestionType.YES_NO,
            )
        ],
    )


def make_persona(index: int) -> PersonaV2:
    return PersonaV2(
        persona_id=f"persona_{index}",
        persona_type=PersonaType.CONSUMER,
        template_name="white_collar",
        name=f"User {index}",
        age=30,
        gender="Male",
        city="Beijing",
        occupation="Engineer",
    )


def make_response(index: int, survey_id: str) -> SurveyResponse:
    return SurveyResponse(
        response_id=f"response_{index}",
        survey_id=survey_id,
        respondent_id=f"persona_{index}",
        answers={
            "q1": Answer(
                question_id="q1",
                answer_value="Yes",
                answered_at=datetime.now(),
            )
        },
    )


class FakePersonaGenerator:
    async def generate_batch(self, template_name, count, persona_type, context=None):
        return [make_persona(i) for i in range(count)], {
            "total": count,
            "llm_success": count,
            "rule_fallback": 0,
            "filtered": 0,
        }


class RecordingPersonaGenerator(FakePersonaGenerator):
    def __init__(self):
        self.template_name = None

    async def generate_batch(self, template_name, count, persona_type, context=None):
        self.template_name = template_name
        return await super().generate_batch(template_name, count, persona_type, context)


class FakeSimulationExecutor:
    async def simulate_personas(self, personas, survey, survey_context=""):
        return [make_response(i, survey.survey_id) for i, _ in enumerate(personas)]


class FakeReportBuilder:
    def build(self, survey, responses, title="Survey Report", output_dir=None):
        return {
            "report": f"# {title}\n\nResponses: {len(responses)}",
            "statistics": {"total_responses": len(responses)},
            "generated_at": datetime.now().isoformat(),
        }


@pytest.mark.asyncio
async def test_pipeline_runs_and_persists_complete_mvp_flow(tmp_path):
    pipeline = SurveySimulationPipeline(
        storage_dir=tmp_path,
        persona_generator=FakePersonaGenerator(),
        simulation_executor=FakeSimulationExecutor(),
        report_builder=FakeReportBuilder(),
    )

    result = await pipeline.run(
        survey=make_survey(),
        template_name="white_collar",
        persona_type="consumer",
        target_count=3,
        context="MVP test",
    )

    assert result["success"] is True
    assert result["status"] == "completed"
    assert result["experiment_id"]
    assert result["survey_id"] == "survey_mvp_001"
    assert result["persona_count"] == 3
    assert result["response_count"] == 3
    assert result["report"]["statistics"]["total_responses"] == 3

    stored = pipeline.get_experiment(result["experiment_id"])
    assert stored["status"] == "completed"
    assert len(stored["personas"]) == 3
    assert len(stored["responses"]) == 3
    assert stored["survey"]["survey_id"] == "survey_mvp_001"


@pytest.mark.asyncio
async def test_pipeline_records_failed_stage_without_returning_fake_success(tmp_path):
    class FailingExecutor:
        async def simulate_personas(self, personas, survey, survey_context=""):
            raise RuntimeError("simulator unavailable")

    pipeline = SurveySimulationPipeline(
        storage_dir=tmp_path,
        persona_generator=FakePersonaGenerator(),
        simulation_executor=FailingExecutor(),
        report_builder=FakeReportBuilder(),
    )

    result = await pipeline.run(survey=make_survey(), target_count=2)

    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["failed_stage"] == "simulating"
    assert "simulator unavailable" in result["error"]
    stored = pipeline.get_experiment(result["experiment_id"])
    assert stored["status"] == "failed"


@pytest.mark.asyncio
async def test_pipeline_default_template_matches_registered_persona_template(tmp_path):
    generator = RecordingPersonaGenerator()
    pipeline = SurveySimulationPipeline(
        storage_dir=tmp_path,
        persona_generator=generator,
        simulation_executor=FakeSimulationExecutor(),
        report_builder=FakeReportBuilder(),
    )

    result = await pipeline.run(survey=make_survey(), target_count=1)

    assert result["success"] is True
    assert generator.template_name == "一线白领"


@pytest.mark.asyncio
async def test_simulation_engine_falls_back_when_llm_answer_is_unavailable():
    from src.survey.engine.simulation_engine import SimulationExecutor

    executor = SimulationExecutor()

    async def unavailable(*args, **kwargs):
        raise ValueError("LLM returned empty")

    executor._call_llm_with_retry = unavailable
    answer = await executor._answer_question(
        make_persona(0), make_survey().questions[0], [], "smoke"
    )

    assert answer.question_id == "q1"
    assert answer.answer_value in {"Yes", "No"} or answer.answer_value.startswith("opt_")


@pytest.mark.asyncio
async def test_pipeline_does_not_report_success_when_no_responses_are_generated(tmp_path):
    class EmptyExecutor:
        async def simulate_personas(self, personas, survey, survey_context=""):
            return []

    pipeline = SurveySimulationPipeline(
        storage_dir=tmp_path,
        persona_generator=FakePersonaGenerator(),
        simulation_executor=EmptyExecutor(),
        report_builder=FakeReportBuilder(),
    )

    result = await pipeline.run(survey=make_survey(), target_count=1)

    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["failed_stage"] == "simulating"


@pytest.mark.asyncio
async def test_fixed_agents_keep_execute_async_compatibility():
    agent = SurveyIntegrationAgent(agent_id="async-compat")
    async def execute(payload):
        return payload
    agent.execute = execute
    result = await agent.execute_async({"ok": True})
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_persona_generation_allows_reasoning_model_to_reach_final_content(monkeypatch):
    import src.survey.engine.persona_generator as module

    captured = {}

    async def fake_call_llm(**kwargs):
        captured.update(kwargs)
        return {"success": True, "content": "{}"}

    monkeypatch.setattr(module, "call_llm", fake_call_llm)
    await module.PersonaGeneratorV2(random_seed=1).generate_batch(
        "一线白领", 1, persona_type="consumer"
    )

    assert captured["max_tokens"] >= 4096
    assert module._PERSONA_LLM_TIMEOUT >= 60


@pytest.mark.asyncio
async def test_simulation_answer_budget_allows_reasoning_model_to_return_content(monkeypatch):
    import src.survey.engine.simulation_engine as module

    captured = {}

    async def fake_call_llm(**kwargs):
        captured.update(kwargs)
        return {"success": True, "content": "Yes"}

    monkeypatch.setattr(module, "call_llm", fake_call_llm)
    executor = module.SimulationExecutor()
    answer = await executor._answer_question(
        make_persona(0), make_survey().questions[0], [], "smoke"
    )

    assert answer.answer_value == "Yes"
    assert captured["max_tokens"] >= 2048


@pytest.mark.asyncio
async def test_integration_agent_uses_persona_v2_and_simulation_executor():
    """The integration entry must use the final V2 engine, not legacy agents."""

    class FakeGenerator:
        async def generate_batch(self, **kwargs):
            assert kwargs["count"] == 1
            return [make_persona(0)], {"total": 1, "llm_success": 0, "rule_fallback": 1}

    class FakeExecutor:
        def __init__(self):
            self.received_personas = None
            self.received_survey = None

        async def simulate_personas(self, personas, survey, **kwargs):
            self.received_personas = personas
            self.received_survey = survey
            return [make_response(0, survey.survey_id)]

    agent = SurveyIntegrationAgent(agent_id="integration-test")
    agent._persona_generator = FakeGenerator()
    agent._simulation_executor = FakeExecutor()
    survey = make_survey()

    personas = await agent._generate_personas("white_collar", 1)
    responses = await agent._simulate_responses(survey.to_dict(), personas)

    assert isinstance(agent._simulation_executor.received_personas[0], PersonaV2)
    assert isinstance(agent._simulation_executor.received_survey, Survey)
    assert responses[0]["survey_id"] == survey.survey_id


@pytest.mark.asyncio
async def test_client_normalizes_canonical_question_schema(tmp_path):
    client = SurveyClient(
        backend_type="ai_simulation",
        task_manager=SurveyTaskManager(storage_path=str(tmp_path / "tasks")),
    )

    survey = await client.create_survey(
        title="Schema contract",
        questions=[
            {
                "question_id": "q1",
                "text": "Recommend?",
                "question_type": "yes_no",
                "options": [
                    {"option_id": "yes", "text": "Yes", "value": 1},
                    {"option_id": "no", "text": "No", "value": 0},
                ],
            }
        ],
    )

    assert survey.questions[0].question_id == "q1"
    assert survey.questions[0].question_type == QuestionType.YES_NO
    assert survey.questions[0].options[0].text == "Yes"
    assert survey.questions[0].options[0].value == 1


def test_survey_api_declares_static_routes_before_dynamic_route():
    paths = [route.path for route in task_api.router.routes]
    assert paths.index("/api/v1/surveys/regions") < paths.index("/api/v1/surveys/{survey_id}")
    assert paths.index("/api/v1/surveys/templates") < paths.index("/api/v1/surveys/{survey_id}")


@pytest.mark.asyncio
async def test_list_surveys_handles_survey_task_objects(monkeypatch):
    class FakeStore:
        async def list_all(self):
            return [type("Task", (), {
                "survey_id": "survey_001",
                "status": type("Status", (), {"value": "completed"})(),
                "collected_count": 2,
                "created_at": "2026-09-05T00:00:00",
            })()]

    monkeypatch.setattr(task_api, "_task_manager", type("TM", (), {"store": FakeStore()})())
    result = await task_api.list_surveys()
    assert result[0].survey_id == "survey_001"
    assert result[0].status == "completed"
    assert result[0].response_count == 2


@pytest.mark.asyncio
async def test_api_create_persists_survey_for_detail_and_list(monkeypatch):
    class FakeClient:
        async def create_survey(self, title, questions, description):
            survey = make_survey()
            survey.title = title
            return survey

    class EmptyStore:
        async def list_all(self):
            return []

    monkeypatch.setattr(task_api, "_client", FakeClient())
    monkeypatch.setattr(task_api, "_task_manager", type("TM", (), {"store": EmptyStore()})())
    task_api._surveys.clear()

    created = await task_api.create_survey(task_api.CreateSurveyRequest(
        title="Persisted UI survey",
        questions=[task_api.QuestionSchema(text="Recommend?", type="yes_no")],
    ))
    task_api._surveys.clear()
    detail = await task_api.get_survey(created["survey_id"])
    summaries = await task_api.list_surveys()

    assert detail["title"] == "Persisted UI survey"
    assert detail["question_count"] == 1
    assert any(item.survey_id == created["survey_id"] for item in summaries)


@pytest.mark.asyncio
async def test_list_surveys_merges_persisted_definition_and_task(monkeypatch):
    survey = make_survey()
    task_api._surveys[survey.survey_id] = survey
    task_api._get_persistence().save_survey(survey)

    class FakeStore:
        async def list_all(self):
            return [type("Task", (), {
                "survey_id": survey.survey_id,
                "status": type("Status", (), {"value": "active"})(),
                "collected_count": 2,
                "created_at": "2026-09-05T00:00:00",
            })()]

    monkeypatch.setattr(task_api, "_task_manager", type("TM", (), {"store": FakeStore()})())
    result = await task_api.list_surveys()

    matching = [item for item in result if item.survey_id == survey.survey_id]
    assert len(matching) == 1
    assert matching[0].status == "active"
    assert matching[0].response_count == 2


@pytest.mark.asyncio
async def test_api_templates_endpoint_loads_registered_persona_templates():
    result = await task_api.list_templates()
    assert "consumer_templates" in result
    assert any(item["id"] == "一线白领" for item in result["consumer_templates"])


@pytest.mark.asyncio
async def test_api_simulate_uses_json_body_sample_size(monkeypatch):
    from src.survey import task_api

    class FakeExecutor:
        seen = None

        def __init__(self, **kwargs):
            pass

        async def execute(self, **kwargs):
            FakeExecutor.seen = kwargs
            return {"task_id": "sim_test", "personas": [make_persona(0)],
                    "responses": [make_response(0, "api_smoke")],
                    "cost_report": {"total_cost": 0.01}, "success": True}

    monkeypatch.setattr("src.survey.engine.simulation_engine.SimulationExecutor", FakeExecutor)
    survey = make_survey()
    survey.survey_id = "api_smoke"
    task_api._surveys["api_smoke"] = survey

    result = await task_api.simulate_survey(
        "api_smoke",
        task_api.SimulateRequest(target_count=1, template="一线白领", persona_type="consumer"),
    )

    assert FakeExecutor.seen["target_count"] == 1
    assert result["response_count"] == 1
    task_api._simulation_results.clear()
    status = await task_api.get_status("api_smoke")
    assert status["collected"] == 1
    assert status["target"] == 1
    history = await task_api.get_simulation_runs("api_smoke")
    assert history["runs"][0]["response_count"] == 1
