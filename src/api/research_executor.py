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

logger = logging.getLogger(__name__)


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
        self._inject_in_progress: bool = False
    
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
            fail_task(session_id, "Task cancelled by user")
            return False

        if cm.is_paused(session_id):
            logger.info(f"Task paused at _check_paused, waiting for resume/cancel: {session_id}")
            r = await cm.wait_for_resume_or_cancel(session_id)
            if r == "cancelled":
                logger.info(f"Task cancelled while paused: {session_id}")
                fail_task(session_id, "Task cancelled by user")
                return False

        return True

    async def _process_pending_injects(
        self,
        session_id: str,
        session_manager: "SessionManager",
        orchestrator_timeout: int = 600,
    ) -> None:
        if self._inject_in_progress:
            return
        self._inject_in_progress = True
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
                        result = await asyncio.wait_for(
                            orch.research(
                                user_input={
                                    "topic": context.get("topic", ""),
                                    "aspects": inject_aspects,
                                    "section_requirements": section_reqs,
                                },
                                output_type=framework.get("output_type", "industry_report"),
                                output_format="html",
                                custom_aspects=inject_aspects,
                                skip_phases=routing_result.skip_phases or None,
                            ),
                            timeout=orchestrator_timeout,
                        )
                        session = session_manager.get(session_id)
                        if session and result and result.status == "completed":
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

                            session["research_result"] = {
                                "task_id": original.get("task_id") or original_task_id,
                                "status": "completed",
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
                            await rs.revise_from_user_feedback(
                                document_path=output_path,
                                task_id=session_id,
                                section=op.get("section_name", ""),
                                adjustment=op.get("requirement", ""),
                                revision_type="addition",
                            )
                    except Exception as e:
                        logger.error(f"[{session_id}] Revision failed for {op.get('section_name')}: {e}")
        finally:
            self._inject_in_progress = False

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
        
        # Set global language from plan/session for all downstream agents
        plan_language = plan.get("language") or session.get("language", "zh")
        set_language(plan_language)
        logger.info(f"ResearchExecutor: set global language to '{plan_language}' for session {session_id}")
        
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
            
            # === 检查是否有可跳过的已完成阶段 ===
            skip_phases = plan.get("skip_phases", [])
            if skip_phases:
                logger.info(f"Resuming with {len(skip_phases)} skip_phases: {skip_phases}")
            
            # === 从 session 中提取动态参数（/template 快速启动传入）===
            user_input_dict: Dict[str, Any] = {
                "session_id": session_id,
                "topic": topic or user_input,
                "output_type": output_type,
                "aspects": framework.get("sections", None),
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

                orchestrator_result = await asyncio.wait_for(
                    orchestrator.research(
                        user_input=user_input_dict,
                        interaction_mode=False,
                        output_type=output_type,
                        custom_aspects=framework.get("sections", None),
                        output_format="html",
                        skip_phases=skip_phases or None,
                    ),
                    timeout=orchestrator_timeout,
                )
            finally:
                async with self._tasks_lock:
                    self._main_tasks.pop(session_id, None)
            
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

                pre_inject_output_path = result.get("output_path", "")
                pre_inject_document_path = result.get("document_path", "")
                await self._process_pending_injects(session_id, session_manager, orchestrator_timeout or 600)
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
                try:
                    from src.core.progress_streamer import push_chat_response
                    push_chat_response(session_id, {
                        "message": _final_msg,
                        "action": "continue_chat",
                        "topic": topic,
                        "directions": [],
                        "suggestions": [
                            {"id": "view_report", "label": "View Report", "example": "Show me the full report"},
                        ],
                    })
                except ImportError:
                    pass

                # 复制预览文件到 data/html_reports/{session_id}.html
                try:
                    from pathlib import Path
                    from src.core.preview_storage import PreviewStorage
                    src_path_str = pre_inject_document_path or pre_inject_output_path or result.get("document_path") or result.get("output_path", "")
                    if src_path_str:
                        src_path = Path(src_path_str)
                        if src_path.exists():
                            PreviewStorage.copy_file(session_id, src_path)
                            logger.info(f"Preview copied for {session_id}")
                except Exception as e:
                    logger.warning(f"Failed to copy preview file for {session_id}: {e}")

                # 完成任务
                complete_task(session_id, result=result)

                logger.info(f"Research completed: {session_id} - agents: {orchestrator_result.agents_used}")
                return result

            else:
                result = {
                    "task_id": session_id,
                    "status": orchestrator_result.status,
                    "error": f"Research failed with status: {orchestrator_result.status}",
                    "summary": orchestrator_result.summary,
                }

                session["research_result"] = result
                session["status"] = "failed"
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
            fail_task(session_id, "Research timed out")
            if session:
                session["status"] = "failed"
            return {"error": "Research timed out"}

        except asyncio.CancelledError:
            logger.info(f"Research cancelled: {session_id}")
            fail_task(session_id, "Task cancelled")
            if session:
                session["status"] = "cancelled"
                session["mode"] = "chat"
            return {"error": "Task cancelled"}

        except Exception as e:
            logger.error(f"Research failed: {session_id} - {e}", exc_info=True)
            fail_task(session_id, str(e))
            if session:
                session["status"] = "failed"
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
