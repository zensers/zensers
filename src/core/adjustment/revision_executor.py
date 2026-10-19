from __future__ import annotations
import json
import copy
import logging
import time
from dataclasses import dataclass, field, replace as dataclasses_replace
from typing import Awaitable, Dict, List, Optional, Any, Callable, Tuple
from uuid import uuid4

from .revision_types import (
    Report, ReportTree, RevisionAction, RevisionPlan,
    ExecContext, ExecFailure, PlanExecutionResult, ExecutionResult,
    ExecutionFlow, ExecutionStatus, PreviewDiff, ValidationResult,
    RollbackResult, StructuralImpact, RestoreResult, SnapshotId, SnapshotType,
    Choice, RevisionOpType, AnalysisResult, TaskStatus, RevisionTask,
    RevisionAbortedException, RevisionSession, RevisionCommit,
    SectionRef, RefType, RevisionTarget, LocationStrategy,
)
from .content_manipulator import ContentManipulator
from .section_locator_v2 import SectionLocatorV2
from .section_renumberer import SectionRenumberer
from .cross_reference_fixer import CrossReferenceFixer
from .snapshot_manager import SnapshotManager
from .structural_analyzer import StructuralAnalyzer, DuplicateDetector
from .atomic_operations.factory import AtomicOperationFactory
from .atomic_operations.base import AtomicRevision
# 延迟导入: dialogue/intent 模块在 adjustment 包初始化完成后导入
# from ..dialogue.revision_sub_state_machine import (
#     RevisionConversationContainer, ClarificationLoop, RevisionSubState,
# )
# from ..intent.revision_intent_analyzer import RevisionIntentAnalyzer
# from ..intent.revision_plan_generator import RevisionPlanGenerator, IdRemapper
from .report_lock_manager import ReportLockManager
from .version_manager import VersionManager
from .revision_intent_mapper import RevisionIntentMapper
from .cascade_update_analyzer import CascadeUpdateAnalyzer
# 注意: dialogue 模块的导入延迟到 __init__ 中,
# 避免 adjustment 包初始化时的循环导入

logger = logging.getLogger(__name__)

# RevisionSubState 由 handle_feedback 及其子方法使用,
# 在方法内部延迟导入以避免循环依赖


class ProgressNotifier:
    def __init__(self, prompt_user_callback: Optional[Callable[[str], Awaitable[str]]] = None):
        self._prompt_user_callback = prompt_user_callback

    def notify(self, session_id: str, current: int, total: int, message: str) -> None:
        logger.info(f"[{session_id}] {current}/{total}: {message}")

    async def prompt_user(self, question: str) -> str:
        if self._prompt_user_callback:
            return await self._prompt_user_callback(question)
        logger.warning(f"ProgressNotifier.prompt_user called but no callback provided. Question: {question}")
        return "y"


class LLMOptimizer:
    CACHE_TTL_SECONDS = 60
    MAX_CACHE_SIZE = 100

    def __init__(self):
        self._cache: Dict[str, Tuple[float, Any]] = {}

    def get_or_call(self, prompt: str, llm_func: Callable[[str], Any]) -> Any:
        now = time.time()
        cached = self._cache.get(prompt)
        if cached is not None and (now - cached[0]) < self.CACHE_TTL_SECONDS:
            return cached[1]

        result = llm_func(prompt)
        if len(self._cache) >= self.MAX_CACHE_SIZE:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][0])
            del self._cache[oldest_key]
        self._cache[prompt] = (now, result)
        return result

    def truncate_context(
        self, messages: List[Dict[str, str]], max_tokens: int
    ) -> List[Dict[str, str]]:
        total = sum(len(m.get("content", "") or "") for m in messages)
        result = list(messages)
        while total > max_tokens and len(result) > 1:
            removed = result.pop(0)
            total -= len(removed.get("content", "") or "")
        return result


class RevisionExecutor:
    def __init__(
        self,
        lock_manager: ReportLockManager,
        notifier: Optional[ProgressNotifier] = None,
    ):
        self._lock_manager = lock_manager
        self._notifier = notifier or ProgressNotifier()

        self._structural_analyzer = StructuralAnalyzer()
        # 延迟导入: 避免循环导入 (adjustment → dialogue → intent → adjustment)
        from ..intent.revision_intent_analyzer import RevisionIntentAnalyzer
        from ..intent.revision_plan_generator import RevisionPlanGenerator
        self._intent_analyzer = RevisionIntentAnalyzer()
        self._plan_generator = RevisionPlanGenerator()
        self._content_manipulator = ContentManipulator()
        self._section_locator_v2 = SectionLocatorV2()
        self._section_renumberer = SectionRenumberer()
        self._cross_ref_fixer = CrossReferenceFixer()
        self.snapshot_manager = SnapshotManager.get_instance()
        self._operation_factory = AtomicOperationFactory()
        self._version_manager = VersionManager.get_instance()
        self._intent_mapper = RevisionIntentMapper()
        self._cascade_analyzer = CascadeUpdateAnalyzer()

    LIGHTWEIGHT_OPTYPES = {
        RevisionOpType.UPDATE_TITLE,
        RevisionOpType.REPLACE_TEXT,
        RevisionOpType.CHANGE_CASE,
        RevisionOpType.FIX_PUNCTUATION,
    }

    def _is_lightweight(self, analysis: AnalysisResult) -> bool:
        if not analysis or not analysis.intents:
            return False
        if len(analysis.intents) != 1:
            return False
        return analysis.intents[0].action_type in self.LIGHTWEIGHT_OPTYPES

    async def handle_feedback(
        self, user_message: str, report: Report
    ) -> ExecutionFlow:
        report_id = getattr(report, "id", str(uuid4()))
        flow = ExecutionFlow()

        # ========== Phase 1: 意图分析 + 澄清（无锁）==========
        try:
            analysis = await self._intent_analyzer.analyze(user_message, report)

            # 轻轨判定（无锁，不碰 begin_session）
            if (self._is_lightweight(analysis)
                    and not analysis.needs_clarification
                    and analysis.intents[0].confidence >= 0.5):
                flow.status = ExecutionStatus.LIGHTWEIGHT_DONE
                flow.tasks = [
                    RevisionTask(id=str(uuid4()), action=action)
                    for action in analysis.intents
                ]
                return flow

            if analysis.needs_clarification:
                if analysis.confidence < 0.3:
                    return await self._handle_unknown_intent(flow, user_message, report)
                original_intents = list(analysis.intents)
                analysis = await self._run_clarification_loop(analysis, report)
                if analysis is None:
                    flow.status = ExecutionStatus.ABORTED
                    return flow
                if not analysis.intents:
                    if original_intents:
                        analysis = AnalysisResult(
                            intents=original_intents,
                            needs_clarification=False,
                            is_uncertain=True,
                            confidence=0.3,
                        )
                    else:
                        flow.status = ExecutionStatus.CLARIFICATION_FAILED
                        flow.error = "Could not understand the revision request after clarification"
                        return flow

                if analysis.is_uncertain and analysis.confidence < 0.3:
                    return await self._handle_unknown_intent(flow, user_message, report)

                if (self._is_lightweight(analysis)
                        and not analysis.needs_clarification
                        and analysis.intents[0].confidence >= 0.5):
                    flow.status = ExecutionStatus.LIGHTWEIGHT_DONE
                    flow.tasks = [
                        RevisionTask(id=str(uuid4()), action=action)
                        for action in analysis.intents
                    ]
                    return flow

            if not analysis.intents:
                return await self._handle_empty_intents(flow)

        except RevisionAbortedException:
            flow.status = ExecutionStatus.ABORTED
            return flow
        except Exception as e:
            logger.exception(f"Revision execution failed: {e}")
            flow.status = ExecutionStatus.FAILED
            flow.error = str(e)
            return flow

        # ========== Phase 2: 树构建 + 规划（有锁）==========
        async with self._lock_manager.acquire_lock(report_id):
            from ..dialogue.revision_sub_state_machine import RevisionConversationContainer
            container = RevisionConversationContainer()
            container.enter_revision_mode(user_message=user_message)
            flow._conversation_container = container
            try:
                self._structural_analyzer.begin_session(report)
                report_tree = self._structural_analyzer.analyze_tree(report)

                _CREATION_OPTYPES = {
                    RevisionOpType.ADD, RevisionOpType.SPLIT,
                    RevisionOpType.ADD_ELEMENT,
                }
                _GLOBAL_OPTYPES = {
                    RevisionOpType.REPLACE_TEXT, RevisionOpType.UPDATE_TITLE,
                    RevisionOpType.CHANGE_CASE, RevisionOpType.FIX_PUNCTUATION,
                    RevisionOpType.TRANSLATE, RevisionOpType.STYLE, RevisionOpType.DEDUP,
                }

                all_targets_found = True
                for action in analysis.intents:
                    if action.action_type in _CREATION_OPTYPES:
                        insert_ids = []
                        if action.source and not action.source.section_refs:
                            src_ids = await self._section_locator_v2.resolve_to_ids(
                                action.source, report_tree)
                            if src_ids:
                                action.source.section_refs = [
                                    SectionRef(uuid=uid, ref_type=RefType.UUID)
                                    for uid in src_ids
                                ]
                                insert_ids = src_ids
                        if not insert_ids and action.source and action.source.section_refs:
                            insert_ids = [ref.uuid for ref in action.source.section_refs if ref.uuid]
                        if not insert_ids and analysis.suggested_section:
                            insert_ids = await self._locate_suggested_section(
                                analysis.suggested_section, report_tree)
                        if insert_ids:
                            action.target.section_refs = [
                                SectionRef(uuid=uid, ref_type=RefType.UUID)
                                for uid in insert_ids
                            ]
                            action.parameters["parent_id"] = insert_ids[0]
                        else:
                            if report_tree.root:
                                action.parameters["parent_id"] = report_tree.root.id
                                action.parameters["position"] = "last"
                            else:
                                all_targets_found = False
                                logger.warning(
                                    f"Could not locate parent for creation action {action.action_id}: "
                                    f"'{action.target.raw_text}'"
                                )
                        continue

                    if action.action_type in _GLOBAL_OPTYPES:
                        continue

                    if action.target and not action.target.section_refs:
                        ids = await self._section_locator_v2.resolve_to_ids(
                            action.target, report_tree)
                        if ids:
                            action.target.section_refs = [
                                SectionRef(uuid=uid, ref_type=RefType.UUID)
                                for uid in ids
                            ]
                        elif analysis.suggested_section:
                            ids = await self._locate_suggested_section(
                                analysis.suggested_section, report_tree)
                            if ids:
                                action.target.section_refs = [
                                    SectionRef(uuid=uid, ref_type=RefType.UUID)
                                    for uid in ids
                                ]
                            else:
                                all_targets_found = False
                                logger.warning(
                                    f"Could not locate target for action {action.action_id}: "
                                    f"'{action.target.raw_text}'"
                                )
                        else:
                            all_targets_found = False
                    elif action.target and action.target.section_refs:
                        valid_refs = [r for r in action.target.section_refs
                                      if r.ref_type == RefType.UUID and r.uuid]
                        if not valid_refs:
                            ids = await self._section_locator_v2.resolve_to_ids(
                                action.target, report_tree)
                            if ids:
                                action.target.section_refs = [
                                    SectionRef(uuid=uid, ref_type=RefType.UUID)
                                    for uid in ids
                                ]
                            elif analysis.suggested_section:
                                ids = await self._locate_suggested_section(
                                    analysis.suggested_section, report_tree)
                                if ids:
                                    action.target.section_refs = [
                                        SectionRef(uuid=uid, ref_type=RefType.UUID)
                                        for uid in ids
                                    ]
                                else:
                                    all_targets_found = False
                            else:
                                all_targets_found = False

                if not all_targets_found:
                    locatable = [a for a in analysis.intents
                                 if a.action_type in _CREATION_OPTYPES
                                 or a.action_type in _GLOBAL_OPTYPES
                                 or (a.target and a.target.section_refs
                                     and any(r.ref_type == RefType.UUID and r.uuid
                                             and r.uuid in report_tree.node_map
                                             for r in a.target.section_refs))]
                    if not locatable:
                        flow.status = ExecutionStatus.CLARIFICATION_FAILED
                        flow.error = "Could not locate target section(s). Please use exact section names."
                        return flow
                    removed = len(analysis.intents) - len(locatable)
                    if removed > 0:
                        logger.warning(
                            f"Removed {removed} action(s) with unresolvable targets, "
                            f"proceeding with {len(locatable)} locatable action(s)"
                        )
                    analysis.intents = locatable

                plan = self._plan_generator.generate(analysis.intents, report_tree)

                for action in plan.actions:
                    if action.action_type == RevisionOpType.ADD:
                        if not action.content:
                            action.content = "## " + action.target.raw_text + "\n\n（待补充内容）"
                        if "title" not in action.parameters or not action.parameters["title"]:
                            action.parameters["title"] = action.target.raw_text

                flow.plan = plan
                flow._report_version = report.version
            finally:
                self._structural_analyzer.end_session()

        # 计划确认（无锁）
        plan = await self._confirm_plan_interactive(flow.plan)
        if not plan:
            flow.status = ExecutionStatus.ABORTED
            return flow

        # ========== Phase 3: 快照 + 执行（有锁）==========
        async with self._lock_manager.acquire_lock(report_id):
            from ..dialogue.revision_sub_state_machine import RevisionConversationContainer
            container = flow._conversation_container or RevisionConversationContainer()
            if not flow._conversation_container:
                container.enter_revision_mode(user_message=user_message)
                flow._conversation_container = container
            try:
                self._structural_analyzer.begin_session(report)

                if report.version != flow._report_version:
                    flow.status = ExecutionStatus.FAILED
                    flow.error = "Report was modified by another session. Please retry."
                    return flow

                report_tree = self._structural_analyzer.analyze_tree(report)
                snapshot_id = await self.snapshot_manager.create_snapshot(
                    report, SnapshotType.FULL,
                )
                flow.snapshot_id = snapshot_id
                flow.tasks = [
                    RevisionTask(id=str(uuid4()), action=action)
                    for action in plan.actions
                ]
                flow.current_index = 0
                flow._report_version = report.version
                while flow.current_index < len(flow.tasks):
                    flow = await self._execute_current(flow, report, report_tree)
                    if flow.status == ExecutionStatus.FAILED and flow.error:
                        break
                if flow.status == ExecutionStatus.PREVIEW_READY and report_tree:
                    self._post_process(report_tree, flow)
                elif flow.status == ExecutionStatus.PENDING:
                    any_failed = any(t.status == TaskStatus.FAILED for t in flow.tasks)
                    all_confirming = all(t.status == TaskStatus.CONFIRMING for t in flow.tasks)
                    if any_failed:
                        flow.status = ExecutionStatus.FAILED
                        flow.error = next((t.error for t in flow.tasks if t.error), "Task failed")
                    elif all_confirming:
                        flow.status = ExecutionStatus.PREVIEW_READY
                return flow
            finally:
                self._structural_analyzer.end_session()

    async def _locate_suggested_section(
        self, suggested: str, report_tree: ReportTree,
    ) -> List[str]:
        if not suggested:
            return []
        fallback_target = RevisionTarget(
            raw_text=suggested, section_refs=[],
            location_strategy=LocationStrategy.KEYWORD, is_ambiguous=False,
        )
        return await self._section_locator_v2.resolve_to_ids(fallback_target, report_tree)

    async def _handle_empty_intents(
        self, flow: ExecutionFlow,
    ) -> ExecutionFlow:
        flow.status = ExecutionStatus.CLARIFICATION_FAILED
        flow.error = "No revision intents could be identified from the message"
        return flow

    async def _handle_unknown_intent(
        self, flow: ExecutionFlow, user_message: str = "", report: Any = None,
    ) -> ExecutionFlow:
        from ..intelligent_routing_adapter import IntelligentRoutingAdapter
        try:
            adapter = IntelligentRoutingAdapter()
            topic = getattr(report, "topic", None) or ""
            aspects = []
            if report and hasattr(report, "sections"):
                aspects = [getattr(s, "title", str(s)) for s in (report.sections or [])]
            if not aspects:
                aspects = ["市场分析", "竞争格局"]
            requirement = {"topic": topic, "aspects": aspects}
            routing_result = adapter.analyze(
                user_request=user_message or "revise report",
                requirement=requirement,
                topic=topic or None,
            )
            flow.status = ExecutionStatus.FULL_RESEARCH_NEEDED
            flow._routing_result = routing_result
            flow.error = "Intent routed to full research pipeline (low confidence or clarification exhausted)"
            logger.info(
                f"[BP1-FIX] Routed unknown intent to IntelligentRoutingAdapter: "
                f"{len(routing_result.execution_plan.phases)} phases, "
                f"{routing_result.execution_plan.total_agents} agents"
            )
        except Exception as e:
            logger.exception(f"[BP1-FIX] IntelligentRoutingAdapter failed: {e}")
            flow.status = ExecutionStatus.FULL_RESEARCH_NEEDED
            flow.error = f"Intent not understood with sufficient confidence (routing fallback: {e})"
        return flow

    async def _run_clarification_loop(
        self, analysis: AnalysisResult, report: Report,
    ) -> Optional[AnalysisResult]:
        from ..dialogue.revision_sub_state_machine import ClarificationLoop
        loop = ClarificationLoop(
            analyzer=self._intent_analyzer,
            report=report,
            ask_user_callback=self._notifier.prompt_user,
        )
        try:
            return await loop.run(analysis)
        except RevisionAbortedException:
            return None

    async def _handle_execution_failure(
        self, result: PlanExecutionResult, report_tree: ReportTree,
        snapshot_id: SnapshotId, flow: ExecutionFlow,
        report: Any = None,
    ) -> ExecutionFlow:
        flow.status = ExecutionStatus.FAILED
        flow.error = result.error or (result.exec_failure.error if result.exec_failure else "Unknown error")
        flow.partial_results = result.sub_results

        rollback = await self._rollback_executed_ops(
            result, report_tree, snapshot_id, report,
        )
        if rollback.success:
            flow.status = ExecutionStatus.ROLLED_BACK

        return flow

    def _format_operation_prompt(self, plan: RevisionPlan) -> str:
        lines = [f"Revision plan ({len(plan.actions)} operations):"]
        for i, action in enumerate(plan.actions):
            target_text = action.target.raw_text or (
                action.target.section_refs[0].raw_text
                if action.target.section_refs else "?"
            )
            lines.append(f"  {i + 1}. [{action.action_type.value}] {target_text}")
        return "\n".join(lines)

    def _parse_choice(self, response: str) -> Choice:
        r = response.strip().lower()
        if r in ("y", "yes", "confirm", "accept", "ok", "okay", "sure", "确认", "可以", "好"):
            return Choice.ACCEPT
        if r in ("n", "no", "reject", "cancel", "stop", "不要", "取消", "不行"):
            return Choice.REJECT
        if r in ("modify", "change", "edit", "改", "修改", "调整"):
            return Choice.MODIFY
        return Choice.REJECT

    async def _ask_operation_confirmation(self, description: str) -> Choice:
        valid_choices = {Choice.ACCEPT, Choice.REJECT, Choice.MODIFY, Choice.ABORT}
        for attempt in range(3):
            question = f"{description}\n\nConfirm execution? (y/n/modify/abort): "
            response = await self._notifier.prompt_user(question)
            choice = self._parse_choice(response)
            if choice in valid_choices:
                return choice
            logger.info(f"Unrecognized input '{response.strip().lower()}' for plan confirmation, retry {attempt+1}/3")
        return Choice.REJECT

    async def _ask_operation_modification(
        self, plan: RevisionPlan,
    ) -> Optional[RevisionPlan]:
        question = "Describe how to modify the plan: "
        response = await self._notifier.prompt_user(question)
        if not response or response.strip().lower() in ("cancel", "abort", "取消"):
            return None
        return plan

    async def _confirm_plan_interactive(
        self, plan: RevisionPlan, report_tree: Optional[ReportTree] = None,
    ) -> Optional[RevisionPlan]:
        confirmed_actions = []
        for i, action in enumerate(plan.actions):
            question = f"[{i+1}/{len(plan.actions)}] {action.action_type.value}: {action.target.raw_text}"
            choice = await self._ask_operation_confirmation(question)
            if choice == Choice.ACCEPT:
                confirmed_actions.append(action)
            elif choice == Choice.REJECT:
                continue
            elif choice == Choice.ABORT:
                return None
        if not confirmed_actions:
            return None
        return RevisionPlan(
            plan_id=plan.plan_id,
            actions=confirmed_actions,
            dependency_graph=plan.dependency_graph,
            id_remap_table=plan.id_remap_table,
            conflicts=plan.conflicts,
        )

    def _generate_preview(
        self, report: Report, pre_tree: ReportTree,
        post_tree: ReportTree, plan: RevisionPlan,
    ) -> PreviewDiff:
        impact = self._structural_analyzer.analyze_plan_impact(plan, report)
        return PreviewDiff(
            before=pre_tree,
            after=post_tree,
            structural_changes=impact,
            commit_message=f"Revision: {len(plan.actions)} operation(s)",
        )

    async def _handle_preview_response(
        self, flow: ExecutionFlow, choice: Choice, report: Report = None,
    ) -> ExecutionFlow:
        if choice == Choice.ACCEPT:
            try:
                commit = await self._version_manager.commit_revision(
                    report=report,
                    plan=flow.plan,
                    snapshot_id=flow.snapshot_id,
                    message=flow.preview.commit_message if flow.preview else "",
                )
                if commit:
                    flow.status = ExecutionStatus.COMPLETED
            except Exception as e:
                logger.exception(f"Commit failed: {e}")
                flow.status = ExecutionStatus.FAILED
                flow.error = str(e)
        elif choice == Choice.REJECT:
            if flow.snapshot_id:
                restored = await self.snapshot_manager.restore_snapshot(flow.snapshot_id)
                if restored is not None:
                    if report is not None and hasattr(report, "restore_from_dict"):
                        report.restore_from_dict(restored)
                    flow.status = ExecutionStatus.ROLLED_BACK
                else:
                    flow.status = ExecutionStatus.FAILED
            else:
                flow.status = ExecutionStatus.ROLLED_BACK
        else:
            flow.status = ExecutionStatus.ABORTED
        return flow

    async def _rollback_executed_ops(
        self, result: PlanExecutionResult, report_tree: ReportTree,
        snapshot_id: SnapshotId, report: Any = None,
    ) -> RollbackResult:
        try:
            if snapshot_id:
                restored = await self.snapshot_manager.restore_snapshot(snapshot_id)
                if restored is not None:
                    # 将快照数据写回 adapter/session
                    if report is not None and hasattr(report, "restore_from_dict"):
                        report.restore_from_dict(restored)
                    return RollbackResult(success=True)
            return RollbackResult(
                success=False, error="No snapshot available for rollback",
            )
        except Exception as e:
            logger.exception(f"Rollback failed: {e}")
            return RollbackResult(success=False, error=str(e))

    def _build_preview_context(
        self, pre_tree: ReportTree, post_tree: ReportTree, plan: RevisionPlan,
    ) -> PreviewDiff:
        return PreviewDiff(
            before=pre_tree,
            after=post_tree,
            commit_message=f"Revision: {len(plan.actions)} operation(s)",
        )

    async def _execute_plan_with_progress(
        self, plan: RevisionPlan, report_tree: ReportTree,
        snapshot_id: SnapshotId, session_id: str,
    ) -> PlanExecutionResult:
        context = ExecContext(
            report=None,
            report_tree=report_tree,
            snapshot_manager=self.snapshot_manager,
            snapshot_id=snapshot_id,
            user_id="",
            session_id=session_id,
            content_manipulator=self._content_manipulator,
            progress_callback=lambda c, t, m: self._notifier.notify(
                session_id, c, t, m,
            ),
            operation_index=0,
            total_operations=len(plan.actions),
        )

        operations = self._operation_factory.create_from_plan(plan)
        sub_results: List[ExecutionResult] = []

        for idx, operation in enumerate(operations):
            context.operation_index = idx
            self._notifier.notify(
                session_id, idx + 1, len(operations),
                f"Executing: {operation.action.action_type.value}",
            )
            try:
                # 前置校验: validate 失败则提前返回，避免无效操作走到 execute
                validation = await operation.validate(context)
                if not validation.valid:
                    err_msg = validation.errors[0] if validation.errors else f"Validation failed for operation {idx}"
                    return PlanExecutionResult(
                        success=False,
                        error=err_msg,
                        exec_failure=ExecFailure(
                            failed_index=idx,
                            error=err_msg,
                        ),
                        sub_results=sub_results,
                    )
                result = await operation.execute(context)
                sub_results.append(result)
                if not result.success:
                    return PlanExecutionResult(
                        success=False,
                        error=result.error,
                        exec_failure=ExecFailure(
                            failed_index=idx,
                            error=result.error or "Operation failed",
                            result=result,
                        ),
                        sub_results=sub_results,
                    )
            except Exception as e:
                logger.exception(f"Operation {idx} failed: {e}")
                return PlanExecutionResult(
                    success=False,
                    error=str(e),
                    exec_failure=ExecFailure(failed_index=idx, error=str(e)),
                    sub_results=sub_results,
                )

        return PlanExecutionResult(success=True, sub_results=sub_results)

    def _post_process(self, report_tree: ReportTree, flow: Optional[ExecutionFlow] = None) -> None:
        old_numbers: Dict[str, str] = {}
        for nid, node in report_tree.node_map.items():
            num = getattr(node.section, "number", None)
            if num:
                old_numbers[nid] = str(num)

        self._section_renumberer.renumber(report_tree)

        renumbering_map: Dict[str, str] = {}
        for nid, old_num in old_numbers.items():
            node = report_tree.node_map.get(nid)
            if node:
                new_num = getattr(node.section, "number", None)
                if new_num and str(new_num) != old_num:
                    renumbering_map[old_num] = str(new_num)

        self._cross_ref_fixer.fix_references(report_tree, renumbering_map)

        all_section_titles = [
            getattr(node.section, "title", "")
            for node in report_tree.node_map.values()
        ]
        modified_titles = []
        for nid in old_numbers:
            node = report_tree.node_map.get(nid)
            if node and node.section:
                title = getattr(node.section, "title", "")
                if title:
                    modified_titles.append(title)
        if modified_titles and all_section_titles:
            cascade_impact = self._cascade_analyzer.analyze_cascade_impact(
                target_sections=modified_titles,
                all_sections=all_section_titles,
            )
            if cascade_impact.affected_sections:
                logger.info(
                    f"[CascadeAnalysis] {len(cascade_impact.affected_sections)} sections "
                    f"may need consistency updates: {cascade_impact.affected_sections}"
                )
                if flow is not None:
                    flow.impacts = StructuralImpact(
                        affected_sections=cascade_impact.affected_sections,
                        toc_changes=[],
                        cross_refs_broken=[],
                        data_refs_affected=cascade_impact.affected_sections,
                    )

    # ---- 任务列表执行模型: 新方法 (V3) ----

    async def continue_revision(
        self, flow: ExecutionFlow, choice: Choice, user_message: str,
        report: Report, report_tree: ReportTree,
    ) -> ExecutionFlow:
        """继续修订: 处理用户对当前任务的确认/选择, 然后执行下一任务"""
        self._structural_analyzer.begin_session(report)
        try:
            if report.version != flow._report_version:
                flow.status = ExecutionStatus.FAILED
                flow.error = "Report was modified by another session. Please retry."
                return flow

            task = flow.tasks[flow.current_index]

            if choice == Choice.ACCEPT:
                task.status = TaskStatus.CONFIRMED
                flow.current_index += 1
                flow._report_version = report.version
                return await self._execute_current(flow, report, report_tree)

            elif choice == Choice.SKIP:
                report_tree = await self._rollback_and_rebuild(task, report, report_tree)
                task.status = TaskStatus.ROLLED_BACK
                flow.current_index += 1
                flow._report_version = report.version
                return await self._execute_current(flow, report, report_tree)

            elif choice == Choice.MODIFY:
                report_tree = await self._rollback_and_rebuild(task, report, report_tree)
                analysis = await self._intent_analyzer.analyze(user_message, report)

                if analysis.intents:
                    try:
                        from ..intent_types import IntentType, TaskComplexity
                        action = analysis.intents[0]
                        _INTENT_TYPE_MAP = {
                            RevisionOpType.MODIFY: IntentType.FIX,
                            RevisionOpType.DELETE: IntentType.FIX,
                            RevisionOpType.ADD: IntentType.RESEARCH,
                            RevisionOpType.REPLACE_TEXT: IntentType.FIX,
                            RevisionOpType.UPDATE_TITLE: IntentType.FIX,
                            RevisionOpType.FIX_PUNCTUATION: IntentType.FIX,
                            RevisionOpType.CHANGE_CASE: IntentType.FIX,
                            RevisionOpType.STYLE: IntentType.FIX,
                            RevisionOpType.REVIEW: IntentType.EVALUATION,
                        }
                        primary = _INTENT_TYPE_MAP.get(action.action_type, IntentType.FIX)
                        n = len(analysis.intents)
                        if n > 2:
                            complexity = TaskComplexity.COMPLEX
                        elif n == 1:
                            complexity = (TaskComplexity.TRIVIAL
                                          if action.action_type in self.LIGHTWEIGHT_OPTYPES
                                          else TaskComplexity.SINGLE)
                        else:
                            complexity = TaskComplexity.SINGLE
                        _revision_intent, route_decision = self._intent_mapper.map(
                            primary_intent=primary,
                            complexity=complexity,
                            user_input=user_message,
                        )
                        flow._route_decision = route_decision
                    except Exception as e:
                        logger.debug(f"IntentMapper integration skipped: {e}")
                    if analysis and analysis.intents:
                        task.action = analysis.intents[0]
                        task.status = TaskStatus.PENDING
                        ids = await self._section_locator_v2.resolve_to_ids(
                            task.action.target, report_tree)
                        if ids:
                            task.action.target.section_refs = [
                                SectionRef(uuid=uid, ref_type=RefType.UUID) for uid in ids
                            ]
                flow._report_version = report.version
                return await self._execute_current(flow, report, report_tree)

            elif choice == Choice.INSERT:
                flow._report_version = report.version
                return await self._insert_and_continue(flow, user_message, report, report_tree)

            elif choice == Choice.REMOVE:
                flow._report_version = report.version
                return await self._remove_and_continue(flow, user_message, report)

            elif choice == Choice.ABORT:
                for i in range(flow.current_index, -1, -1):
                    t = flow.tasks[i]
                    report_tree = await self._rollback_and_rebuild(t, report, report_tree)
                flow.tasks.clear()
                flow.status = ExecutionStatus.ABORTED
                flow._report_version = report.version
                return flow

            return flow
        finally:
            self._structural_analyzer.end_session()

    async def _execute_current(
        self, flow: ExecutionFlow, report: Report, report_tree: ReportTree,
    ) -> ExecutionFlow:
        """执行当前索引指向的下一个待办 Task (每次最多执行一个)"""
        if flow.current_index >= len(flow.tasks):
            flow.status = ExecutionStatus.PREVIEW_READY
            flow.preview = self._generate_merged_preview(flow)
            return flow

        task = flow.tasks[flow.current_index]

        if task.status == TaskStatus.CONFIRMED:
            flow.current_index += 1
            return flow

        # REVIEW: 只读, 不需要 checkpoint
        if task.action.action_type == RevisionOpType.REVIEW:
            ids = await self._section_locator_v2.resolve_to_ids(
                task.action.target, report_tree)
            if not ids:
                task.status = TaskStatus.FAILED
                task.error = "Target not found"
                flow.current_index += 1
                return flow
            node = report_tree.find(ids[0]) if ids else None
            content = node.section.content if node else ""
            task.status = TaskStatus.CONFIRMING
            task.preview = PreviewDiff(before=content)
            return flow

        # 非 REVIEW: checkpoint → 定位 → 执行 → sync → 版本号更新
        cid = await self.snapshot_manager.create_snapshot(report, SnapshotType.FULL)
        task.checkpoint_id = cid

        _CREATION_OPTYPES_EXEC = {
            RevisionOpType.ADD, RevisionOpType.SPLIT,
            RevisionOpType.ADD_ELEMENT,
        }
        _GLOBAL_OPTYPES_EXEC = {
            RevisionOpType.REPLACE_TEXT, RevisionOpType.UPDATE_TITLE,
            RevisionOpType.CHANGE_CASE, RevisionOpType.FIX_PUNCTUATION,
            RevisionOpType.TRANSLATE, RevisionOpType.STYLE, RevisionOpType.DEDUP,
        }
        if task.action.action_type not in _CREATION_OPTYPES_EXEC and task.action.action_type not in _GLOBAL_OPTYPES_EXEC:
            has_valid_refs = (task.action.target and task.action.target.section_refs
                              and any(r.ref_type == RefType.UUID and r.uuid
                                      and r.uuid in report_tree.node_map
                                      for r in task.action.target.section_refs))
            if not has_valid_refs:
                ids = await self._section_locator_v2.resolve_to_ids(
                    task.action.target, report_tree)
                if not ids:
                    task.status = TaskStatus.FAILED
                    task.error = f"Could not locate target: {task.action.target.raw_text}"
                    flow.current_index += 1
                    flow.error = task.error
                    return flow

        operation = self._operation_factory.create(task.action)
        if operation is None:
            task.status = TaskStatus.CONFIRMING
            task.preview = PreviewDiff(
                before="(global operation)",
                after=task.action.content or task.action.parameters.get("old_text", ""),
            )
            flow.current_index += 1
            all_confirming = all(
                t.status == TaskStatus.CONFIRMING
                for t in flow.tasks[:flow.current_index]
            )
            if all_confirming and flow.current_index >= len(flow.tasks):
                flow.status = ExecutionStatus.PREVIEW_READY
            return flow

        result = await operation.execute(ExecContext(
            report=None, report_tree=report_tree,
            snapshot_manager=self.snapshot_manager,
        ))
        if not result.success:
            await self._rollback_and_rebuild(task, report, report_tree)
            task.status = TaskStatus.FAILED
            task.error = result.error
            flow.current_index += 1
            flow.error = result.error or f"Task {task.id} failed"
            all_failed = all(
                t.status in (TaskStatus.FAILED, TaskStatus.ROLLED_BACK)
                for t in flow.tasks[:flow.current_index]
            )
            if all_failed:
                flow.status = ExecutionStatus.FAILED
            return flow

        # 同步回 adapter + 更新版本号
        report_tree.sync_to_report(report)
        flow._report_version = report.version
        task.status = TaskStatus.CONFIRMING
        task.result = result
        task.preview = result.diff or PreviewDiff()
        flow.current_index += 1
        all_confirming = all(
            t.status == TaskStatus.CONFIRMING
            for t in flow.tasks[:flow.current_index]
        )
        if all_confirming and flow.current_index >= len(flow.tasks):
            flow.status = ExecutionStatus.PREVIEW_READY
        return flow

    async def _rollback_and_rebuild(
        self, task: RevisionTask, report: Report, report_tree: ReportTree,
    ) -> ReportTree:
        """回滚指定任务, 同步 session, 重建 ReportTree"""
        if not task.checkpoint_id:
            return report_tree
        restored = await self.snapshot_manager.restore_snapshot(task.checkpoint_id)
        if restored is not None and hasattr(report, "restore_from_dict"):
            report.restore_from_dict(restored)
            return self._structural_analyzer.analyze_tree(report)
        return report_tree

    def _generate_merged_preview(self, flow: ExecutionFlow) -> PreviewDiff:
        """将所有已确认 task 的 preview 合并为最终预览"""
        before_sections = []
        after_sections = []
        ops = []
        for task in flow.tasks:
            if task.preview:
                if task.preview.before:
                    before_sections.append(task.preview.before)
                if task.preview.after:
                    after_sections.append(task.preview.after)
                ops.append(f"[{task.action.action_type.value}] {task.action.target.raw_text}")
        commit_msg = "; ".join(ops) if ops else "Revision completed"
        return PreviewDiff(
            before=before_sections if before_sections else None,
            after=after_sections if after_sections else None,
            commit_message=commit_msg,
        )

    def _format_task_message(self, task: RevisionTask) -> str:
        """生成任务确认提示"""
        op_names = {
            RevisionOpType.MODIFY: "修改",
            RevisionOpType.DELETE: "删除",
            RevisionOpType.ADD: "增加",
            RevisionOpType.REVIEW: "查看",
            RevisionOpType.COPY: "复制",
            RevisionOpType.MERGE: "合并",
            RevisionOpType.SPLIT: "拆分",
            RevisionOpType.SWAP: "交换",
            RevisionOpType.REORDER: "重排",
            RevisionOpType.STYLE: "样式",
        }
        op_name = op_names.get(task.action.action_type, str(task.action.action_type.value))
        target = task.action.target.raw_text
        msg = f"任务: {op_name} 「{target}」\n\n"
        if task.preview:
            if task.action.action_type == RevisionOpType.REVIEW:
                msg += f"内容预览:\n{task.preview.before}\n\n"
            else:
                if task.preview.before:
                    before_str = str(task.preview.before)
                    msg += f"修改前: {before_str[:200]}...\n" if len(before_str) > 200 else f"修改前: {before_str}\n"
                if task.preview.after:
                    after_str = str(task.preview.after)
                    msg += f"修改后: {after_str[:200]}...\n" if len(after_str) > 200 else f"修改后: {after_str}\n"
        msg += "\n确认(y)/跳过(s)/修改(m)/加(ins)/删(del)/取消(abort):"
        return msg

    async def _insert_and_continue(
        self, flow: ExecutionFlow, user_message: str,
        report: Report, report_tree: ReportTree,
    ) -> ExecutionFlow:
        """在当前任务之后插入新任务"""
        analysis = await self._intent_analyzer.analyze(user_message, report)
        if not analysis.intents:
            return flow
        new_task = RevisionTask(
            id=str(uuid4()), action=analysis.intents[0], status=TaskStatus.PENDING,
        )
        insert_pos = flow.current_index + 1
        flow.tasks.insert(insert_pos, new_task)
        return flow

    async def _remove_and_continue(
        self, flow: ExecutionFlow, user_message: str,
        report: Report, report_tree: ReportTree = None,
    ) -> ExecutionFlow:
        """从 Plan 中移除指定任务"""
        analysis = await self._intent_analyzer.analyze(user_message, report)
        if not analysis or not analysis.intents:
            return flow
        target_text = analysis.intents[0].target.raw_text
        if not target_text:
            return flow
        for i in range(flow.current_index + 1, len(flow.tasks)):
            if target_text in flow.tasks[i].action.target.raw_text:
                flow.tasks.pop(i)
                break
        return flow


def parse_choice_extended(user_input: str) -> Choice:
    """扩展的 Choice 解析, 支持任务确认场景"""
    r = user_input.strip().lower()
    if r in ("y", "yes", "ok", "确认", "好", "可以"):
        return Choice.ACCEPT
    if r in ("s", "skip", "跳过", "算了", "下一个"):
        return Choice.SKIP
    if r in ("m", "mod", "改", "修改", "重做"):
        return Choice.MODIFY
    if r in ("ins", "加", "增加", "插入", "添加"):
        return Choice.INSERT
    if r in ("del", "删", "删除", "去掉", "移除"):
        return Choice.REMOVE
    if r in ("reorder", "重排", "排序", "移"):
        return Choice.REORDER
    if r in ("abort", "取消", "不修了", "退出"):
        return Choice.ABORT
    if r in ("commit", "提交", "完成"):
        return Choice.COMMIT
    if "加" in r and "删" not in r:
        return Choice.INSERT
    if "删" in r or "去" in r:
        return Choice.REMOVE
    if "改" in r or "重做" in r:
        return Choice.MODIFY
    return Choice.ACCEPT
