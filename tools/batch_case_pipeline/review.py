# -*- coding: utf-8 -*-
"""审查收集器：质量Agent + 元数据 + 漂移 + 图表 + docx 五类检查 → review_report.json。"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from .config import CaseConfig

logger = logging.getLogger(__name__)

_PASS_SCORE = 70
_LEAK_SOURCES = {"content", "fetched", "public data compilation"}


async def collect_issues_async(research_result: Dict[str, Any], case: CaseConfig,
                               case_dir: Path) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []

    # 1) 质量Agent分章节检查（纯规则，无 LLM 调用；不可用则跳过不阻塞）
    try:
        from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent
        agent = QualityCheckAgent(agent_id="batch_review")
        section_result = await agent.check_by_sections(
            research_result.get("sections", []))
        for name, info in (section_result.get("section_results") or {}).items():
            for it in info.get("issues", []):
                issues.append({
                    "code": "content_issue", "section": name,
                    "severity": it.get("severity", "low"),
                    "detail": it.get("message", ""),
                })
    except Exception as exc:
        logger.warning("check_by_sections 跳过: %s", exc)

    # 2) 研究元数据
    if research_result.get("formal_complete") is False:
        issues.append({"code": "formal_incomplete", "section": "-",
                       "severity": "medium", "detail": "formal_complete=False"})
    gate = research_result.get("quality_gate_status")
    if gate and gate not in ("passed", "pass", "completed"):
        issues.append({"code": "quality_gate", "section": "-",
                       "severity": "medium", "detail": str(gate)})
    da = research_result.get("defense_audit") or {}
    for it in (da.get("issues") or []):
        if it.get("code") == "missing_source_url":
            issues.append({"code": "missing_source_url",
                           "section": str(it.get("section", "-")),
                           "severity": "high", "detail": "L3证据缺URL"})

    # 3) 主题漂移（领域词密度：每千字命中 <1.0 记 issue）
    for s in research_result.get("sections", []):
        content = s.get("content", "")
        hits = sum(content.count(k) for k in case.domain_keywords)
        density = hits / max(1, len(content) / 1000)
        if density < 1.0:
            issues.append({"code": "topic_drift", "section": s.get("title", ""),
                           "severity": "medium",
                           "detail": f"领域词密度 {density:.2f}"})

    # 4) 图表
    for s in research_result.get("sections", []):
        for c in (s.get("charts") or []):
            src = str(c.get("source", "")).strip().lower()
            if src in _LEAK_SOURCES:
                issues.append({"code": "chart_leak", "section": s.get("title", ""),
                               "severity": "high", "detail": f"source={src}"})
            if not c.get("caption"):
                issues.append({"code": "chart_no_caption", "section": s.get("title", ""),
                               "severity": "low", "detail": c.get("title", "")})
            png = Path(str(c.get("path", "")))
            if str(c.get("path", "")) and not png.is_file():
                issues.append({"code": "chart_missing", "section": s.get("title", ""),
                               "severity": "high", "detail": str(png)})

    # 5) docx 抽验（draft 存在时）
    draft = case_dir / "report_draft.docx"
    if draft.is_file():
        try:
            import docx as docx_mod
            d = docx_mod.Document(str(draft))
            xml = d.element.xml
            if "TOC" not in xml:
                issues.append({"code": "docx_format", "section": "-",
                               "severity": "low", "detail": "缺TOC域"})
            n_imgs = len(d.inline_shapes)
            n_charts = sum(len(s.get("charts") or [])
                           for s in research_result.get("sections", []))
            if n_charts and n_imgs < n_charts:
                issues.append({"code": "docx_format", "section": "-",
                               "severity": "medium",
                               "detail": f"图片 {n_imgs} < 图表 {n_charts}"})
        except Exception as exc:
            logger.warning("docx 抽验跳过: %s", exc)

    high = [i for i in issues if i["severity"] == "high"]
    score = max(0, 100 - 25 * len(high) - 5 * len(issues))
    return {"pass": not high and score >= _PASS_SCORE,
            "score": score, "issues": issues}


def collect_issues(research_result: Dict[str, Any], case: CaseConfig,
                   case_dir: Path) -> Dict[str, Any]:
    """同步包装（测试与脚本场景用）。"""
    return asyncio.run(collect_issues_async(research_result, case, case_dir))


def save_review_report(case_dir: Path, round_num: int, report: Dict[str, Any]) -> None:
    payload = {"round": round_num, **report}
    (case_dir / "review_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
