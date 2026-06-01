"""
AI Simulated Respondent Backend.

Implements SurveyBackend using PersonaGeneratorV2 + SimulationExecutor.
Design: fail fast, cost controlled, type safe.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from .base import SurveyBackend
from ..models import Survey, SurveyResponse, SurveyStatus, DistributionConfig, Answer
from ..engine.persona_models import PersonaV2, PersonaType, PromptLevel
from ..engine.persona_generator import PersonaGeneratorV2, PersonaGenerationError
from ..engine.simulation_engine import SimulationExecutor
from ..engine.errors import SurveySimulationError

logger = logging.getLogger(__name__)

_MAX_SURVEYS = 100


class AISimulationBackend(SurveyBackend):
    """AI Simulated Respondent Backend."""

    def __init__(self, llm_skill=None, prompt_level=PromptLevel.ENHANCED,
                 min_fidelity=0.0, budget_limit=5.0):
        self._llm_skill = llm_skill
        self._prompt_level = prompt_level
        self._min_fidelity = min_fidelity
        self._budget_limit = budget_limit
        self._generator = PersonaGeneratorV2(llm_skill=llm_skill)
        self._executor = None
        self._surveys = {}
        self._personas = {}
        self._responses = {}
        self._status = {}

    def _enforce_capacity(self):
        if len(self._surveys) > _MAX_SURVEYS:
            oldest = next(iter(self._surveys))
            del self._surveys[oldest]
            del self._personas[oldest]
            del self._responses[oldest]
            del self._status[oldest]

    @property
    def backend_type(self):
        return "ai_simulation"

    @property
    def backend_name(self):
        return "AI Simulated Respondent"

    @property
    def capabilities(self):
        return {"quota_control": False, "pause_resume": True, "webhook": False,
                "real_time_status": True, "incentive": True}

    async def create_survey(self, survey):
        eid = f"sim_{uuid.uuid4().hex[:8]}"
        self._surveys[eid] = survey
        self._responses[eid] = []
        self._status[eid] = SurveyStatus.DRAFT
        self._enforce_capacity()
        logger.info(f"AI survey created: {eid}")
        return eid

    async def update_survey(self, eid, survey):
        if eid in self._surveys:
            self._surveys[eid] = survey
            return True
        return False

    async def delete_survey(self, eid):
        self._surveys.pop(eid, None)
        self._personas.pop(eid, None)
        self._responses.pop(eid, None)
        self._status.pop(eid, None)
        return True

    async def distribute(self, eid, config):
        survey = self._surveys.get(eid)
        if not survey:
            raise ValueError(f"Survey not found: {eid}")
        target = config.target_count
        template = "一线白领"
        persona_type = "consumer"
        if config.sampling_spec:
            template = config.sampling_spec.get("template", template)
            persona_type = config.sampling_spec.get(
                "persona_type", persona_type)
        logger.info(f"AI sim start: {eid}, template={template}, n={target}")
        self._executor = SimulationExecutor(
            llm_skill=self._llm_skill, prompt_level=self._prompt_level,
            min_fidelity=self._min_fidelity, budget_limit=self._budget_limit)
        result = await self._executor.execute(
            survey=survey, template_name=template, persona_type=persona_type,
            target_count=target, survey_context=survey.title)
        self._personas[eid] = result["personas"]
        self._responses[eid] = result["responses"]
        self._status[eid] = SurveyStatus.COMPLETED
        try:
            await self._persist_results(eid, survey, result["personas"], result["responses"])
        except Exception as ex:
            logger.warning(f"Persist failed: {ex}")
        logger.info(
            f"AI sim done: {eid}, responses={
                len(
                    result['responses'])}, cost=${
                result['cost_report']['total_cost']:.2f}")
        return f"sim_task_{eid}"

    async def pause(self, eid):
        self._status[eid] = SurveyStatus.PAUSED
        return True

    async def resume(self, eid):
        self._status[eid] = SurveyStatus.ACTIVE
        return True

    async def close(self, eid):
        self._status[eid] = SurveyStatus.COMPLETED
        return True

    async def get_status(self, eid):
        return self._status.get(eid, SurveyStatus.FAILED)

    async def get_statistics(self, eid):
        resp = self._responses.get(eid, [])
        return {"total_views": len(resp), "total_starts": len(resp),
                "total_completes": len(resp), "completion_rate": 1.0,
                "avg_duration": 0, "persona_count": len(self._personas.get(eid, [])),
                "simulation_status": self._status.get(eid, SurveyStatus.FAILED).value,
                "cost_report": self._executor.get_cost_report() if self._executor else None}

    async def get_results(self, eid, limit=None, offset=None):
        resp = self._responses.get(eid, [])
        start = offset or 0
        end = start + limit if limit else len(resp)
        return resp[start:end]

    async def generate_mock_responses(self, eid, count=10):
        survey = self._surveys.get(eid)
        if not survey:
            return []
        from random import choice
        personas = [self._generator._generate_with_rules(
            {"age_range": (25, 40), "cities": ["Beijing"], "occupations": ["Tester"],
             "income_range": ("100k-200k",), "education": ["Bachelor"], "traits": ["Rational"]},
            "consumer", i, "mock") for i in range(count)]
        resp = []
        for p in personas:
            answers = {}
            for q in survey.questions:
                val = choice(q.options).text if q.options else ""
                answers[q.question_id] = Answer(
                    question_id=q.question_id, answer_value=val)
            resp.append(SurveyResponse(
                response_id=f"fast_{uuid.uuid4().hex[:8]}", survey_id=survey.survey_id,
                respondent_id=p.persona_id, answers=answers, completed_at=datetime.now()))
        self._responses[eid] = resp
        return resp

    async def _persist_results(self, eid, survey, personas, responses):
        try:
            from ..stores import SurveyResponseStore, SurveyPersonaStore
            rs, ps = SurveyResponseStore(), SurveyPersonaStore()
            for r in responses:
                rd = r.to_dict()
                rd["task_id"] = eid
                rd["source"] = "ai_simulation"
                try:
                    rs.add(rd)
                except Exception:
                    pass
            for p in personas:
                pd = p.to_dict()
                pd["task_id"] = eid
                try:
                    ps.add(pd)
                except Exception:
                    pass
            logger.info(f"Persisted: {len(responses)}x{len(personas)}")
        except ImportError:
            pass

    async def close_client(self):
        self._surveys.clear()
        self._personas.clear()
        self._responses.clear()
        self._status.clear()
        self._executor = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close_client()
