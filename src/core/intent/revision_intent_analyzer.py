from __future__ import annotations
import json
import logging
import re as regex_module
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from uuid import uuid4

logger = logging.getLogger(__name__)

from ..adjustment.revision_types import (
    RevisionOpType, RevisionAction, RevisionTarget, AnalysisResult,
    LocationStrategy, SectionRef, RefType, Report,
)

# LLM 意图分析系统提示词
_REVISION_SYSTEM_PROMPT = """You are a revision intent analyzer for a research report system.
Analyze the user's revision request and output a structured JSON describing the revision intents.

Available revision operations:
- modify: change existing content
- delete: remove a section
- add: insert new content
- copy: duplicate content from one section to another
- merge: combine multiple sections
- split: divide a section
- swap: exchange content between two sections
- reorder: rearrange section order
- dedup: remove duplicate content
- style: change formatting/style
- update_title: Change the report title. Set "content" to the new title.
- replace_text: Replace text. Set parameters["old_text"] and "content".
- change_case: Change case. Set parameters["case_style"] to "upper"/"lower"/"title".
- fix_punctuation: Fix punctuation. Set parameters["punct_rule"] to "cn2en"/"en2cn".
- modify_table: Modify a table cell. Set parameters["table_index"], "row", "col", "value". Heavy track.
- modify_chart: Replace an image. Set parameters["img_index"], "alt", "src". Heavy track.
- delete_element: Delete a table or image. Set parameters["element_type"] ("table"/"image"), "element_index". Heavy track.
- add_element: Add a table or image to a section. Set "content" to the Markdown. Heavy track.
- translate: Translate the report content. Set parameters["target_lang"] to "en"/"zh"/"ja"/etc. Heavy track.

IMPORTANT - Implicit intent inference:
Users often express revision needs implicitly rather than with explicit action verbs. You MUST infer implicit revision intents:
- If the user questions report quality (e.g. "为什么评分低", "why is the score so low", "这个章节写得不好"), this implies dissatisfaction and desire to improve. Map to "modify" for the relevant sections.
- If the user expresses that something is insufficient (e.g. "深度不够", "数据不足", "not enough detail"), infer the intent to improve/expand the relevant content. Map to "modify".
- If the user asks "why" about a poor metric or low score, infer the intent to investigate and improve. Map to "modify" with the relevant section as target.
- When the user's feedback applies to the report as a whole (e.g. "整体评分只有52.4", "overall quality is poor"), set "is_global_feedback" to true.
- Do NOT return empty intents for such requests — instead, map them to appropriate revision operations (e.g. "modify" for the relevant sections with "is_global_feedback"=true).

IMPORTANT - Target specification rules:
For "add" operations:
- Set "target.raw_text" to the NEW section title you want to add
- Set "source.raw_text" to the EXISTING section title AFTER WHICH to insert
  (use the exact title from the report, e.g. "竞争格局" not "竞争部分")

For "modify" operations:
- Set "target.raw_text" to the EXACT section title from the report
  (e.g. "营收分析" not "营收数据" or "revenue section")
- Use "suggested_section" to hint which section if target is ambiguous

Output format:
{output_schema}
"""

_REVISION_USER_PROMPT_TEMPLATE = """User's revision request: {user_message}

{section_context}

Analyze the above request and identify the revision intents.
Output ONLY valid JSON, no other text."""


REVISION_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "intents": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action_type": {
                        "type": "string",
                        "enum": [
                            "modify", "delete", "add", "copy", "merge",
                            "split", "swap", "reorder", "dedup", "style",
                            "update_title", "replace_text", "change_case",
                            "fix_punctuation", "modify_table", "modify_chart",
                            "delete_element", "add_element",
                            "translate",
                        ],
                    },
                    "target": {
                        "type": "object",
                        "properties": {
                            "raw_text": {"type": "string"},
                            "section_refs": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "uuid": {"type": "string"},
                                        "ref_type": {
                                            "type": "string",
                                            "enum": ["uuid", "number", "index"],
                                        },
                                        "number": {"type": "string"},
                                        "index": {"type": "integer"},
                                        "parent_id": {"type": "string"},
                                        "raw_text": {"type": "string"},
                                    },
                                    "required": ["uuid", "ref_type"],
                                },
                            },
                            "location_strategy": {
                                "type": "string",
                                "enum": ["ordinal", "reference", "keyword", "semantic"],
                            },
                            "is_ambiguous": {"type": "boolean"},
                        },
                        "required": ["raw_text", "section_refs", "location_strategy", "is_ambiguous"],
                    },
                    "source": {
                        "type": "object",
                        "properties": {
                            "raw_text": {"type": "string"},
                            "section_refs": {"type": "array", "items": {"type": "object"}},
                            "location_strategy": {"type": "string"},
                            "is_ambiguous": {"type": "boolean"},
                        },
                    },
                    "content": {"type": "string"},
                    "parameters": {"type": "object"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "ambiguity_flags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["action_type", "target"],
            },
        },
        "needs_clarification": {"type": "boolean"},
        "clarification_questions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "is_uncertain": {"type": "boolean"},
        "suggested_section": {"type": "string"},
        "is_global_feedback": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["intents"],
}


INTENT_TO_REVISION_MAP_V2: Dict[str, RevisionOpType] = {}

_IMPLICIT_INTENT_PATTERNS = regex_module.compile(r"placeholder_not_used", regex_module.IGNORECASE)

_GLOBAL_FEEDBACK_PATTERNS = regex_module.compile(r"placeholder_not_used", regex_module.IGNORECASE)


def _init_patterns_from_registry() -> None:
    from ..intent.keyword_registry import get_registry
    registry = get_registry()
    global INTENT_TO_REVISION_MAP_V2, _IMPLICIT_INTENT_PATTERNS, _GLOBAL_FEEDBACK_PATTERNS

    INTENT_TO_REVISION_MAP_V2.clear()
    for pattern_str, action_type_str in registry.get_revision_pattern_strings().items():
        try:
            op_type = RevisionOpType(action_type_str)
            INTENT_TO_REVISION_MAP_V2[pattern_str] = op_type
        except (ValueError, TypeError):
            continue

    ii = registry.get_implicit_pattern_strings()
    zh_parts = "|".join(ii.get("chinese", []))
    en_parts = "|".join(ii.get("english", []))
    combined = zh_parts + "|" + en_parts if zh_parts and en_parts else zh_parts or en_parts or "placeholder"
    _IMPLICIT_INTENT_PATTERNS = regex_module.compile(combined, regex_module.IGNORECASE)

    gf = registry.get_global_feedback_pattern_strings()
    zh_gf = "|".join(gf.get("chinese", []))
    en_gf = "|".join(gf.get("english", []))
    combined_gf = zh_gf + "|" + en_gf if zh_gf and en_gf else zh_gf or en_gf or "placeholder"
    _GLOBAL_FEEDBACK_PATTERNS = regex_module.compile(combined_gf, regex_module.IGNORECASE)


_init_patterns_from_registry()

_REF_TYPE_MAP: Dict[str, RefType] = {
    "uuid": RefType.UUID,
    "number": RefType.NUMBER,
    "index": RefType.INDEX,
}

_LOCATION_STRATEGY_MAP: Dict[str, LocationStrategy] = {
    "ordinal": LocationStrategy.ORDINAL,
    "reference": LocationStrategy.REFERENCE,
    "keyword": LocationStrategy.KEYWORD,
    "semantic": LocationStrategy.SEMANTIC,
}


class RevisionIntentAnalyzer:
    MAX_LLM_RETRIES = 2

    async def analyze(
        self,
        user_message: str,
        report: object,
        previous_analysis: Optional[AnalysisResult] = None,
    ) -> AnalysisResult:
        if not user_message or not user_message.strip():
            return AnalysisResult(
                intents=[],
                needs_clarification=False,
                clarification_questions=[],
                is_uncertain=True,
                suggested_section=None,
                is_global_feedback=False,
                confidence=0.0,
            )

        for attempt in range(self.MAX_LLM_RETRIES):
            raw_json = await self._call_llm(user_message, report)
            result = await self.validate_llm_output(raw_json)
            if result is not None:
                return result

        fallback = await self.fallback_to_regex(user_message)
        return fallback

    def _build_section_context(self, report) -> str:
        if report is None:
            return ""
        try:
            sections = getattr(report, "sections", None)
            if sections is None:
                return ""
            lines = ["Current report sections:"]
            for i, sec in enumerate(sections):
                title = getattr(sec, "title", None) or getattr(sec, "id", None) or ""
                if title:
                    lines.append(f"  {i+1}. {title}")
            if len(lines) <= 1:
                return ""
            return "\n".join(lines)
        except Exception:
            return ""

    async def _call_llm(self, user_message: str, report: object) -> str:
        try:
            from src.skills.llm_skill import LLMSkill
            from src.config.settings import settings as app_settings
            llm_skill = LLMSkill()

            system_prompt = _REVISION_SYSTEM_PROMPT.format(
                output_schema=json.dumps(REVISION_JSON_SCHEMA, ensure_ascii=False, indent=2)
            )
            section_context = self._build_section_context(report)
            user_prompt = _REVISION_USER_PROMPT_TEMPLATE.format(
                user_message=user_message,
                section_context=section_context,
            )

            result = await llm_skill.execute(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=app_settings.llm.cheap_model,
                max_tokens=2048,
                temperature=0.3,
            )
            if not result.get("success"):
                logger.warning(f"LLM intent analysis failed: {result.get('error', 'unknown')}")
                return "{}"
            content = result.get("content", "")
            if not content or not content.strip():
                return "{}"

            json_match = regex_module.search(r'\{.*\}', content, regex_module.DOTALL)
            if json_match:
                return json_match.group(0)
            return content.strip()
        except Exception as e:
            logger.warning(f"LLM call failed, falling back to regex: {e}")
            return "{}"

    async def validate_llm_output(
        self, raw_json: str
    ) -> Optional[AnalysisResult]:
        try:
            data = json.loads(raw_json)
        except (json.JSONDecodeError, ValueError, TypeError):
            return None

        if not isinstance(data, dict):
            return None

        intents_data = data.get("intents", [])
        if not isinstance(intents_data, list):
            return None

        intents: List[RevisionAction] = []
        for item in intents_data:
            if not isinstance(item, dict):
                continue
            action = self._parse_intent_to_action(item)
            if action is not None:
                intents.append(action)

        if not intents:
            return None

        return AnalysisResult(
            intents=intents,
            needs_clarification=bool(data.get("needs_clarification", False)),
            clarification_questions=data.get("clarification_questions", []),
            is_uncertain=bool(data.get("is_uncertain", False)),
            suggested_section=data.get("suggested_section"),
            is_global_feedback=bool(data.get("is_global_feedback", False)),
            confidence=float(data.get("confidence", 1.0)),
        )

    def _parse_intent_to_action(
        self, intent_dict: Dict[str, Any]
    ) -> Optional[RevisionAction]:
        try:
            action_type_str = intent_dict.get("action_type", "unknown")
            action_type = RevisionOpType(action_type_str)
        except (ValueError, TypeError):
            return None

        target_data = intent_dict.get("target", {})
        if not isinstance(target_data, dict):
            return None

        section_refs: List[SectionRef] = []
        for ref_data in target_data.get("section_refs", []):
            if not isinstance(ref_data, dict):
                continue
            ref_type_str = ref_data.get("ref_type", "uuid")
            ref_type = _REF_TYPE_MAP.get(ref_type_str, RefType.UUID)
            section_refs.append(
                SectionRef(
                    uuid=ref_data.get("uuid", str(uuid4())),
                    ref_type=ref_type,
                    number=ref_data.get("number"),
                    index=ref_data.get("index"),
                    parent_id=ref_data.get("parent_id"),
                    raw_text=ref_data.get("raw_text", ""),
                )
            )

        loc_strategy_str = target_data.get("location_strategy", "keyword")
        loc_strategy = _LOCATION_STRATEGY_MAP.get(
            loc_strategy_str, LocationStrategy.KEYWORD
        )

        target = RevisionTarget(
            raw_text=target_data.get("raw_text", ""),
            section_refs=section_refs,
            location_strategy=loc_strategy,
            is_ambiguous=bool(target_data.get("is_ambiguous", False)),
        )

        source_data = intent_dict.get("source")
        source: Optional[RevisionTarget] = None
        if isinstance(source_data, dict):
            source_section_refs: List[SectionRef] = []
            for ref_data in source_data.get("section_refs", []):
                if not isinstance(ref_data, dict):
                    continue
                sref_type_str = ref_data.get("ref_type", "uuid")
                sref_type = _REF_TYPE_MAP.get(sref_type_str, RefType.UUID)
                source_section_refs.append(
                    SectionRef(
                        uuid=ref_data.get("uuid", str(uuid4())),
                        ref_type=sref_type,
                        number=ref_data.get("number"),
                        index=ref_data.get("index"),
                        parent_id=ref_data.get("parent_id"),
                        raw_text=ref_data.get("raw_text", ""),
                    )
                )
            source_loc_str = source_data.get("location_strategy", "keyword")
            source_loc = _LOCATION_STRATEGY_MAP.get(source_loc_str, LocationStrategy.KEYWORD)
            source = RevisionTarget(
                raw_text=source_data.get("raw_text", ""),
                section_refs=source_section_refs,
                location_strategy=source_loc,
                is_ambiguous=bool(source_data.get("is_ambiguous", False)),
            )

        return RevisionAction(
            action_id=str(uuid4()),
            action_type=action_type,
            target=target,
            source=source,
            content=intent_dict.get("content"),
            parameters=intent_dict.get("parameters", {}),
            confidence=float(intent_dict.get("confidence", 1.0)),
            ambiguity_flags=intent_dict.get("ambiguity_flags", []),
        )

    async def fallback_to_regex(self, user_message: str) -> AnalysisResult:
        return await self._fallback_to_regex(user_message)

    async def _fallback_to_regex(self, user_message: str) -> AnalysisResult:
        matched_type = RevisionOpType.UNKNOWN
        max_priority = -1
        best_match_len = 0

        for pattern, op_type in INTENT_TO_REVISION_MAP_V2.items():
            try:
                match = regex_module.search(pattern, user_message)
                if match:
                    priority_score = len(regex_module.findall(pattern, user_message))
                    match_len = len(match.group(0))
                    if priority_score > max_priority or (priority_score == max_priority and match_len > best_match_len):
                        max_priority = priority_score
                        best_match_len = match_len
                        matched_type = op_type
            except regex_module.error:
                continue

        is_global = bool(_GLOBAL_FEEDBACK_PATTERNS.search(user_message))

        if matched_type == RevisionOpType.UNKNOWN:
            if _IMPLICIT_INTENT_PATTERNS.search(user_message):
                matched_type = RevisionOpType.MODIFY
            elif is_global:
                matched_type = RevisionOpType.MODIFY
            else:
                return self._degrade_unknown_intent(None)

        action = RevisionAction(
            action_id=str(uuid4()),
            action_type=matched_type,
            target=RevisionTarget(
                raw_text=user_message,
                section_refs=[],
                location_strategy=LocationStrategy.KEYWORD,
                is_ambiguous=True,
            ),
            content=None,
            confidence=0.25,
            ambiguity_flags=["regex_fallback"],
        )

        return AnalysisResult(
            intents=[action],
            needs_clarification=False,
            clarification_questions=[],
            is_uncertain=True,
            suggested_section=None,
            is_global_feedback=is_global,
            confidence=0.25,
        )

    def extract_actions(self, analysis: AnalysisResult) -> List[RevisionAction]:
        return list(analysis.intents)

    def _degrade_unknown_intent(
        self, report: object
    ) -> AnalysisResult:
        return AnalysisResult(
            intents=[],
            needs_clarification=True,
            clarification_questions=[
                "请描述您想要如何修改报告？例如：修改某段内容、添加新章节、删除某部分等。"
            ],
            is_uncertain=True,
            suggested_section=None,
            is_global_feedback=False,
            confidence=0.2,
        )
