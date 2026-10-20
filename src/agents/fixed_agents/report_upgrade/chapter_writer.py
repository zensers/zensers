import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

from .models import ChapterWriteInput, ChapterWriteOutput, DataPoint
from .prompt_manager import PromptManager
from src.core.content_contract import (
    check_content, check_finding_line, content_opens_meta, current_report_language,
)
from src.core.llm_client import call_llm, call_llm_ex, call_llm_with_tools
from src.core.llm_retry import LLMBudgetExhausted, ParseOutcome, RetryVariations
from src.core.failure_audit import FailureAudit
from src.skills.file_skill import FileSkill

DATAPOINT_FIELDS = {
    "metric", "value", "unit", "source", "chapter_id", "sub_section_id", "confidence",
    "source_url", "evidence_id", "provenance_id", "evidence_excerpt", "locator",
    "geographic_scope", "period", "population",
    "epistemic_level", "evidence_status",
}

# Primary chapter output contract: delimiter-based fixed format.  Provider
# models differ wildly in JSON-contract adherence (ses_d6417b3a: a coding
# model produced 10.5k chars of reasoning instead of chapter JSON; long-form
# Chinese inside JSON demands perfect escaping), so the chapter envelope is a
# delimiter format and JSON is demoted to compatibility fallback.
DELIMITER_OUTPUT_CONTRACT = "chapter_delimiter"
_DELIMITER_START = "<<<REPORT_CHAPTER>>>"
_DELIMITER_END = "<<<END_REPORT_CHAPTER>>>"
_DELIMITER_CONTENT_MARKER = "<<<CONTENT>>>"
_DELIMITER_CONCLUSIONS_MARKER = "<<<CONCLUSIONS>>>"
_DELIMITER_DATAPOINTS_MARKER = "<<<DATAPOINTS>>>"
_DELIMITER_NEXT_AFTER_CONTENT = (
    _DELIMITER_CONCLUSIONS_MARKER, _DELIMITER_DATAPOINTS_MARKER, _DELIMITER_END,
)
_DELIMITER_NEXT_AFTER_CONCLUSIONS = (_DELIMITER_DATAPOINTS_MARKER, _DELIMITER_END)

# strict_json_prefix rung reinforcement for the delimiter contract (the
# engine's STRICT_JSON_PREFIX demands JSON, which contradicts this contract).
_DELIMITER_FORMAT_REINFORCEMENT = "严格按上述标记格式输出，不要输出任何其他内容。"

logger = logging.getLogger(__name__)

# Chapter prose targets compete with the JSON envelope for the same output
# budget.  The legacy 8192-token cap truncates long chapters mid-JSON and the
# parse failure discards the whole chapter.  Raise per-deployment via
# ZENSERS_CHAPTER_MAX_TOKENS while keeping repo behavior unchanged.
_CHAPTER_MAX_TOKENS_ENV = "ZENSERS_CHAPTER_MAX_TOKENS"


def _chapter_max_tokens() -> int:
    try:
        value = int(os.environ.get(_CHAPTER_MAX_TOKENS_ENV, "8192"))
    except (TypeError, ValueError):
        return 8192
    return max(4096, min(32768, value))


# A JSON-looking chapter reply that still needs at least this much prose to
# be trustworthy salvage (below it, prefer the explicit failed status so
# audits do not mistake scraps for research).
_SALVAGE_MIN_CHARS = 800

# E1 (ses_d6417b3a): reasoning-first profiles sometimes answer with raw
# repair/chain-of-thought narration instead of the chapter.  The opener
# marker set now lives in src/core/content_contract.py (C1) and is reached
# through the ``_looks_like_meta_reasoning`` delegate below.


def _looks_like_meta_reasoning(text: str) -> bool:
    """兼容包装（I1 迁移）：委托给统一内容契约的 C1 开头硬检测。"""
    return content_opens_meta(text)


class ChapterWriter:

    def __init__(self, prompt_manager: PromptManager = None, use_streaming: bool = True) -> None:
        self._prompts = prompt_manager
        self._raw_data_location = ""
        self._use_streaming = bool(use_streaming)

    async def write(self, input_data: ChapterWriteInput) -> ChapterWriteOutput:
        self._raw_data_location = input_data.raw_data_location or ""
        chapter_spec = input_data.chapter_spec
        raw_location = input_data.raw_data_location or ""
        try:
            expected_chars = int((chapter_spec or {}).get("word_count_target") or 2000)
        except (TypeError, ValueError):
            expected_chars = 2000
        task_tag = f"writer:{(chapter_spec or {}).get('section_id', '')}"
        try:
            outcome = await call_llm_ex(
                lambda variations: self._build_write_prompt(
                    input_data, variations, input_data.preceding_summary),
                output_contract=DELIMITER_OUTPUT_CONTRACT,
                expected_output_chars=expected_chars,
                parse=lambda raw: self._parse_with_outcome(raw, chapter_spec),
                stream=self._use_streaming,
                on_token=None,
                task_tag=task_tag,
            )
            chapter = outcome if isinstance(outcome, ChapterWriteOutput) \
                else self._parse_output(str(outcome or ""), chapter_spec)
        except LLMBudgetExhausted as exhausted:
            logger.error(
                "ChapterWriter budget exhausted for %s: %s",
                (chapter_spec or {}).get("section_id"), exhausted,
            )
            chapter = None
            if raw_location and Path(raw_location).is_file():
                # Compatibility: the engine transport binds no tools, so the
                # chapter is written from the inline data. Before marking it
                # failed for the defense rescue loop, give the data-grounded
                # chapter one last legacy attempt with read_json actually
                # bound (tools_bound=True prompt + tool-enabled call).
                try:
                    fallback_prompt = self._build_write_prompt(
                        input_data, RetryVariations(), input_data.preceding_summary,
                        tools_bound=True)
                    fallback_raw = await self._call_llm_with_tools(
                        fallback_prompt, raw_location)
                    fallback_chapter = self._parse_output(fallback_raw, chapter_spec)
                    if (
                        str(getattr(fallback_chapter, "status", "ready")).lower() == "ready"
                        and str(fallback_chapter.content or "").strip()
                    ):
                        # I4 兜底同验收：tools 最后通道的产出也必须通过与
                        # 主路径相同的 I1 内容契约（终审 P1#1——此通道原先
                        # 仅查 ready+非空，垃圾可直达交付物）。
                        fallback_verdict = check_content(
                            str(fallback_chapter.content or ""),
                            kind="chapter",
                            section_name=str((chapter_spec or {}).get("section_name", "") or ""),
                            language=current_report_language(),
                        )
                        if fallback_verdict.passed:
                            chapter = fallback_chapter
                        else:
                            logger.warning(
                                "[CONTENT_CONTRACT] ChapterWriter tools fallback "
                                "rejected for %s: %s",
                                (chapter_spec or {}).get("section_id"),
                                fallback_verdict.fail_codes,
                            )
                            FailureAudit.record(
                                stage="report.write.tools_fallback",
                                subject_id=str((chapter_spec or {}).get("section_id", "") or ""),
                                action="content_contract_rejected",
                                reason=f"tools fallback failed I1: {fallback_verdict.fail_codes}",
                                task_id="",
                            )
                except Exception as fallback_error:
                    logger.warning(
                        "ChapterWriter tools fallback failed for %s: %s",
                        (chapter_spec or {}).get("section_id"), fallback_error,
                    )
            if chapter is None:
                chapter = self._parse_output("", chapter_spec)
                chapter.error = (
                    f"budget_exhausted:{exhausted.classification.error_class.value}")
        return chapter

    def _build_write_prompt(self, input_data: ChapterWriteInput,
                            variations: RetryVariations, preceding_summary: str,
                            tools_bound: bool = False) -> str:
        chapter_spec = input_data.chapter_spec or {}
        prompt_kwargs = dict(
            topic=input_data.task_structure.get('topic', ''),
            framework_name=input_data.framework_config.get('name', '通用研究报告'),
            section_name=chapter_spec.get('section_name', ''),
            section_id=chapter_spec.get('section_id', ''),
            section_role=str(chapter_spec.get('section_role', '')),
            preceding_summary=preceding_summary,
            used_metrics_summary=input_data.used_metrics_summary,
            chapter_data=json.dumps(input_data.chapter_data, ensure_ascii=False, indent=2)
                         if input_data.chapter_data else '无可用数据',
            raw_data_summary=input_data.raw_data_summary if input_data.raw_data_summary else '无原始数据摘要',
            base_content=input_data.base_content if input_data.base_content else '无分析初稿，请基于数据从头撰写',
            upstream_data_points_json=json.dumps(input_data.upstream_data_points, ensure_ascii=False, indent=2)
                                      if input_data.upstream_data_points else '无可用数据',
            global_evidence_pool_json=json.dumps(input_data.global_evidence_pool, ensure_ascii=False, indent=2)
                                      if input_data.global_evidence_pool else '无可用原始搜索证据',
            raw_data_location=input_data.raw_data_location or '未提供（请使用当前任务的原始证据池）',
            chapter_requirements_json=json.dumps(input_data.chapter_requirements, ensure_ascii=False, indent=2)
                                      if input_data.chapter_requirements else '无明确章节需求',
            used_evidence_ids_json=json.dumps(input_data.used_evidence_ids, ensure_ascii=False),
        )
        raw_location = input_data.raw_data_location or ""
        has_raw_cache = bool(raw_location) and Path(raw_location).is_file()
        # The read_json promise is only honest when a tool is actually bound:
        # the engine transport binds none, so write() passes tools_bound=False
        # and the model is told to write from the inline data instead.
        if has_raw_cache and tools_bound:
            prompt_kwargs["data_read_step"] = (
                f"调用 `read_json(filepath={raw_location})` 读取完整原始数据缓存，"
                "了解报告涉及的全部数据。"
            )
            prompt_kwargs["raw_data_guidance"] = (
                f"### 完整原始数据位置（优先读取）\n{raw_location}\n\n"
                "你拥有只读工具 `read_json`。当章节数据不足、章节 ID 不匹配或需要核对完整证据时，必须优先调用\n"
                f"`read_json(filepath={raw_location})` 读取该任务的完整原始数据缓存，再判断是否真的缺失。\n"
                "该工具只允许读取当前任务的这个 JSON 文件，不能读取其他路径。"
            )
        else:
            prompt_kwargs["data_read_step"] = (
                "通读下方提供的章节数据、上游数据点与全局证据池，了解报告涉及的全部数据。"
            )
            prompt_kwargs["raw_data_guidance"] = (
                f"完整原始数据缓存：{raw_location or '无单独缓存文件'}（该位置不可用）。\n"
                "本次调用未绑定任何文件读取工具，也不存在 read_json 工具。"
                "不要尝试调用或输出任何工具调用语句，请直接依据上文提供的数据与证据撰写章节。"
            )
        # 策略接线 B：pptx 要点字数上限由 PPTXStrategy 单一来源注入模板
        #（${bullet_max_chars}）；PromptManager.substitute 对缺失模板变量抛
        # KeyError，故 pptx 路径必须提供；docx 模板无该占位符，多余 kwarg
        # 会被 Template.substitute 静默忽略，不受影响。
        if input_data.output_format == "pptx":
            try:
                from src.content.format_strategy import get_format_strategy
                directive = get_format_strategy(
                    input_data.output_format).get_writing_directive()
                prompt_kwargs["bullet_max_chars"] = directive.bullet_max_chars or 25
            except Exception as e:
                logger.warning(f"Failed to read bullet_max_chars from format strategy: {e}, using 25")
                prompt_kwargs["bullet_max_chars"] = 25
        prompt_name = "chapter_write_pptx" if input_data.output_format == "pptx" else "chapter_write"
        try:
            prompt = self._prompts.get(prompt_name, **prompt_kwargs)
        except FileNotFoundError:
            # Keep custom/legacy prompt directories working until they add the
            # optional PPT template.
            prompt = self._prompts.get("chapter_write", **prompt_kwargs)
        if variations.strip_reasoning:
            prompt = f"直接输出正式章节内容，不要输出任何思考过程。\n{prompt}"
        if variations.strict_json_prefix:
            # Delimiter contract: the engine only prepends STRICT_JSON_PREFIX
            # for output_contract="json", so this builder owns the rung and
            # reinforces the marker format instead of demanding JSON.
            prompt = f"{prompt}\n{_DELIMITER_FORMAT_REINFORCEMENT}"
        return prompt

    async def rewrite(self, original_chapter: ChapterWriteOutput,
                      review_feedback, framework_config: Dict,
                      chapter_spec: Dict, preceding_summary: str,
                      chapter_data: Dict = None) -> ChapterWriteOutput:
        original_len = len(str(original_chapter.content or "").strip())
        try:
            # The retired legacy path (3x stream retry loop in _call_llm) is
            # replaced by the retry engine: rewrite() is ONE LLM call, so the
            # engine owns transport/output retries with mutations and the F1b
            # degenerate-replacement rule lives in the parse hook as a
            # classification (single source of truth).  Budget exhaustion
            # keeps the last known good chapter (F1b contract).
            rewritten = await call_llm_ex(
                lambda variations: self._build_rewrite_prompt(
                    original_chapter, review_feedback, chapter_spec, variations,
                    preceding_summary, chapter_data),
                output_contract=DELIMITER_OUTPUT_CONTRACT,
                expected_output_chars=max(2000, original_len),
                parse=lambda raw: self._rewrite_parse_with_outcome(
                    raw, chapter_spec, original_len),
                stream=self._use_streaming,
                on_token=None,
                task_tag=f"rewrite:{original_chapter.chapter_id}",
            )
        except LLMBudgetExhausted as exhausted:
            logger.warning(
                "ChapterWriter.rewrite kept original content for chapter %s "
                "after engine budget exhaustion: %s",
                original_chapter.chapter_id, exhausted,
            )
            return original_chapter
        # Engine success returns the parse hook's chapter value; the legacy
        # escape hatch (LLM_RETRY_ENGINE=legacy) returns a raw string.
        if not isinstance(rewritten, ChapterWriteOutput):
            rewritten = self._parse_output(str(rewritten or ""), chapter_spec)
        return rewritten

    def _build_rewrite_prompt(self, original_chapter: ChapterWriteOutput,
                              review_feedback, chapter_spec: Dict,
                              variations: RetryVariations, preceding_summary: str,
                              chapter_data: Dict = None) -> str:
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
        if variations.strip_reasoning:
            # Same no-reasoning note as _build_write_prompt: the engine's
            # EMPTY_CONTENT ladder mutates with strip_reasoning.
            prompt = f"直接输出正式章节内容，不要输出任何思考过程。\n{prompt}"
        if variations.strict_json_prefix:
            # Same delimiter reinforcement as _build_write_prompt.
            prompt = f"{prompt}\n{_DELIMITER_FORMAT_REINFORCEMENT}"
        return prompt

    def _content_contract_reject(self, chapter: ChapterWriteOutput,
                                 chapter_spec: Dict) -> str:
        """I1 内容契约门（write/rewrite/patch 三钩子共用）。

        对已判 ready 的章节跑统一健全检查；min_length=50 是引擎深处的既有
        下限（章节级 400 下限仍由组装口把关），显式传 50 避免微型测试夹具
        被杀。返回 fail 代码串；通过时返回空串。
        """
        verdict = check_content(
            str(chapter.content or ""), kind="chapter",
            data_points_count=len(chapter.data_points_used or []),
            section_name=str((chapter_spec or {}).get("section_name", "") or ""),
            min_length=50,
            language=current_report_language(),
        )
        if verdict.passed:
            return ""
        return ",".join(verdict.fail_codes)

    def _rewrite_parse_with_outcome(self, raw_output: str, chapter_spec: Dict,
                                    original_len: int) -> ParseOutcome:
        """Retry-engine classification hook for rewrite().

        ok requires a ready chapter that passes the F1b acceptance rule: a
        rewrite must not shrink a real chapter below a third of its original
        length (or below a small absolute floor for micro chapters).  The
        rule is classified as degenerate so the engine retries with
        mutations; budget exhaustion then keeps the original chapter.
        """
        stripped = (raw_output or "").strip()
        if not stripped:
            return ParseOutcome(False, "no_json")
        if stripped in ("...", "。。。", "。") or len(stripped) < 30:
            return ParseOutcome(False, "degenerate")
        delimiter_chapter = self._parse_delimiter_format(raw_output, chapter_spec)
        if delimiter_chapter is not None:
            # Primary contract answered.  A ready rewrite still must pass the
            # F1b shrink rule — a tiny-but-valid delimiter rewrite must never
            # silently replace a full chapter (same contract as the JSON path
            # below); degenerate classification lets the engine retry.
            if str(getattr(delimiter_chapter, "status", "")).lower() == "ready":
                content_len = len(str(delimiter_chapter.content or "").strip())
                if original_len >= 600 and content_len < max(200, original_len // 3):
                    return ParseOutcome(False, "degenerate")
                if original_len < 600 and content_len < 50:
                    return ParseOutcome(False, "degenerate")
                # I1 contract check runs AFTER the shrink rule passes.
                if self._content_contract_reject(delimiter_chapter, chapter_spec):
                    return ParseOutcome(False, "degenerate")
            # Explicit failed status: engine-final, Defense rescue owns it.
            return ParseOutcome(True, value=delimiter_chapter)
        if _looks_like_meta_reasoning(stripped):
            # E1: meta-reasoning opens never contain the chapter; classify as
            # degenerate so the engine retries with mutations and budget
            # exhaustion keeps the last known good chapter (F1b contract).
            return ParseOutcome(False, "degenerate")
        try:
            chapter = self._parse_output(raw_output, chapter_spec)
        except Exception as parse_error:
            logger.warning("ChapterWriter rewrite parse hook crashed: %s", parse_error)
            return ParseOutcome(False, "no_json")
        if (
            str(getattr(chapter, "status", "")).lower() == "ready"
            and len(str(chapter.content or "").strip())
        ):
            content_len = len(str(chapter.content or "").strip())
            # F1b acceptance rule as classification (mirrors the retired
            # post-call guard in the legacy rewrite path).
            if original_len >= 600 and content_len < max(200, original_len // 3):
                return ParseOutcome(False, "degenerate")
            if original_len < 600 and content_len < 50:
                return ParseOutcome(False, "degenerate")
            # I1 contract check runs AFTER the shrink rule passes.
            if self._content_contract_reject(chapter, chapter_spec):
                return ParseOutcome(False, "degenerate")
            return ParseOutcome(True, value=chapter)
        # Output looked like JSON but no usable chapter came out of it.
        if "```json" not in stripped and not stripped.lstrip().startswith("{"):
            return ParseOutcome(False, "no_json")
        return ParseOutcome(False, "truncated")

    async def patch_data(self, chapter: ChapterWriteOutput,
                         patch_instructions: List[str],
                         framework_config: Dict) -> ChapterWriteOutput:
        chapter_spec = {
            "section_id": chapter.chapter_id,
            "section_name": chapter.title,
            "sub_section_id": chapter.sub_section_id,
        }
        original_len = len(str(chapter.content or "").strip())
        try:
            # Same engine contract as rewrite(): the F1/F1b "keep last known
            # good" acceptance rules are classified by the parse hook; failed,
            # empty and degenerate patches are retried by the engine, and
            # budget exhaustion keeps the original chapter intact (a failed
            # patch is a repair attempt, not a chapter replacement).
            patched = await call_llm_ex(
                lambda variations: self._build_patch_prompt(
                    chapter, patch_instructions, framework_config, variations),
                output_contract=DELIMITER_OUTPUT_CONTRACT,
                expected_output_chars=max(2000, original_len),
                parse=lambda raw: self._patch_parse_with_outcome(
                    raw, chapter_spec, original_len),
                stream=self._use_streaming,
                on_token=None,
                task_tag=f"patch:{chapter.chapter_id}",
            )
        except LLMBudgetExhausted as exhausted:
            logger.warning(
                "ChapterWriter.patch_data kept original content for chapter %s "
                "after engine budget exhaustion: %s",
                chapter.chapter_id, exhausted,
            )
            return chapter
        # Engine success returns the parse hook's chapter value; the legacy
        # escape hatch (LLM_RETRY_ENGINE=legacy) returns a raw string.
        if not isinstance(patched, ChapterWriteOutput):
            patched = self._parse_output(str(patched or ""), chapter_spec)
        patched.data_points_used = self._merge_patched_data_points(
            chapter.data_points_used, patched.data_points_used,
            chapter_id=chapter.chapter_id,
            sub_section_id=chapter.sub_section_id,
        )
        return patched

    def _build_patch_prompt(self, chapter: ChapterWriteOutput,
                            patch_instructions: List[str], framework_config: Dict,
                            variations: RetryVariations) -> str:
        prompt = self._prompts.get(
            "chapter_patch_data",
            chapter_content=chapter.content,
            patch_instructions=chr(10).join(f'- {inst}' for inst in patch_instructions),
            section_name=chapter.title,
            section_id=chapter.chapter_id,
        )
        if variations.strip_reasoning:
            # Same no-reasoning note as _build_write_prompt.
            prompt = f"直接输出正式章节内容，不要输出任何思考过程。\n{prompt}"
        if variations.strict_json_prefix:
            # Same delimiter reinforcement as _build_write_prompt.
            prompt = f"{prompt}\n{_DELIMITER_FORMAT_REINFORCEMENT}"
        return prompt

    def _patch_parse_with_outcome(self, raw_output: str, chapter_spec: Dict,
                                  original_len: int) -> ParseOutcome:
        """Retry-engine classification hook for patch_data().

        Same F1/F1b acceptance rule as the rewrite hook (identical
        thresholds, single source of truth): failed/empty patches and
        degenerate scraps are rejected so the engine retries with
        mutations; budget exhaustion keeps the original chapter.
        """
        return self._rewrite_parse_with_outcome(raw_output, chapter_spec, original_len)

    @staticmethod
    def _merge_patched_data_points(
        original: List[DataPoint],
        patched: List[DataPoint],
        *,
        chapter_id: str,
        sub_section_id: str = "",
    ) -> List[DataPoint]:
        """Preserve evidence identity when an LLM patch omits unchanged fields."""
        original_by_metric = {
            str(point.metric).strip().lower(): point
            for point in (original or [])
            if str(point.metric).strip()
        }
        merged: List[DataPoint] = []
        seen_metrics = set()
        for point in patched or []:
            metric_key = str(point.metric).strip().lower()
            previous = original_by_metric.get(metric_key)
            if previous is not None:
                for field_name in (
                    "source", "source_url", "evidence_id", "provenance_id",
                    "evidence_excerpt", "locator",
                    "geographic_scope", "period", "population", "epistemic_level",
                    "evidence_status",
                ):
                    current_value = getattr(point, field_name, "")
                    previous_value = getattr(previous, field_name, "")
                    if (
                        not current_value
                        or (
                            field_name == "evidence_status"
                            and current_value == "unverified"
                            and previous_value == "verified"
                        )
                    ):
                        setattr(point, field_name, getattr(previous, field_name, ""))
            point.chapter_id = point.chapter_id or chapter_id
            point.sub_section_id = point.sub_section_id or sub_section_id
            merged.append(point)
            if metric_key:
                seen_metrics.add(metric_key)

        # Data patches are content corrections, not permission to discard
        # unchanged structured evidence. Keep omitted original points so the
        # final audit cannot lose valid citations merely because the LLM
        # returned a partial JSON payload.
        for point in original or []:
            metric_key = str(point.metric).strip().lower()
            if metric_key and metric_key not in seen_metrics:
                preserved = DataPoint(**{
                    field_name: getattr(point, field_name)
                    for field_name in DataPoint.__dataclass_fields__
                })
                preserved.chapter_id = preserved.chapter_id or chapter_id
                preserved.sub_section_id = preserved.sub_section_id or sub_section_id
                merged.append(preserved)
        return merged

    async def _call_llm_with_tools(self, prompt: str, raw_data_location: str) -> str:
        """Legacy tool-enabled call (read_json over the task raw-data cache).

        Kept as write()'s budget-exhaustion compatibility fallback only:
        rewrite()/patch_data() and the primary write() path all go through
        the retry engine (call_llm_ex); the retired streaming 3x-retry
        loop lived above this method.
        """
        raw_path = Path(raw_data_location).resolve() if raw_data_location else None

        async def _read_raw_json(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
            if tool_name != "read_json":
                return {"success": False, "error": f"Unsupported tool: {tool_name}"}
            requested = Path(str(arguments.get("filepath", ""))).resolve()
            # The report writer may read only the current task's cache file.
            if raw_path is None or requested != raw_path:
                logger.warning("ChapterWriter denied file read outside current raw-data file: %s", requested)
                return {"success": False, "error": "Only the current task raw-data cache may be read"}
            skill = FileSkill(allowed_dirs=[str(raw_path.parent)])
            result = await skill.execute(action="read_json", filepath=str(requested))
            logger.info(
                "ChapterWriter raw-data read %s: success=%s",
                requested,
                result.get("success", False),
            )
            return result

        tools = [{
            "type": "function",
            "function": {
                "name": "read_json",
                "description": "Read the current report task's complete raw-data JSON cache. Use it before concluding that data is missing.",
                "parameters": {
                    "type": "object",
                    "properties": {"filepath": {"type": "string"}},
                    "required": ["filepath"],
                    "additionalProperties": False,
                },
            },
        }]
        result = await call_llm_with_tools(
            prompt=prompt,
            tools=tools,
            tool_handler=_read_raw_json,
            max_tokens=_chapter_max_tokens(),
            temperature=0.7,
        )
        # Fall back to the legacy call when an OpenAI-compatible endpoint does
        # not support tool calls; the report remains backward compatible.
        if result.get("error") == "llm_tool_call_failed":
            result = await call_llm(prompt=prompt, max_tokens=_chapter_max_tokens(), temperature=0.7)
        if not result.get("success"):
            raise RuntimeError(f"LLM call failed: {result}")
        return result["content"]

    def _parse_with_outcome(self, raw_output: str, chapter_spec: Dict) -> ParseOutcome:
        """Retry-engine classification hook: map raw output to a ParseOutcome.

        ok requires _parse_output to yield a ready chapter with real content;
        everything else is bucketed so the engine can pick the right mutation
        (truncated -> max_tokens x1.5, no_json/degenerate -> strict_json /
        switch_model).
        """
        stripped = (raw_output or "").strip()
        if not stripped:
            return ParseOutcome(False, "no_json")
        if stripped in ("...", "。。。", "。") or len(stripped) < 30:
            return ParseOutcome(False, "degenerate")
        delimiter_chapter = self._parse_delimiter_format(raw_output, chapter_spec)
        if delimiter_chapter is not None:
            # Primary contract answered (ready or an explicit failed status,
            # which the defense loop owns): a ready chapter must additionally
            # pass the I1 content contract before the engine accepts it.
            if str(getattr(delimiter_chapter, "status", "")).lower() == "ready":
                if self._content_contract_reject(delimiter_chapter, chapter_spec):
                    return ParseOutcome(False, "degenerate")
            return ParseOutcome(True, value=delimiter_chapter)
        if _looks_like_meta_reasoning(stripped):
            # E1: same self-defense as the rewrite hook — chain-of-thought /
            # repair narration is a degenerate output, never chapter content.
            return ParseOutcome(False, "degenerate")
        try:
            chapter = self._parse_output(raw_output, chapter_spec)
        except Exception as parse_error:
            logger.warning("ChapterWriter parse hook crashed: %s", parse_error)
            return ParseOutcome(False, "no_json")
        if (
            str(getattr(chapter, "status", "")).lower() == "ready"
            and len(str(chapter.content or "").strip()) >= 50
        ):
            if self._content_contract_reject(chapter, chapter_spec):
                return ParseOutcome(False, "degenerate")
            return ParseOutcome(True, value=chapter)
        # Output looked like JSON but no usable chapter came out of it.
        if "```json" not in stripped and not stripped.lstrip().startswith("{"):
            return ParseOutcome(False, "no_json")
        return ParseOutcome(False, "truncated")

    def _parse_delimiter_format(self, raw: str,
                                chapter_spec: Dict) -> Optional[ChapterWriteOutput]:
        """Parse the primary delimiter-based fixed format contract.

        Returns a ChapterWriteOutput whenever the reply carries the
        ``<<<REPORT_CHAPTER>>>`` marker (ready or failed), and None when the
        contract is absent so the JSON compatibility path still gets its turn.
        Post-processing mirrors ``_parse_output``: content sanitization,
        manifest-owned title, chapter-scoped data points.
        """
        text = str(raw or "")
        if _DELIMITER_START not in text:
            return None
        header = text.split(_DELIMITER_CONTENT_MARKER, 1)[0]
        status_match = re.search(
            r"^\s*STATUS\s*:\s*(\S+)", header, re.MULTILINE | re.IGNORECASE)
        title_match = re.search(
            r"^\s*TITLE\s*:\s*(.*)$", header, re.MULTILINE | re.IGNORECASE)
        status = status_match.group(1).strip().lower() if status_match else "ready"
        model_title = title_match.group(1).strip() if title_match else ""

        def _section(marker: str, next_markers) -> str:
            start = text.find(marker)
            if start == -1:
                return ""
            start += len(marker)
            ends = [pos for pos in (text.find(m, start) for m in next_markers)
                    if pos != -1]
            return text[start:min(ends)] if ends else text[start:]

        content = self._sanitize_report_content(
            _section(_DELIMITER_CONTENT_MARKER, _DELIMITER_NEXT_AFTER_CONTENT))
        conclusions = []
        for line in _section(
                _DELIMITER_CONCLUSIONS_MARKER,
                _DELIMITER_NEXT_AFTER_CONCLUSIONS).splitlines():
            conclusion = line.strip().lstrip("-").strip()
            if conclusion:
                conclusions.append(conclusion)
        # I1 一行式结论检查：元思考行/残留行直接丢弃（key_conclusions 曾是
        # 唯一从未设防的 LLM 生成面，经 payload 与顶层 conclusion join 双通道
        # 进入交付物）。
        conclusions = [c for c in conclusions if check_finding_line(c)]
        data_points = []
        for line in _section(
                _DELIMITER_DATAPOINTS_MARKER, (_DELIMITER_END,)).splitlines():
            parts = [p.strip() for p in line.strip().lstrip("-").strip().split("|")]
            if len(parts) < 2 or not parts[0] or not parts[1]:
                continue  # malformed data-point line
            data_points.append(DataPoint(
                metric=parts[0],
                value=parts[1],
                unit=parts[2] if len(parts) > 2 else "",
                source=parts[3] if len(parts) > 3 else "",
                chapter_id=str(chapter_spec.get("section_id", "") or ""),
                sub_section_id=str(chapter_spec.get("sub_section_id", "") or ""),
            ))

        manifest_title = str(chapter_spec.get("section_name", "") or "").strip()
        if status != "ready" or len(content) < 50:
            issue = (
                "章节生成失败（模型报告 failed）"
                if status != "ready"
                else "章节输出 content 过短，视为生成失败"
            )
            # I2: self_check 无确定性消费者（LLM 评审提示词不算）
            FailureAudit.record(
                stage="report.write",
                subject_id=str(chapter_spec.get("section_id", "") or ""),
                action="self_check_flagged",
                reason=";".join([issue])[:200],
                task_id="",
            )
            return ChapterWriteOutput(
                chapter_id=chapter_spec.get("section_id", ""),
                title=manifest_title,
                content="",
                sub_section_id=str(chapter_spec.get("sub_section_id", "") or ""),
                data_points_used=[],
                key_conclusions=[],
                self_check_passed=False,
                self_check_issues=[issue],
                status="failed",
                error=issue,
            )
        return ChapterWriteOutput(
            chapter_id=chapter_spec.get("section_id", ""),
            title=manifest_title or model_title,
            content=content,
            sub_section_id=str(chapter_spec.get("sub_section_id", "") or ""),
            data_points_used=data_points,
            key_conclusions=conclusions,
        )

    def _materialize(self, outcome: ParseOutcome, chapter_spec: Dict) -> ChapterWriteOutput:
        # test-support helper; write() inlines the equivalent for the success path
        if outcome.ok and isinstance(outcome.value, ChapterWriteOutput):
            return outcome.value
        return self._parse_output("", chapter_spec)

    DATAPOINT_STR_FIELDS = {
        "metric", "value", "unit", "source", "chapter_id", "sub_section_id", "source_url",
        "evidence_id", "provenance_id", "evidence_excerpt", "locator",
        "geographic_scope", "period", "population",
        "epistemic_level", "evidence_status",
    }

    def _coerce_data_point(self, dp_dict: Dict[str, Any]) -> DataPoint:
        if not isinstance(dp_dict, dict):
            raise TypeError("data_points_used 的每个元素必须是对象")
        coerced = {}
        for k, v in dp_dict.items():
            if k in self.DATAPOINT_STR_FIELDS and not isinstance(v, str):
                coerced[k] = str(v)
            else:
                coerced[k] = v
        for required_field in ("metric", "value", "unit", "source"):
            coerced.setdefault(required_field, "")
        return DataPoint(**{k: v for k, v in coerced.items() if k in DATAPOINT_FIELDS})

    def _parse_output(self, raw: str, chapter_spec: Dict) -> ChapterWriteOutput:
        _SKIP_TITLES = {
            "数据精准修补任务", "章节精修任务", "章节精修润色任务", "章节撰写任务",
            "核心结论", "核心判断", "核心发现",
            "论证与分析", "逻辑推导", "论证", "分析",
            "数据支撑", "数据支持", "数据来源",
            "风险提示", "风险与不确定性",
            "核心结论与论证分析", "核心结论与论证",
            "核心结论与数据支撑", "论证分析与数据支撑",
        }
        _GENERIC_PATTERNS = ("核心结论", "核心判断", "核心发现", "论证与分析", "数据支撑", "数据支持", "数据来源", "风险提示", "风险与不确定性")
        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', raw, re.DOTALL)
            json_str = None
            if json_match:
                json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_match.group(1))
            else:
                logger.warning(f"ChapterWriter: no ```json``` block found, trying raw JSON. Raw len={len(raw)}")
                brace_match = re.search(r'\{.*\}', raw, re.DOTALL)
                if brace_match:
                    json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', brace_match.group(0))
                elif raw.lstrip().startswith("{"):
                    # Truncated JSON has no closing brace, so brace matching
                    # above fails while the prose is still intact.  Hand the
                    # whole reply to the prefix-repair loader.
                    json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', raw.lstrip())
            if json_str:
                data = self._load_chapter_json(json_str)
                if not isinstance(data, dict):
                    raise ValueError("章节输出必须是 JSON 对象")
                content = self._sanitize_report_content(data.get("content"))
                if not content:
                    raise ValueError("章节输出缺少非空 content")
                if "data_points_used" in data and not isinstance(data["data_points_used"], list):
                    raise ValueError("data_points_used 必须是数组")
                if "key_conclusions" in data and not isinstance(data["key_conclusions"], list):
                    raise ValueError("key_conclusions 必须是数组")
                if "self_check_issues" in data and not isinstance(data["self_check_issues"], list):
                    raise ValueError("self_check_issues 必须是数组")
                # The manifest owns the reader-facing chapter identity.  Do
                # not allow the model to rename a chapter or promote an
                # internal paragraph heading to chapter level.
                manifest_title = str(chapter_spec.get("section_name", "") or "").strip()
                writer_self_check_issues = [str(i) for i in data.get("self_check_issues", [])]
                if writer_self_check_issues:
                    # I2: 模型自检问题原本只进 LLM 评审提示词，无确定性消费者
                    FailureAudit.record(
                        stage="report.write",
                        subject_id=str(chapter_spec.get("section_id", "") or ""),
                        action="self_check_flagged",
                        reason=";".join(writer_self_check_issues)[:200],
                        task_id="",
                    )
                return ChapterWriteOutput(
                    chapter_id=chapter_spec.get("section_id", ""),
                    title=manifest_title,
                    content=content,
                    sub_section_id=str(chapter_spec.get("sub_section_id", "") or ""),
                    data_points_used=[
                        self._coerce_data_point(dp)
                        for dp in data.get("data_points_used", [])
                    ],
                    key_conclusions=[
                        str(c) for c in data.get("key_conclusions", [])
                        if check_finding_line(str(c))
                    ],
                    self_check_passed=data.get("self_check_passed", True),
                    self_check_issues=writer_self_check_issues,
                    planning_assessment=data.get("planning_assessment"),
                )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to parse structured output: {e}")

        # A reply without a JSON envelope (or one that cannot be repaired)
        # still often contains the finished chapter as Markdown.  Salvage it
        # before falling back to the failed placeholder.
        salvaged = self._salvage_chapter_prose(raw, chapter_spec)
        if salvaged is not None:
            if _looks_like_meta_reasoning(str(salvaged.content or "")):
                # E1: with the reviewer budget exhausted nothing else catches
                # meta-reasoning, so the parse layer must self-defend: the
                # salvaged "prose" is repair narration, not a chapter.  Drop
                # it into the normal failed->rescue flow.
                logger.warning(
                    "ChapterWriter salvage rejected meta-reasoning output for %s",
                    (chapter_spec or {}).get("section_id"),
                )
            else:
                # I4 兜底同验收：salvage 产出必须通过与主路径相同的 I1
                # 检查（C1-C6；此前仅元思考单门）。垃圾兜底按失败处理，
                # 落入下方 failed 占位符流程，绝不降格验收。
                salvage_verdict = check_content(
                    str(salvaged.content or ""),
                    kind="chapter",
                    min_length=_SALVAGE_MIN_CHARS,
                    section_name=str((chapter_spec or {}).get("section_name", "") or ""),
                    language=current_report_language(),
                )
                if not salvage_verdict.passed:
                    logger.warning(
                        "[CONTENT_CONTRACT] ChapterWriter salvage rejected for %s: %s",
                        (chapter_spec or {}).get("section_id"),
                        salvage_verdict.fail_codes,
                    )
                    FailureAudit.record(
                        stage="report.write.salvage",
                        subject_id=str((chapter_spec or {}).get("section_id", "") or ""),
                        action="content_contract_rejected",
                        reason=f"salvage failed I1: {salvage_verdict.fail_codes}",
                        task_id="",
                    )
                else:
                    return salvaged

        # A malformed model response is a quality/diagnostic failure, not
        # report content.  Returning the raw response here used to leak JSON
        # fragments, tool traces, and model instructions into HTML.  Keep the
        # chapter object so assembly can remain non-blocking, while making the
        # failed state explicit for formal and diagnostic consumers.
        parse_issue = "JSON解析失败，输出格式不规范"
        # I2: self_check 无确定性消费者（LLM 评审提示词不算）
        FailureAudit.record(
            stage="report.write",
            subject_id=str(chapter_spec.get("section_id", "") or ""),
            action="self_check_flagged",
            reason=parse_issue,
            task_id="",
        )
        return ChapterWriteOutput(
            chapter_id=chapter_spec.get("section_id", ""),
            title=chapter_spec.get("section_name", ""),
            content="",
            sub_section_id=str(chapter_spec.get("sub_section_id", "") or ""),
            data_points_used=[],
            key_conclusions=[],
            self_check_passed=False,
            self_check_issues=[parse_issue],
            status="failed",
            error=parse_issue,
        )

    @staticmethod
    def _load_chapter_json(json_str: str) -> Any:
        """Progressively repair truncated/envelope-broken chapter JSON.

        Long chapters are routinely cut off mid-JSON by the output budget;
        without recovery the whole chapter is lost even when the prose is
        complete.  Every candidate must still decode to a JSON object with a
        non-empty ``content`` field to be accepted by the caller.
        """
        try:
            return json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            pass
        repaired = re.sub(r",\s*([}\]])", r"\1", json_str)
        if repaired != json_str:
            try:
                return json.loads(repaired)
            except (json.JSONDecodeError, ValueError):
                pass
        # Truncation repair: keep only the decodable prefix, then close the
        # open string/object/array scopes in reverse order.
        decoder = json.JSONDecoder()
        for end in range(len(json_str), 0, -1):
            prefix = json_str[:end].rstrip()
            if len(prefix) < len(json_str) - 256:
                break
            closers: List[str] = []
            in_string = False
            escaped = False
            stack: List[str] = []
            for ch in prefix:
                if in_string:
                    if escaped:
                        escaped = False
                    elif ch == "\\":
                        escaped = True
                    elif ch == '"':
                        in_string = False
                elif ch == '"':
                    in_string = True
                elif ch in "{[":
                    stack.append(ch)
                elif ch in "}]":
                    if stack and ((ch == "}" and stack[-1] == "{") or (ch == "]" and stack[-1] == "[")):
                        stack.pop()
            if in_string:
                closers.append('"')
            for opener in reversed(stack):
                closers.append("}" if opener == "{" else "]")
            candidate = prefix + "".join(closers)
            try:
                return json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                continue
        raise ValueError("章节输出缺少可解析的 JSON 对象")

    def _salvage_chapter_prose(self, raw: str, chapter_spec: Dict) -> Any:
        """Rescue prose from a reply that is not valid chapter JSON.

        The model sometimes answers with bare Markdown (a fenced
        ```markdown block or plain headings) instead of the requested JSON
        envelope.  When the prose is long enough to be a real chapter, keep
        it — flagged in self_check_issues — instead of failing the chapter.
        Returns None when nothing trustworthy can be salvaged.
        """
        text = str(raw or "")
        fenced = re.search(r"```(?:markdown|md)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
        envelope_only = re.match(r'\s*\{\s*"(?:content|title)"\s*:\s*"', text)
        candidates = [fenced.group(1)] if fenced else []
        candidates.append(re.sub(r"```json\s*.*?\s*```", "", text, flags=re.DOTALL))
        if envelope_only:
            # A truncated reply may open a JSON envelope without ever closing
            # it; from that point on every chunk is chapter prose.
            stripped = text[envelope_only.end():]
            stripped = stripped.replace("\\n", "\n").replace('\\"', '"')
            candidates.append(stripped.rstrip('"').rstrip())
        for candidate in candidates:
            candidate = re.sub(r"^\s*(?:json|markdown|md)\s*", "", candidate)
            # A candidate that is still envelope-shaped must take the JSON
            # path, never the prose path.  Without this check a ```json
            # reply whose decode failed leaks the whole envelope (including
            # escaped-\\n planning text) into the report body.
            if candidate.lstrip().startswith("{"):
                try:
                    data = self._load_chapter_json(candidate)
                except (json.JSONDecodeError, ValueError, KeyError, TypeError):
                    continue
                if isinstance(data, dict) and str(
                    self._sanitize_report_content(data.get("content")) or ""
                ).strip():
                    manifest_title = str(chapter_spec.get("section_name", "") or "").strip()
                    content = self._sanitize_report_content(data.get("content"))
                    # I2: self_check 无确定性消费者（LLM 评审提示词不算）
                    FailureAudit.record(
                        stage="report.write",
                        subject_id=str(chapter_spec.get("section_id", "") or ""),
                        action="self_check_flagged",
                        reason="章节输出经容错 JSON 解析恢复",
                        task_id="",
                    )
                    return ChapterWriteOutput(
                        chapter_id=chapter_spec.get("section_id", ""),
                        title=manifest_title,
                        content=content,
                        sub_section_id=str(chapter_spec.get("sub_section_id", "") or ""),
                        self_check_passed=False,
                        self_check_issues=["章节输出经容错 JSON 解析恢复"],
                    )
                continue
            if re.search(r'"content"\s*:\s*"', candidate):
                continue
            content = self._sanitize_report_content(candidate)
            if len(content) < _SALVAGE_MIN_CHARS:
                continue
            if not re.search(r"^#{1,4}\s+\S", content, re.MULTILINE):
                continue
            manifest_title = str(chapter_spec.get("section_name", "") or "").strip()
            # I2: self_check 无确定性消费者（LLM 评审提示词不算）
            FailureAudit.record(
                stage="report.write",
                subject_id=str(chapter_spec.get("section_id", "") or ""),
                action="self_check_flagged",
                reason="章节输出未使用 JSON 信封，已抢救 Markdown 正文",
                task_id="",
            )
            return ChapterWriteOutput(
                chapter_id=chapter_spec.get("section_id", ""),
                title=manifest_title,
                content=content,
                sub_section_id=str(chapter_spec.get("sub_section_id", "") or ""),
                self_check_passed=False,
                self_check_issues=["章节输出未使用 JSON 信封，已抢救 Markdown 正文"],
            )
        return None

    @staticmethod
    def _sanitize_report_content(content: Any) -> str:
        """Remove model work-log leakage from user-facing chapter content.

        Chapter content is a deliverable, not a transcript.  Models sometimes
        put cache-reading attempts or rewrite instructions inside the JSON
        ``content`` field even when the surrounding response is valid JSON.
        Keep the actual chapter starting at the first Markdown heading and
        discard trailing instructions addressed to the user.
        """
        text = str(content or "").strip()
        if not text:
            return text

        # These are prompt/input sentinels, not reader-facing prose.  Remove
        # only complete lines so legitimate qualitative discussion of a data
        # gap remains available to the report.
        internal_placeholders = (
            "无可用数据",
            "无原始数据摘要",
            "无可用原始搜索证据",
            "无明确章节需求",
            "无分析初稿，请基于数据从头撰写",
            "未提供（请使用当前任务",
            "数据来源待补充",
        )
        text = "\n".join(
            line for line in text.splitlines()
            if not any(placeholder in line for placeholder in internal_placeholders)
        ).strip()
        if not text:
            return text

        internal_start = re.search(r"\[数据获取尝试\]", text)
        if internal_start:
            heading = re.search(r"\n#{1,6}\s+", text[internal_start.end():])
            if heading:
                # Drop the model's preamble as well; it is an execution
                # transcript, not report prose.
                text = text[internal_start.end() + heading.start():]
            else:
                text = text[:internal_start.start()]

        rewrite_note = re.search(r"(?:\n---\s*\n|\n)\s*\**改写说明\**\s*[：:]", text)
        if rewrite_note:
            text = text[:rewrite_note.start()]

        # A user-directed offer at the end is also internal narration.
        text = re.split(r"\n\s*如果您需要(?:更简练|进一步|继续)", text, maxsplit=1)[0]
        return ChapterWriter._normalize_source_lists(text.strip())

    @staticmethod
    def _normalize_source_lists(text: str) -> str:
        """Render Python/Markdown URL lists as readable linked source names."""
        # Stop at a paragraph boundary, not the first `]` inside a Markdown
        # link.  The latter caused only the first URL fragment to be matched.
        pattern = re.compile(
            r"来源\s*[：:]\s*(\[[^\r\n。！？]*https?://[^\r\n。！？]*\])",
            re.DOTALL,
        )

        def replace(match: re.Match) -> str:
            raw = match.group(1)[1:-1]
            # Accept both Markdown links and the common Python repr emitted
            # by models (including HTML-escaped quotes after export).
            links = re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", raw)
            if not links:
                links = [("", url) for url in re.findall(r"https?://[^\s,\]'\"]+", raw)]
            if not links:
                return match.group(0)
            rendered = []
            for label, url in links:
                label = label.strip().strip("'\"")
                if label.startswith(("http://", "https://")):
                    parsed = urlparse(url)
                    label = parsed.netloc.removeprefix("www.") or url
                rendered.append(f"[{label}]({url})")
            return "来源：" + "、".join(rendered)

        return pattern.sub(replace, text)

    @staticmethod
    def _extract_conclusions(text: str) -> List[str]:
        lines = text.split("\n")
        conclusions = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("- **") and "结论" in stripped:
                conclusions.append(stripped.lstrip("- ").strip("*"))
        return conclusions[:5]
