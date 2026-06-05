"""
DynamicPhaseOrchestrator - Dynamically generates execution phases from task structure and intent.
"""
import logging
import uuid
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .semantic_intent import DeepIntentResult
from .task_structure import TaskStructure, SectionRole

logger = logging.getLogger(__name__)


class PhaseType(Enum):
    DATA_COLLECTION = "data_collection"
    ANALYSIS = "analysis"
    SYNTHESIS = "synthesis"
    REPORT = "report"
    SURVEY = "survey"
    CROSS_SYNTHESIS = "cross_synthesis"
    VALIDATION = "validation"


@dataclass
class ContentLockRule:
    target_section: str
    required_sections: List[str]
    lock_type: str = "completion"
    quality_threshold: float = 75.0
    lock_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"target_section": self.target_section, "required_sections": self.required_sections,
                "lock_type": self.lock_type, "quality_threshold": self.quality_threshold}


@dataclass
class AgentSpec:
    agent_id: str
    agent_type: str
    section_ids: List[str]
    priority: int = 0
    parallel_group: int = 0
    quality_threshold: float = 75.0
    max_retries: int = 3
    config: Dict[str, Any] = field(default_factory=dict)
    system_prompt: str = ""
    # R-FIX-4: cognitive fields for context-aware execution
    dependencies: List[str] = field(default_factory=list)
    core_question: str = ""
    section_role_desc: str = ""
    upstream_sections: List[str] = field(default_factory=list)
    downstream_sections: List[str] = field(default_factory=list)
    produces_metrics: List[str] = field(default_factory=list)
    consumes_metrics: List[str] = field(default_factory=list)


@dataclass
class ExecutionPhase:
    phase_id: str
    phase_type: PhaseType
    agent_specs: List[AgentSpec]
    section_ids: List[str]
    depends_on: List[str] = field(default_factory=list)
    parallel: bool = True
    estimated_duration: Optional[str] = None
    unlock_conditions: Dict[str, str] = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    plan_id: str
    task_structure: TaskStructure
    phases: List[ExecutionPhase]
    content_lock_rules: List[ContentLockRule]
    total_agents: int = 0
    estimated_duration: Optional[str] = None

    def get_all_agents(self) -> List[AgentSpec]:
        agents = []
        for phase in self.phases:
            agents.extend(phase.agent_specs)
        return agents

    def to_decomposition_plan(self):
        from .decomposition.strategies import (
            DecompositionPlan, ResearchPhase, AgentSpec as OriginalAgentSpec
        )

        phase_type_to_research_phase = {
            PhaseType.SURVEY: ResearchPhase.DATA_COLLECTION,
            PhaseType.DATA_COLLECTION: ResearchPhase.DATA_COLLECTION,
            PhaseType.ANALYSIS: ResearchPhase.DEEP_ANALYSIS,
            PhaseType.SYNTHESIS: ResearchPhase.SYNTHESIS,
            PhaseType.CROSS_SYNTHESIS: ResearchPhase.SYNTHESIS,
            PhaseType.REPORT: ResearchPhase.REPORT_GENERATION,
            PhaseType.VALIDATION: ResearchPhase.DATA_VALIDATION,
        }

        phases: Dict[ResearchPhase, List[OriginalAgentSpec]] = {}
        for phase in self.phases:
            rp = phase_type_to_research_phase.get(
                phase.phase_type, ResearchPhase.DEEP_ANALYSIS
            )
            for spec in phase.agent_specs:
                orig = OriginalAgentSpec(
                    agent_id=spec.agent_id,
                    agent_type=spec.agent_type,
                    category=spec.agent_type,
                    task_description=spec.core_question or "",
                    input_keys=[],
                    output_keys=spec.section_ids,
                    dependencies=spec.config.get("resolved_dependencies", []) or spec.config.get("content_dependency", []),
                    priority=spec.priority,
                    parallel_group=spec.parallel_group,
                    quality_threshold=spec.quality_threshold,
                    max_retries=spec.max_retries,
                )
                phases.setdefault(rp, []).append(orig)

        execution_order = [
            rp for rp in [
                ResearchPhase.DATA_COLLECTION,
                ResearchPhase.DATA_VALIDATION,
                ResearchPhase.DEEP_ANALYSIS,
                ResearchPhase.SYNTHESIS,
                ResearchPhase.REPORT_GENERATION,
            ] if phases.get(rp)
        ]

        quality_gates = {
            ResearchPhase.DATA_COLLECTION: 0.7,
            ResearchPhase.DATA_VALIDATION: 0.8,
            ResearchPhase.DEEP_ANALYSIS: 0.75,
            ResearchPhase.SYNTHESIS: 0.8,
            ResearchPhase.REPORT_GENERATION: 0.85,
        }

        return DecompositionPlan(
            task_id=self.plan_id,
            phases=phases,
            execution_order=execution_order,
            quality_gates=quality_gates,
            estimated_agents=self.total_agents,
            estimated_duration=self.estimated_duration or "unknown",
        )


class DynamicPhaseOrchestrator:
    """Generates execution plans from task structure and intent analysis."""

    def __init__(self):
        self.phases: List[ExecutionPhase] = []

    def plan(self, task_structure: TaskStructure, intent: DeepIntentResult,
             topic: Optional[str] = None) -> ExecutionPlan:
        plan_id = f"plan_{uuid.uuid4().hex[:8]}"
        topic = topic or task_structure.topic
        logger.info(f"[{plan_id}] Generating plan for {len(task_structure.sections)} sections, "
                    f"{len(task_structure.parallel_groups)} DAG layers")
        phases = self._generate_phases(task_structure, intent, topic)
        content_lock_rules = self._generate_content_lock_rules(task_structure, phases)
        total_agents = sum(len(p.agent_specs) for p in phases)
        return ExecutionPlan(plan_id=plan_id, task_structure=task_structure, phases=phases,
                             content_lock_rules=content_lock_rules, total_agents=total_agents)

    def _generate_phases(self, task_structure, intent, topic):
        phases = []
        counter = 1
        section_map = {s.section_id: s for s in task_structure.sections}
        global_section_to_agent = {}  # R-FIX-3: cross-phase section_id→agent_id mapping

        # Phase 0: SURVEY (if required)
        if intent.requires_primary_data:
            survey_sections = task_structure.sections[:1] if task_structure.sections else []
            phase = self._create_phase(f"phase_{counter}", PhaseType.SURVEY, survey_sections,
                                        task_structure, topic, parallel=False, depends_on=[],
                                        section_to_agent=global_section_to_agent)
            phases.append(phase)
            counter += 1

        # DAG layers from parallel_groups
        dag_layers = task_structure.parallel_groups
        if not dag_layers and task_structure.sections:
            dag_layers = [[s.section_id for s in task_structure.sections]]

        for layer_ids in dag_layers:
            phase_id = f"phase_{counter}"
            layer_sections = [section_map[sid] for sid in layer_ids if sid in section_map]
            if not layer_sections:
                continue

            roles_in_layer = [section_map[sid].section_role for sid in layer_ids if sid in section_map]
            dominant_role = Counter(roles_in_layer).most_common(1)[0][0]
            phase_type = self._role_to_phase_type(dominant_role)

            depends_on = [phases[-1].phase_id] if phases else []

            phase = self._create_phase(phase_id, phase_type, layer_sections,
                                        task_structure, topic, parallel=True,
                                        depends_on=depends_on,
                                        section_to_agent=global_section_to_agent)
            phases.append(phase)
            counter += 1

        # CROSS_SYNTHESIS if both survey and desk research exist
        has_survey = any(p.phase_type == PhaseType.SURVEY for p in phases)
        has_desk = any(p.phase_type in (PhaseType.DATA_COLLECTION, PhaseType.ANALYSIS, PhaseType.SYNTHESIS)
                       for p in phases)
        if has_survey and has_desk:
            depends_on = [phases[-1].phase_id] if phases else []
            phases.append(self._create_phase(f"phase_{counter}", PhaseType.CROSS_SYNTHESIS, [],
                                              task_structure, topic, parallel=False,
                                              depends_on=depends_on,
                                              section_to_agent=global_section_to_agent))
            counter += 1

        # REPORT phase (always last)
        depends_on = [phases[-1].phase_id] if phases else []
        phases.append(self._create_report_phase(f"phase_{counter}", task_structure, topic,
                                                 depends_on=depends_on))
        return phases

    def _role_to_phase_type(self, role: SectionRole) -> PhaseType:
        mapping = {
            SectionRole.DATA_COLLECTION: PhaseType.DATA_COLLECTION,
            SectionRole.ANALYSIS: PhaseType.ANALYSIS,
            SectionRole.SYNTHESIS: PhaseType.SYNTHESIS,
            SectionRole.SUPPORTING: PhaseType.DATA_COLLECTION,
        }
        return mapping.get(role, PhaseType.ANALYSIS)

    def _create_phase(self, phase_id, phase_type, sections, task_structure, topic,
                      parallel=True, unlock_conditions=None, depends_on=None,
                      section_to_agent=None):
        """Create phase with optional section_id→agent_id dependency conversion (R-FIX-3)."""
        if section_to_agent is None:
            section_to_agent = {}
        agents = []
        for i, section in enumerate(sections):
            deps = section.content_dependency if hasattr(section, 'content_dependency') else []
            agent_id = f"{phase_id}_agent_{i}"
            agent = AgentSpec(
                agent_id=agent_id, agent_type=phase_type.value,
                section_ids=[section.section_id] if hasattr(section, 'section_id') else [],
                priority=i,
                config={"content_dependency": deps})
            agents.append(agent)
            if hasattr(section, 'section_id'):
                section_to_agent[section.section_id] = agent_id
        
        # R-FIX-3: convert section_id dependencies to agent_id
        for agent in agents:
            raw_deps = agent.config.get("content_dependency", [])
            resolved = [section_to_agent[sid] for sid in raw_deps if sid in section_to_agent]
            agent.config["resolved_dependencies"] = resolved
        
        section_ids = [s.section_id for s in sections if hasattr(s, 'section_id')]
        return ExecutionPhase(phase_id=phase_id, phase_type=phase_type, agent_specs=agents,
                              section_ids=section_ids, parallel=parallel,
                              depends_on=depends_on or [],
                              unlock_conditions=unlock_conditions or {})

    def _create_report_phase(self, phase_id, task_structure, topic,
                              depends_on=None, unlock_conditions=None):
        return ExecutionPhase(
            phase_id=phase_id, phase_type=PhaseType.REPORT, agent_specs=[
                AgentSpec(agent_id=f"{phase_id}_report", agent_type="report_generation",
                          section_ids=[], priority=0)],
            section_ids=[], parallel=False, depends_on=depends_on or [],
            unlock_conditions=unlock_conditions or {})

    def _generate_content_lock_rules(self, task_structure, phases):
        rules = []

        # Build dependency map from ContentDependency[]
        # ContentDependency.from_section → to_section means to_section depends on from_section
        dep_map: Dict[str, List[str]] = {}
        for dep in task_structure.dependencies:
            dep_map.setdefault(dep.to_section, []).append(dep.from_section)

        # Supplement with SectionSpec.content_dependency
        for section in task_structure.sections:
            if section.content_dependency:
                existing = dep_map.setdefault(section.section_id, [])
                for cd in section.content_dependency:
                    if cd not in existing:
                        existing.append(cd)

        # Generate ContentLockRule per section, deduplicated
        for phase in phases:
            for agent in phase.agent_specs:
                for sid in agent.section_ids:
                    if sid in dep_map:
                        rules.append(ContentLockRule(
                            target_section=sid,
                            required_sections=list(dict.fromkeys(dep_map[sid])),
                            lock_type="completion",
                            quality_threshold=75.0,  # C-FIX-3: was 0.0, align with ContentDependency default
                            lock_reason=f"Depends on: {', '.join(dep_map[sid])}"
                        ))
                    # sid not in dep_map → no rules → auto-unlocked by ContentLockManager
        return rules
