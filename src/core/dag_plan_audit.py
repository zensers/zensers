"""Pre-execution audit for the task DAG produced by intelligent routing."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

from .dynamic_orchestrator import PhaseType


@dataclass(frozen=True)
class DAGIssue:
    code: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DAGAuditResult:
    passed: bool
    issues: List[DAGIssue] = field(default_factory=list)
    revision_feedback: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "issues": [
                {"code": issue.code, "message": issue.message, "details": issue.details}
                for issue in self.issues
            ],
            "revision_feedback": list(self.revision_feedback),
        }


class DAGPlanAuditor:
    """Validate an ``ExecutionPlan`` before any Agent is dispatched.

    The auditor owns only plan invariants.  It does not execute Agents,
    inspect evidence, or evaluate report content.
    """

    def audit(self, execution_plan: Any) -> DAGAuditResult:
        issues: List[DAGIssue] = []
        structure = getattr(execution_plan, "task_structure", None)
        sections = list(getattr(structure, "sections", []) or [])
        section_ids = [str(getattr(section, "section_id", "") or "").strip() for section in sections]
        known_sections = {sid for sid in section_ids if sid}

        duplicates = sorted({sid for sid in section_ids if sid and section_ids.count(sid) > 1})
        if duplicates:
            issues.append(DAGIssue(
                "duplicate_section",
                "DAG contains duplicate section IDs.",
                {"section_ids": duplicates},
            ))

        phase_list = list(getattr(execution_plan, "phases", []) or [])
        phase_ids = [str(getattr(phase, "phase_id", "") or "").strip() for phase in phase_list]
        duplicate_phases = sorted({phase_id for phase_id in phase_ids if phase_id and phase_ids.count(phase_id) > 1})
        if duplicate_phases:
            issues.append(DAGIssue(
                "duplicate_phase",
                "DAG contains duplicate phase IDs.",
                {"phase_ids": duplicate_phases},
            ))
        phase_index = {phase_id: index for index, phase_id in enumerate(phase_ids) if phase_id}
        section_phase: Dict[str, int] = {}
        section_phase_occurrences: Dict[str, List[int]] = {}
        for index, phase in enumerate(phase_list):
            for section_id in getattr(phase, "section_ids", []) or []:
                section_id = str(section_id or "").strip()
                if section_id:
                    if section_id not in known_sections:
                        issues.append(DAGIssue(
                            "unknown_phase_section",
                            f"Phase {phase.phase_id} contains unknown section {section_id}.",
                            {"phase_id": phase.phase_id, "section_id": section_id},
                        ))
                    section_phase_occurrences.setdefault(section_id, []).append(index)
                    # A section's final phase is the point at which its
                    # output becomes available to dependent sections.  This
                    # matters for the legitimate data-collection -> analysis
                    # two-stage route.
                    section_phase[section_id] = index

            for dependency in getattr(phase, "depends_on", []) or []:
                dependency = str(dependency or "").strip()
                if dependency not in phase_index:
                    issues.append(DAGIssue(
                        "unknown_phase_dependency",
                        f"Phase {phase.phase_id} depends on an unknown phase {dependency}.",
                        {"phase_id": phase.phase_id, "dependency": dependency},
                    ))
                elif phase_index[dependency] >= index:
                    issues.append(DAGIssue(
                        "phase_order",
                        f"Phase {phase.phase_id} depends on a later or same phase {dependency}.",
                        {"phase_id": phase.phase_id, "dependency": dependency},
                    ))

        for section_id, occurrences in section_phase_occurrences.items():
            unique_occurrences = sorted(set(occurrences))
            if len(unique_occurrences) <= 1:
                continue
            phase_types = [phase_list[index].phase_type for index in unique_occurrences]
            allowed_two_stage = (
                len(unique_occurrences) == 2
                and phase_types[0] in (PhaseType.SURVEY, PhaseType.DATA_COLLECTION)
                and phase_types[1] == PhaseType.ANALYSIS
            )
            if not allowed_two_stage:
                issues.append(DAGIssue(
                    "duplicate_phase_section",
                    f"Section {section_id} is assigned to incompatible multiple phases.",
                    {
                        "section_id": section_id,
                        "phases": [phase_list[index].phase_id for index in unique_occurrences],
                        "phase_types": [getattr(item, "value", str(item)) for item in phase_types],
                    },
                ))
        graph: Dict[str, List[str]] = {sid: [] for sid in known_sections}
        for section in sections:
            target = str(getattr(section, "section_id", "") or "").strip()
            for source in getattr(section, "content_dependency", []) or []:
                source = str(source or "").strip()
                if source not in known_sections:
                    issues.append(DAGIssue(
                        "unknown_section_dependency",
                        f"Section {target} depends on unknown section {source}.",
                        {"section_id": target, "dependency": source},
                    ))
                    continue
                if source == target:
                    issues.append(DAGIssue(
                        "dependency_cycle",
                        f"Section {target} depends on itself.",
                        {"section_id": target},
                    ))
                    continue
                graph.setdefault(source, []).append(target)
                source_phase = section_phase.get(source)
                target_phase = section_phase.get(target)
                if source_phase is not None and target_phase is not None and source_phase >= target_phase:
                    issues.append(DAGIssue(
                        "dependency_order",
                        f"Section {target} is scheduled before its dependency {source}.",
                        {
                            "section_id": target,
                            "dependency": source,
                            "dependency_phase": source_phase,
                            "section_phase": target_phase,
                        },
                    ))

        unassigned_sections = sorted(known_sections - set(section_phase))
        if unassigned_sections:
            issues.append(DAGIssue(
                "unassigned_section",
                "Some sections are not assigned to any execution phase.",
                {"section_ids": unassigned_sections},
            ))

        if self._has_cycle(graph):
            issues.append(DAGIssue("dependency_cycle", "DAG contains a section dependency cycle."))

        # The compatibility plan must never carry a section ID as an Agent
        # dependency.  This catches the exact failure that otherwise reaches
        # ExecutionScheduler too late.
        try:
            decomposition_plan = execution_plan.to_decomposition_plan()
        except Exception as exc:
            issues.append(DAGIssue(
                "plan_conversion",
                f"Execution plan cannot be converted for execution: {exc}",
            ))
        else:
            all_specs = [
                spec
                for phase_specs in (getattr(decomposition_plan, "phases", {}) or {}).values()
                for spec in phase_specs
            ]
            agent_index = {str(spec.agent_id): index for index, spec in enumerate(all_specs)}
            duplicate_agents = sorted({agent_id for agent_id in agent_index if sum(
                1 for spec in all_specs if str(spec.agent_id) == agent_id
            ) > 1})
            if duplicate_agents:
                issues.append(DAGIssue(
                    "duplicate_agent",
                    "DAG contains duplicate Agent IDs.",
                    {"agent_ids": duplicate_agents},
                ))

            agent_graph: Dict[str, List[str]] = {agent_id: [] for agent_id in agent_index}
            for spec in all_specs:
                agent_id = str(spec.agent_id)
                for dependency in getattr(spec, "dependencies", []) or []:
                    dependency = str(dependency).strip()
                    if dependency not in agent_index:
                        issues.append(DAGIssue(
                            "unresolved_agent_dependency",
                            f"AgentSpec {agent_id} depends on an unknown Agent ID {dependency}.",
                            {"agent_id": agent_id, "dependency": dependency},
                        ))
                        continue
                    if agent_index[dependency] >= agent_index[agent_id]:
                        issues.append(DAGIssue(
                            "agent_dependency_order",
                            f"AgentSpec {agent_id} depends on a later or same Agent {dependency}.",
                            {
                                "agent_id": agent_id,
                                "dependency": dependency,
                                "dependency_index": agent_index[dependency],
                                "agent_index": agent_index[agent_id],
                            },
                        ))
                    agent_graph.setdefault(dependency, []).append(agent_id)
            if self._has_cycle(agent_graph):
                issues.append(DAGIssue(
                    "agent_dependency_cycle",
                    "Agent dependency graph contains a cycle.",
                ))

        feedback = [self._feedback(issue) for issue in issues]
        return DAGAuditResult(passed=not issues, issues=issues, revision_feedback=feedback)

    def revise_order(self, execution_plan: Any, audit: DAGAuditResult) -> bool:
        """Apply one safe local repair for an acyclic ordering problem.

        This is deliberately narrower than a planner: unknown references,
        duplicate nodes, and cycles are returned to intelligent routing for
        semantic revision instead of being guessed here.
        """
        repairable = {"dependency_order", "unresolved_agent_dependency"}
        if not audit.issues or any(issue.code not in repairable for issue in audit.issues):
            return False

        structure = getattr(execution_plan, "task_structure", None)
        sections = list(getattr(structure, "sections", []) or [])
        section_ids = [str(getattr(section, "section_id", "") or "").strip() for section in sections]
        if not sections or any(not section_id for section_id in section_ids):
            return False
        known = set(section_ids)
        edges: Dict[str, List[str]] = {section_id: [] for section_id in known}
        indegree: Dict[str, int] = {section_id: 0 for section_id in known}
        original_index = {section_id: index for index, section_id in enumerate(section_ids)}
        for section in sections:
            target = str(getattr(section, "section_id", "") or "").strip()
            for source in getattr(section, "content_dependency", []) or []:
                source = str(source or "").strip()
                if source not in known or source == target:
                    return False
                if target not in edges[source]:
                    edges[source].append(target)
                    indegree[target] += 1

        ordered_ids: List[str] = []
        layers: List[List[str]] = []
        ready = sorted(
            [section_id for section_id, degree in indegree.items() if degree == 0],
            key=original_index.__getitem__,
        )
        while ready:
            layer = list(ready)
            layers.append(layer)
            ordered_ids.extend(layer)
            next_ready: List[str] = []
            for source in layer:
                for target in edges[source]:
                    indegree[target] -= 1
                    if indegree[target] == 0:
                        next_ready.append(target)
            ready = sorted(next_ready, key=original_index.__getitem__)

        if len(ordered_ids) != len(section_ids):
            return False

        by_id = {section_id: section for section_id, section in zip(section_ids, sections)}
        structure.sections = [by_id[section_id] for section_id in ordered_ids]
        structure.parallel_groups = layers
        return True

    def document(
        self,
        execution_plan: Any,
        audit: DAGAuditResult,
        review_history: List[DAGAuditResult] | None = None,
    ) -> Dict[str, Any]:
        """Return a stable, inspectable DAG document for routing diagnostics."""
        phases = []
        for phase in getattr(execution_plan, "phases", []) or []:
            phases.append({
                "phase_id": str(getattr(phase, "phase_id", "")),
                "phase_type": getattr(getattr(phase, "phase_type", None), "value", ""),
                "section_ids": list(getattr(phase, "section_ids", []) or []),
                "depends_on": list(getattr(phase, "depends_on", []) or []),
                "agents": [
                    {
                        "agent_id": str(getattr(spec, "agent_id", "")),
                        "section_ids": list(getattr(spec, "section_ids", []) or []),
                        "dependencies": list(getattr(spec, "dependencies", []) or []),
                    }
                    for spec in (getattr(phase, "agent_specs", []) or [])
                ],
            })
        structure = getattr(execution_plan, "task_structure", None)
        sections = [
            {
                "section_id": str(getattr(section, "section_id", "")),
                "title": str(getattr(section, "section_name", "")),
                "content_dependency": list(getattr(section, "content_dependency", []) or []),
            }
            for section in (getattr(structure, "sections", []) or [])
        ]
        return {
            "document_type": "intelligent_routing_dag",
            "sections": sections,
            "phases": phases,
            "audit": audit.to_dict(),
            "review_history": [item.to_dict() for item in (review_history or [])],
        }

    @staticmethod
    def _has_cycle(graph: Dict[str, List[str]]) -> bool:
        visiting: Set[str] = set()
        visited: Set[str] = set()

        def visit(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            if any(visit(child) for child in graph.get(node, [])):
                return True
            visiting.remove(node)
            visited.add(node)
            return False

        return any(visit(node) for node in graph)

    @staticmethod
    def _feedback(issue: DAGIssue) -> str:
        if issue.code == "dependency_order":
            return (
                f"请将上游章节 {issue.details.get('dependency')} 调整到 "
                f"下游章节 {issue.details.get('section_id')} 之前。"
            )
        if issue.code == "unresolved_agent_dependency":
            return (
                f"请重新拆解任务 {issue.details.get('agent_id')}，将依赖转换为当前计划中的实际 Agent ID。"
            )
        if issue.code == "agent_dependency_order":
            return (
                f"请将 Agent {issue.details.get('dependency')} 调整到 "
                f"Agent {issue.details.get('agent_id')} 之前。"
            )
        if issue.code == "unassigned_section":
            return "请为每个章节分配数据收集、分析或汇总执行阶段。"
        if issue.code == "dependency_cycle":
            return "请消除任务依赖循环，确保 DAG 可以按顺序执行。"
        if issue.code == "unknown_section_dependency":
            return "请补充依赖章节，或删除不存在的章节依赖。"
        if issue.code == "phase_order":
            return "请调整阶段顺序，使每个阶段只依赖之前已经完成的阶段。"
        if issue.code == "unknown_phase_dependency":
            return "请修订阶段依赖，确保依赖的阶段存在于当前任务计划中。"
        return issue.message
