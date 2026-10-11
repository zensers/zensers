# -*- coding: utf-8 -*-
"""流水线执行阶段：research / charts / render / finalize。

阶段函数签名统一: (ctx, case, case_dir, state[, research_result]) -> meta dict
ctx 为依赖容器（DefaultCtx=真实接线；测试注入替身）。
"""
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple

from .config import CaseConfig
from .state import CaseState

logger = logging.getLogger(__name__)


def load_research_result(case_dir: Path) -> Dict[str, Any]:
    """读取并校验 research_result.json；缺失/损坏/空 sections 返回 {}。"""
    path = case_dir / "research_result.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("research_result.json 损坏: %s", path)
        return {}
    return data if isinstance(data, dict) and data.get("sections") else {}


class DefaultCtx:
    """真实依赖：ResearchOrchestrator + DocumentGenerationAgent（懒加载单例）。"""

    def __init__(self):
        self._research_orchestrator = None
        self._doc_agent = None

    async def run_research(self, case: CaseConfig, case_dir: Path) -> Dict[str, Any]:
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        if self._research_orchestrator is None:
            self._research_orchestrator = ResearchOrchestrator(
                use_intelligent_routing=True)
        session_id = f"{case.case_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        result = await self._research_orchestrator.research(
            user_input={
                "session_id": session_id,
                "topic": case.topic,
                "aspects": case.effective_chapters,
                "output_type": "industry_report",
                "output_format": "html",
            },
            user_id="batch_pipeline",
            interaction_mode=False,
            output_type="industry_report",
            custom_aspects=case.effective_chapters,
            framework="standard",
            output_format="html",
        )
        if result.status not in ("completed", "completed_with_warnings"):
            raise RuntimeError(f"研究失败: {result.status}")
        report = result.report or {}
        if not isinstance(report.get("sections"), list) or not report["sections"]:
            raise RuntimeError("研究产出无有效 sections")
        return report

    async def run_charts(self, case: CaseConfig, case_dir: Path,
                         research_result: Dict[str, Any]
                         ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        from src.agents.fixed_agents.document_generation_agent import (
            DocumentGenerationAgent,
        )
        if self._doc_agent is None:
            self._doc_agent = DocumentGenerationAgent(
                agent_id=f"batch_{case.case_id}")
        research_result = await self._doc_agent._generate_charts_for_html(
            research_result)
        records = _chart_records(research_result)
        return research_result, {"charts": len(records)}

    async def run_render(self, case: CaseConfig, case_dir: Path,
                         research_result: Dict[str, Any]) -> Dict[str, Any]:
        from src.agents.fixed_agents.document_generation_agent import (
            DocumentGenerationAgent, DocumentGenerationRequest,
        )
        if self._doc_agent is None:
            self._doc_agent = DocumentGenerationAgent(
                agent_id=f"batch_{case.case_id}")

        req = DocumentGenerationRequest.from_dict({
            "action": "produce_document",
            "task_id": case.case_id,
            "output_format": "html",
            "output_dir": str(case_dir),
            "research_result": research_result,
        })
        html_res = await self._doc_agent._handle_produce_document(req)
        if not html_res.get("success"):
            raise RuntimeError(f"HTML 渲染失败: {html_res.get('error')}")
        html_path = Path(html_res["document_path"])
        html_path.replace(case_dir / "report.html")

        req2 = DocumentGenerationRequest.from_dict({
            "action": "produce_document",
            "task_id": case.case_id,
            "output_format": "docx",
            "output_dir": str(case_dir),
            "research_result": research_result,
            "_preview_html_path": str(case_dir / "report.html"),
        })
        docx_res = await self._doc_agent._handle_produce_document(req2)
        if not docx_res.get("success"):
            raise RuntimeError(f"DOCX 渲染失败: {docx_res.get('error')}")
        draft = Path(docx_res["document_path"])
        draft.replace(case_dir / "report_draft.docx")
        size = (case_dir / "report_draft.docx").stat().st_size
        if size < 300 * 1024:
            raise RuntimeError(f"DOCX 过小({size}B)，疑似渲染异常")
        return {"html": str(case_dir / "report.html"),
                "docx": str(case_dir / "report_draft.docx")}


def _chart_records(research_result: Dict[str, Any]) -> list:
    """从研究结果提取图表清单（section/path/title/source/chart_type）。"""
    return [
        {"section": s.get("title"), "path": c.get("path"),
         "title": c.get("title"), "source": c.get("source"),
         "chart_type": c.get("chart_type")}
        for s in research_result.get("sections", [])
        for c in (s.get("charts") or [])
    ]


async def run_research(ctx, case: CaseConfig, case_dir: Path,
                       state: CaseState) -> Dict[str, Any]:
    state.mark_running("research")
    existing = load_research_result(case_dir)
    if existing:
        meta = {"sections": len(existing["sections"]), "skipped": True}
        state.mark_done("research", meta)
        logger.info("[%s] research 跳过（已有 %d 章节）",
                    case.case_id, meta["sections"])
        return meta
    report = await ctx.run_research(case, case_dir)
    (case_dir / "research_result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    meta = {"sections": len(report["sections"]), "skipped": False}
    state.mark_done("research", meta)
    return meta


async def run_charts(ctx, case: CaseConfig, case_dir: Path, state: CaseState,
                     research_result: Dict[str, Any]) -> Dict[str, Any]:
    state.mark_running("charts")
    research_result, meta = await ctx.run_charts(case, case_dir, research_result)
    (case_dir / "charts.json").write_text(
        json.dumps({"charts": _chart_records(research_result)},
                   ensure_ascii=False, indent=1),
        encoding="utf-8")
    state.mark_done("charts", meta)
    return meta


async def run_render(ctx, case: CaseConfig, case_dir: Path, state: CaseState,
                     research_result: Dict[str, Any]) -> Dict[str, Any]:
    state.mark_running("render")
    meta = await ctx.run_render(case, case_dir, research_result)
    state.mark_done("render", meta)
    return meta


def run_finalize(case: CaseConfig, case_dir: Path, state: CaseState,
                 final_score: float, rounds: int) -> Dict[str, Any]:
    """定稿：report_draft.docx → <报告标题>.docx + manifest.json。"""
    state.mark_running("finalize")
    draft = case_dir / "report_draft.docx"
    if not draft.is_file():
        raise RuntimeError("定稿失败: report_draft.docx 不存在")
    title = load_research_result(case_dir).get("title") or case.topic
    final = case_dir / f"{title}.docx"
    shutil.copy2(draft, final)
    manifest = {
        "case_id": case.case_id,
        "topic": case.topic,
        "status": state.case_status,
        "final_score": final_score,
        "review_rounds": rounds,
        "docx": str(final),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    (case_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    state.mark_done("finalize", {"docx": str(final)})
    return manifest
