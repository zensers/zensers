import re
import json
import logging
from typing import Dict, Any, List

from .models import ChapterWriteInput, ChapterWriteOutput, DataPoint
from .prompt_manager import PromptManager
from src.core.llm_client import call_llm

DATAPOINT_FIELDS = {"metric", "value", "unit", "source", "chapter_id", "confidence"}

logger = logging.getLogger(__name__)


class ChapterWriter:

    def __init__(self, llm_skill=None, prompt_manager: PromptManager = None) -> None:
        # llm_skill kept for backward compatibility; agents use call_llm() directly now
        self._prompts = prompt_manager

    async def write(self, input_data: ChapterWriteInput) -> ChapterWriteOutput:
        chapter_spec = input_data.chapter_spec
        prompt = self._prompts.get(
            "chapter_write",
            topic=input_data.task_structure.get('topic', ''),
            framework_name=input_data.framework_config.get('name', '通用研究报告'),
            section_name=chapter_spec.get('section_name', ''),
            section_id=chapter_spec.get('section_id', ''),
            section_role=str(chapter_spec.get('section_role', '')),
            preceding_summary=input_data.preceding_summary,
            used_metrics_summary=input_data.used_metrics_summary,
            chapter_data=json.dumps(input_data.chapter_data, ensure_ascii=False, indent=2)
                         if input_data.chapter_data else '无可用数据',
            raw_data_summary=input_data.raw_data_summary if input_data.raw_data_summary else '无原始数据摘要',
            base_content=input_data.base_content if input_data.base_content else '无分析初稿，请基于数据从头撰写',
            upstream_data_points_json=json.dumps(input_data.upstream_data_points, ensure_ascii=False, indent=2)
                                      if input_data.upstream_data_points else '无可用数据',
        )
        raw_output = await self._call_llm(prompt)
        return self._parse_output(raw_output, chapter_spec)

    async def rewrite(self, original_chapter: ChapterWriteOutput,
                      review_feedback, framework_config: Dict,
                      chapter_spec: Dict, preceding_summary: str,
                      chapter_data: Dict = None) -> ChapterWriteOutput:
        issue_instructions = []
        for issue in review_feedback.issues:
            issue_instructions.append(
                f"- [{issue.severity}] {issue.description}\n  修正方向：{issue.suggestion}"
            )

        prompt = self._prompts.get(
            "chapter_rewrite",
            original_content=original_chapter.content,
            review_feedback=chr(10).join(issue_instructions),
            section_name=chapter_spec.get('section_name', ''),
            section_id=chapter_spec.get('section_id', ''),
            chapter_data=json.dumps(chapter_data, ensure_ascii=False, indent=2)
                         if chapter_data else '无可用数据',
        )
        raw_output = await self._call_llm(prompt)
        return self._parse_output(raw_output, chapter_spec)

    async def patch_data(self, chapter: ChapterWriteOutput,
                         patch_instructions: List[str],
                         framework_config: Dict) -> ChapterWriteOutput:
        prompt = self._prompts.get(
            "chapter_patch_data",
            chapter_content=chapter.content,
            patch_instructions=chr(10).join(f'- {inst}' for inst in patch_instructions),
            section_name=chapter.title,
            section_id=chapter.chapter_id,
        )
        raw_output = await self._call_llm(prompt)
        chapter_spec = {"section_id": chapter.chapter_id, "section_name": chapter.title}
        return self._parse_output(raw_output, chapter_spec)

    async def _call_llm(self, prompt: str) -> str:
        result = await call_llm(prompt=prompt, max_tokens=8192, temperature=0.7)
        if not result.get("success"):
            raise RuntimeError(f"LLM call failed: {result}")
        return result["content"]

    DATAPOINT_STR_FIELDS = {"metric", "value", "unit", "source", "chapter_id"}

    def _coerce_data_point(self, dp_dict: Dict[str, Any]) -> DataPoint:
        coerced = {}
        for k, v in dp_dict.items():
            if k in self.DATAPOINT_STR_FIELDS and not isinstance(v, str):
                coerced[k] = str(v)
            else:
                coerced[k] = v
        return DataPoint(**{k: v for k, v in coerced.items() if k in DATAPOINT_FIELDS})

    def _parse_output(self, raw: str, chapter_spec: Dict) -> ChapterWriteOutput:
        _SKIP_TITLES = {"数据精准修补任务", "章节精修任务", "章节精修润色任务", "章节撰写任务"}
        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', raw, re.DOTALL)
            if json_match:
                json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_match.group(1))
                data = json.loads(json_str)
                title = data.get("title", chapter_spec.get("section_name", ""))
                if title in _SKIP_TITLES:
                    title = chapter_spec.get("section_name", "")
                return ChapterWriteOutput(
                    chapter_id=chapter_spec.get("section_id", ""),
                    title=title,
                    content=data.get("content", ""),
                    data_points_used=[
                        self._coerce_data_point(dp)
                        for dp in data.get("data_points_used", [])
                    ],
                    key_conclusions=[str(c) for c in data.get("key_conclusions", [])],
                    self_check_passed=data.get("self_check_passed", True),
                    self_check_issues=[str(i) for i in data.get("self_check_issues", [])],
                )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse structured output: {e}")

        return ChapterWriteOutput(
            chapter_id=chapter_spec.get("section_id", ""),
            title=chapter_spec.get("section_name", ""),
            content=raw,
            data_points_used=[],
            key_conclusions=self._extract_conclusions(raw),
            self_check_passed=False,
            self_check_issues=["JSON解析失败，输出格式不规范"],
        )

    @staticmethod
    def _extract_conclusions(text: str) -> List[str]:
        lines = text.split("\n")
        conclusions = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("- **") and "结论" in stripped:
                conclusions.append(stripped.lstrip("- ").strip("*"))
        return conclusions[:5]
