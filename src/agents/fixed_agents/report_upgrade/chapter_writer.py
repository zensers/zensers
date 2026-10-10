import asyncio
import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from urllib.parse import urlparse

from .models import ChapterWriteInput, ChapterWriteOutput, DataPoint
from .prompt_manager import PromptManager
from src.core.llm_client import call_llm, call_llm_stream, call_llm_with_tools
from src.skills.file_skill import FileSkill

DATAPOINT_FIELDS = {
    "metric", "value", "unit", "source", "chapter_id", "sub_section_id", "confidence",
    "source_url", "evidence_id", "provenance_id", "evidence_excerpt", "locator",
    "geographic_scope", "period", "population",
    "epistemic_level", "evidence_status",
}

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


class ChapterWriter:

    def __init__(self, prompt_manager: PromptManager = None, use_streaming: bool = True) -> None:
        self._prompts = prompt_manager
        self._raw_data_location = ""
        self._use_streaming = bool(use_streaming)

    async def write(self, input_data: ChapterWriteInput) -> ChapterWriteOutput:
        self._raw_data_location = input_data.raw_data_location or ""
        chapter_spec = input_data.chapter_spec
        prompt_kwargs = dict(
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
            global_evidence_pool_json=json.dumps(input_data.global_evidence_pool, ensure_ascii=False, indent=2)
                                      if input_data.global_evidence_pool else '无可用原始搜索证据',
            raw_data_location=input_data.raw_data_location or '未提供（请使用当前任务的原始证据池）',
            chapter_requirements_json=json.dumps(input_data.chapter_requirements, ensure_ascii=False, indent=2)
                                      if input_data.chapter_requirements else '无明确章节需求',
            used_evidence_ids_json=json.dumps(input_data.used_evidence_ids, ensure_ascii=False),
        )
        prompt_name = "chapter_write_pptx" if input_data.output_format == "pptx" else "chapter_write"
        try:
            prompt = self._prompts.get(prompt_name, **prompt_kwargs)
        except FileNotFoundError:
            # Keep custom/legacy prompt directories working until they add the
            # optional PPT template.
            prompt = self._prompts.get("chapter_write", **prompt_kwargs)
        raw_output = await self._call_llm(
            prompt,
            raw_data_location=input_data.raw_data_location,
        )
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
        raw_output = await self._call_llm(prompt, raw_data_location=self._raw_data_location)
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
        raw_output = await self._call_llm(prompt, raw_data_location=self._raw_data_location)
        chapter_spec = {
            "section_id": chapter.chapter_id,
            "section_name": chapter.title,
            "sub_section_id": chapter.sub_section_id,
        }
        patched = self._parse_output(raw_output, chapter_spec)
        if (
            str(getattr(patched, "status", "ready") or "ready").lower() != "ready"
            or not str(patched.content or "").strip()
        ):
            # A failed patch is a repair attempt, not a chapter replacement.
            # Concretely: the defense repair loop must not swap a good chapter
            # for an empty parse-failed patch and let final assembly render the
            # '未生成可验证内容' placeholder.  Keep the original chapter intact.
            logger.warning(
                "ChapterWriter.patch_data dropped failed/empty patch for chapter %s; keeping original content",
                chapter.chapter_id,
            )
            return chapter
        patched.data_points_used = self._merge_patched_data_points(
            chapter.data_points_used, patched.data_points_used,
            chapter_id=chapter.chapter_id,
            sub_section_id=chapter.sub_section_id,
        )
        return patched

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

    async def _call_llm(self, prompt: str, raw_data_location: str = "") -> str:
        if self._use_streaming:
            # A provider timeout is retried before compatibility fallback. The
            # stream itself is an inactivity-timed transport, so a report that
            # continues to emit chunks is not subject to a hidden 120s total
            # deadline. Never replay a partially emitted response: doing so
            # would duplicate content and is less safe than surfacing the
            # failure to the report orchestrator.
            try:
                stream_retries = max(0, int(os.environ.get("LLM_STREAM_RETRIES", "2")))
            except (TypeError, ValueError):
                stream_retries = 2
            try:
                retry_delay = max(0.0, float(os.environ.get("LLM_STREAM_RETRY_DELAY_SECONDS", "1")))
            except (TypeError, ValueError):
                retry_delay = 1.0
            last_stream_error = None
            for attempt in range(stream_retries + 1):
                chunks = []
                try:
                    async for chunk in call_llm_stream(
                        prompt=prompt, max_tokens=_chapter_max_tokens(), temperature=0.7,
                    ):
                        if chunk:
                            chunks.append(str(chunk))
                    streamed_content = "".join(chunks).strip()
                    if streamed_content:
                        return streamed_content
                    raise RuntimeError("streaming LLM returned empty content")
                except Exception as stream_error:
                    last_stream_error = stream_error
                    if chunks:
                        raise RuntimeError(
                            "streaming LLM failed after partial output; refusing to replay it"
                        ) from stream_error
                    if attempt >= stream_retries:
                        break
                    logger.warning(
                        "ChapterWriter streaming call failed; retrying (%s/%s): %s",
                        attempt + 1, stream_retries, stream_error,
                    )
                    if retry_delay:
                        await asyncio.sleep(retry_delay * (2 ** attempt))
            # Streaming is the primary path. Tool-capable legacy calls remain
            # a compatibility fallback only after all configured stream
            # attempts have failed without producing content.
            logger.warning(
                "ChapterWriter streaming retries exhausted; using compatibility path: %s",
                last_stream_error,
            )

        # Preserve the legacy path for callers/tests that do not provide a
        # task-scoped raw-data file.  Tool use is enabled only when the report
        # has an explicit, validated file location.
        if not raw_data_location or not Path(raw_data_location).is_file():
            result = await call_llm(prompt=prompt, max_tokens=_chapter_max_tokens(), temperature=0.7)
            if not result.get("success"):
                raise RuntimeError(f"LLM call failed: {result}")
            return result["content"]
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
                return ChapterWriteOutput(
                    chapter_id=chapter_spec.get("section_id", ""),
                    title=manifest_title,
                    content=content,
                    sub_section_id=str(chapter_spec.get("sub_section_id", "") or ""),
                    data_points_used=[
                        self._coerce_data_point(dp)
                        for dp in data.get("data_points_used", [])
                    ],
                    key_conclusions=[str(c) for c in data.get("key_conclusions", [])],
                    self_check_passed=data.get("self_check_passed", True),
                    self_check_issues=[str(i) for i in data.get("self_check_issues", [])],
                    planning_assessment=data.get("planning_assessment"),
                )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to parse structured output: {e}")

        # A reply without a JSON envelope (or one that cannot be repaired)
        # still often contains the finished chapter as Markdown.  Salvage it
        # before falling back to the failed placeholder.
        salvaged = self._salvage_chapter_prose(raw, chapter_spec)
        if salvaged is not None:
            return salvaged

        # A malformed model response is a quality/diagnostic failure, not
        # report content.  Returning the raw response here used to leak JSON
        # fragments, tool traces, and model instructions into HTML.  Keep the
        # chapter object so assembly can remain non-blocking, while making the
        # failed state explicit for formal and diagnostic consumers.
        parse_issue = "JSON解析失败，输出格式不规范"
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
