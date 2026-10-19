"""MVP orchestration for the first-party AI survey simulation flow.

This module is intentionally independent from third-party survey backends.  It
provides one durable application-level entry point for:

    Survey -> PersonaV2 -> SimulationExecutor -> responses -> report

The repository format is JSON for the MVP so the flow can be exercised without
introducing another storage migration.  Writes are atomic and every stage is
recorded in the experiment document.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ..analysis.report_builder import SurveyReportBuilder
from ..models import Survey
from ..engine.persona_generator import PersonaGeneratorV2
from ..engine.simulation_engine import SimulationExecutor


class SurveySimulationPipeline:
    """Run and persist the MVP AI survey simulation lifecycle."""

    def __init__(
        self,
        storage_dir: str | Path = "data/survey_mvp",
        persona_generator: Optional[Any] = None,
        simulation_executor: Optional[Any] = None,
        report_builder: Optional[Any] = None,
    ) -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.persona_generator = persona_generator or PersonaGeneratorV2()
        self.simulation_executor = simulation_executor or SimulationExecutor()
        self.report_builder = report_builder or SurveyReportBuilder()

    async def run(
        self,
        survey: Survey,
        template_name: str = "一线白领",
        persona_type: str = "consumer",
        target_count: int = 10,
        context: str = "",
    ) -> Dict[str, Any]:
        """Run all MVP stages and return a durable experiment summary."""
        if target_count < 1:
            raise ValueError("target_count must be greater than 0")

        experiment_id = f"exp_{uuid.uuid4().hex[:12]}"
        record: Dict[str, Any] = {
            "experiment_id": experiment_id,
            "survey_id": survey.survey_id,
            "status": "created",
            "created_at": self._now(),
            "updated_at": self._now(),
            "config": {
                "template_name": template_name,
                "persona_type": persona_type,
                "target_count": target_count,
                "context": context,
            },
            "survey": survey.to_dict(),
            "personas": [],
            "responses": [],
            "report": None,
        }
        self._save(record)

        current_stage = "created"
        try:
            current_stage = "generating_personas"
            record["status"] = "generating_personas"
            self._touch(record)
            personas, generation_stats = await self.persona_generator.generate_batch(
                template_name=template_name,
                count=target_count,
                persona_type=persona_type,
                context=context,
            )
            record["personas"] = [p.to_dict() for p in personas]
            record["generation_stats"] = generation_stats
            self._save(record)

            current_stage = "simulating"
            record["status"] = "simulating"
            self._touch(record)
            responses = await self._simulate(personas, survey, context)
            if not responses:
                raise RuntimeError("No survey responses were generated")
            record["responses"] = [r.to_dict() for r in responses]
            self._save(record)

            current_stage = "analyzing"
            record["status"] = "analyzing"
            self._touch(record)
            report = self.report_builder.build(
                survey=survey,
                responses=responses,
                title=f"Survey Report - {survey.title}",
                output_dir=str(self.storage_dir / experiment_id),
            )
            record["report"] = report
            record["status"] = "completed"
            self._touch(record)
            self._save(record)
            return self._summary(record)
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = str(exc)
            record["failed_stage"] = current_stage
            self._touch(record)
            self._save(record)
            return self._summary(record)

    async def _simulate(self, personas, survey: Survey, context: str):
        """Use the formal public executor API, with a narrow compatibility hook."""
        simulate = getattr(self.simulation_executor, "simulate_personas", None)
        if simulate is not None:
            return await simulate(personas, survey, survey_context=context)
        return await self.simulation_executor._simulate_all(personas, survey, context)

    def get_experiment(self, experiment_id: str) -> Dict[str, Any]:
        path = self._path(experiment_id)
        if not path.is_file():
            raise FileNotFoundError(experiment_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def _path(self, experiment_id: str) -> Path:
        if not experiment_id or Path(experiment_id).name != experiment_id:
            raise ValueError("invalid experiment_id")
        return self.storage_dir / f"{experiment_id}.json"

    def _save(self, record: Dict[str, Any]) -> None:
        path = self._path(record["experiment_id"])
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _touch(self, record: Dict[str, Any]) -> None:
        record["updated_at"] = self._now()

    @staticmethod
    def _summary(record: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "success": record["status"] == "completed",
            "experiment_id": record["experiment_id"],
            "survey_id": record["survey_id"],
            "status": record["status"],
            "failed_stage": record.get("failed_stage"),
            "error": record.get("error"),
            "persona_count": len(record.get("personas", [])),
            "response_count": len(record.get("responses", [])),
            "report": record.get("report"),
        }
