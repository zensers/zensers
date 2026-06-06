# -*- coding: utf-8 -*-
"""
Layer 3: 分析深度评估 (LLM-as-Judge 升级版)

升级自 llm_judge.py:
- 评分维度从硬编码4维 → MKB rubric 动态加载
- model: cheap_model → default_model
- temperature: 0.3 → 0.2
- max_retries: 0 → 2
- 截断: 4000 → 8000 字符
- 回退: 35.0 保持

设计参考: 08_未来优化方向设计.md §4.2 Track B Layer 3
"""

__all__ = ["Layer3DepthScorer", "Layer3Result"]

import asyncio
import concurrent.futures
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DIMENSIONS = [
    {"name": "洞察力", "weight": 0.25, "description": "是否有超越陈述事实的分析洞见"},
    {"name": "逻辑链完整性", "weight": 0.25, "description": "因果推断是否自洽闭合"},
    {"name": "数据批判性", "weight": 0.20, "description": "是否标注来源/置信度/口径"},
    {"name": "前瞻性", "weight": 0.15, "description": "是否提供可验证的预测/情景"},
    {"name": "可验证性", "weight": 0.15, "description": "结论能否被第三方复现"},
]

_JUDGE_PROMPT_TEMPLATE = """\
你是一位严格的分析质量评审专家。按以下评分维度评审报告内容。

评分维度:
{dimensions_text}

评分规则:
- 每个维度 0-100 分
- 必须用具体整数, 不用范围
- 如果内容缺少某维度的支撑, 该维度应低于 50

报告内容:
---
{content}
---

仅返回JSON:
{{{score_json_template}}}

"issues" 为该内容的主要问题列表(每个不超过20字)。"""

_FALLBACK_SCORE = 35.0
_MAX_RETRIES = 2
_MAX_CONTENT_CHARS = 8000


@dataclass
class Layer3Result:
    score: float
    dimension_scores: Dict[str, float]
    issues: List[str]
    rubric_id: str
    details: Dict[str, Any] = field(default_factory=dict)


class Layer3DepthScorer:
    """
    Layer 3 分析深度评估 (LLM-as-Judge 升级版)

    特性:
    - 动态加载 MKB rubric 评分维度 (fallback 到默认5维)
    - model: default_model, temperature: 0.2
    - max_retries: 2
    - 回退: 35.0
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        rubrics_dir: Optional[str] = None,
    ):
        self._llm_client = llm_client
        self._rubrics_dir = rubrics_dir or str(
            Path(__file__).resolve().parents[3] / "data" / "knowledge" / "methodology" / "rubrics"
        )
        self._rubric_cache: Dict[str, Dict[str, Any]] = {}

    def score(
        self,
        content: str,
        section_type: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Layer3Result:
        """同步评分接口"""
        if not content:
            return Layer3Result(
                score=0.0, dimension_scores={}, issues=["内容为空"],
                rubric_id="none", details={},
            )

        rubric = self._load_rubric(section_type)
        dimensions = self._extract_dimensions(rubric)

        prompt = self._build_prompt(content, dimensions)

        scores = None
        last_error = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = self._call_llm(prompt)
                scores = self._parse_response(response, dimensions)
                if scores:
                    break
            except Exception as e:
                last_error = e
                logger.warning(f"Layer 3 attempt {attempt + 1} failed: {e}")

        if not scores:
            logger.warning(f"Layer 3 all retries exhausted, fallback to {_FALLBACK_SCORE}")
            return Layer3Result(
                score=_FALLBACK_SCORE,
                dimension_scores={d["name"]: _FALLBACK_SCORE for d in dimensions},
                issues=["LLM评分失败, 使用回退分数"],
                rubric_id=rubric.get("rubric_id", "default"),
                details={"error": str(last_error) if last_error else "parse failed"},
            )

        total = sum(
            scores.get(d["name"], 50) * d["weight"] for d in dimensions
        )
        issues = scores.pop("_issues", [])

        return Layer3Result(
            score=round(min(total, 100.0), 1),
            dimension_scores={k: v for k, v in scores.items() if not k.startswith("_")},
            issues=issues,
            rubric_id=rubric.get("rubric_id", "default"),
            details={"attempts": attempt + 1} if scores else {},
        )

    def _load_rubric(self, section_type: str) -> Dict[str, Any]:
        """从 MKB rubrics 目录加载 rubric"""
        if section_type in self._rubric_cache:
            return self._rubric_cache[section_type]

        try:
            import yaml
            path = Path(self._rubrics_dir) / f"{section_type}_rubric.yaml"
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if data:
                    self._rubric_cache[section_type] = data
                    return data
        except Exception as e:
            logger.debug(f"Failed to load rubric for {section_type}: {e}")

        default = {"rubric_id": "default", "dimensions": _DEFAULT_DIMENSIONS}
        self._rubric_cache[section_type] = default
        return default

    def _extract_dimensions(self, rubric: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从 rubric 提取维度列表"""
        dims = rubric.get("dimensions", [])
        if not dims:
            return _DEFAULT_DIMENSIONS
        result = []
        for d in dims:
            if isinstance(d, dict) and "name" in d and "weight" in d:
                desc = ""
                levels = d.get("levels", {})
                if isinstance(levels, dict):
                    excellent = levels.get("excellent", "")
                    if isinstance(excellent, str):
                        desc = excellent[:80]
                result.append({
                    "name": d["name"],
                    "weight": float(d["weight"]),
                    "description": desc,
                })
        return result if result else _DEFAULT_DIMENSIONS

    def _build_prompt(self, content: str, dimensions: List[Dict[str, Any]]) -> str:
        dims_text = "\n".join(
            f"- {d['name']} (权重{d['weight']:.0%}): {d.get('description', '')}"
            for d in dimensions
        )
        score_template = ", ".join(
            f'"{d["name"]}": <0-100>' for d in dimensions
        )
        return _JUDGE_PROMPT_TEMPLATE.format(
            dimensions_text=dims_text,
            content=content[:_MAX_CONTENT_CHARS],
            score_json_template=score_template + ', "issues": ["<问题>"]',
        )

    def _call_llm(self, prompt: str) -> str:
        """同步 LLM 调用"""
        from src.config import settings
        from openai import AsyncOpenAI

        async def _do():
            client = AsyncOpenAI(
                api_key=settings.llm.api_key,
                base_url=settings.llm.base_url,
            )
            try:
                model = settings.llm.model
                resp = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "你是严格的分析质量评审专家。仅输出JSON。"},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=800,
                    temperature=0.2,
                )
                return resp.choices[0].message.content or ""
            finally:
                try:
                    await client.close()
                except Exception:
                    pass

        try:
            asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, _do()).result(timeout=90)
        except RuntimeError:
            return asyncio.run(_do())

    def _parse_response(
        self, response: str, dimensions: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """解析 LLM JSON 响应"""
        if not response:
            return None
        try:
            s = response.find("{")
            e = response.rfind("}") + 1
            if s < 0 or e <= s:
                return None
            parsed = json.loads(response[s:e])
            if not isinstance(parsed, dict):
                return None

            result = {}
            for d in dimensions:
                name = d["name"]
                val = parsed.get(name)
                if val is not None:
                    try:
                        result[name] = max(0, min(100, float(val)))
                    except (ValueError, TypeError):
                        result[name] = 50
                else:
                    result[name] = 50

            result["_issues"] = parsed.get("issues", [])
            return result

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Layer 3 JSON parse failed: {e}")
            return None
