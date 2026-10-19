from __future__ import annotations
from uuid import uuid4
from typing import Dict, List, Optional, Set, Tuple
from collections import deque

from ..adjustment.revision_types import (
    RevisionAction, RevisionPlan, ReportTree, RevisionOpType,
    Conflict, ConflictType, ImpactAnalysis, PlanConflictError,
    SectionRef, RefType, SectionNode,
)


class IdRemapper:
    def remap(
        self,
        plan: RevisionPlan,
        current_tree: ReportTree,
        executed_indices: Optional[List[int]] = None,
    ) -> RevisionPlan:
        executed_indices = executed_indices or []
        remap_table: Dict[str, str] = {}

        for i, action in enumerate(plan.actions):
            if i in executed_indices:
                continue
            for ref in action.target.section_refs:
                resolved = self._resolve_ref(ref, current_tree)
                if resolved and resolved != ref.uuid:
                    remap_table[ref.uuid] = resolved
                    ref.uuid = resolved
            if action.source:
                for ref in action.source.section_refs:
                    resolved = self._resolve_ref(ref, current_tree)
                    if resolved and resolved != ref.uuid:
                        remap_table[ref.uuid] = resolved
                        ref.uuid = resolved

        merged = {**plan.id_remap_table, **remap_table}
        return RevisionPlan(
            plan_id=plan.plan_id,
            actions=plan.actions,
            dependency_graph=plan.dependency_graph,
            id_remap_table=merged,
            conflicts=plan.conflicts,
            snapshot_required=plan.snapshot_required,
            estimated_impact=plan.estimated_impact,
        )

    def _resolve_ref(self, ref: SectionRef, tree: ReportTree) -> Optional[str]:
        if ref.ref_type == RefType.UUID:
            node = tree.find(ref.uuid)
            if node is not None:
                return node.id
            return None
        elif ref.ref_type == RefType.NUMBER and ref.number:
            node = tree.find_by_number(ref.number)
            if node is not None:
                return node.id
            return None
        elif ref.ref_type == RefType.INDEX and ref.parent_id and ref.index is not None:
            node = tree.find_by_index(ref.parent_id, ref.index)
            if node is not None:
                return node.id
            return None
        return None


class RevisionPlanGenerator:
    def __init__(self):
        self.id_remapper = IdRemapper()

    def generate(
        self, actions: List[RevisionAction], report_tree: ReportTree
    ) -> RevisionPlan:
        dag = self.build_dependency_graph(actions)

        conflicts = self.detect_conflicts(actions)
        fatal_conflict_types = {
            ConflictType.CIRCULAR_DEPENDENCY,
            ConflictType.SAME_TARGET_MODIFY_DELETE,
        }
        fatal = [c for c in conflicts if c.type in fatal_conflict_types]
        if fatal:
            raise PlanConflictError(
                "Fatal conflicts detected in revision plan", conflicts=fatal
            )

        execution_order = self.optimize_execution_order(dag)

        ordered_actions: List[RevisionAction] = []
        action_map = {a.action_id: a for a in actions}
        seen: Set[str] = set()
        for action_id in execution_order:
            if action_id in action_map and action_id not in seen:
                ordered_actions.append(action_map[action_id])
                seen.add(action_id)

        for action in actions:
            if action.action_id not in seen:
                ordered_actions.append(action)
                seen.add(action.action_id)

        snapshot_required = any(
            a.action_type
            in {
                RevisionOpType.MODIFY,
                RevisionOpType.DELETE,
                RevisionOpType.MERGE,
                RevisionOpType.SPLIT,
                RevisionOpType.SWAP,
                RevisionOpType.REORDER,
                RevisionOpType.DEDUP,
            }
            for a in ordered_actions
        )

        plan = RevisionPlan(
            plan_id=str(uuid4()),
            actions=ordered_actions,
            dependency_graph=dag,
            id_remap_table={},
            conflicts=conflicts,
            snapshot_required=snapshot_required,
            estimated_impact=ImpactAnalysis(
                affected_sections=list(
                    {
                        ref.uuid
                        for a in ordered_actions
                        for ref in a.target.section_refs
                    }
                ),
                risk_level="medium" if snapshot_required else "low",
            ),
        )

        plan = self.resolve_id_references(plan, report_tree)
        return plan

    def build_dependency_graph(
        self, actions: List[RevisionAction]
    ) -> Dict[str, List[str]]:
        dag: Dict[str, List[str]] = {}
        action_map = {a.action_id: a for a in actions}

        for action in actions:
            dag[action.action_id] = []

        for action_a in actions:
            for action_b in actions:
                if action_a.action_id == action_b.action_id:
                    continue
                if self._has_dependency(action_a, action_b, action_map):
                    dag[action_a.action_id].append(action_b.action_id)

        return dag

    def _has_dependency(
        self,
        from_action: RevisionAction,
        to_action: RevisionAction,
        action_map: Dict[str, RevisionAction],
    ) -> bool:
        from_targets = {
            ref.uuid for ref in from_action.target.section_refs
        }
        to_targets = {
            ref.uuid for ref in to_action.target.section_refs
        }
        if from_targets & to_targets:
            if from_action.action_type in {
                RevisionOpType.MODIFY,
                RevisionOpType.DELETE,
            } and to_action.action_type in {
                RevisionOpType.ADD,
                RevisionOpType.COPY,
                RevisionOpType.MERGE,
            }:
                return True
            if from_action.action_type == RevisionOpType.REORDER:
                return True
        return False

    def resolve_id_references(
        self,
        plan: RevisionPlan,
        report_tree: ReportTree,
        executed_indices: Optional[List[int]] = None,
    ) -> RevisionPlan:
        return self.id_remapper.remap(plan, report_tree, executed_indices)

    def optimize_execution_order(
        self, dag: Dict[str, List[str]]
    ) -> List[str]:
        in_degree: Dict[str, int] = {node: 0 for node in dag}
        adjacency: Dict[str, List[str]] = {node: [] for node in dag}

        for node, deps in dag.items():
            for dep in deps:
                if dep in in_degree:
                    in_degree[dep] += 1
                adjacency[node].append(dep)

        queue: deque[str] = deque()
        for node, degree in in_degree.items():
            if degree == 0:
                queue.append(node)

        result: List[str] = []
        while queue:
            node = queue.popleft()
            result.append(node)
            for successor in adjacency[node]:
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)

        remaining = [n for n in dag if n not in result]
        result.extend(remaining)
        return result

    def detect_conflicts(
        self, actions: List[RevisionAction]
    ) -> List[Conflict]:
        conflicts: List[Conflict] = []

        conflicts.extend(self._detect_same_target_conflicts(actions))
        conflicts.extend(self._detect_circular_dependency_conflicts(actions))
        conflicts.extend(self._detect_order_sensitive_conflicts(actions))
        conflicts.extend(self._detect_resource_contention_conflicts(actions))

        return conflicts

    def _detect_same_target_conflicts(
        self, actions: List[RevisionAction]
    ) -> List[Conflict]:
        conflicts: List[Conflict] = []
        modify_delete: Dict[str, List[RevisionAction]] = {}

        for action in actions:
            for ref in action.target.section_refs:
                if ref.uuid not in modify_delete:
                    modify_delete[ref.uuid] = []
                modify_delete[ref.uuid].append(action)

        for uuid, ref_actions in modify_delete.items():
            types = {a.action_type for a in ref_actions}
            has_modify = RevisionOpType.MODIFY in types
            has_delete = RevisionOpType.DELETE in types
            if has_modify and has_delete:
                conflicts.append(
                    Conflict(
                        type=ConflictType.SAME_TARGET_MODIFY_DELETE,
                        description=f"Section {uuid} has both MODIFY and DELETE operations",
                        involved_action_ids=[a.action_id for a in ref_actions],
                    )
                )

        return conflicts

    def _detect_circular_dependency_conflicts(
        self, actions: List[RevisionAction]
    ) -> List[Conflict]:
        conflicts: List[Conflict] = []
        dag = self.build_dependency_graph(actions)

        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def _dfs(node: str, path: List[str]) -> Optional[List[str]]:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            for neighbor in dag.get(node, []):
                if neighbor not in visited:
                    result = _dfs(neighbor, path)
                    if result is not None:
                        return result
                elif neighbor in rec_stack:
                    cycle_start = path.index(neighbor)
                    return path[cycle_start:] + [neighbor]
            path.pop()
            rec_stack.discard(node)
            return None

        for node in dag:
            if node not in visited:
                cycle = _dfs(node, [])
                if cycle is not None:
                    conflicts.append(
                        Conflict(
                            type=ConflictType.CIRCULAR_DEPENDENCY,
                            description=f"Circular dependency detected: {' -> '.join(cycle)}",
                            involved_action_ids=cycle[:-1],
                        )
                    )

        return conflicts

    def _detect_order_sensitive_conflicts(
        self, actions: List[RevisionAction]
    ) -> List[Conflict]:
        conflicts: List[Conflict] = []
        reorder_actions = [
            a for a in actions
            if a.action_type == RevisionOpType.REORDER
        ]

        for ra in reorder_actions:
            other_ops = [
                a for a in actions
                if a.action_id != ra.action_id
                and a.target.section_refs
                and ra.target.section_refs
                and {ref.uuid for ref in a.target.section_refs}
                & {ref.uuid for ref in ra.target.section_refs}
            ]
            if other_ops:
                conflicts.append(
                    Conflict(
                        type=ConflictType.ORDER_SENSITIVE,
                        description=f"REORDER action {ra.action_id} overlaps with other operations",
                        involved_action_ids=[ra.action_id] + [o.action_id for o in other_ops],
                        resolution="Ensure REORDER executes after other modifications",
                    )
                )

        return conflicts

    def _detect_resource_contention_conflicts(
        self, actions: List[RevisionAction]
    ) -> List[Conflict]:
        conflicts: List[Conflict] = []
        target_map: Dict[str, List[RevisionAction]] = {}

        for action in actions:
            for ref in action.target.section_refs:
                if ref.uuid not in target_map:
                    target_map[ref.uuid] = []
                target_map[ref.uuid].append(action)

        for uuid, ref_actions in target_map.items():
            if len(ref_actions) > 1:
                non_add = [
                    a for a in ref_actions
                    if a.action_type not in {RevisionOpType.ADD, RevisionOpType.COPY}
                ]
                if len(non_add) > 1:
                    conflicts.append(
                        Conflict(
                            type=ConflictType.RESOURCE_CONTENTION,
                            description=f"Multiple non-additive operations on section {uuid}",
                            involved_action_ids=[a.action_id for a in non_add],
                            resolution="Consider merging operations or sequential execution",
                        )
                    )

        return conflicts
