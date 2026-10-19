# -*- coding: utf-8 -*-
"""issue → 修复动作分派。就地修订 research_result，返回需重跑的阶段集合。"""
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

logger = logging.getLogger(__name__)

_LEAK_SOURCES = {"content", "fetched", "public data compilation"}


async def _default_llm(prompt: str, **kwargs) -> Dict[str, Any]:
    from src.core.llm_client import call_llm
    return await call_llm(prompt, **kwargs)


async def _rewrite_section(content: str, issue: Dict[str, Any],
                           keywords: Iterable[str],
                           llm_fn) -> Optional[str]:
    """LLM 修订单章节；失败/异常返回 None（保持原内容）。"""
    prompt = (
        "你是行业研究报告主编。针对审查问题修订指定章节：保持事实与引用不变，"
        f"紧扣领域关键词补足论证与量化细节。\n"
        f"审查问题: {issue.get('code')} - {issue.get('detail')}\n"
        f"领域关键词: {', '.join(keywords)}\n"
        f"## 原章节内容\n{content}\n\n请直接输出修订后的完整章节，不要前缀说明。")
    try:
        response = await llm_fn(prompt, max_tokens=4000, temperature=0.4)
    except Exception as exc:
        logger.warning("LLM 修订异常: %s", exc)
        return None
    if not response.get("success"):
        logger.warning("LLM 修订失败: %s", response.get("message"))
        return None
    revised = str(response.get("content") or "").strip()
    return revised or None


async def apply_fixes(issues: List[Dict[str, Any]], research_result: Dict[str, Any],
                      domain_keywords: Iterable[str] = (),
                      llm_fn=None) -> Set[str]:
    """按 issue code 分派修复。llm_fn 缺省用真实 call_llm（async）。"""
    rerun: Set[str] = set()
    if llm_fn is None:
        llm_fn = _default_llm
    keywords = list(domain_keywords)
    sections = research_result.get("sections", [])
    for issue in issues:
        code = issue.get("code")
        if code == "chart_leak":
            for s in sections:
                for c in (s.get("charts") or []):
                    if str(c.get("source", "")).strip().lower() in _LEAK_SOURCES:
                        c["source"] = "公开资料整理"
            rerun |= {"render"}
        elif code == "chart_missing":
            for s in sections:
                s["charts"] = [c for c in (s.get("charts") or [])
                               if not str(c.get("path") or "")
                               or Path(str(c.get("path"))).is_file()]
            rerun |= {"charts", "render"}
        elif code in ("topic_drift", "content_issue", "formal_incomplete"):
            target = next((s for s in sections
                           if s.get("title") == issue.get("section")), None)
            if target is None:
                logger.warning("[%s] 未找到章节，跳过修订: %s",
                               issue.get("code"), issue.get("section"))
                continue
            revised = await _rewrite_section(
                target.get("content", ""), issue, keywords, llm_fn)
            if revised and revised != target.get("content"):
                target["content"] = revised
                rerun |= {"charts", "render"}
        elif code in ("docx_format", "quality_gate", "missing_source_url",
                      "chart_no_caption"):
            rerun.add("render")
        else:
            logger.warning("未识别的 issue code，跳过: %s", code)
    return rerun
