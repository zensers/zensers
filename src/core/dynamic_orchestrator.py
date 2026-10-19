"""
DynamicPhaseOrchestrator - Dynamically generates execution phases from task structure and intent.
"""
import logging
import uuid
import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .semantic_intent import DeepIntentResult
from .task_structure import TaskStructure, SectionRole, ContentDependency

logger = logging.getLogger(__name__)


class PhaseType(Enum):
    DATA_COLLECTION = "data_collection"
    ANALYSIS = "analysis"
    SYNTHESIS = "synthesis"
    REPORT = "report"
    SURVEY = "survey"
    CROSS_SYNTHESIS = "cross_synthesis"
    VALIDATION = "validation"
    CALIBRATION = "calibration"


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
            PhaseType.CALIBRATION: ResearchPhase.CALIBRATION,
            PhaseType.REPORT: ResearchPhase.REPORT_GENERATION,
            PhaseType.VALIDATION: ResearchPhase.DATA_VALIDATION,
        }

        phases: Dict[ResearchPhase, List[OriginalAgentSpec]] = {}
        for phase in self.phases:
            rp = phase_type_to_research_phase.get(
                phase.phase_type, ResearchPhase.DEEP_ANALYSIS
            )
            for spec in phase.agent_specs:
                # M1-a + M5-b: Category override to match generic_agent routing
                if rp == ResearchPhase.DATA_COLLECTION:
                    category_override = "research"
                elif rp == ResearchPhase.DATA_VALIDATION:
                    category_override = "quality-check"
                elif rp == ResearchPhase.CALIBRATION:
                    category_override = "calibration"
                else:
                    category_override = spec.agent_type

                orig = OriginalAgentSpec(
                    agent_id=spec.agent_id,
                    agent_type=spec.agent_type,
                    category=category_override,
                    task_description=spec.core_question or "",
                    input_keys=[],
                    output_keys=spec.section_ids,
                    dependencies=spec.config.get("resolved_dependencies", []) or spec.config.get("content_dependency", []),
                    priority=spec.priority,
                    parallel_group=spec.parallel_group,
                    quality_threshold=spec.quality_threshold,
                    max_retries=spec.max_retries,
                )
                orig.context.update(spec.config)
                phases.setdefault(rp, []).append(orig)

        execution_order = [
            rp for rp in [
                ResearchPhase.DATA_COLLECTION,
                ResearchPhase.DATA_VALIDATION,
                ResearchPhase.DEEP_ANALYSIS,
                ResearchPhase.SYNTHESIS,
                ResearchPhase.CALIBRATION,
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
            section_data_specs=list(getattr(self.task_structure, "section_data_specs", []) or []),
            section_manifest=list(getattr(self.task_structure, "section_manifest", []) or []),
        )


class DynamicPhaseOrchestrator:
    """Generates execution plans from task structure and intent analysis."""

    def __init__(self):
        self.phases: List[ExecutionPhase] = []

    @staticmethod
    def _expand_subsection_leaves(task_structure: TaskStructure) -> None:
        """Expand confirmed subsection specs before dynamic agents are made.

        The old router kept subsections only in prompts.  This made the
        report writer aware of chapters that data collection and analysis had
        never executed.  This method turns each data-bearing subsection into
        a stable ``parent::sub`` SectionSpec and records a single manifest
        used by all later phases.
        """
        raw_specs = getattr(task_structure, "section_data_specs", []) or []
        existing_manifest = [
            item for item in (getattr(task_structure, "section_manifest", None) or [])
            if isinstance(item, dict) and str(item.get("section_id") or "").strip()
        ]
        if existing_manifest:
            # Do not treat a parent-only/legacy manifest as complete merely
            # because it is non-empty.  A confirmed tree with children must
            # have one executable leaf entry per child before routing can
            # proceed.
            existing_id_list = [str(item["section_id"]).strip() for item in existing_manifest]
            existing_ids = set(existing_id_list)
            current_section_ids = {
                str(getattr(section, "section_id", "") or "").strip()
                for section in task_structure.sections
                if str(getattr(section, "section_id", "") or "").strip()
            }
            subsection_parent_ids = {
                str(
                    (candidate.get("section_id") if isinstance(candidate, dict)
                     else getattr(candidate, "section_id", "")) or ""
                ).strip()
                for candidate in raw_specs
                if (
                    (candidate.get("sub_sections") if isinstance(candidate, dict)
                     else getattr(candidate, "sub_sections", None))
                    and str(
                        (candidate.get("section_id") if isinstance(candidate, dict)
                         else getattr(candidate, "section_id", "")) or ""
                    ).strip()
                )
            }
            duplicate_existing_ids = {
                section_id for section_id in existing_id_list
                if existing_id_list.count(section_id) > 1
            }
            if duplicate_existing_ids:
                raise ValueError(
                    f"Manifest validation failed: duplicate section IDs {sorted(duplicate_existing_ids)}"
                )
            # Planning can be retried after a DAG order repair.  The first
            # plan expands task_structure.sections in place and freezes the
            # matching manifest; a second plan must reuse that canonical leaf
            # state instead of trying to bind raw parent specs to section_N::sub
            # IDs again.
            if (
                current_section_ids
                and existing_ids == current_section_ids
                and (
                    not subsection_parent_ids
                    or any("::" in section_id for section_id in current_section_ids)
                )
                and not (current_section_ids & subsection_parent_ids)
            ):
                return
            expected_leaf_ids = set()
            for section in task_structure.sections:
                raw = section if isinstance(section, dict) else section
                section_id = str(
                    raw.get("section_id") if isinstance(raw, dict)
                    else getattr(raw, "section_id", "")
                ).strip()
                spec = next(
                    (
                        candidate for candidate in raw_specs
                        if str((candidate.get("section_id") if isinstance(candidate, dict) else getattr(candidate, "section_id", "")) or "").strip() == section_id
                    ),
                    None,
                )
                raw_subs = spec.get("sub_sections", []) if isinstance(spec, dict) else getattr(spec, "sub_sections", []) if spec else []
                def collect_leaf_ids(items, parent_path=()):
                    for index, sub in enumerate(items or []):
                        sub_id = str(
                            (sub.get("sub_section_id") or sub.get("id") or f"sub_{index}")
                            if isinstance(sub, dict)
                            else (getattr(sub, "sub_section_id", "") or getattr(sub, "id", "") or f"sub_{index}")
                        ).strip()
                        if not sub_id:
                            continue
                        path = parent_path + (sub_id,)
                        children = (
                            sub.get("sub_sections") or sub.get("subsections") or sub.get("children") or []
                            if isinstance(sub, dict)
                            else getattr(sub, "sub_sections", []) or []
                        )
                        if children:
                            yield from collect_leaf_ids(children, path)
                        else:
                            yield f"{section_id}::{'::'.join(path)}"

                expected_leaf_ids.update(collect_leaf_ids(raw_subs))
            has_subsection_contract = any(
                bool(
                    (candidate.get("sub_sections") if isinstance(candidate, dict)
                     else getattr(candidate, "sub_sections", None))
                )
                for candidate in raw_specs
            )
            if has_subsection_contract and not expected_leaf_ids:
                raise ValueError(
                    "Manifest validation failed: subsection contract exists but no expected leaf IDs could be bound"
                )
            if expected_leaf_ids == existing_ids:
                return
            logger.warning(
                "Existing section_manifest is incomplete; expanding missing subsection leaves: %s",
                sorted(expected_leaf_ids - existing_ids),
            )

        def fields(value: Any) -> Dict[str, Any]:
            if isinstance(value, dict):
                return value

            def subsection_fields(sub: Any) -> Dict[str, Any]:
                if isinstance(sub, dict):
                    return dict(sub)
                return {
                    "sub_section_id": getattr(sub, "sub_section_id", "") or getattr(sub, "id", ""),
                    "name": getattr(sub, "name", ""),
                    "data_needs": getattr(sub, "data_needs", []),
                    "required_metrics": getattr(sub, "required_metrics", []),
                    "points": getattr(sub, "points", []),
                    "data_source_type": getattr(sub, "data_source_type", "search"),
                    "sub_sections": [
                        subsection_fields(child)
                        for child in (getattr(sub, "sub_sections", None) or [])
                    ],
                }

            return {
                "section_id": getattr(value, "section_id", ""),
                "name": getattr(value, "name", ""),
                "sub_sections": [
                    subsection_fields(sub)
                    for sub in (getattr(value, "sub_sections", []) or [])
                ],
            }

        specs_by_name = {}
        specs_by_id = {}
        for raw in raw_specs:
            spec = fields(raw)
            name = str(spec.get("name", "") or "").strip()
            sid = str(spec.get("section_id", "") or "").strip()
            if name:
                specs_by_name.setdefault(name, []).append(spec)
            if sid:
                if sid in specs_by_id:
                    raise ValueError(f"Manifest validation failed: duplicate data spec ID {sid}")
                specs_by_id[sid] = spec

        def resolve_spec(section):
            by_id = specs_by_id.get(section.section_id)
            if by_id is not None:
                return by_id
            candidates = specs_by_name.get(section.section_name, [])
            if len(candidates) > 1:
                raise ValueError(
                    f"Manifest validation failed: ambiguous subsection binding for {section.section_name}"
                )
            return candidates[0] if candidates else None

        expanded_sections = []
        leaf_map: Dict[str, List[str]] = {}
        manifest = []
        changed = False

        def output_slot(section_name: str, role: SectionRole, config: Optional[Dict[str, Any]] = None) -> str:
            """Return the explicit report output slot for a section.

            The slot is metadata, not identity: summary/conclusion results are
            still joined by ``section_id``.  Keep the title fallback only for
            old LLM plans that did not emit an explicit slot.
            """
            cfg = config or {}
            explicit = str(cfg.get("output_slot", "") or "").strip().lower()
            if explicit in {"exec_summary", "conclusion", "body"}:
                return explicit
            if role == SectionRole.SYNTHESIS:
                title = str(section_name or "").lower()
                if "摘要" in title or "summary" in title:
                    return "exec_summary"
                if "结论" in title or "conclusion" in title or "总结" in title:
                    return "conclusion"
            return "body"
        for section in task_structure.sections:
            spec = resolve_spec(section)
            if (
                spec is None
                and section.section_role in (SectionRole.ANALYSIS, SectionRole.DATA_COLLECTION)
                and any(
                    bool((candidate.get("sub_sections") if isinstance(candidate, dict)
                          else getattr(candidate, "sub_sections", None)))
                    for candidate in raw_specs
                )
            ):
                raise ValueError(
                    f"Manifest validation failed: subsection contract could not bind to {section.section_id}"
                )
            subs = (spec or {}).get("sub_sections", []) if spec else []
            valid_subs = [sub for sub in subs if isinstance(sub, dict) and str(sub.get("name", "")).strip()]
            if section.section_role not in (SectionRole.ANALYSIS, SectionRole.DATA_COLLECTION) or not valid_subs:
                expanded_sections.append(section)
                leaf_map[section.section_id] = [section.section_id]
                manifest.append({
                    "section_id": section.section_id,
                    "parent_section_id": section.section_id,
                    "sub_section_id": "",
                    "title": section.section_name,
                    "role": section.section_role.value,
                    "output_slot": output_slot(
                        section.section_name, section.section_role,
                        getattr(section, "config", {}) or {},
                    ),
                    "required_metrics": [],
                    "status": "pending",
                    "evidence_ids": [],
                })
                continue

            changed = True
            leaves = []
            generated_leaf_ids = set()
            def iter_leaf_subsections(items, parent_path=()):
                for index, sub in enumerate(items):
                    if not isinstance(sub, dict) or not str(sub.get("name", "")).strip():
                        raise ValueError(
                            f"Invalid subsection under {section.section_id}: title is required"
                        )
                    sub_id = str(
                        sub.get("sub_section_id") or sub.get("id") or f"sub_{index}"
                    ).strip()
                    if not sub_id:
                        raise ValueError(f"Invalid subsection under {section.section_id}: stable ID is required")
                    path = parent_path + (sub_id,)
                    children = sub.get("sub_sections") or sub.get("subsections") or sub.get("children") or []
                    if children:
                        yield from iter_leaf_subsections(children, path)
                    else:
                        yield path, sub

            for path, sub in iter_leaf_subsections(valid_subs):
                leaf_id = f"{section.section_id}::{'::'.join(path)}"
                if leaf_id in generated_leaf_ids:
                    raise ValueError(f"Manifest validation failed: duplicate generated leaf ID {leaf_id}")
                generated_leaf_ids.add(leaf_id)
                parent_id = f"{section.section_id}::{'::'.join(path[:-1])}" if len(path) > 1 else section.section_id
                sub_id = path[-1]
                child = copy.deepcopy(section)
                child.section_id = leaf_id
                child.section_name = str(sub.get("name")).strip()
                child.config = {
                    **(child.config or {}),
                    "parent_section_id": parent_id,
                    "sub_section_id": sub_id,
                    "required_metrics": list(sub.get("data_needs") or sub.get("required_metrics") or sub.get("points") or []),
                    "data_source_type": sub.get("data_source_type", "search"),
                }
                child.content_dependency = []
                expanded_sections.append(child)
                leaves.append(leaf_id)
                manifest.append({
                    "section_id": leaf_id,
                    "parent_section_id": parent_id,
                    "sub_section_id": sub_id,
                    "title": child.section_name,
                    "role": child.section_role.value,
                    "output_slot": output_slot(child.section_name, child.section_role, child.config),
                    "required_metrics": child.config["required_metrics"],
                    "status": "pending",
                    "evidence_ids": [],
                })
            leaf_map[section.section_id] = leaves

        if not changed:
            # Still freeze a manifest for non-nested plans.
            task_structure.section_manifest = manifest
            return

        expanded_dependencies = []
        seen = set()
        for dependency in task_structure.dependencies:
            sources = leaf_map.get(dependency.from_section, [dependency.from_section])
            targets = leaf_map.get(dependency.to_section, [dependency.to_section])
            for source in sources:
                for target in targets:
                    if source == target or (source, target) in seen:
                        continue
                    seen.add((source, target))
                    expanded_dependencies.append(ContentDependency(
                        from_section=source,
                        to_section=target,
                        dependency_type=dependency.dependency_type,
                        dependency_reason=dependency.dependency_reason,
                        unlock_condition=dependency.unlock_condition,
                        quality_threshold=dependency.quality_threshold,
                    ))
        dependency_map = {section.section_id: [] for section in expanded_sections}
        for dependency in expanded_dependencies:
            dependency_map.setdefault(dependency.to_section, []).append(dependency.from_section)
        for section in expanded_sections:
            section.content_dependency = dependency_map.get(section.section_id, [])

        task_structure.sections = expanded_sections
        task_structure.dependencies = expanded_dependencies
        task_structure.parallel_groups = [[section.section_id for section in expanded_sections]]
        task_structure.section_manifest = manifest

    def plan(self, task_structure: TaskStructure, intent: DeepIntentResult,
             topic: Optional[str] = None) -> ExecutionPlan:
        self._expand_subsection_leaves(task_structure)
        plan_id = f"plan_{uuid.uuid4().hex[:8]}"
        topic = topic or task_structure.topic
        logger.info(f"[{plan_id}] Generating plan for {len(task_structure.sections)} sections, "
                    f"{len(task_structure.parallel_groups)} DAG layers")
        phases = self._generate_phases(task_structure, intent, topic)
        self._attach_manifest_producers(task_structure, phases)
        content_lock_rules = self._generate_content_lock_rules(task_structure, phases)
        total_agents = sum(len(p.agent_specs) for p in phases)
        return ExecutionPlan(plan_id=plan_id, task_structure=task_structure, phases=phases,
                             content_lock_rules=content_lock_rules, total_agents=total_agents)

    @staticmethod
    def _attach_manifest_producers(task_structure: TaskStructure, phases: List[ExecutionPhase]) -> None:
        """Freeze the actual phase Agent IDs into every Manifest item.

        The report boundary must be able to prove which created Agents were
        responsible for each output.  Do this only after all phases exist so
        compact and two-pass routes produce the same schema.
        """
        manifest = getattr(task_structure, "section_manifest", None) or []
        by_section = {str(item.get("section_id") or "").strip(): item
                      for item in manifest if isinstance(item, dict)}
        for item in by_section.values():
            item["producer_agent_ids"] = {}
        phase_key = {
            PhaseType.DATA_COLLECTION: "data_collection",
            PhaseType.SURVEY: "data_collection",
            PhaseType.VALIDATION: "validation",
            PhaseType.ANALYSIS: "analysis",
            PhaseType.SYNTHESIS: "synthesis",
            PhaseType.CROSS_SYNTHESIS: "synthesis",
        }
        for phase in phases:
            key = phase_key.get(phase.phase_type)
            if not key:
                continue
            for spec in phase.agent_specs:
                for section_id in spec.section_ids:
                    item = by_section.get(str(section_id).strip())
                    if item is None:
                        continue
                    item.setdefault("producer_agent_ids", {}).setdefault(key, []).append(spec.agent_id)
        missing = [section_id for section_id, item in by_section.items()
                   if not item.get("producer_agent_ids")]
        if missing:
            raise ValueError(f"Manifest producer binding failed for sections: {sorted(missing)}")

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
        section_ids = set(section_map)
        normalized_layers = [
            [sid for sid in layer if sid in section_ids]
            for layer in (dag_layers or [])
        ]
        normalized_layers = [layer for layer in normalized_layers if layer]
        covered_ids = {sid for layer in normalized_layers for sid in layer}
        if not normalized_layers or covered_ids != section_ids:
            normalized_layers = [[s.section_id for s in task_structure.sections]]
            has_explicit_dag = False
        else:
            has_explicit_dag = True
        dag_layers = normalized_layers

        # Preserve an explicit multi-layer DAG exactly.  When no DAG was
        # supplied, keep an all-ANALYSIS task compact, but split a mixed-role
        # structure into role layers so explicit DATA_COLLECTION sections do
        # not silently disappear into an ANALYSIS phase.
        if not has_explicit_dag:
            role_groups = []
            for role in (SectionRole.DATA_COLLECTION, SectionRole.ANALYSIS, SectionRole.SYNTHESIS, SectionRole.SUPPORTING):
                group = [s.section_id for s in task_structure.sections if s.section_role == role]
                if group:
                    role_groups.append(group)
            if len(role_groups) > 1:
                dag_layers = role_groups
                has_explicit_dag = True
            else:
                return self._generate_layered_phases(
                    phases, dag_layers, section_map, task_structure, topic,
                    counter, global_section_to_agent, add_calibration=False,
                )

        if len(dag_layers) > 1:
            return self._generate_layered_phases(
                phases, dag_layers, section_map, task_structure, topic,
                counter, global_section_to_agent,
                add_calibration=(len(dag_layers) == 1 and has_explicit_dag),
            )

        # M1: Split ANALYSIS sections into DC + Analysis dual phases only
        # when the task actually needs a multi-stage plan.  A SINGLE task
        # already has an analysis agent capable of searching for missing
        # evidence; forcing a second agent per section doubles LLM calls and
        # was the main source of 14-section MIMO timeouts.
        analysis_sections = []
        synthesis_sections = []
        other_sections = []
        dc_section_to_agent = {}  # separate map: section_id -> DC agent_id (never overwritten)

        for layer_ids in dag_layers:
            for sid in layer_ids:
                section = section_map.get(sid)
                if not section:
                    continue
                if section.section_role == SectionRole.ANALYSIS:
                    analysis_sections.append(section)
                elif section.section_role == SectionRole.SYNTHESIS:
                    synthesis_sections.append(section)
                else:
                    other_sections.append(section)

        complexity_value = getattr(getattr(intent, "complexity", None), "value", "")
        explicit_primary_data = bool(getattr(intent, "requires_primary_data", False))
        force_two_pass = any(
            bool((getattr(section, "config", {}) or {}).get("requires_separate_data_collection"))
            for section in analysis_sections
        )
        compact_large_report = len(analysis_sections) > 8 and not explicit_primary_data
        split_analysis_passes = (
            (complexity_value in {"multi", "complex"}
             and not compact_large_report
             and not explicit_primary_data)
            or force_two_pass
            # Keyword/rule fallback does not know the true task complexity;
            # keep the data-first route conservative in that case.
            or (getattr(intent, "used_fallback", False) is True
                and not compact_large_report)
        )
        dc_sections = list(analysis_sections) if split_analysis_passes else []
        if not split_analysis_passes:
            logger.info(
                "[Routing] Compact route: using one-pass analysis agents "
                "instead of per-section data-collection duplication"
            )

        # M1 Phase A: DATA_COLLECTION — ANALYSIS sections do pure search first
        dc_phase = None
        if dc_sections:
            dc_phase = self._create_dc_phase(f"phase_{counter}", dc_sections, task_structure, topic,
                                              section_to_agent=dc_section_to_agent)
            phases.append(dc_phase)
            counter += 1

        # M1 Phase B: DEEP_ANALYSIS — ANALYSIS sections analyze with DC data
        analysis_phase = None
        if analysis_sections:
            dc_depends = [dc_phase.phase_id] if dc_phase else []
            analysis_phase = self._create_analysis_phase_with_deps(
                f"phase_{counter}", analysis_sections, task_structure, topic,
                dc_agent_map=dc_section_to_agent,
                section_to_agent=global_section_to_agent,
                depends_on=dc_depends,
                compact_route=compact_large_report,
            )
            phases.append(analysis_phase)
            counter += 1

        # Phase C: SYNTHESIS sections (keep original logic)
        if synthesis_sections:
            depends_on = [phases[-1].phase_id] if phases else []
            phase = self._create_phase(f"phase_{counter}", PhaseType.SYNTHESIS, synthesis_sections,
                                        task_structure, topic, parallel=True,
                                        depends_on=depends_on,
                                        section_to_agent=global_section_to_agent)
            phases.append(phase)
            counter += 1

        # Phase D: Other sections (DATA_COLLECTION, SUPPORTING)
        if other_sections:
            depends_on = [phases[-1].phase_id] if phases else []
            grouped_sections = {}
            for section in other_sections:
                phase_type = self._role_to_phase_type(section.section_role)
                grouped_sections.setdefault(phase_type, []).append(section)

            # Sections with the same execution role are independent by
            # default.  Put them in one parallel phase instead of creating a
            # serial phase per section; explicit DAG dependencies are already
            # represented by the preceding analysis/synthesis phases.
            for phase_type, grouped in grouped_sections.items():
                phase = self._create_phase(f"phase_{counter}", phase_type, grouped,
                                            task_structure, topic, parallel=True,
                                            depends_on=depends_on,
                                            section_to_agent=global_section_to_agent)
                phases.append(phase)
                depends_on = [phase.phase_id]
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

        # M5-b Phase E: CALIBRATION — cross-agent numeric consistency check
        _has_analysis = any(p.phase_type == PhaseType.ANALYSIS for p in phases)
        if _has_analysis:
            # Calibrator must depend on ALL prior agents so scheduler puts it in a later batch.
            # Phase-level depends_on controls execution flow; agent-level resolved_dependencies
            # ensures the scheduler topological sort batches the calibrator after all prior agents.
            _prior_agent_ids_set = set()
            for _p in phases:
                for _spec in _p.agent_specs:
                    if _spec.agent_id:
                        _prior_agent_ids_set.add(_spec.agent_id)
            _prior_agent_ids = sorted(_prior_agent_ids_set)
            cal_depends_on = [phases[-1].phase_id] if phases else []
            cal_phase = ExecutionPhase(
                phase_id=f"phase_{counter}",
                phase_type=PhaseType.CALIBRATION,
                agent_specs=[
                    AgentSpec(
                        agent_id=f"phase_{counter}_calibrator",
                        agent_type="calibration",
                        section_ids=[],
                        priority=0,
                        config={
                            "content_dependency": [],
                            "resolved_dependencies": _prior_agent_ids,
                            "category": "calibration",
                        },
                        core_question="统一全报告数据口径，消除数值和叙述矛盾",
                    ),
                ],
                section_ids=[],
                parallel=False,
                depends_on=cal_depends_on,
            )
            phases.append(cal_phase)
            counter += 1

        # REPORT phase (always last)
        depends_on = [phases[-1].phase_id] if phases else []
        phases.append(self._create_report_phase(f"phase_{counter}", task_structure, topic,
                                                 depends_on=depends_on))
        return phases

    def _generate_layered_phases(self, phases, dag_layers, section_map,
                                 task_structure, topic, counter,
                                 section_to_agent, add_calibration=True):
        """Generate one phase per real DAG layer without reordering sections."""
        for layer in dag_layers:
            sections = [section_map[sid] for sid in layer if sid in section_map]
            if not sections:
                continue
            roles = {section.section_role for section in sections}
            if roles == {SectionRole.SYNTHESIS}:
                phase_type = PhaseType.SYNTHESIS
            elif roles.issubset({SectionRole.DATA_COLLECTION, SectionRole.SUPPORTING}):
                phase_type = PhaseType.DATA_COLLECTION
            else:
                phase_type = PhaseType.ANALYSIS
            depends_on = [phases[-1].phase_id] if phases else []
            phases.append(self._create_phase(
                f"phase_{counter}", phase_type, sections, task_structure, topic,
                parallel=True, depends_on=depends_on,
                section_to_agent=section_to_agent,
            ))
            counter += 1

        has_survey = any(p.phase_type == PhaseType.SURVEY for p in phases)
        has_desk = any(p.phase_type in (
            PhaseType.DATA_COLLECTION, PhaseType.ANALYSIS, PhaseType.SYNTHESIS
        ) for p in phases)
        if has_survey and has_desk:
            depends_on = [phases[-1].phase_id] if phases else []
            phases.append(self._create_phase(
                f"phase_{counter}", PhaseType.CROSS_SYNTHESIS, [], task_structure, topic,
                parallel=False, depends_on=depends_on,
                section_to_agent=section_to_agent,
            ))
            counter += 1

        if add_calibration and any(p.phase_type == PhaseType.ANALYSIS for p in phases):
            prior_agent_ids = sorted(
                spec.agent_id
                for phase in phases
                for spec in phase.agent_specs
                if spec.agent_id
            )
            phases.append(ExecutionPhase(
                phase_id=f"phase_{counter}",
                phase_type=PhaseType.CALIBRATION,
                agent_specs=[AgentSpec(
                    agent_id=f"phase_{counter}_calibrator",
                    agent_type="calibration",
                    section_ids=[],
                    config={
                        "content_dependency": [],
                        "resolved_dependencies": prior_agent_ids,
                        "category": "calibration",
                    },
                    core_question="统一全报告数据口径，消除数值和叙述矛盾",
                )],
                section_ids=[], parallel=False,
                depends_on=[phases[-1].phase_id] if phases else [],
            ))
            counter += 1

        phases.append(self._create_report_phase(
            f"phase_{counter}", task_structure, topic,
            depends_on=[phases[-1].phase_id] if phases else [],
        ))
        return phases

    def _create_dc_phase(self, phase_id, sections, task_structure, topic,
                          section_to_agent=None):
        """M1: Create pure data collection phase for ANALYSIS sections."""
        if section_to_agent is None:
            section_to_agent = {}
        agents = []
        for i, section in enumerate(sections):
            agent_id = f"{phase_id}_agent_{i}"
            agent = AgentSpec(
                agent_id=agent_id,
                agent_type=PhaseType.DATA_COLLECTION.value,
                section_ids=[section.section_id],
                priority=i,
                config={"content_dependency": [], "resolved_dependencies": []},
                core_question=f"收集 {section.section_name} 维度的基础数据",
            )
            agents.append(agent)
            section_to_agent[section.section_id] = agent_id
        section_ids = [s.section_id for s in sections]
        return ExecutionPhase(
            phase_id=phase_id, phase_type=PhaseType.DATA_COLLECTION,
            agent_specs=agents, section_ids=section_ids,
            parallel=True, depends_on=[],
        )

    def _create_analysis_phase_with_deps(self, phase_id, sections, task_structure, topic,
                                          dc_agent_map=None, section_to_agent=None, depends_on=None,
                                          compact_route=False):
        """M1: Create analysis phase where each agent depends on its DC agent."""
        if dc_agent_map is None:
            dc_agent_map = {}
        if section_to_agent is None:
            section_to_agent = {}
        agents = []
        for i, section in enumerate(sections):
            agent_id = f"{phase_id}_agent_{i}"
            dc_dep = dc_agent_map.get(section.section_id, "")
            resolved = [dc_dep] if dc_dep else []
            content_deps = getattr(section, 'content_dependency', []) or []
            for dep_sid in content_deps:
                dep_aid = section_to_agent.get(dep_sid) or dc_agent_map.get(dep_sid)
                if dep_aid and dep_aid not in resolved:
                    resolved.append(dep_aid)
            agent = AgentSpec(
                agent_id=agent_id,
                agent_type=PhaseType.ANALYSIS.value,
                section_ids=[section.section_id],
                priority=i,
                config={
                    "content_dependency": content_deps,
                    "resolved_dependencies": resolved,
                    "compact_route": compact_route,
                },
                core_question=section.section_name,
                dependencies=resolved,
            )
            agents.append(agent)
            section_to_agent[section.section_id] = agent_id
        section_ids = [s.section_id for s in sections]
        return ExecutionPhase(
            phase_id=phase_id, phase_type=PhaseType.ANALYSIS,
            agent_specs=agents, section_ids=section_ids,
            parallel=True, depends_on=depends_on or [],
        )

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
                config={
                    "content_dependency": deps,
                    "section_manifest": list(getattr(task_structure, "section_manifest", []) or []),
                    "section_metadata": {
                        "section_id": getattr(section, "section_id", ""),
                        "title": getattr(section, "section_name", ""),
                        "role": getattr(getattr(section, "section_role", None), "value", ""),
                        "output_slot": (getattr(section, "config", {}) or {}).get("output_slot", ""),
                    },
                })
            agents.append(agent)
            if hasattr(section, 'section_id'):
                section_to_agent[section.section_id] = agent_id
        
        # R-FIX-3: convert section_id dependencies to agent_id
        for agent in agents:
            raw_deps = agent.config.get("content_dependency", [])
            resolved = [section_to_agent[sid] for sid in raw_deps if sid in section_to_agent]
            # Synthesis is a reducer over all upstream reportable chapters.
            # A phase dependency alone is insufficient: the scheduler and
            # recovery logic need the exact producer set as a content contract.
            if phase_type in (PhaseType.SYNTHESIS, PhaseType.CROSS_SYNTHESIS):
                upstream = [aid for sid, aid in section_to_agent.items()
                            if sid not in {s.section_id for s in sections}]
                resolved = list(dict.fromkeys(resolved + upstream))
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
                          section_ids=[], priority=0,
                          config={
                              "section_manifest": list(getattr(task_structure, "section_manifest", []) or []),
                              "report_contract": "manifest_exact_join",
                          })],
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
        seen_lock_targets = set()
        for phase in phases:
            for agent in phase.agent_specs:
                for sid in agent.section_ids:
                    if sid in dep_map and sid not in seen_lock_targets:
                        seen_lock_targets.add(sid)
                        rules.append(ContentLockRule(
                            target_section=sid,
                            required_sections=list(dict.fromkeys(dep_map[sid])),
                            lock_type="completion",
                            quality_threshold=75.0,  # C-FIX-3: was 0.0, align with ContentDependency default
                            lock_reason=f"Depends on: {', '.join(dep_map[sid])}"
                        ))
                    # sid not in dep_map → no rules → auto-unlocked by ContentLockManager
        return rules

    def _orchestrate_forensic_phases(self, task_structure, intent, topic):
        """Generate forensic analysis phases: DC→Analysis→Synthesis→Calibration→Report."""
        phases = []
        counter = 1
        section_map = {s.section_id: s for s in task_structure.sections}
        global_section_to_agent = {}

        dc_sections = [s for s in task_structure.sections if s.section_role == SectionRole.DATA_COLLECTION]
        analysis_sections = [s for s in task_structure.sections if s.section_role == SectionRole.ANALYSIS]
        synthesis_sections = [s for s in task_structure.sections if s.section_role == SectionRole.SYNTHESIS]

        # Phase A: DATA_COLLECTION — single agent for precise data extraction
        dc_phase = None
        if dc_sections:
            dc_agent = AgentSpec(
                agent_id=f"phase_{counter}_dc_0",
                agent_type=PhaseType.DATA_COLLECTION.value,
                section_ids=[s.section_id for s in dc_sections],
                priority=0,
                config={"content_dependency": [], "resolved_dependencies": []},
                core_question="根据所有假设的数据需求，从年报中精准提取相关数据",
            )
            dc_phase = ExecutionPhase(
                phase_id=f"phase_{counter}",
                phase_type=PhaseType.DATA_COLLECTION,
                agent_specs=[dc_agent],
                section_ids=[s.section_id for s in dc_sections],
                parallel=False,
                depends_on=[],
            )
            phases.append(dc_phase)
            counter += 1

        # Phase B: DEEP_ANALYSIS — one agent per hypothesis
        analysis_phase = None
        if analysis_sections:
            dc_depends = [dc_phase.phase_id] if dc_phase else []
            agents = []
            for i, section in enumerate(analysis_sections):
                agent_id = f"phase_{counter}_agent_{i}"
                dc_dep = dc_phase.agent_specs[0].agent_id if dc_phase else ""
                resolved = [dc_dep] if dc_dep else []
                content_deps = getattr(section, 'content_dependency', []) or []
                for dep_sid in content_deps:
                    dep_aid = global_section_to_agent.get(dep_sid)
                    if dep_aid and dep_aid not in resolved:
                        resolved.append(dep_aid)
                agent_config = {
                    "content_dependency": content_deps,
                    "resolved_dependencies": resolved,
                }
                if hasattr(section, 'config') and section.config:
                    agent_config.update(section.config)
                agent = AgentSpec(
                    agent_id=agent_id,
                    agent_type=PhaseType.ANALYSIS.value,
                    section_ids=[section.section_id],
                    priority=i,
                    config=agent_config,
                    core_question=section.section_name,
                    dependencies=resolved,
                )
                agents.append(agent)
                global_section_to_agent[section.section_id] = agent_id
            analysis_phase = ExecutionPhase(
                phase_id=f"phase_{counter}",
                phase_type=PhaseType.ANALYSIS,
                agent_specs=agents,
                section_ids=[s.section_id for s in analysis_sections],
                parallel=True,
                depends_on=dc_depends,
            )
            phases.append(analysis_phase)
            counter += 1

        # Phase C: SYNTHESIS — causal attribution
        if synthesis_sections:
            depends_on = [analysis_phase.phase_id] if analysis_phase else ([dc_phase.phase_id] if dc_phase else [])
            agents = []
            for i, section in enumerate(synthesis_sections):
                agent_id = f"phase_{counter}_agent_{i}"
                content_deps = getattr(section, 'content_dependency', []) or []
                resolved = [global_section_to_agent[sid] for sid in content_deps if sid in global_section_to_agent]
                agent = AgentSpec(
                    agent_id=agent_id,
                    agent_type=PhaseType.SYNTHESIS.value,
                    section_ids=[section.section_id],
                    priority=i,
                    config={"content_dependency": content_deps, "resolved_dependencies": resolved},
                    core_question=section.section_name,
                    dependencies=resolved,
                )
                agents.append(agent)
                global_section_to_agent[section.section_id] = agent_id
            phase = ExecutionPhase(
                phase_id=f"phase_{counter}",
                phase_type=PhaseType.SYNTHESIS,
                agent_specs=agents,
                section_ids=[s.section_id for s in synthesis_sections],
                parallel=False,
                depends_on=depends_on,
            )
            phases.append(phase)
            counter += 1

        # Phase D: CALIBRATION
        _prior_agent_ids = sorted({spec.agent_id for p in phases for spec in p.agent_specs if spec.agent_id})
        cal_depends_on = [phases[-1].phase_id] if phases else []
        cal_phase = ExecutionPhase(
            phase_id=f"phase_{counter}",
            phase_type=PhaseType.CALIBRATION,
            agent_specs=[
                AgentSpec(
                    agent_id=f"phase_{counter}_calibrator",
                    agent_type="calibration",
                    section_ids=[],
                    priority=0,
                    config={
                        "content_dependency": [],
                        "resolved_dependencies": _prior_agent_ids,
                        "category": "calibration",
                    },
                    core_question="统一全报告数据口径，消除数值和叙述矛盾",
                ),
            ],
            section_ids=[],
            parallel=False,
            depends_on=cal_depends_on,
        )
        phases.append(cal_phase)
        counter += 1

        # Phase E: REPORT
        depends_on = [phases[-1].phase_id] if phases else []
        phases.append(self._create_report_phase(f"phase_{counter}", task_structure, topic,
                                                  depends_on=depends_on))
        return phases

    def plan_forensic(self, task_structure, intent, topic):
        """Public entry point for forensic phase orchestration."""
        phases = self._orchestrate_forensic_phases(task_structure, intent, topic)
        content_lock_rules = self._generate_content_lock_rules(task_structure, phases)
        total_agents = sum(len(p.agent_specs) for p in phases)
        return ExecutionPlan(
            plan_id=f"forensic_{task_structure.task_id}",
            task_structure=task_structure,
            phases=phases,
            content_lock_rules=content_lock_rules,
            total_agents=total_agents,
        )
