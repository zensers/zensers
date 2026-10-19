# -*- coding: utf-8 -*-
"""
Research Executor
=================

Execute research tasks in the background and push progress updates.

Usage example:
    # Start a background task in the API endpoint
    executor = ResearchExecutor()
    asyncio.create_task(executor.execute(session_id, plan))
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.session_manager import SessionManager

from src.core.progress_streamer import (
    ProgressStreamer,
    TaskPhase,
    start_phase,
    complete_phase,
    update_progress,
    complete_task,
    fail_task,
)
from src.config.settings import settings
from src.core.i18n import set_language, get_language


def _section_display_name(section: Any) -> str:
    """Return a comparable display name from a framework section."""
    if isinstance(section, str):
        return section
    if not isinstance(section, dict):
        return str(section or "")
    name = section.get("name", section.get("title", section.get("id", "")))
    if isinstance(name, dict):
        return str(name.get("zh") or name.get("en") or next(iter(name.values()), ""))
    return str(name or section.get("id", ""))


def _section_match_score(requested: str, candidate: str) -> int:
    """Match template detail names to requested aspects without widening scope."""
    req = requested.strip().lower()
    cand = candidate.strip().lower()
    if not req or not cand:
        return 0
    if req == cand:
        return 100
    aliases = {
        "市场定义": ("industry overview", "market definition", "industry definition"),
        "市场规模": ("market size", "market size & growth"),
        "增长驱动": ("growth drivers", "growth driver", "development trends"),
        "市场细分": ("market segmentation", "market segments", "market sub"),
        "竞争格局": ("competitive landscape", "competition", "competitive"),
        "政策环境": ("policy", "regulation"),
        "技术趋势": ("technology", "technology trends"),
        "产业链分析": ("value chain", "industry chain", "supply chain"),
        "风险分析": ("risk", "risk analysis"),
    }
    for alias, candidates in aliases.items():
        if alias in req and any(token in cand for token in candidates):
            return 80
    if len(req) >= 4 and (req in cand or cand in req):
        return 60
    return 0


def _select_section_details(section_details: Any, requested_aspects: Any) -> list:
    """Align framework metadata to selected aspects and never widen the scope."""
    details = list(section_details or []) if isinstance(section_details, (list, tuple)) else []
    requested = []
    for aspect in requested_aspects or []:
        name = _section_display_name(aspect).strip()
        if name and name not in requested:
            requested.append(name)
    if not requested:
        return details

    unused = list(details)
    selected = []
    # IndustryResearchStrategy numbers data-bearing sections independently of
    # synthesis/dependent sections.  Keep the same numbering here; using the
    # raw selected-list index would make a leading "summary" shift every
    # downstream section_id by one.
    dependent_names = {
        "summary", "conclusion", "executive_summary", "key_insights",
        "research_summary", "research_conclusion", "synthesis",
        "key_findings", "insights", "synthesis_analysis", "core_findings",
        "key_discoveries", "strategic_intent", "strategic intent",
        "战略意图", "战略意图推断", "执行摘要", "摘要", "结论",
    }
    normal_index = 0
    synthesis_index = 0
    for index, name in enumerate(requested):
        best_index = -1
        best_score = 0
        for candidate_index, detail in enumerate(unused):
            score = _section_match_score(name, _section_display_name(detail))
            if score > best_score:
                best_index, best_score = candidate_index, score
        if best_index >= 0:
            raw = unused.pop(best_index)
            normalized = dict(raw) if isinstance(raw, dict) else {}
            # Runtime section identity must match the AgentSpec identity. Keep
            # the catalog id only as metadata; never let it diverge from the
            # stable positional section id used by aggregation and caching.
            catalog_id = normalized.get("id") or normalized.get("section_id", "")
            is_dependent = name.strip().lower() in dependent_names
            if is_dependent:
                stable_id = f"synthesis_{synthesis_index}"
                synthesis_index += 1
            else:
                stable_id = f"section_{normal_index}"
                normal_index += 1
            if catalog_id:
                normalized["template_id"] = catalog_id
            normalized["id"] = stable_id
            normalized["section_id"] = stable_id
            normalized["name"] = name
            selected.append(normalized)
        else:
            is_dependent = name.strip().lower() in dependent_names
            if is_dependent:
                stable_id = f"synthesis_{synthesis_index}"
                synthesis_index += 1
            else:
                stable_id = f"section_{normal_index}"
                normal_index += 1
            selected.append({
                "id": stable_id,
                "section_id": stable_id,
                "name": name,
                "content": name,
            })
    return selected

logger = logging.getLogger(__name__)


def _complete_orchestration_phase(session_id: str) -> None:
    """Close the executor-owned orchestration phase before agent execution."""
    complete_phase(session_id, "orchestrating")


def _get_container_km():
    try:
        from src.core.container import get_container
        from src.core.memory import KnowledgeManager
        container = get_container()
        if container.has(KnowledgeManager):
            return container.resolve(KnowledgeManager)
    except Exception:
        pass
    return None


def _publish_report_context(session_id: str, session: Any, **kwargs) -> None:
    """Persist and publish the public report snapshot from executor paths."""
    try:
        from src.core.report_context import update_report_context
        update_report_context(session_id, session, **kwargs)
    except Exception as exc:
        logger.warning("Report context update failed for %s: %s", session_id, exc)


def _mark_persisted_result_status(
    task_id: str,
    status: str,
) -> None:
    """Close the incremental result record when executor-level control fires."""
    try:
        from src.core.storage import ResearchResultStore, ResearchStatus

        status_enum = ResearchStatus(status)
        store = ResearchResultStore(storage_path="data")
        if store.load_metadata(task_id) is not None:
            store.update_result(task_id, status=status_enum)
    except Exception as exc:
        logger.warning("Failed to persist terminal status for %s: %s", task_id, exc)


class ResearchExecutor:
    """
    Research task background executor
    
    Responsible for executing research tasks and pushing progress via ProgressStreamer.
    """
    
    def __init__(self):
        # Do NOT store orchestrator as instance variable — local variable in execute() instead.
        # Prevents concurrent session interference via get_executor() global singleton.
        self._main_tasks: Dict[str, asyncio.Task] = {}
        self._tasks_lock = asyncio.Lock()
        # Injection/replanning is scoped per research session. A process-wide
        # boolean would make task A block task B during parallel execution.
        self._inject_in_progress: set[str] = set()
    
    async def _check_paused(
        self,
        session_id: str,
        session_manager: "SessionManager",
    ) -> bool:
        """
        Check if task is paused or cancelled.
        Uses CancelManager's Condition-based wait (no polling).

        Returns:
            True = should continue, False = should stop
        """
        from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager
        cm = get_cancel_manager()

        if cm.is_cancelled(session_id):
            logger.info(f"Task cancelled: {session_id}")
            return False

        if cm.is_paused(session_id):
            logger.info(f"Task paused at _check_paused, waiting for resume/cancel: {session_id}")
            r = await cm.wait_for_resume_or_cancel(session_id)
            if r == "cancelled":
                logger.info(f"Task cancelled while paused: {session_id}")
                return False

        return True

    async def _process_pending_injects(
        self,
        session_id: str,
        session_manager: "SessionManager",
        orchestrator_timeout: int = None,
    ) -> None:
        if session_id in self._inject_in_progress:
            return
        self._inject_in_progress.add(session_id)
        try:
            for _ in range(3):
                session = session_manager.get(session_id)
                if not session:
                    return
                pending = list(session.get("_pending_section_injects", []))
                session["_pending_section_injects"] = []
                if not pending:
                    return

                context = session.get("research_context", {})
                framework = context.get("framework", {})
                sections = list(framework.get("sections", []))
                section_reqs = session.get("section_requirements", {})

                add_ops = [p for p in pending if p["op"] == "add_section"]
                cancel_ops = [p for p in pending if p["op"] == "cancel_section"]
                merge_ops = [p for p in pending if p["op"] == "merge_requirement"]
                revise_ops = [p for p in pending if p["op"] == "revise"]

                if not add_ops and not cancel_ops and not merge_ops and not revise_ops:
                    return

                if add_ops or merge_ops:
                    from src.core.orchestrator.orchestrator import ResearchOrchestrator
                    from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter
                    adapter = IntelligentRoutingAdapter(use_llm=True, fallback_to_keyword=True)
                    original_result = session.get("research_result", {})
                    original_task_id = original_result.get("task_id", "")
                    cache_path = None
                    for candidate in [original_task_id, session_id]:
                        if candidate:
                            p = Path("data") / candidate / "research_result_cache.json"
                            if p.exists():
                                cache_path = p
                                break
                    if not cache_path:
                        cache_path = Path("data") / session_id / "research_result_cache.json"
                    completed = []
                    if cache_path.exists():
                        try:
                            data = json.loads(cache_path.read_text(encoding="utf-8"))
                            completed = [s.get("title", s.get("id", "")) for s in data.get("sections", [])]
                        except Exception:
                            pass
                    routing_result = adapter.analyze_incremental(
                        user_request=f"Add: {[o['section_name'] for o in add_ops]}",
                        requirement={"topic": context.get("topic", ""), "aspects": sections},
                        completed_aspects=completed if completed else None,
                        topic=context.get("topic", ""),
                    )

                    new_section_names = [o["section_name"] for o in add_ops]
                    inject_aspects = new_section_names if new_section_names else sections

                    orch = ResearchOrchestrator(
                        use_intelligent_routing=True,
                        knowledge_manager=_get_container_km(),
                    )
                    try:
                        result = await orch.research(
                                user_input={
                                    "topic": context.get("topic", ""),
                                    "aspects": inject_aspects,
                                    "section_requirements": section_reqs,
                                },
                                output_type=framework.get("output_type", "industry_report"),
                                output_format=session.get('output_format', 'docx'),
                                custom_aspects=inject_aspects,
                                skip_phases=routing_result.skip_phases or None,
                        )
                        session = session_manager.get(session_id)
                        if session and result and result.status in ("completed", "completed_with_warnings"):
                            original = session.get("research_result", {})
                            original_report = original.get("report", {}) if isinstance(original.get("report"), dict) else {}
                            original_sections = original_report.get("sections", [])
                            inject_report = (getattr(result, 'report', None) or {}) if hasattr(result, 'report') else {}
                            inject_sections = inject_report.get("sections", []) if isinstance(inject_report, dict) else []

                            merged_sections = list(original_sections)
                            for s in inject_sections:
                                if s.get("id") not in [x.get("id") for x in merged_sections]:
                                    merged_sections.append(s)

                            merged_report = dict(original_report)
                            merged_report["sections"] = merged_sections

                            _original_status = original.get("status", "completed")
                            _inject_status = result.status
                            _merged_status = "completed_with_warnings" if (
                                _original_status == "completed_with_warnings" or _inject_status == "completed_with_warnings"
                            ) else "completed"
                            session["research_result"] = {
                                "task_id": original.get("task_id") or original_task_id,
                                "status": _merged_status,
                                "output_path": original.get("output_path", ""),
                                "document_path": original.get("document_path", ""),
                                "topic": result.topic,
                                "stages_completed": (original.get("stages_completed", 0) or 0) + (result.stages_completed or 0),
                                "report": merged_report,
                                "summary": result.summary,
                            }
                    except Exception as e:
                        logger.error(f"[{session_id}] Inject research failed: {e}")

                for op in revise_ops:
                    try:
                        from src.core.adjustment.revision_service import RevisionService
                        rs = RevisionService()
                        s = session_manager.get(session_id)
                        output_path = (s or {}).get("research_result", {}).get("output_path", "")
                        if output_path:
                            revision_result = await rs.revise_from_user_feedback(
                                document_path=output_path,
                                task_id=session_id,
                                section=op.get("section_name", ""),
                                adjustment=op.get("requirement", ""),
                                revision_type="addition",
                            )
                            # RevisionService writes a new versioned artifact.
                            # Persist that path immediately so preview, API
                            # responses, and subsequent revisions do not keep
                            # opening the initial HTML.
                            revised_path = getattr(revision_result, "document_path", None)
                            revision_succeeded = bool(getattr(revision_result, "success", False))
                            if isinstance(revision_result, dict):
                                revised_path = revision_result.get("document_path") or revision_result.get("output_path")
                                revision_succeeded = bool(revision_result.get("success"))
                            if revision_succeeded and revised_path:
                                current = session_manager.get(session_id)
                                if current is not None:
                                    research_result = dict(current.get("research_result") or {})
                                    research_result["output_path"] = str(revised_path)
                                    research_result["document_path"] = str(revised_path)
                                    current["research_result"] = research_result
                                    session_manager.update(session_id, {"research_result": research_result})
                    except Exception as e:
                        logger.error(f"[{session_id}] Revision failed for {op.get('section_name')}: {e}")
        finally:
            self._inject_in_progress.discard(session_id)

    async def execute(
        self,
        session_id: str,
        plan: Dict[str, Any],
        session_manager: "SessionManager",
    ) -> Dict[str, Any]:
        """
        Execute research task
        
        Args:
            session_id: Session ID
            plan: Research plan
            session_manager: SessionManager instance
            
        Returns:
            Execution result
        """
        session = session_manager.get(session_id)
        if not session:
            fail_task(session_id, "Session not found")
            return {"error": "Session not found"}

        run_id = f"run_{uuid.uuid4().hex[:12]}"
        from src.core.diagnostics.phase_manifest import PhaseManifestStore
        manifest = PhaseManifestStore(session_id, session_id, Path("data"), run_id)
        manifest.record("PHASE_START", phase="research_execution")
        
        # Set global language from plan/session for all downstream agents
        plan_language = plan.get("language") or session.get("language", "zh")
        set_language(plan_language)
        logger.info(f"ResearchExecutor: set global language to '{plan_language}' for session {session_id}")
        _publish_report_context(session_id, session, phase="researching")
        
        # 执行前检查暂停/取消
        if not await self._check_paused(session_id, session_manager):
            return {"status": "paused_or_cancelled", "message": "Task start blocked by pause/cancel"}
        
        try:
            # 初始化 Orchestrator（延迟导入避免循环依赖）
            # Use local variable, not instance var, to prevent concurrency issues
            # when get_executor() returns the same singleton for multiple sessions.
            from src.core.orchestrator.orchestrator import ResearchOrchestrator
            orchestrator = ResearchOrchestrator(
                use_intelligent_routing=True,
                knowledge_manager=_get_container_km(),
            )
            
            # 获取研究参数
            context = session.get("research_context", {})
            topic = context.get("topic", "")
            user_input = session.get("user_input", topic)
            framework = context.get("framework", {})

            # === Level D: User preference routing ===
            km = _get_container_km()
            cm = km.core_memory if km else None
            if cm:
                prefs = getattr(cm, 'user_profile', None)
                if prefs and prefs.focus_areas:
                    focus_areas_str = str(prefs.focus_areas)
                    FOCUS_KEYWORDS = [
                        (["政策", "法规", "监管"], "policy_analysis"),
                        (["技术", "研发", "创新"], "technology_assessment"),
                        (["财务", "估值", "盈利"], "financial_valuation"),
                        (["竞争", "格局", "份额"], "competitive_landscape"),
                        (["风险", "不确定性"], "risk_assessment"),
                    ]
                    try:
                        from src.methodologies.registry import get_aspect_map
                        supported_aspects = get_aspect_map()
                    except ImportError:
                        supported_aspects = {}
                    extra_aspects = []
                    for keywords, aspect_id in FOCUS_KEYWORDS:
                        if any(kw in focus_areas_str for kw in keywords):
                            if aspect_id in supported_aspects:
                                extra_aspects.append(aspect_id)
                    if extra_aspects:
                        sections = framework.get("sections", [])
                        for ea in extra_aspects:
                            if ea not in sections:
                                sections.append(ea)
                        framework["sections"] = sections

            output_type = session.get("output_type", framework.get("output_type", "industry_report"))
            
            # 初始化进度跟踪
            start_phase(session_id, "orchestrating", "Task Orchestration",
                        description="Orchestrating research task...")
            update_progress(session_id, 0.05, phase_id="orchestrating",
                            message=f"Starting research on 「{topic}」...")

            # Push agent message for orchestrator start (Issue 5)
            try:
                from src.core.session_streamer import SessionStreamer
                SessionStreamer.push_agent_message(session_id, {
                    "agent_id": "orchestrator",
                    "agent_name": "Research Orchestrator",
                    "action": "analyzing",
                    "content": f"Starting research on 「{topic}」...",
                })
            except ImportError:
                pass

            try:
                from src.core.progress_heartbeat import ProgressHeartbeat
                ProgressHeartbeat.start(session_id)
            except Exception:
                pass
            
            # === 检查是否有可跳过的已完成阶段 ===
            skip_phases = plan.get("skip_phases", [])
            if skip_phases:
                logger.info(f"Resuming with {len(skip_phases)} skip_phases: {skip_phases}")
            
            # === 从 session 中提取动态参数（/template 快速启动传入）===
            _section_details = plan.get("section_details") or session.get("section_details", [])
            # The plan is authoritative for selected scope. Do not let the
            # complete framework catalog silently widen a quick-start task.
            selected_aspects = (
                plan.get("aspects")
                or session.get("selected_sections")
                or framework.get("sections")
                or []
            )
            selected_aspects = [
                _section_display_name(aspect)
                for aspect in selected_aspects
                if _section_display_name(aspect).strip()
            ]
            _section_details = _select_section_details(_section_details, selected_aspects)
            user_input_dict: Dict[str, Any] = {
                "session_id": session_id,
                "topic": topic or user_input,
                "output_type": output_type,
                "aspects": selected_aspects,
                "sections_tree": plan.get("sections_tree"),
                "section_details": _section_details,
                "output_format": session.get("output_format", plan.get("output_format", "docx")),
                "_run_id": run_id,
            }
            # 从 session 读取动态参数（由 quick_start 存入）
            param_keys = ("region", "time_range", "depth", "company_name",
                          "market", "primary_company", "policy_name",
                          "quarter", "year", "call_date")
            for key in param_keys:
                if key in session:
                    user_input_dict[key] = session[key]
            # 如果有完整的 custom_params，合并进去
            custom_params = session.get("custom_params", {})
            if isinstance(custom_params, dict):
                for k, v in custom_params.items():
                    if k not in user_input_dict:
                        user_input_dict[k] = v

            # === Execute via Orchestrator (with pause monitoring) ===
            orchestrator_timeout = getattr(settings.agents, 'orchestrator_timeout', None)
            logger.info(f"Executing orchestrator (timeout={orchestrator_timeout or 'none'}s) for {session_id}")

            # The executor owns the initial orchestration phase.  Close it
            # before the orchestrator starts publishing execution progress so
            # the UI never presents both phases as active.
            _complete_orchestration_phase(session_id)

            from src.core.orchestrator.execution.coordinator.cancel_manager import (
                get_cancel_manager,
            )
            cm = get_cancel_manager()

            # 执行前取消/暂停检查
            session_id_inner = session_id

            async with self._tasks_lock:
                self._main_tasks[session_id] = asyncio.current_task()

            try:
                # 取消检查
                if cm.is_cancelled(session_id_inner):
                    logger.info(f"Cancel detected before execution: {session_id_inner}")
                    return {"status": "cancelled", "message": "Research cancelled before execution"}

                # 暂停检查
                if cm.is_paused(session_id_inner):
                    logger.info(f"Paused before execution: {session_id_inner}, waiting...")
                    pause_result = await cm.wait_for_resume_or_cancel(session_id_inner)
                    if pause_result == "cancelled":
                        return {"status": "cancelled", "message": "Research cancelled while paused"}

                orchestrator_result = await orchestrator.research(
                        user_input=user_input_dict,
                        interaction_mode=False,
                        output_type=output_type,
                        custom_aspects=selected_aspects,
                        output_format=session.get('output_format', 'docx'),
                        skip_phases=skip_phases or None,
                )
                manifest.record(
                    "PHASE_OUTPUT", phase="research_execution",
                    output_status=getattr(orchestrator_result, "status", ""),
                )
            finally:
                async with self._tasks_lock:
                    self._main_tasks.pop(session_id, None)
                try:
                    from src.core.progress_heartbeat import ProgressHeartbeat
                    ProgressHeartbeat.stop(session_id)
                except Exception:
                    pass
            
            # 转换结果为统一格式
            if orchestrator_result.status in ("completed", "completed_with_warnings"):
                result = {
                    "task_id": orchestrator_result.task_id,
                    "status": orchestrator_result.status,
                    "output_path": str(orchestrator_result.output_path) if orchestrator_result.output_path else "",
                    "document_path": str(orchestrator_result.document_path) if orchestrator_result.document_path else "",
                    "topic": orchestrator_result.topic,
                    "agents_used": orchestrator_result.agents_used,
                    "stages_completed": orchestrator_result.stages_completed,
                    "report": orchestrator_result.report,
                    "summary": orchestrator_result.summary,
                }

                if orchestrator_result.status == "completed_with_warnings":
                    result["quality_score"] = getattr(orchestrator_result, "quality_score", 0)
                    result["quality_issues"] = getattr(orchestrator_result, "quality_issues", [])
                    try:
                        from src.core.session_streamer import SessionStreamer
                        SessionStreamer.push_quality_result(session_id, {
                            "overall_score": result["quality_score"],
                            "overall_status": "warning",
                            "section_results": {},
                            "issues": result["quality_issues"],
                        })
                    except Exception:
                        pass

                # 保存结��到会话
                session["research_result"] = result
                session["status"] = orchestrator_result.status
                _publish_report_context(
                    session_id, session, phase="completed",
                    report_version_increment=True,
                )

                pre_inject_output_path = result.get("output_path", "")
                pre_inject_document_path = result.get("document_path", "")
                await self._process_pending_injects(session_id, session_manager)
                session = session_manager.get(session_id)
                if session and session.get("research_result"):
                    result = session["research_result"]

                state_machine = session.get("state_machine")
                if state_machine:
                    try:
                        from src.api.research_api import ConversationState
                        state_machine.transition(ConversationState.COMPLETED)
                    except Exception:
                        pass
                update_progress(session_id, 1.0, message="研究完成")

                # Push agent message for completion
                try:
                    from src.core.session_streamer import SessionStreamer
                    SessionStreamer.push_agent_message(session_id, {
                        "agent_id": "orchestrator",
                        "agent_name": "Research Orchestrator",
                        "action": "completed",
                        "content": f"Research completed! {orchestrator_result.stages_completed} stages completed.",
                    })
                    
                    _q_score = getattr(orchestrator_result, 'quality_score', 0)
                    _q_issues = getattr(orchestrator_result, 'quality_issues', [])
                    if _q_score > 0 or _q_issues:
                        SessionStreamer.push_quality_result(session_id, {
                            "overall_score": _q_score,
                            "overall_status": "passed" if orchestrator_result.status == "completed" else "warning",
                            "section_results": {},
                            "issues": _q_issues[:20],
                        })
                except ImportError:
                    pass

                # Push final summary as chat_response
                _summary_text = orchestrator_result.summary or result.get("summary", "")
                _report_sections = orchestrator_result.report.get("sections", []) if orchestrator_result.report else []
                _section_count = len(_report_sections)
                _final_msg = f"**Research Complete** ✅\n\n{_summary_text[:1000]}" if _summary_text else (
                    f"**Research Complete** ✅\n\n"
                    f"Research on 「{topic}」has been completed. "
                    f"{orchestrator_result.stages_completed} stages completed, "
                    f"{_section_count} sections generated."
                )
                _suggestions = [
                    {"id": "view_report", "label": "View Report", "example": "Show me the full report"},
                ]
                if orchestrator_result.status == "completed_with_warnings":
                    _final_msg = (
                        f"**Research Complete** ⚠️\n\n"
                        f"Quality score: {getattr(orchestrator_result, 'quality_score', 0):.1f} — "
                        f"report has quality issues but is available for preview.\n\n"
                        f"{_summary_text[:800]}"
                    ) if _summary_text else (
                        f"**Research Complete** ⚠️\n\n"
                        f"Research on 「{topic}」has been completed with quality warnings. "
                        f"Quality score: {getattr(orchestrator_result, 'quality_score', 0):.1f}. "
                        f"You can preview the report and request revisions.\n"
                    )
                    _suggestions = [
                        {"id": "view_report", "label": "View Report", "example": "Show me the full report"},
                        {"id": "improve_quality", "label": "Improve Quality", "example": "Please improve the report quality"},
                    ]
                try:
                    from src.core.progress_streamer import push_chat_response
                    push_chat_response(session_id, {
                        "message": _final_msg,
                        "action": "continue_chat",
                        "topic": topic,
                        "directions": [],
                        "suggestions": _suggestions,
                    })
                except ImportError:
                    pass

                # 复制预览文件到 data/html_reports/{session_id}.html
                try:
                    from src.core.preview_storage import PreviewStorage
                    src_path_str = pre_inject_document_path or pre_inject_output_path or result.get("document_path") or result.get("output_path", "")
                    if src_path_str and Path(src_path_str).exists():
                        src_path = Path(src_path_str)
                        if src_path.suffix.lower() in ('.pptx', '.docx', '.pdf'):
                            html_src = src_path.with_suffix('.preview.html')
                            if not html_src.exists():
                                html_src = src_path.parent / (src_path.stem.rsplit('_', 1)[0] + '*.html')
                                html_candidates = sorted(src_path.parent.glob(src_path.stem.rsplit('_', 1)[0] + '*.html'))
                                html_src = html_candidates[0] if html_candidates else None
                            if html_src and html_src.exists():
                                src_path = html_src
                            else:
                                logger.warning(f"Preview source is {src_path.suffix}, no HTML fallback found for {session_id}")
                                src_path = None
                        if src_path:
                            PreviewStorage.copy_file(session_id, src_path)
                            logger.info(f"Preview copied for {session_id}")
                except Exception as e:
                    logger.warning(f"Failed to copy preview file for {session_id}: {e}")

                # The preview may only become available after the result is
                # persisted. Publish once more so the UI receives its URL.
                _publish_report_context(
                    session_id, session, phase="completed",
                    document_version="final",
                )

                # 完成任务
                complete_task(session_id, result=result)
                manifest.record("PHASE_COMPLETE", phase="research_execution")

                logger.info(f"Research completed: {session_id} - agents: {orchestrator_result.agents_used}")
                return result

            else:
                _detail = orchestrator_result.summary or orchestrator_result.status
                result = {
                    "task_id": session_id,
                    "status": orchestrator_result.status,
                    "error": f"Research failed: {_detail}",
                    "summary": orchestrator_result.summary,
                }

                session["research_result"] = result
                session["status"] = "failed"
                _publish_report_context(session_id, session, phase="failed")
                update_progress(session_id, 0.0, message="研究失败")

                # Push failure message to frontend
                _error = result.get("error", "Unknown error")
                try:
                    from src.core.progress_streamer import push_chat_response
                    push_chat_response(session_id, {
                        "message": f"**Research Failed** ❌\n\n{_error}",
                        "action": "continue_chat",
                        "topic": topic,
                        "directions": [],
                        "suggestions": [
                            {"id": "retry", "label": "Retry", "example": "Retry the research with different parameters"},
                        ],
                    })
                except ImportError:
                    pass

                fail_task(session_id, _error)

                logger.warning(f"Research failed: {session_id} - status: {orchestrator_result.status}, error: {_error[:200]}")
                return result
            
        except asyncio.TimeoutError:
            logger.error(f"Research timed out: {session_id}")
            _mark_persisted_result_status(session_id, "failed")
            fail_task(session_id, "Research timed out")
            if session:
                session["status"] = "failed"
                _publish_report_context(session_id, session, phase="failed")
            return {"error": "Research timed out"}

        except asyncio.CancelledError:
            logger.info(f"Research cancelled: {session_id}")
            _mark_persisted_result_status(session_id, "cancelled")
            from src.core.progress_streamer import cancel_task
            cancel_task(session_id, "Task cancelled")
            manifest.record("PHASE_FAILED", phase="research_execution", reason="cancelled")
            if session:
                session["status"] = "cancelled"
                session["mode"] = "chat"
                _publish_report_context(session_id, session, phase="failed")
            return {"error": "Task cancelled"}

        except Exception as e:
            logger.error(f"Research failed: {session_id} - {e}", exc_info=True)
            _mark_persisted_result_status(session_id, "failed")
            fail_task(session_id, str(e))
            manifest.record("PHASE_FAILED", phase="research_execution", reason=type(e).__name__)
            if session:
                session["status"] = "failed"
                _publish_report_context(session_id, session, phase="failed")
            return {"error": str(e)}


# 全局执行器实例
_executor: Optional[ResearchExecutor] = None


def get_executor() -> ResearchExecutor:
    """Get the global executor instance"""
    global _executor
    if _executor is None:
        _executor = ResearchExecutor()
    return _executor


__all__ = ["ResearchExecutor", "get_executor"]
