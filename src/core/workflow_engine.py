# -*- coding: utf-8 -*-
"""
Workflow - Workflow Definition

Phase 12: Workflow Engine

Defines workflow stages and workflow templates.

Design Doc: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/COMPOSITE_REQUIREMENT_ORCHESTRATION_ANALYSIS.md
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional, Set


class StageStatus(Enum):
    """Stage status"""
    PENDING = "pending"          # Pending execution
    RUNNING = "running"          # Running
    COMPLETED = "completed"      # Completed
    FAILED = "failed"            # Failed
    SKIPPED = "skipped"          # Skipped
    WAITING = "waiting"          # Waiting (e.g., waiting for survey callback)


class StageType(Enum):
    """Stage type"""
    DATA_COLLECTION = "data_collection"      # Data collection
    ANALYSIS = "analysis"                    # Analysis
    SURVEY_DESIGN = "survey_design"          # Survey design
    SURVEY_EXECUTION = "survey_execution"    # Survey distribution
    SURVEY_ANALYSIS = "survey_analysis"      # Survey analysis
    REPORT = "report"                        # Report generation


@dataclass
class WorkflowStage:
    """
    Workflow Stage

    Defines a single stage in the workflow, including its dependencies, inputs and outputs.

    Attributes:
        stage_id: Stage unique identifier
        stage_name: Stage name
        stage_type: Stage type
        research_types: Research types involved in this stage
        agents: List of required Agents
        dependencies: List of prerequisite stage IDs
        input_keys: Input keys to get from prerequisite stages
        output_key: Output key for this stage
        timeout_seconds: Timeout (seconds)
        retry_count: Failure retry count
        is_checkpoint: Whether it's a checkpoint (for recovery)
        can_generate_interim: Whether interim report can be generated at this stage
    """

    stage_id: str
    stage_name: str
    stage_type: StageType
    research_types: List[Any]  # List[ResearchType]
    agents: List[str]
    dependencies: List[str] = field(default_factory=list)
    input_keys: List[str] = field(default_factory=list)
    output_key: Optional[str] = None
    timeout_seconds: int = 3600  # 1 hour
    retry_count: int = 2
    is_checkpoint: bool = False
    can_generate_interim: bool = False

    def __post_init__(self):
        """Post-initialization processing"""
        # Default output key is stage_id
        if self.output_key is None:
            self.output_key = f"stage_output.{self.stage_id}"

    def can_execute(self, completed_stages: Set[str]) -> bool:
        """
        Check if can execute

        Args:
            completed_stages: Set of completed stage IDs

        Returns:
            Whether can execute
        """
        return all(dep in completed_stages for dep in self.dependencies)

    def get_missing_dependencies(self, completed_stages: Set[str]) -> List[str]:
        """Get missing dependencies"""
        return [dep for dep in self.dependencies if dep not in completed_stages]

    def is_survey_stage(self) -> bool:
        """Whether it's a survey-related stage"""
        return self.stage_type in [
            StageType.SURVEY_DESIGN,
            StageType.SURVEY_EXECUTION,
            StageType.SURVEY_ANALYSIS,
        ]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize"""
        return {
            "stage_id": self.stage_id,
            "stage_name": self.stage_name,
            "stage_type": self.stage_type.value,
            "research_types": [rt.value if hasattr(rt, 'value') else str(rt) for rt in self.research_types],
            "agents": self.agents,
            "dependencies": self.dependencies,
            "input_keys": self.input_keys,
            "output_key": self.output_key,
            "timeout_seconds": self.timeout_seconds,
            "retry_count": self.retry_count,
            "is_checkpoint": self.is_checkpoint,
            "can_generate_interim": self.can_generate_interim,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowStage":
        """Deserialize"""
        from .research_type import ResearchType

        stage_type = StageType(data.get("stage_type", "data_collection"))
        research_types = []
        for rt in data.get("research_types", []):
            if isinstance(rt, str):
                rtype = ResearchType.from_string(rt)
                if rtype:
                    research_types.append(rtype)
            else:
                research_types.append(rt)

        return cls(
            stage_id=data["stage_id"],
            stage_name=data["stage_name"],
            stage_type=stage_type,
            research_types=research_types,
            agents=data.get("agents", []),
            dependencies=data.get("dependencies", []),
            input_keys=data.get("input_keys", []),
            output_key=data.get("output_key"),
            timeout_seconds=data.get("timeout_seconds", 3600),
            retry_count=data.get("retry_count", 2),
            is_checkpoint=data.get("is_checkpoint", False),
            can_generate_interim=data.get("can_generate_interim", False),
        )


@dataclass
class ResearchWorkflow:
    """
    Research Workflow

    Defines a complete research workflow, including multiple stages and their execution order.

    Attributes:
        workflow_id: Workflow unique identifier
        name: Workflow name
        description: Workflow description
        stages: Stage list (in execution order)
        default_output_mode: Default output mode
        supports_interim: Whether interim reports are supported
        interim_after_stages: Stages after which interim reports can be generated
    """

    workflow_id: str
    name: str
    description: str = ""
    stages: List[WorkflowStage] = field(default_factory=list)
    default_output_mode: str = "staged"
    supports_interim: bool = True
    interim_after_stages: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Post-initialization processing"""
        # Validate stage dependencies
        self._validate_dependencies()

        # Set default interim report generation points
        if self.supports_interim and not self.interim_after_stages:
            # Generate interim report before survey execution stage
            for stage in self.stages:
                if stage.stage_type == StageType.SURVEY_EXECUTION:
                    self.interim_after_stages = [stage.stage_id]
                    break

    def _validate_dependencies(self) -> None:
        """Validate if stage dependencies are valid"""
        stage_ids = {s.stage_id for s in self.stages}

        for stage in self.stages:
            for dep in stage.dependencies:
                if dep not in stage_ids:
                    raise ValueError(
                        f"Stage {stage.stage_id} has invalid dependency: {dep}"
                    )

    def get_execution_order(self) -> List[str]:
        """
        Get stage execution order (topological sort)

        Returns:
            Stage ID list (in execution order)
        """
        # Topological sort
        in_degree = {s.stage_id: len(s.dependencies) for s in self.stages}
        queue = [s.stage_id for s in self.stages if in_degree[s.stage_id] == 0]
        result = []

        while queue:
            # Get node with in-degree 0
            current = queue.pop(0)
            result.append(current)

            # Update in-degree of nodes depending on current node
            for stage in self.stages:
                if current in stage.dependencies:
                    in_degree[stage.stage_id] -= 1
                    if in_degree[stage.stage_id] == 0:
                        queue.append(stage.stage_id)

        if len(result) != len(self.stages):
            # Circular dependency exists
            raise ValueError("Circular dependency detected in workflow")

        return result

    def get_stage(self, stage_id: str) -> Optional[WorkflowStage]:
        """Get specified stage"""
        for stage in self.stages:
            if stage.stage_id == stage_id:
                return stage
        return None

    def get_survey_execution_stage(self) -> Optional[WorkflowStage]:
        """Get survey execution stage"""
        for stage in self.stages:
            if stage.stage_type == StageType.SURVEY_EXECUTION:
                return stage
        return None

    def get_stages_before_survey(self) -> List[WorkflowStage]:
        """Get all stages before survey execution"""
        survey_stage = self.get_survey_execution_stage()
        if not survey_stage:
            return []

        # Get all stages before survey execution
        order = self.get_execution_order()
        survey_idx = order.index(survey_stage.stage_id)
        before_ids = set(order[:survey_idx])

        return [s for s in self.stages if s.stage_id in before_ids]

    def get_stages_after_survey(self) -> List[WorkflowStage]:
        """Get all stages after survey execution"""
        survey_stage = self.get_survey_execution_stage()
        if not survey_stage:
            return []

        order = self.get_execution_order()
        survey_idx = order.index(survey_stage.stage_id)
        after_ids = set(order[survey_idx + 1:])

        return [s for s in self.stages if s.stage_id in after_ids]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize"""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "stages": [s.to_dict() for s in self.stages],
            "default_output_mode": self.default_output_mode,
            "supports_interim": self.supports_interim,
            "interim_after_stages": self.interim_after_stages,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResearchWorkflow":
        """Deserialize"""
        stages = [WorkflowStage.from_dict(s) for s in data.get("stages", [])]

        return cls(
            workflow_id=data["workflow_id"],
            name=data["name"],
            description=data.get("description", ""),
            stages=stages,
            default_output_mode=data.get("default_output_mode", "staged"),
            supports_interim=data.get("supports_interim", True),
            interim_after_stages=data.get("interim_after_stages", []),
        )


@dataclass
class WorkflowExecution:
    """
    Workflow Execution State

    Tracks workflow execution state and progress.
    """

    workflow_id: str
    task_id: str
    status: StageStatus = StageStatus.PENDING
    current_stage: Optional[str] = None
    completed_stages: Set[str] = field(default_factory=set)
    failed_stages: Set[str] = field(default_factory=set)
    stage_outputs: Dict[str, Any] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    # Staged reporting related
    interim_report_version: Optional[str] = None
    survey_task_id: Optional[str] = None
    waiting_for_survey: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize"""
        return {
            "workflow_id": self.workflow_id,
            "task_id": self.task_id,
            "status": self.status.value,
            "current_stage": self.current_stage,
            "completed_stages": list(self.completed_stages),
            "failed_stages": list(self.failed_stages),
            "stage_outputs": self.stage_outputs,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "interim_report_version": self.interim_report_version,
            "survey_task_id": self.survey_task_id,
            "waiting_for_survey": self.waiting_for_survey,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowExecution":
        """Deserialize"""
        return cls(
            workflow_id=data.get("workflow_id", ""),
            task_id=data.get("task_id", ""),
            status=StageStatus(data.get("status", "pending")),
            current_stage=data.get("current_stage"),
            completed_stages=set(data.get("completed_stages", [])),
            failed_stages=set(data.get("failed_stages", [])),
            stage_outputs=data.get("stage_outputs", {}),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            error_message=data.get("error_message"),
            interim_report_version=data.get("interim_report_version"),
            survey_task_id=data.get("survey_task_id"),
            waiting_for_survey=data.get("waiting_for_survey", False),
        )


__all__ = [
    "StageStatus",
    "StageType",
    "WorkflowStage",
    "ResearchWorkflow",
    "WorkflowExecution",
]
