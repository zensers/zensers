import re
import json
import asyncio
import hashlib
import logging
from dataclasses import asdict
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Set, Tuple

from .models import (
    ChapterWriteInput, ChapterWriteOutput, ChapterReviewInput, ChapterReviewOutput,
    ReviewInput, ReviewOutput, DataGap, DataConflict, DataPoint, DataConflictResolution,
    DataRepairResult, QualityIssueDiagnosis, ChapterDiagnostic, QualityReport,
    ChapterIssue, FixSuggestion, ReportEvidenceContext, ChapterRequirement,
)
from .data_registry import DataRegistry
from .chapter_writer import ChapterWriter, DATAPOINT_FIELDS

_DP_STR_KEYS = {
    "metric", "value", "unit", "source", "chapter_id", "sub_section_id", "source_url",
    "evidence_id", "provenance_id", "geographic_scope", "period", "population",
    "epistemic_level", "evidence_status",
}
from .chapter_reviewer import ChapterReviewAgent
from .global_reviewer import GlobalReviewAgent, serialize_report_for_review
from .data_repair import DataRepairAgent, ConflictResolver
from .structured_data_repair import StructuredDataRepairAgent
from .coverage_checker import ChapterCoverageChecker
from .evidence_acquisition import ReportEvidenceAcquirer
from .report_integrity import ReportIntegrityChecker
from .defense_audit import ReportDefenseAudit
from .defense_loop import DefenseLoopController
from .prompt_manager import PromptManager
from .revision_models import RevisionLocation
from src.core.content_contract import (
    check_content, check_finding_line, content_opens_meta, current_report_language,
)
from src.core.failure_audit import FailureAudit
from src.core.quality.checkers import AnalysisQualityChecker
from src.core.llm_client import call_llm

logger = logging.getLogger(__name__)


def _canonical_section_id(value: Any) -> str:
    """Use the runtime chapter identity when joining legacy routing output."""
    text = str(value or "").strip()
    match = re.match(r"^(section|synthesis)_(\d+)(?:_|$)", text)
    return f"{match.group(1)}_{match.group(2)}" if match else text


def _checkpoint_filename(chapter_id: Any) -> str:
    """Build a portable checkpoint filename without changing the chapter ID."""
    canonical = str(chapter_id or "").strip() or "unknown"
    safe_stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", canonical).strip(" .") or "unknown"
    digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:10]
    return f"chapter_{safe_stem}_{digest}.json"

_FORBIDDEN_SECTION_PATTERNS = [
    (r'^#+\s*反证(?:与|及|和)?边界条件', 'risk_disclosure'),
    (r'^#+\s*反证(?:证据)?', 'risk_disclosure'),
    (r'^#+\s*边界条件(?:假设)?', 'risk_disclosure'),
    (r'^#+\s*正面?论证', 'argument'),
    (r'^#+\s*反面?论证', 'argument'),
    (r'^#+\s*(?:决策)?启示', 'risk_disclosure'),  # merge全量内容到风险提示
    (r'^#+\s*含义', 'risk_disclosure'),             # 同上，保留分析内容
    (r'^#+\s*影响$', 'risk_disclosure'),            # 同上
    (r'^\*\*经营现金流[^**]+\*\*', 'risk_disclosure'),  # 经营现金流等违规内嵌标题
    (r'^\*\*研发投入[^**]+\*\*', 'risk_disclosure'),
]

_RISK_DISCLOSURE_HEADING = "#### 风险提示"

# Standard failed-chapter placeholder used by final assembly (empty content
# and sanity-gate replacements share the same reader-facing text).
_CHAPTER_FAILED_PLACEHOLDER = (
    "本章节未生成可验证内容。系统已记录该章节失败状态，请在补充证据后重新生成。"
)

# Raw fixed-format contract leakage inside delivered chapter content.
_CONTRACT_LEAK_MARKERS = ("<<<REPORT_CHAPTER>>>", "<<<CONTENT>>>")


def _enforce_structure_compliance(content: str) -> str:
    """N1: 程序化后处理——将违规段落标题替换/收拢为规范结构。"""
    _MD_STRIP = re.compile(r'[*_]+')
    if not content:
        return content
    lines = content.split('\n')
    result_lines = []
    risk_buffer = []
    has_risk_section = False

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        clean_line = _MD_STRIP.sub('', stripped)  # strip bold/italic markdown for pattern matching
        matched = False
        for pattern, action in _FORBIDDEN_SECTION_PATTERNS:
            if re.match(pattern, clean_line):
                matched = True
                j = i + 1
                section_content = []
                while j < len(lines):
                    next_stripped = lines[j].strip()
                    is_next_heading = (next_stripped.startswith('#')
                                       or (not next_stripped
                                           and j + 1 < len(lines)
                                           and lines[j + 1].strip().startswith('#')))
                    if is_next_heading:
                        break
                    section_content.append(lines[j])
                    j += 1
                if action == 'risk_disclosure':
                    risk_buffer.extend(section_content)
                elif action == 'argument':
                    matched_text = re.match(pattern, clean_line).group()
                    result_lines.append(stripped.replace(matched_text, '#### 论证分析'))
                    result_lines.extend(section_content)
                i = j
                break
        if not matched:
            if '风险提示' in clean_line:
                has_risk_section = True
            result_lines.append(lines[i])
            i += 1

    if risk_buffer:
        if has_risk_section:
            insert_idx = len(result_lines)
            for idx in range(len(result_lines)):
                line_check = _MD_STRIP.sub('', result_lines[idx].strip())
                if line_check.startswith('#') and '风险提示' in line_check:
                    insert_idx = idx + 1
                    while insert_idx < len(result_lines) and not result_lines[insert_idx].strip().startswith('#'):
                        insert_idx += 1
                    break
            for k, line in enumerate(risk_buffer):
                result_lines.insert(insert_idx + k, line)
        else:
            result_lines.append('')
            result_lines.append(_RISK_DISCLOSURE_HEADING)
            result_lines.extend(risk_buffer)

    return '\n'.join(result_lines)


_VAGUE_SOURCE_PATTERNS = re.compile(
    r'^(行业综合数据|综合数据|公开数据|市场数据|统计数据|研究报告|行业报告|综合来源|公开信息|行业信息'
    r'|行业综合报道|综合报道|行业报道|多方报道|综合多方报道|市场综合报道|行业综合来源)$',
    re.IGNORECASE,
)


def _is_vague_source(source: str) -> bool:
    if not source or not source.strip():
        return True
    return bool(_VAGUE_SOURCE_PATTERNS.match(source.strip()))


def _source_url_for(source: str, available_sources: List[Dict[str, Any]]) -> str:
    """Resolve a source title to its URL without inventing provenance."""
    if not source or _is_vague_source(source):
        return ""
    source_norm = source.strip().lower()
    exact = []
    fuzzy = []
    for item in available_sources or []:
        title = str(item.get("title", "") or "").strip()
        url = str(item.get("url", "") or item.get("href", "") or "").strip()
        if not url:
            continue
        title_norm = title.lower()
        if source_norm == title_norm:
            exact.append(url)
        elif source_norm in title_norm or title_norm in source_norm:
            fuzzy.append(url)
    if len(set(exact)) == 1:
        return exact[0]
    if not exact and len(set(fuzzy)) == 1:
        return fuzzy[0]
    return ""


class RetryPolicy:
    # retired: write() is engine-budgeted (spec §8#9) — kept for API compat,
    # no longer drives any write re-run.
    MAX_CHAPTER_RETRIES = 2
    MAX_REVIEW_RETRIES = 2
    MAX_FULL_RETRIES = 0
    RETRY_BACKOFF_BASE = 2
    MIN_REVIEW_SCORE_TO_ACCEPT = 60
    MAX_CONVERGENCE_ROUNDS = 3
    MIN_CONVERGENCE_IMPROVEMENT = 5  # kept for backward compatibility
    MIN_CONVERGENCE_IMPROVEMENT_ROUNDS = [3, 2, 1]  # E1: progressive thresholds by round_idx
    TARGET_SCORE = 80

    NON_RETRYABLE_ERRORS = {"insufficient_balance", "invalid_request_error", "authentication_error"}

    @staticmethod
    def get_delay(attempt: int) -> float:
        return RetryPolicy.RETRY_BACKOFF_BASE ** attempt

    @staticmethod
    def get_min_improvement(round_idx: int) -> int:
        rounds = RetryPolicy.MIN_CONVERGENCE_IMPROVEMENT_ROUNDS
        if round_idx < len(rounds):
            return rounds[round_idx]
        return rounds[-1]


class ReportOrchestrator:

    @staticmethod
    def _quality_issue_key(issue: Any, chapters: List[ChapterWriteOutput]) -> str:
        """Build a stable key for quality-loop findings across LLM re-audits."""
        location = getattr(issue, "location", "")
        if isinstance(location, (list, tuple, set)):
            location_text = "|".join(str(item or "").strip() for item in location)
        else:
            location_text = str(location or "").strip()
        chapter_id = ReportOrchestrator._resolve_location_for_key(location_text, chapters)
        dimension = str(getattr(issue, "dimension", "") or "").strip()
        description = re.sub(r"\d+(?:\.\d+)?", "#", str(getattr(issue, "description", "") or ""))
        description = re.sub(r"\s+", "", description).strip()
        return "|".join((dimension, chapter_id or location_text, description[:160]))

    @staticmethod
    def _resolve_location_for_key(location: str, chapters: List[ChapterWriteOutput]) -> str:
        if not location:
            return ""
        for chapter in chapters:
            if chapter.chapter_id in location or chapter.title in location:
                return chapter.chapter_id
        return location

    def _cache_chapter_rescue_material(
        self, chapter_id: str, section_spec: Dict[str, Any],
        chapter_data: Any,
    ) -> None:
        """Store write-phase material for a failed chapter.

        The defense loop re-runs `chapter_writer.write` with this material as
        base_content, turning a total write failure (JSON parse exhaustion)
        into a second chance built from agent analysis that already exists.
        """
        try:
            payload = dict(chapter_data) if isinstance(chapter_data, dict) else {}
            self._chapter_rescue_cache[str(chapter_id)] = {
                "section_spec": dict(section_spec or {}),
                "chapter_data": payload,
                "base_content": str(payload.get("content") or "").strip(),
                "upstream_data_points": payload.get("upstream_data_points"),
                "raw_data_summary": self._extract_raw_summary({
                    "data_points": payload.get("upstream_data_points", []),
                }),
            }
        except Exception:
            logger.debug("Failed to cache rescue material for chapter %s", chapter_id)

    @staticmethod
    def _looks_like_failed_chapter(chapter: ChapterWriteOutput) -> bool:
        status = str(getattr(chapter, "status", "ready") or "ready").lower()
        content = str(chapter.content or "").strip()
        placeholder_markers = (
            "本章节数据不足", "无法生成完整分析", "内容待补充",
            "摘要生成失败", "章节生成失败", "未生成可验证内容",
        )
        return (
            status not in {"ready", "completed", ""}
            or not content
            # Degenerate ready output (observed: a 3-char '...' chapter that
            # shipped as ready after a destructive patch) must still be
            # caught; real chapters are hundreds of characters long.
            or len(content) < 150
            or any(marker in content[:200] for marker in placeholder_markers)
        )

    async def _rescue_failed_chapters(
        self,
        chapters: List[ChapterWriteOutput],
        task_structure: Dict[str, Any],
        framework_config: Dict[str, Any],
    ) -> Tuple[List[ChapterWriteOutput], List[Dict[str, Any]]]:
        """Rewrite failed/placeholder chapters using cached write material.

        Coverage audits correctly flag failed chapters, but the defense loop
        only responded with evidence searches - a failed chapter with ample
        agent material stayed empty through every round (real failure:
        sections 5/6 delivered 37-char placeholders in a delivered report).
        """
        rescued: List[Dict[str, Any]] = []
        for index, chapter in enumerate(chapters):
            if not self._looks_like_failed_chapter(chapter):
                continue
            material = self._chapter_rescue_cache.get(str(chapter.chapter_id))
            if not material or not material.get("base_content"):
                # I2: rescue 静默跳过曾零日志（空报告无任何线索事故）
                FailureAudit.record(
                    stage="report.defense.rescue",
                    subject_id=str(chapter.chapter_id),
                    action="skip",
                    reason=f"no material(base_content={bool(material and material.get('base_content'))})",
                    task_id=self._task_id,
                    delivery_impact="degraded",
                )
                continue
            try:
                rewritten = await self._chapter_writer.write(ChapterWriteInput(
                    framework_config=framework_config,
                    task_structure=task_structure,
                    chapter_spec=material.get("section_spec") or {
                        "section_id": chapter.chapter_id, "section_name": chapter.title,
                    },
                    chapter_data=material.get("chapter_data") or {},
                    raw_data_summary=material.get("raw_data_summary") or "无原始数据摘要",
                    preceding_summary="",
                    used_metrics_summary=self._data_registry.serialize_used_metrics(),
                    base_content=material["base_content"],
                    upstream_data_points=material.get("upstream_data_points"),
                    parent_section_context={},
                    global_evidence_pool=self._evidence_context.raw_search_results,
                    raw_search_results=self._evidence_context.raw_search_results,
                    raw_data_location=str(
                        Path("data", self._task_id, "research_result_cache.json").resolve()
                    ),
                    sibling_section_summaries=self._evidence_context.section_index.get("siblings", []),
                    chapter_requirements={},
                    used_evidence_ids=[],
                    output_format=str(task_structure.get("output_format", "docx")),
                ))
            except Exception as rescue_error:
                logger.warning(
                    "Defense rescue rewrite failed for chapter %s: %s",
                    chapter.chapter_id, rescue_error,
                )
                continue
            content = str(rewritten.content or "").strip()
            if (
                str(getattr(rewritten, "status", "ready") or "ready").lower() == "ready"
                and len(content) >= 400
            ):
                # I4: rescue 兜底产出必须通过与主路径相同的 I1 内容契约
                # （FailureAudit 结构化留痕在 Task 3 接入，先以
                # [CONTENT_CONTRACT] 前缀 warning 留痕）。
                rescue_spec = material.get("section_spec") or {}
                verdict = check_content(
                    content, kind="chapter", min_length=400,
                    data_points_count=len(rewritten.data_points_used or []),
                    section_name=str(rescue_spec.get("section_name", "") or ""),
                    language=current_report_language(),
                )
                if not verdict.passed:
                    logger.warning(
                        "[CONTENT_CONTRACT] Defense rescue content rejected for "
                        "chapter %s: %s; keeping original chapter",
                        chapter.chapter_id, verdict.fail_codes,
                    )
                    continue
                rewritten.content = _enforce_structure_compliance(content)
                chapters[index] = rewritten
                self._cache_chapter_rescue_material(
                    str(chapter.chapter_id), material.get("section_spec") or {},
                    material.get("chapter_data") or {},
                )
                rescued.append({
                    "chapter_id": rewritten.chapter_id,
                    "chars": len(rewritten.content),
                })
                self._report_progress(
                    "completed",
                    f"✅ 章节「{rewritten.title}」在收尾修复轮重新生成成功"
                    f"（约 {len(rewritten.content)} 字）。",
                )
            else:
                logger.warning(
                    "Defense rescue produced unusable content for chapter %s "
                    "(status=%s, len=%d); keeping original chapter",
                    chapter.chapter_id,
                    getattr(rewritten, "status", "?"),
                    len(content),
                )
        return chapters, rescued

    @staticmethod
    def _build_defense_search_gaps(audit: Dict[str, Any]) -> List[DataGap]:
        """Turn evidence and chapter-coverage failures into search gaps.

        Coverage failures are P0: a missing topic/section is never allowed to
        be treated as a prose rewrite.  Older code only accepted L2/L3
        issues with a non-empty ``metric`` and silently discarded chapter
        coverage issues, which is why missing sections escaped L1-L5 repair.
        """
        gaps: List[DataGap] = []
        seen: Set[Tuple[str, str]] = set()
        for issue in (audit.get("issues", []) if isinstance(audit, dict) else []):
            if not isinstance(issue, dict):
                continue
            layer = str(issue.get("layer", "") or "")
            code = str(issue.get("code", "") or "")
            is_coverage = code != "synthesis_content_missing" and (layer == "coverage" or code in {
                "missing_chapter", "missing_section", "missing_topic",
                "chapter_content_missing", "placeholder_content",
            })
            if not is_coverage and layer not in {"L2", "L3"}:
                # I2: 白名单外 issue 无对应动作（如 invalid_epistemic_level）
                FailureAudit.record(
                    stage="report.defense",
                    subject_id=str(issue.get("chapter_id", "") or ""),
                    action="no_action_available",
                    reason=code or f"layer_not_actionable:{layer}",
                    severity="blocking",
                )
                continue
            if not is_coverage and code not in {
                "missing_geographic_scope", "missing_period", "missing_population",
                "missing_source", "missing_source_url", "unverified_evidence",
            }:
                # I2: 白名单外 issue 无对应动作（如 incomplete_evidence_identity）
                FailureAudit.record(
                    stage="report.defense",
                    subject_id=str(issue.get("chapter_id", "") or ""),
                    action="no_action_available",
                    reason=code or "unknown_issue_code",
                    severity="blocking",
                )
                continue
            if not is_coverage and layer == "L2" and code in {
                "missing_geographic_scope", "missing_period", "missing_population",
            }:
                # P2-F（复审修订，ses_baf7a884）：范畴错误纠偏——L2 元数据
                # 缺失靠外部搜索填不上（action_lifecycle 全部 failed 的实证
                # 来源）。元数据由 _ground_data_point_sources 的目录回填
                # 通路治理（P0-B 配套），不派发 search_evidence。
                FailureAudit.record(
                    stage="report.defense",
                    subject_id=str(issue.get("chapter_id", "") or ""),
                    action="metadata_backfill_skipped",
                    reason=f"{code}: 非搜索可补，走证据目录回填",
                    severity="warning",
                )
                continue
            chapter_id = str(issue.get("chapter_id", "") or "").strip()
            metric = str(
                issue.get("metric") or issue.get("topic") or issue.get("section_title")
                or ("章节内容" if is_coverage else "")
            ).strip()
            if not chapter_id or not metric or (chapter_id, metric) in seen:
                continue
            seen.add((chapter_id, metric))
            context = str(issue.get("message", "") or issue.get("code", ""))
            gaps.append(DataGap(
                chapter_id=chapter_id,
                metric=metric,
                context=context,
                search_keywords=[metric, str(issue.get("section_title", "") or "").strip()],
                audit_layer="coverage" if is_coverage else layer,
            ))
        return gaps

    def _build_report_coverage_issues(
        self, chapters: List[ChapterWriteOutput], task_structure: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Audit required chapters after writing, including placeholder output."""
        chapter_by_id = {str(chapter.chapter_id): chapter for chapter in chapters}
        issues: List[Dict[str, Any]] = []
        placeholder_markers = (
            "本章节数据不足", "无法生成完整分析", "内容待补充",
            "摘要生成失败", "章节生成失败",
        )
        # Manifest is the frozen report identity contract.  Do not fall back
        # to the mutable/nested section tree when it is available.
        report_specs = self._report_chapter_specs(task_structure)

        for spec in report_specs:
            chapter_id = str(spec.get("section_id", "") or "").strip()
            title = str(spec.get("name", "") or spec.get("title", "") or chapter_id).strip()
            chapter = chapter_by_id.get(chapter_id)
            if chapter is None:
                issues.append({
                    "layer": "coverage", "code": "missing_section",
                    "chapter_id": chapter_id, "section_title": title,
                    "message": f"缺少必需章节：{title}",
                })
                continue
            content = str(chapter.content or "").strip()
            is_synthesis = str(spec.get("section_role", "")).lower() == "synthesis"
            chapter_status = str(getattr(chapter, "status", "ready") or "ready").lower()
            if (
                chapter_status not in {"ready", "completed", ""}
                or not content
                or any(marker in content for marker in placeholder_markers)
            ):
                issues.append({
                    "layer": "coverage",
                    "code": "synthesis_content_missing" if is_synthesis else "chapter_content_missing",
                    "chapter_id": chapter_id, "section_title": title,
                    "topic": title,
                    "message": (
                        f"综合章节未生成有效内容：{title}"
                        if is_synthesis else f"必需章节没有可交付内容：{title}"
                    ),
                })
                continue
            requirement = self._build_chapter_requirement(spec)
            data = {
                "content": content,
                "upstream_data_points": [
                    asdict(point) if hasattr(point, "__dataclass_fields__") else point
                    for point in (chapter.data_points_used or [])
                ],
            }
            coverage = self._coverage_checker.check(
                requirement, data, ReportEvidenceContext(),
            )
            for topic_name in coverage.missing_topics:
                issues.append({
                    "layer": "coverage", "code": "missing_topic",
                    "chapter_id": chapter_id, "section_title": title,
                    "topic": topic_name,
                    "message": f"必需章节缺少主题：{topic_name}",
                })
            for metric in coverage.missing_metrics:
                issues.append({
                    "layer": "coverage", "code": "missing_metric",
                    "chapter_id": chapter_id, "section_title": title,
                    "metric": metric,
                    "message": f"必需章节缺少指标：{metric}",
                })
        return issues

    @staticmethod
    def _report_chapter_specs(task_structure: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return the same frozen chapter set for writing, restore and audit."""
        manifest = [
            item for item in (task_structure.get("section_manifest", []) or [])
            if isinstance(item, dict) and str(item.get("section_id") or "").strip()
        ]
        if not manifest:
            return ReportOrchestrator._iter_report_chapter_specs(
                task_structure.get("sections", [])
            )
        # The routing manifest is the single ordering contract shared by
        # execution and report writing.  Keep explicit planner order when it
        # is present, while retaining legacy manifest order for old tasks.
        indexed_manifest = list(enumerate(manifest))
        if any("execution_order" in item for item in manifest):
            indexed_manifest.sort(key=lambda pair: (
                1 if str(pair[1].get("role", pair[1].get("section_role", ""))).lower() == "synthesis" else 0,
                pair[1].get("execution_order", pair[0]),
                pair[0],
            ))
        specs = []
        for _, item in indexed_manifest:
            spec = dict(item)
            spec.setdefault("name", spec.get("title") or spec["section_id"])
            spec.setdefault("section_name", spec.get("title") or spec["section_id"])
            spec.setdefault("section_role", spec.get("role") or "analysis")
            spec.setdefault("required_metrics", item.get("required_metrics", []))
            spec.setdefault("required_topics", item.get("required_topics", []))
            specs.append(spec)
        return specs

    @staticmethod
    def _apply_defense_structural_repairs(
        chapters: List[ChapterWriteOutput], audit: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Apply only deterministic L1 repairs that cannot change meaning."""
        planned = ReportOrchestrator._build_defense_structural_actions(chapters, audit)
        applied: List[Dict[str, Any]] = []
        chapter_by_id = {chapter.chapter_id: chapter for chapter in chapters}
        for action in planned:
            chapter_id = action["chapter_id"]
            metric = action["metric"]
            chapter = chapter_by_id.get(chapter_id)
            if chapter is None:
                continue
            for data_point in chapter.data_points_used or []:
                point_metric = data_point.get("metric") if isinstance(data_point, dict) else data_point.metric
                point_chapter_id = data_point.get("chapter_id") if isinstance(data_point, dict) else data_point.chapter_id
                if point_metric != metric or point_chapter_id:
                    continue
                if isinstance(data_point, dict):
                    data_point["chapter_id"] = chapter_id
                else:
                    data_point.chapter_id = chapter_id
                applied.append({
                    "layer": "L1",
                    "type": "bind_chapter",
                    "chapter_id": chapter_id,
                    "metric": metric,
                })
                break
        return applied

    @staticmethod
    def _build_defense_structural_actions(
        chapters: List[ChapterWriteOutput], audit: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Plan only L1 bindings that have an unambiguous target data point."""
        actions: List[Dict[str, Any]] = []
        chapter_by_id = {chapter.chapter_id: chapter for chapter in chapters}
        for issue in (audit.get("issues", []) if isinstance(audit, dict) else []):
            if not isinstance(issue, dict):
                continue
            if issue.get("layer") != "L1" or issue.get("code") != "missing_chapter_binding":
                continue
            chapter_id = str(issue.get("chapter_id", "") or "").strip()
            metric = str(issue.get("metric", "") or "").strip()
            chapter = chapter_by_id.get(chapter_id)
            if not chapter_id or not metric or chapter is None:
                continue
            if any(
                (point.get("metric") if isinstance(point, dict) else point.metric) == metric
                and not (point.get("chapter_id") if isinstance(point, dict) else point.chapter_id)
                for point in (chapter.data_points_used or [])
            ):
                action = {
                    "layer": "L1",
                    "type": "bind_chapter",
                    "chapter_id": chapter_id,
                    "metric": metric,
                }
                if action not in actions:
                    actions.append(action)
        return actions

    @staticmethod
    def _build_defense_rewrite_actions(
        audit: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Create one scoped rewrite request per chapter.

        Several audit rules can flag the same chapter at once.  Sending one
        LLM patch request per issue caused a repair storm and made a real
        report spend most of its time repeatedly rewriting the same chapter.
        Merge the instructions by chapter while retaining every issue code and
        message for the single chapter-level repair.
        """
        actions: List[Dict[str, Any]] = []
        grouped: Dict[str, Dict[str, Any]] = {}
        for issue in (audit.get("issues", []) if isinstance(audit, dict) else []):
            if not isinstance(issue, dict):
                continue
            if issue.get("code") not in {
                "scope_collision", "unlabeled_future_value", "unbound_numeric_claim",
            }:
                continue
            if issue.get("layer") != "L4" and issue.get("code") != "unbound_numeric_claim":
                continue
            chapter_id = str(issue.get("chapter_id", "") or "").strip()
            code = str(issue.get("code", "") or "").strip()
            if not chapter_id or not code:
                continue
            group = grouped.setdefault(chapter_id, {
                "layer": "L3" if code == "unbound_numeric_claim" and issue.get("layer") == "L3" else "L4",
                "type": "rewrite_scope",
                "chapter_id": chapter_id,
                "codes": [],
                "instructions": [],
            })
            layer = str(issue.get("layer", "L4") or "L4")
            if layer == "L3" and code == "unbound_numeric_claim":
                group["layer"] = layer
            if code not in group["codes"]:
                group["codes"].append(code)
            message = str(issue.get("message", "") or code).strip()
            if message and message not in group["instructions"]:
                group["instructions"].append(message)

        for group in grouped.values():
            group["code"] = "+".join(group.pop("codes"))
            group["instruction"] = "；".join(group.pop("instructions"))
            actions.append(group)
        return actions

    @staticmethod
    def _build_defense_conflict_actions(
        audit: Dict[str, Any], conflicts: List[DataConflict]
    ) -> List[Dict[str, Any]]:
        """Plan L5 resolution only from typed registry conflicts."""
        has_l5_issue = any(
            isinstance(issue, dict)
            and issue.get("layer") == "L5"
            and issue.get("code") == "unresolved_registry_conflict"
            for issue in (audit.get("issues", []) if isinstance(audit, dict) else [])
        )
        if not has_l5_issue:
            return []
        actions = []
        for conflict in conflicts or []:
            if not isinstance(conflict, DataConflict) or not conflict.metric:
                continue
            actions.append({
                "layer": "L5",
                "type": "resolve_conflict",
                "metric": conflict.metric,
            })
        return actions

    @staticmethod
    def _is_safe_conflict_resolution(resolution: DataConflictResolution) -> bool:
        """Reject resolver fallbacks that merely select the first entry."""
        if not isinstance(resolution, DataConflictResolution):
            return False
        reason = str(resolution.reason or "").lower()
        unsafe_markers = (
            "using first entry",
            "no search skill",
            "llm failed",
            "json parse failed",
        )
        return bool(
            resolution.canonical_value
            and resolution.canonical_source
            and not any(marker in reason for marker in unsafe_markers)
        )

    async def _run_defense_repair_loop(
        self,
        chapters: List[ChapterWriteOutput],
        review: ReviewOutput,
        framework_config: Dict[str, Any],
        topic: str,
        task_structure: Dict[str, Any],
        original_sources: List[Dict[str, Any]],
        quality_report: Optional[QualityReport],
        conflicts_summary: str,
        max_rounds: int = 3,
    ) -> Dict[str, Any]:
        """Run bounded evidence repair and full re-audit for assistant delivery."""
        controller = DefenseLoopController(max_rounds=max_rounds)
        current_chapters = chapters
        exec_summary = await self._generate_exec_summary(
            current_chapters, task_structure, topic
        )
        history: List[Dict[str, Any]] = []

        while True:
            # P0 rewrite first: a failed chapter with cached material is
            # regenerated BEFORE assembly+audit, so the decision sees the
            # repaired state instead of re-planning evidence searches
            # against a placeholder (observed in ses_c0d6cd9f: two failed
            # chapters stayed empty through all three defense rounds).
            rescue_report: List[Dict[str, Any]] = []
            try:
                current_chapters, rescue_report = await self._rescue_failed_chapters(
                    current_chapters, task_structure, framework_config,
                )
            except Exception as rescue_error:
                logger.warning("Defense rescue step failed: %s", rescue_error)
            if rescue_report:
                # The executive summary was generated from the pre-rescue
                # chapter set; failed chapters contributed nothing but
                # failure notices.  Refresh it so key findings reflect the
                # rescued report instead of the failure snapshot.
                try:
                    refreshed = await self._generate_exec_summary(
                        current_chapters, task_structure, topic
                    )
                    if refreshed and "摘要生成失败" not in refreshed:
                        exec_summary = refreshed
                except Exception as summary_error:
                    logger.warning("Post-rescue exec summary refresh failed: %s", summary_error)
            self._chapters = current_chapters
            report = self._assemble_final_report(
                current_chapters,
                exec_summary,
                review,
                topic,
                self._merge_repair_sources(original_sources, self._repair_results),
                quality_report=quality_report,
                # L5 状态取组装时刻的注册表实时值——conflicts_summary 参数
                # 在防御轮之前计算（ses_f8f31c10 实证：冲突已被防御轮
                # 解决，stale 摘要仍把 L5 烙进审计，报告被误判 blocked）。
                conflicts_summary=self._data_registry.serialize_conflicts(),
                llm_trace=self._llm_trace,
                task_id=self._task_id,
            )
            audit = report.get("defense_audit", {})
            coverage_issues = self._build_report_coverage_issues(
                current_chapters, task_structure,
            )
            if coverage_issues:
                # P1-C（复审修订，ses_baf7a884）：coverage 缺口不再强制
                # 防御审计失败（曾致 formal_complete=False 的旁路真相源）。
                # 覆盖状态独立输出，正式性由交付签名统一裁决；issue 仍
                # 附带在案供诊断。
                audit = dict(audit or {})
                audit["issues"] = list(audit.get("issues", []) or []) + coverage_issues
                audit["coverage_status"] = "missing_metrics"
                audit["coverage_missing"] = [
                    str(i.get("metric") or "") for i in coverage_issues
                ]
                report["defense_audit"] = audit
            report["evidence_stats"] = {
                "raw_search_evidence_count": len(self._evidence_context.raw_search_results),
                "evidence_registry_count": len(self._evidence_context.evidence_registry),
                "external_search_count": self._evidence_search_count,
            }
            # The previous repair round is only complete after this audit of
            # the newly assembled report.  Keep this explicit so a warning
            # delivery remains auditable without making HTML generation a
            # hard-failure path.
            controller.finalize_action_verification(audit)
            gaps = self._build_defense_search_gaps(audit)
            conflicts = self._data_registry.get_conflicts()
            # P0 coverage acquisition must precede binding, prose rewrites,
            # and L5 conflict handling.
            actions = [
                {
                    "layer": gap.audit_layer or "L3",
                    "type": "search_evidence",
                    "chapter_id": gap.chapter_id,
                    "metric": gap.metric,
                }
                for gap in gaps
            ] + self._build_defense_structural_actions(current_chapters, audit) + self._build_defense_rewrite_actions(audit) + self._build_defense_conflict_actions(
                audit, conflicts
            )
            decision = controller.evaluate(audit, actions)
            logger.info(
                "DEFENSE_DECISION task_id=%s round=%d status=%s should_repair=%s "
                "actions=%d termination_reason=%s issue_signature=%s",
                self._task_id,
                decision.round_number,
                decision.status,
                decision.should_repair,
                len(decision.actions),
                decision.termination_reason or "none",
                decision.issue_signature,
            )
            history_record = {
                "status": decision.status,
                "round": decision.round_number,
                "stages": decision.stages,
                "termination_reason": decision.termination_reason,
                "issue_signature": decision.issue_signature,
                "audit_passed": bool(audit.get("passed", False)),
                "audit_score": audit.get("score"),
                "issue_count": len(audit.get("issues", []) or []),
                "rescued": [dict(item) for item in rescue_report],
                "issues": [
                    {
                        "layer": item.get("layer", ""),
                        "code": item.get("code", ""),
                        "chapter_id": item.get("chapter_id", ""),
                        "metric": item.get("metric", ""),
                    }
                    for item in (audit.get("issues", []) or [])
                    if isinstance(item, dict)
                ],
                "planned_actions": [dict(action) for action in decision.actions],
            }
            history.append(history_record)

            if not decision.should_repair:
                report = await self._plan_and_render_charts(report)
                report["defense_loop"] = {
                    "status": decision.status,
                    "rounds": controller.rounds,
                    "history": history,
                    "issue_states": dict(sorted(controller.issue_states.items())),
                    "action_lifecycle": [dict(item) for item in controller.action_lifecycle],
                }
                return report

            structural_actions = [
                action for action in decision.actions if action.get("type") == "bind_chapter"
            ]
            successful_actions: List[Dict[str, Any]] = []
            failed_actions: List[Dict[str, Any]] = []
            applied_structural = (
                self._apply_defense_structural_repairs(current_chapters, audit)
                if structural_actions else []
            )
            if structural_actions:
                (successful_actions if applied_structural else failed_actions).extend(structural_actions)
            rewrite_actions = [
                action for action in decision.actions if action.get("type") == "rewrite_scope"
            ]
            applied_rewrites = []
            chapter_positions = {
                chapter.chapter_id: index
                for index, chapter in enumerate(current_chapters)
            }
            for action in rewrite_actions:
                chapter_index = chapter_positions.get(action.get("chapter_id", ""))
                if chapter_index is None:
                    failed_actions.append(action)
                    continue
                chapter = current_chapters[chapter_index]
                try:
                    patched = await self._chapter_writer.patch_data(
                        chapter=chapter,
                        patch_instructions=[
                            f"{action['layer']}审计修复（{action['code']}）：{action['instruction']}。"
                            "不得改变已有可验证数值；对无据数字只能删除、降级为数据不足，"
                            "对口径冲突必须拆分并明确范围。"
                        ],
                        framework_config=framework_config,
                    )
                except Exception as repair_error:
                    logger.warning("Defense rewrite action failed: %s", repair_error)
                    failed_actions.append(action)
                    continue
                if (
                    isinstance(patched, ChapterWriteOutput)
                    and str(getattr(patched, "status", "ready") or "ready").lower() == "ready"
                    and str(patched.content or "").strip()
                ):
                    current_chapters[chapter_index] = patched
                    applied_rewrites.append(action)
                    successful_actions.append(action)
                else:
                    # patch_data already returns the original chapter on a
                    # failed parse; this guard keeps the audit trail honest
                    # for non-ChapterWriteOutput results.
                    logger.warning(
                        "Defense rewrite produced no usable content for %s; keeping original chapter",
                        action.get("chapter_id", ""),
                    )
                    failed_actions.append(action)
            applied_safety_repairs = self._apply_defense_content_safety_repairs(
                current_chapters, audit,
            )
            conflict_actions = [
                action for action in decision.actions if action.get("type") == "resolve_conflict"
            ]
            conflict_by_metric = {conflict.metric: conflict for conflict in conflicts}
            conflict_resolutions = []
            for action in conflict_actions:
                conflict = conflict_by_metric.get(action.get("metric", ""))
                if conflict is None:
                    failed_actions.append(action)
                    continue
                try:
                    resolution = await self._conflict_resolver.resolve(conflict, topic)
                except Exception as repair_error:
                    logger.warning("Defense conflict action failed: %s", repair_error)
                    failed_actions.append(action)
                    continue
                if self._is_safe_conflict_resolution(resolution):
                    conflict_resolutions.append(resolution)
                    successful_actions.append(action)
                else:
                    failed_actions.append(action)
            try:
                repair_results = await self._acquire_evidence_batch(
                    gaps, topic, scope="report_revision",
                )
            except Exception as repair_error:
                logger.warning("Defense evidence action batch failed: %s", repair_error)
                controller.mark_actions_failed(decision.actions)
                history_record["repair_result"] = {
                    "status": "failed",
                    "error": str(repair_error),
                }
                continue
            search_actions = [
                action for action in decision.actions if action.get("type") == "search_evidence"
            ]
            successful_search_actions, failed_search_actions = (
                self._classify_evidence_search_actions(search_actions, repair_results)
            )
            successful_actions.extend(successful_search_actions)
            failed_actions.extend(failed_search_actions)
            found_results = [result for result in repair_results if result.found]
            self._repair_results.extend(found_results)
            if (
                not found_results
                and not applied_structural
                and not applied_rewrites
                and not applied_safety_repairs
                and not conflict_resolutions
            ):
                # Re-audit unchanged data once; the controller will convert
                # the repeated signature into a warning delivery outcome.
                controller.mark_actions_failed(decision.actions)
                history_record["repair_result"] = "no_change"
                continue

            if found_results:
                current_chapters, _ = await self._apply_data_repairs(
                    current_chapters,
                    found_results,
                    [],
                    framework_config,
                )
            if conflict_resolutions:
                current_chapters, _ = await self._apply_data_repairs(
                    current_chapters,
                    [],
                    conflict_resolutions,
                    framework_config,
                )
            # Only successful repair work becomes ``executed``.  The next
            # audit transitions it to verified or unresolved; failed/no-op
            # actions remain visible as failed.
            controller.mark_actions_processed(successful_actions)
            controller.mark_actions_failed(failed_actions)
            history_record["repair_result"] = {
                "found_evidence": len(found_results),
                "bound_chapters": len(applied_structural),
                "rewritten_chapters": len(applied_rewrites),
                "content_safety_repairs": len(applied_safety_repairs),
                "resolved_conflicts": len(conflict_resolutions),
            }
            exec_summary = await self._generate_exec_summary(
                current_chapters, task_structure, topic
            )

    @staticmethod
    def _apply_defense_content_safety_repairs(
        chapters: List[ChapterWriteOutput], audit: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Apply conservative repairs without inventing or changing numeric facts."""
        issues = audit.get("issues", []) if isinstance(audit, dict) else []
        by_chapter: Dict[str, Set[str]] = {}
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            code = str(issue.get("code", ""))
            if code in {"scope_collision", "unbound_numeric_claim"}:
                by_chapter.setdefault(str(issue.get("chapter_id", "")), set()).add(code)

        quantified = re.compile(
            r"-?\d+(?:\.\d+)?\s*(?:%|％|百分比|亿元|万亿元|亿美元|万元|万亿美元|万辆|万台|吨|万人|万人次|人|家|个|件|台)"
        )
        repaired: List[Dict[str, Any]] = []
        _DOT_GUARD = "\x00"  # G10：数字间数点保护符（见下方两处使用）
        for chapter in chapters:
            codes = by_chapter.get(chapter.chapter_id, set())
            content = chapter.content or ""
            if not codes or not content:
                continue

            if "unbound_numeric_claim" in codes:
                valid_values = {
                    (re.sub(r",", "", str(point.value or "")).strip(), str(point.unit or "").strip())
                    for point in (chapter.data_points_used or [])
                }
                stripped_any: List[bool] = []

                def _safe_sentence(sentence: str) -> str:
                    for match in quantified.findall(sentence):
                        value_match = re.match(r"(-?\d+(?:\.\d+)?)\s*(.*)", match)
                        if not value_match:
                            continue
                        value, unit = value_match.groups()
                        if not any(
                            value == known_value
                            and (unit == known_unit or unit in known_unit or known_unit in unit)
                            for known_value, known_unit in valid_values
                        ):
                            stripped_any.append(True)
                            return ""
                    return sentence

                # Treat the Chinese semicolon as a clause boundary: without
                # it, one unbound claim inside a semicolon chain guts the
                # whole chain (real damage: sibling bound sentences vanish
                # silently and downstream content shrinks toward stubs).
                #
                # G10（格式标准 F2/F3，2026-10-18）：修复注入点两条硬约束——
                # a) 小数点保护：下方句界类排除"."，若不保护，"1.2" 的数点
                #    被当句界，句子被拦腰切成孤儿碎片（ses_92c64980
                #    section_2 实证："…基于1." + "2万亿元等宏观数据推演…"）。
                #    处理前把数字间数点替换为守卫符，匹配窗口恢复后比对。
                # b) 表格行跳过：markdown 表格行承载结构化数据，列本身
                #    就是口径与来源，绝不改写（ses_92c64980 section_4
                #    实证：表格行被替换成散文免责声明，破坏表格）。
                protected = re.sub(r"(?<=\d)\.(?=\d)", _DOT_GUARD, content)
                lines = protected.split("\n")
                for idx, line in enumerate(lines):
                    if line.lstrip().startswith("|"):
                        continue
                    lines[idx] = re.sub(
                        r"[^。！？.!?；;\n]*(?:" + quantified.pattern + r")[^。！？.!?；;\n]*[。！？.!?；;]?",
                        lambda match: _safe_sentence(match.group(0).replace(_DOT_GUARD, ".")),
                        line,
                    )
                content = "\n".join(lines).replace(_DOT_GUARD, ".")
                if stripped_any:
                    content = re.sub(r"[；;]{2,}", "；", content).strip("；;")
                    if "当前数据尚缺少可核验的结构化证据" not in content:
                        note = "当前数据尚缺少可核验的结构化证据。"
                        content = f"{content}\n{note}" if content.strip() else note

            if "scope_collision" in codes:
                paragraphs = []
                for paragraph in content.split("\n\n"):
                    if (
                        re.search(r"全球|世界", paragraph)
                        and re.search(r"国内|中国", paragraph)
                        and re.search(r"销量|市场|增速|增长|渗透率", paragraph)
                    ):
                        # G10（F2 同根因）：数点保护后再切句，避免 "1.85"
                        # 被切成 "…1." + "85万亿美元…" 两段，往表格行/数字
                        # 中间插入换行（ses_92c64980 section_4 实证损伤）。
                        protected_paragraph = re.sub(r"(?<=\d)\.(?=\d)", _DOT_GUARD, paragraph)
                        sentences = [
                            part for part in re.split(r"(?<=[。！？.!?])\s*", protected_paragraph)
                            if part
                        ]
                        rebuilt = []
                        for sentence in sentences:
                            restored = sentence.replace(_DOT_GUARD, ".")
                            # G10（F3）：表格行/单元格片段不参与口径替换——
                            # 表格列本身就是口径标注，改写会摧毁表格结构。
                            if (
                                "|" not in sentence
                                and re.search(r"全球|世界", restored)
                                and re.search(r"国内|中国", restored)
                            ):
                                restored = "全球与中国市场统计口径不同，本文不将两者直接合并比较。"
                            if (
                                rebuilt
                                and "|" not in sentence
                                and re.search(r"国内|中国", restored)
                                and re.search(r"全球|世界", "".join(rebuilt))
                            ):
                                rebuilt.append("\n")
                            rebuilt.append(restored)
                        paragraph = "".join(rebuilt).replace(_DOT_GUARD, ".")
                    paragraphs.append(paragraph)
                content = "\n\n".join(paragraphs)

            if content != chapter.content:
                chapter.content = content
                repaired.append({"chapter_id": chapter.chapter_id, "codes": sorted(codes)})
        return repaired

    @staticmethod
    def _merge_repair_sources(
        original_sources: Optional[List[Dict[str, Any]]],
        repair_results: List[DataRepairResult],
    ) -> List[Dict[str, Any]]:
        """Merge uniquely identified repair evidence into the source catalog."""
        merged = [dict(source) for source in (original_sources or [])]
        for result in repair_results or []:
            if not result.found or not result.source_url:
                continue
            repaired = {
                "title": result.source_title or result.source or result.source_url,
                "url": result.source_url,
                "type": "web",
                "evidence_id": result.evidence_id,
                "provenance_id": result.provenance_id,
                "evidence_excerpt": result.evidence_excerpt,
                "locator": result.locator,
            }
            existing = next(
                (
                    source for source in merged
                    if source.get("url") == repaired["url"]
                    or (
                        repaired["evidence_id"]
                        and source.get("evidence_id") == repaired["evidence_id"]
                    )
                ),
                None,
            )
            if existing is None:
                merged.append(repaired)
            else:
                for key, value in repaired.items():
                    if value not in (None, ""):
                        existing[key] = value
        return merged

    @staticmethod
    def _ensure_source_evidence_identity(
        sources: Optional[List[Dict[str, Any]]],
        *,
        task_id: str = "report",
    ) -> List[Dict[str, Any]]:
        """Normalize every persisted source into auditable evidence.

        Sources loaded from pre-gateway checkpoints are valid legacy inputs,
        but they do not carry gateway identities.  Assign deterministic IDs at
        the final report boundary so legacy and newly repaired sources follow
        the same evidence contract.
        """
        normalized: List[Dict[str, Any]] = []
        for raw in sources or []:
            source = dict(raw)
            url = str(source.get("url") or source.get("href") or "").strip()
            title = str(source.get("title") or "").strip()
            provider = str(source.get("source") or source.get("provider") or "").strip()
            excerpt = str(
                source.get("evidence_excerpt")
                or source.get("excerpt")
                or source.get("snippet")
                or ""
            ).strip()
            locator = str(source.get("locator") or url).strip()
            if not (url or title or excerpt):
                normalized.append(source)
                continue
            evidence_id = str(source.get("evidence_id") or "").strip()
            if not evidence_id:
                material = "|".join((provider, url, title, excerpt, locator))
                evidence_id = "ev_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
            provenance_id = str(source.get("provenance_id") or "").strip()
            if not provenance_id:
                material = "|".join((str(task_id or "report"), evidence_id))
                provenance_id = "prov_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
            source["url"] = url or source.get("url") or source.get("href", "")
            source["evidence_id"] = evidence_id
            source["provenance_id"] = provenance_id
            if excerpt:
                source["evidence_excerpt"] = excerpt
            if locator:
                source["locator"] = locator
            normalized.append(source)
        return normalized

    def __init__(
        self,
        chapter_writer: ChapterWriter,
        chapter_reviewer: ChapterReviewAgent,
        global_reviewer: GlobalReviewAgent,
        data_repair_agent: Optional[DataRepairAgent] = None,
        conflict_resolver: Optional[ConflictResolver] = None,
        prompt_manager: PromptManager = None,
        skill_registry=None,
        search_gateway=None,
        search_skill=None,
        web_scraper_skill=None,
        chart_planner=None,
        chart_generator=None,
        checkpoint_dir: Optional[Path] = None,
    ) -> None:
        self._chapter_writer = chapter_writer
        self._chapter_reviewer = chapter_reviewer
        self._global_reviewer = global_reviewer
        self._data_repair_agent = data_repair_agent
        self._conflict_resolver = conflict_resolver
        self._prompts = prompt_manager or PromptManager()
        self._data_registry = DataRegistry()
        self._task_structure: Dict[str, Any] = {}
        self._MAX_PRECEDING_SUMMARY_LENGTH = 3000
        self._llm_call_count = 0
        self._total_tokens_used = 0
        self._skill_registry = skill_registry
        self._search_gateway = search_gateway
        self._search_skill = search_skill
        self._web_scraper_skill = web_scraper_skill
        # Chart planning/rendering is injected by the production orchestrator
        # so report-upgrade tests remain deterministic and do not call an LLM.
        self._chart_planner = chart_planner
        self._chart_generator = chart_generator
        self._structured_data_repair = StructuredDataRepairAgent(skill_registry=skill_registry)
        self._llm_trace: List[Dict[str, Any]] = []
        self._chapters: List[ChapterWriteOutput] = []
        self._framework_config: Dict[str, Any] = {}
        self._repair_results: List[DataRepairResult] = []
        self._task_id: str = "report"
        # Keep checkpoints beside the task's output when the caller provides
        # an output directory. The legacy data/<task_id> location remains the
        # default for direct/standalone callers.
        self._checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir else None
        self._evidence_context = ReportEvidenceContext()
        self._coverage_checker = ChapterCoverageChecker()
        self._evidence_acquirer = ReportEvidenceAcquirer(
            search_gateway=search_gateway, prompt_manager=self._prompts,
        )
        # Rescue cache: agent-analysis material for chapters whose write
        # failed, so the defense loop can rewrite the chapter from existing
        # material instead of only searching for evidence.  Keyed by
        # chapter_id; value holds the raw chapter_data snapshot from the
        # write phase (content / upstream_data_points / section spec).
        self._chapter_rescue_cache: Dict[str, Dict[str, Any]] = {}
        self._evidence_search_count = 0

    def _report_progress(self, action: str, content: str) -> None:
        """Push a user-visible progress note for the running report task.

        The report-generation phase runs for tens of minutes with only
        log output; without these pushes the frontend conversation
        history shows nothing but periodic heartbeats.
        """
        try:
            from src.core.session_streamer import SessionStreamer
            SessionStreamer.push_agent_message(self._task_id, {
                "agent_id": "report_generator",
                "agent_name": "Report Generator",
                "action": action,
                "content": content,
            })
        except Exception:
            pass

    async def _plan_and_render_charts(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """Attach semantically planned chart artifacts to the final sections.

        The report-upgrade path used to return ``charts=[]`` unconditionally.
        That bypassed the existing HTML/DOCX/PPTX chart insertion contract.
        Planning happens after chapter writing and evidence repair so the LLM
        sees the final narrative and verified data, while rendering remains a
        deterministic local operation.
        """
        if self._chart_planner is None or self._chart_generator is None:
            return report

        from src.services.chart_generator import ChartSidecar, ChartSpec

        sidecar = None
        if self._checkpoint_dir is not None:
            try:
                sidecar = ChartSidecar(str(Path(self._checkpoint_dir) / "charts.json"))
            except Exception:
                logger.warning("Chart sidecar unavailable; continuing without audit records")
                sidecar = None

        for section in report.get("sections", []):
            if not isinstance(section, dict):
                continue
            try:
                plans = await self._chart_planner.plan(
                    content=str(section.get("content", "")),
                    topic=str(report.get("topic", "")),
                    section_title=str(section.get("title", "")),
                )
            except Exception as exc:
                logger.warning(
                    "Chart planning failed for section '%s': %s",
                    section.get("title", ""), exc,
                )
                section["charts"] = []
                continue

            charts = []
            for plan in plans or []:
                try:
                    spec = ChartSpec(
                        chart_type=plan.chart_type,
                        title=plan.title or section.get("title", ""),
                        data=plan.data,
                        question=plan.reason or plan.title or section.get("title", ""),
                        subtitle=plan.subtitle,
                        unit=plan.unit,
                        source=getattr(plan, "source", "") or "公开资料整理",
                        xlabel=plan.xlabel,
                        ylabel=plan.ylabel,
                        caption=plan.caption,
                    )
                    rendered = self._chart_generator.generate(spec)
                    if not rendered.success or not rendered.image_path:
                        logger.warning(
                            "Chart rendering failed for section '%s': %s",
                            section.get("title", ""), rendered.error,
                        )
                        continue
                    chart_ref = {
                        "path": rendered.image_path,
                        "caption": plan.caption or plan.title,
                        "title": plan.title,
                        "subtitle": plan.subtitle,
                        "source": getattr(plan, "source", "") or "公开资料整理",
                        "insertion_anchor": plan.insertion_anchor,
                        "anchor_type": plan.anchor_type,
                        "unit": plan.unit,
                    }
                    if sidecar is not None:
                        try:
                            ref = sidecar.append(
                                section=str(section.get("id") or section.get("title", "")),
                                spec=spec,
                                path=rendered.image_path,
                            )
                            chart_ref["chart_id"] = ref["chart_id"]
                        except Exception:
                            logger.warning("Chart sidecar append failed; continuing with light reference")
                    charts.append(chart_ref)
                except Exception as exc:
                    logger.warning(
                        "Chart rendering raised for section '%s': %s",
                        section.get("title", ""), exc,
                    )
            section["charts"] = charts
            logger.info(
                "Charts attached section='%s' planned=%d rendered=%d",
                section.get("title", ""), len(plans or []), len(charts),
            )
        return report

    async def generate_report(
        self,
        task_structure: Dict[str, Any],
        framework_config: Dict[str, Any],
        aggregated_result: Any,
        topic: str = "",
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self._generate_report_impl(
            task_structure, framework_config, aggregated_result, topic, task_id,
        )

    async def _generate_report_impl(
        self,
        task_structure: Dict[str, Any],
        framework_config: Dict[str, Any],
        aggregated_result: Any,
        topic: str = "",
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        last_error = None
        self._repair_results = []
        self._evidence_search_count = 0
        self._task_id = str(task_id or "report")

        for full_attempt in range(RetryPolicy.MAX_FULL_RETRIES + 1):
            try:
                chapter_specs = self._report_chapter_specs(task_structure)
                if task_id:
                    requested_section_ids = {
                        str(section.get("section_id", ""))
                        for section in chapter_specs
                        if section.get("section_id")
                    }
                    restored = await self._restore_from_checkpoint(
                        task_id,
                        allowed_section_ids=requested_section_ids,
                        checkpoint_root=getattr(self, "_checkpoint_dir", None),
                    )
                    if restored:
                        chapters, registry_snapshot = restored
                        self._data_registry = DataRegistry.from_snapshot(registry_snapshot)
                        preceding_summary = self._rebuild_preceding_summary(chapters)
                        completed_section_ids = {ch.chapter_id for ch in chapters}
                        logger.info(f"Restored {len(chapters)} chapters from checkpoint (attempt {full_attempt+1})")
                        self._report_progress(
                            "analyzing",
                            f"已从检查点恢复 {len(chapters)}/{len(chapter_specs)} 个已完成章节，继续生成剩余章节。",
                        )
                    else:
                        self._data_registry = DataRegistry()
                        chapters = []
                        preceding_summary = ""
                        completed_section_ids = set()
                else:
                    self._data_registry = DataRegistry()
                    chapters = []
                    preceding_summary = ""
                    completed_section_ids = set()

                self._task_structure = task_structure
                self._aggregated_result = aggregated_result
                self._framework_config = framework_config
                self._evidence_context = self._build_evidence_context(
                    aggregated_result, task_structure, task_id=self._task_id,
                )

                narrative_context = self._understand_framework(task_structure, framework_config)

                for section_spec in self._report_chapter_specs(task_structure):
                    section_id = section_spec.get("section_id", "")

                    if section_id in completed_section_ids:
                        continue

                    chapter_data, raw_data_summary = self._extract_chapter_data(
                        aggregated_result,
                        section_spec.get("parent_section_id", section_id),
                        section_spec.get("content_dependency", []),
                        sub_section_id=section_spec.get("sub_section_id", ""),
                        skill_registry=self._skill_registry,
                    )
                    requirement = self._build_chapter_requirement(section_spec)
                    coverage = self._coverage_checker.check(
                        requirement, chapter_data, self._evidence_context,
                    )
                    is_synthesis = str(section_spec.get("section_role", "")).lower() == "synthesis"
                    if not coverage.ready_to_write and not is_synthesis:
                        logger.warning(
                            "Chapter %s has uncovered requirements: topics=%s metrics=%s",
                            section_id, coverage.missing_topics, coverage.missing_metrics,
                        )
                        # Topics are first-class coverage requirements too.
                        # Using only missing_metrics here made an entire
                        # subsection disappear when it had no numeric metric.
                        missing_requirements = [
                            (metric, f"章节覆盖检查缺少指标：{metric}")
                            for metric in coverage.missing_metrics
                        ] + [
                            (topic_name, f"章节覆盖检查缺少主题/章节内容：{topic_name}")
                            for topic_name in coverage.missing_topics
                        ]
                        gaps = [
                            DataGap(
                                chapter_id=section_id,
                                metric=gap_name,
                                context=gap_context,
                                search_keywords=[gap_name, section_spec.get("name", "")],
                                audit_layer="coverage",
                            )
                            for gap_name, gap_context in missing_requirements
                        ]
                        found = [
                            item for item in await self._acquire_evidence_batch(
                                gaps, topic or task_structure.get("topic", ""),
                                scope="report_generation",
                            ) if item.found
                        ]
                        self._repair_results.extend(found)
                        for item in found:
                            chapter_data.setdefault("upstream_data_points", []).append({
                                "metric": item.gap.metric,
                                "value": item.value or "",
                                "unit": item.unit or "",
                                "source": item.source_title or item.source or "",
                                "source_url": item.source_url,
                                "evidence_id": item.evidence_id,
                                "provenance_id": item.provenance_id,
                                "evidence_excerpt": item.evidence_excerpt,
                                "period": item.period,
                                "geographic_scope": item.geographic_scope,
                                "population": item.population,
                                "epistemic_level": item.epistemic_level,
                            })
                        if found:
                            raw_data_summary = self._extract_raw_summary({
                                "data_points": chapter_data.get("upstream_data_points", []),
                            })
                            coverage = self._coverage_checker.check(
                                requirement, chapter_data, self._evidence_context,
                            )

                    chapter = await self._write_section_chapter(
                        section_spec=section_spec,
                        section_id=section_id,
                        task_structure=task_structure,
                        framework_config=framework_config,
                        chapter_data=chapter_data,
                        preceding_summary=preceding_summary,
                        raw_data_summary=raw_data_summary,
                    )

                    # Cache rescue material for ANY failed write, whichever
                    # path produced it: the production failure mode (logs
                    # 2026-10-14) is the writer returning a status=failed
                    # chapter object (JSON parse exhaustion), not an
                    # exception - only the None path got cached before.
                    if self._looks_like_failed_chapter(chapter):
                        self._cache_chapter_rescue_material(
                            section_id, section_spec, chapter_data,
                        )

                    chapters.append(chapter)
                    _chapter_title = str(chapter.title or section_spec.get("name") or section_id)
                    if chapter.status == "ready":
                        preceding_summary = self._append_preceding_summary(
                            preceding_summary, chapter
                        )
                        self._report_progress(
                            "completed",
                            f"✅ 章节「{_chapter_title}」已完成（约 {len(chapter.content or '')} 字，{len(chapters)}/{len(chapter_specs)}）。",
                        )
                    else:
                        self._report_progress(
                            "analyzing",
                            f"⚠️ 章节「{_chapter_title}」本轮未生成可验证内容，已标记待修补。",
                        )

                    if task_id:
                        await self._checkpoint_chapter(task_id, chapter)

                report_summary = serialize_report_for_review(chapters, self._data_registry)
                conflicts_summary = self._data_registry.serialize_conflicts()

                review = await self._global_reviewer.review(
                    ReviewInput(
                        framework_config=framework_config,
                        report_summary=report_summary,
                        conflicts_summary=conflicts_summary,
                    )
                )

                if review.issues:
                    verified_issues = await self._global_reviewer.verify_issues(
                        review.issues, chapters,
                    )
                    review.issues = verified_issues

                quality_report = QualityReport()
                if review.overall_score < RetryPolicy.TARGET_SCORE:
                    chapters, quality_report = await self._quality_convergence_loop(
                        chapters, review, framework_config, topic, task_structure,
                    )

                original_sources = self._merge_repair_sources(
                    getattr(aggregated_result, 'sources', []),
                    self._repair_results,
                )
                return await self._run_defense_repair_loop(
                    chapters=chapters,
                    review=review,
                    framework_config=framework_config,
                    topic=topic,
                    task_structure=task_structure,
                    original_sources=original_sources,
                    quality_report=quality_report,
                    conflicts_summary=conflicts_summary,
                )

            except Exception as e:
                last_error = e
                logger.exception("Report generation attempt %d failed", full_attempt + 1)
                if full_attempt < RetryPolicy.MAX_FULL_RETRIES:
                    delay = RetryPolicy.get_delay(full_attempt)
                    logger.warning(f"Full attempt {full_attempt+1} failed: {e}")
                    await asyncio.sleep(delay)

        raise RuntimeError(
            f"Report generation failed after {RetryPolicy.MAX_FULL_RETRIES + 1} attempts. "
            f"Last error: {last_error}"
        )

    async def _write_section_chapter(
        self,
        *,
        section_spec: Dict[str, Any],
        section_id: str,
        task_structure: Dict[str, Any],
        framework_config: Dict[str, Any],
        chapter_data: Any,
        preceding_summary: str,
        raw_data_summary: str,
    ) -> ChapterWriteOutput:
        """Single engine-budgeted write per section (spec §8#9).

        writer.write() runs the failure-aware retry engine internally and
        returns either a ready chapter or a failed chapter (budget
        exhausted), so re-running it with identical input cannot change a
        deterministic outcome: the retired blind MAX_CHAPTER_RETRIES loop
        is gone and write() is called exactly once per phase-4 pass.  A
        non-ready chapter is finalized as a visible failed placeholder and
        its write material is cached for the Defense rescue pass (spec A3).
        """
        safe_chapter_data = chapter_data if isinstance(chapter_data, dict) else {}
        base_content = safe_chapter_data.get("content", "")
        upstream_data_points = safe_chapter_data.get("upstream_data_points")
        requirement = self._build_chapter_requirement(section_spec)
        coverage = self._coverage_checker.check(requirement, safe_chapter_data, self._evidence_context)

        chapter: Optional[ChapterWriteOutput] = None
        write_error = ""
        try:
            chapter = await self._chapter_writer.write(
                ChapterWriteInput(
                    framework_config=framework_config,
                    task_structure=task_structure,
                    chapter_spec=section_spec,
                    chapter_data=chapter_data,
                    raw_data_summary=raw_data_summary,
                    preceding_summary=preceding_summary,
                    used_metrics_summary=self._data_registry.serialize_used_metrics(),
                    base_content=base_content,
                    upstream_data_points=upstream_data_points,
                    parent_section_context=section_spec.get("parent_section_context", {}),
                    global_evidence_pool=self._evidence_context.raw_search_results,
                    raw_search_results=self._evidence_context.raw_search_results,
                    raw_data_location=str(
                        Path("data", self._task_id, "research_result_cache.json").resolve()
                    ),
                    sibling_section_summaries=self._evidence_context.section_index.get("siblings", []),
                    chapter_requirements={**asdict(requirement), "coverage": asdict(coverage)},
                    used_evidence_ids=[
                        str(dp.get("evidence_id", ""))
                        for dp in (upstream_data_points or [])
                        if isinstance(dp, dict) and dp.get("evidence_id")
                    ],
                    output_format=str(
                        task_structure.get("output_format", "docx")
                    ),
                )
            )
        except Exception as e:
            # Budget exhaustion surfaces as a failed chapter object, not an
            # exception; remaining failures converge to a failed chapter so
            # the Defense rescue pass can retry with cached material.  Only
            # hard account/config errors abort the whole report.
            if self._is_non_retryable_error(e):
                raise
            write_error = str(e)
            logger.error(f"Chapter {section_id} write failed: {e}")

        if chapter is not None:
            chapter.content = _enforce_structure_compliance(chapter.content)

            # Log planning assessment from LLM
            if chapter.planning_assessment:
                assessment = chapter.planning_assessment
                logger.info(
                    "CHAPTER_PLANNING_ASSESSMENT section=%s severity=%s "
                    "framework_issues=%s data_sufficiency=%s recommended=%s",
                    section_id,
                    assessment.get("severity", "unknown"),
                    assessment.get("framework_issues", []),
                    assessment.get("data_sufficiency", {}),
                    assessment.get("recommended_actions", []),
                )
                if assessment.get("severity") in ("high", "critical"):
                    logger.warning(
                        "Chapter %s flagged %s severity issues: %s",
                        section_id,
                        assessment.get("severity"),
                        assessment.get("framework_issues", []),
                    )

            validated_dps = self._extract_and_validate_data_points(chapter)
            for dp in validated_dps:
                self._data_registry.register(
                    metric=dp.metric, value=dp.value, unit=dp.unit,
                    chapter_id=chapter.chapter_id, source=dp.source,
                    evidence_id=dp.evidence_id, provenance_id=dp.provenance_id,
                    source_url=dp.source_url, period=dp.period,
                    geographic_scope=dp.geographic_scope, population=dp.population,
                )

            if str(getattr(chapter, "status", "ready") or "ready").lower() == "ready":
                best_chapter = chapter
                best_score = 0.0

                for rewrite_round in range(RetryPolicy.MAX_REVIEW_RETRIES):
                    review = await self._chapter_reviewer.review(
                        ChapterReviewInput(
                            framework_config=framework_config,
                            chapter_spec=section_spec,
                            chapter_content=chapter.content,
                            preceding_summary=preceding_summary,
                            used_metrics_summary=self._data_registry.serialize_used_metrics(),
                            topic=task_structure.get('topic', ''),
                            writer_self_check_issues=chapter.self_check_issues,
                            chapter_data=chapter_data,
                        )
                    )

                    if getattr(review, "parse_failed", False):
                        # Reviewer output was unparseable: no usable signal to
                        # rewrite against. Skip patch/rewrite this round; the
                        # round still counts toward MAX_REVIEW_RETRIES so a
                        # persistently-failing reviewer cannot loop forever.
                        logger.warning(
                            "Chapter %s review parse failed (round %s); "
                            "skipping rewrite this round",
                            section_id, rewrite_round,
                        )
                        # I2: parse_failed 消耗轮次但有日志无状态传播
                        FailureAudit.record(
                            stage="report.review",
                            subject_id=str(chapter.chapter_id),
                            action="skip_rewrite",
                            reason="reviewer parse_failed",
                            task_id=self._task_id,
                        )
                        continue

                    if review.score > best_score:
                        best_chapter = chapter
                        best_score = review.score

                    if review.passed or review.score >= RetryPolicy.TARGET_SCORE:
                        break
                    if review.score >= RetryPolicy.MIN_REVIEW_SCORE_TO_ACCEPT and rewrite_round >= 2:
                        break

                    anchoring_issues = [
                        iss for iss in review.issues
                        if iss.category in ("data_anchoring", "data_support")
                        and iss.severity in ("CRITICAL", "HIGH")
                    ]
                    logic_issues = [
                        iss for iss in review.issues
                        if iss.category not in ("data_anchoring", "data_support")
                        and iss.severity in ("CRITICAL", "HIGH")
                    ]

                    if anchoring_issues:
                        patch_instructions = self._build_anchor_patch_instructions(
                            anchoring_issues, chapter_data,
                            raw_data_summary=raw_data_summary,
                        )
                        if patch_instructions:
                            patched = await self._chapter_writer.patch_data(
                                chapter=chapter,
                                patch_instructions=patch_instructions,
                                framework_config=framework_config,
                            )
                            patch_review = await self._chapter_reviewer.review(
                                ChapterReviewInput(
                                    framework_config=framework_config,
                                    chapter_spec=section_spec,
                                    chapter_content=patched.content,
                                    preceding_summary=preceding_summary,
                                    used_metrics_summary=self._data_registry.serialize_used_metrics(),
                                    topic=task_structure.get('topic', ''),
                                    chapter_data=chapter_data,
                                )
                            )
                            if patch_review.score >= review.score:
                                chapter = patched
                                validated_dps = self._extract_and_validate_data_points(chapter)
                                for dp in validated_dps:
                                    self._data_registry.register(
                                        metric=dp.metric, value=dp.value, unit=dp.unit,
                                        chapter_id=chapter.chapter_id, source=dp.source,
                                        evidence_id=dp.evidence_id, provenance_id=dp.provenance_id,
                                        source_url=dp.source_url, period=dp.period,
                                        geographic_scope=dp.geographic_scope, population=dp.population,
                                    )
                            if patch_review.score > best_score:
                                best_chapter = chapter
                                best_score = patch_review.score
                            if patch_review.passed or patch_review.score >= RetryPolicy.TARGET_SCORE:
                                break
                            if patch_review.score >= RetryPolicy.MIN_REVIEW_SCORE_TO_ACCEPT and rewrite_round >= 2:
                                break

                    if logic_issues and best_score < RetryPolicy.TARGET_SCORE:
                        chapter = await self._chapter_writer.rewrite(
                            original_chapter=chapter,
                            review_feedback=review,
                            framework_config=framework_config,
                            chapter_spec=section_spec,
                            preceding_summary=preceding_summary,
                            chapter_data=chapter_data,
                        )
                        rewrite_review = await self._chapter_reviewer.review(
                            ChapterReviewInput(
                                framework_config=framework_config,
                                chapter_spec=section_spec,
                                chapter_content=chapter.content,
                                preceding_summary=preceding_summary,
                                used_metrics_summary=self._data_registry.serialize_used_metrics(),
                                topic=task_structure.get('topic', ''),
                                chapter_data=chapter_data,
                            )
                        )
                        if rewrite_review.score > best_score:
                            best_chapter = chapter
                            best_score = rewrite_review.score
                        if rewrite_review.passed or rewrite_review.score >= RetryPolicy.TARGET_SCORE:
                            break
                        if rewrite_review.score >= RetryPolicy.MIN_REVIEW_SCORE_TO_ACCEPT and rewrite_round >= 2:
                            break

                chapter = best_chapter
                return chapter

        if chapter is None:
            logger.error(f"Chapter {section_id} failed after engine budget")
            # Keep the planned chapter visible in the report.  A
            # silent continue makes the actual chapter set look
            # complete to downstream consumers and prevents L0
            # coverage from distinguishing failure from omission.
            failure_title = str(section_spec.get("name") or section_spec.get("title") or section_id)
            failure_reason = write_error or "chapter_write_failed"
            chapter = ChapterWriteOutput(
                chapter_id=section_id,
                title=failure_title,
                # Never emit an empty section.  Keep the chapter
                # visible with a controlled, auditable status
                # sentence; coverage still treats status=failed
                # as blocking and the defense loop can repair it.
                content=(
                    f"本章节未生成可验证内容（{failure_reason[:240]}）。"
                    "系统已记录该章节失败状态，后续修订应补充证据后重新生成。"
                ),
                sub_section_id=str(section_spec.get("sub_section_id") or ""),
                self_check_passed=False,
                self_check_issues=[write_error or "chapter_write_failed"],
                status="failed",
                error=write_error or "chapter_write_failed",
            )
        logger.warning(
            "Chapter %s not ready after engine budget (%s); Defense rescue will retry with cached material",
            section_id, getattr(chapter, "error", ""),
        )
        return chapter

    @staticmethod
    def _understand_framework(task_structure: Dict, framework_config: Dict) -> str:
        sections = task_structure.get("sections", [])
        section_names = [s.get("section_name", "") for s in sections]
        return (
            f"研究主题：{task_structure.get('topic', '')}\n"
            f"框架配置：{framework_config.get('name', '通用研究报告')}\n"
            f"章节结构：{' → '.join(section_names)}"
        )

    def _resolve_chapter_id(self, location: str, chapters: List[ChapterWriteOutput]) -> str:
        if not location:
            return ""
        if isinstance(location, (list, tuple, set)):
            for item in location:
                resolved = self._resolve_chapter_id(str(item or "").strip(), chapters)
                if resolved:
                    return resolved
            return ""
        location = str(location).strip()
        for ch in chapters:
            if ch.chapter_id == location or ch.title == location:
                return ch.chapter_id
        cn_num_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4,
                      "六": 5, "七": 6, "八": 7, "九": 8, "十": 9}
        m = re.search(r'第([一二三四五六七八九十\d])[章节]', location)
        if m:
            idx_str = m.group(1)
            idx = cn_num_map.get(idx_str, int(idx_str) if idx_str.isdigit() else -1)
            if 0 <= idx < len(chapters):
                return chapters[idx].chapter_id
        for ch in chapters:
            if ch.chapter_id in location or ch.title[:10] in location:
                return ch.chapter_id
        return ""

    async def _quality_convergence_loop(
        self,
        chapters: List[ChapterWriteOutput],
        review: ReviewOutput,
        framework_config: Dict,
        topic: str,
        task_structure: Dict,
    ) -> tuple:
        quality_report = QualityReport()
        prev_score = review.overall_score
        best_chapters = list(chapters)
        best_score = prev_score
        processed_issue_keys: Set[str] = set()

        for round_idx in range(RetryPolicy.MAX_CONVERGENCE_ROUNDS):
            logger.info(f"Convergence round {round_idx + 1}/{RetryPolicy.MAX_CONVERGENCE_ROUNDS}, score={prev_score:.1f}")
            active_issues = [
                issue for issue in (review.issues or [])
                if self._quality_issue_key(issue, chapters) not in processed_issue_keys
            ]
            if not active_issues:
                logger.info("Convergence stopped: no unprocessed quality issues remain")
                break
            review_for_repair = ReviewOutput(
                overall_score=review.overall_score,
                dimension_scores=review.dimension_scores,
                issues=active_issues,
                fix_suggestions=review.fix_suggestions,
            )
            before_fingerprints = [
                hashlib.sha256((chapter.content or "").encode("utf-8")).hexdigest()
                for chapter in chapters
            ]
            chapters = await self._phase4_fix_and_optimize(
                chapters, review_for_repair, framework_config, topic,
            )
            processed_issue_keys.update(
                self._quality_issue_key(issue, chapters) for issue in active_issues
            )
            after_fingerprints = [
                hashlib.sha256((chapter.content or "").encode("utf-8")).hexdigest()
                for chapter in chapters
            ]
            if before_fingerprints == after_fingerprints:
                logger.info("Convergence stopped: repair produced no content change")
                break

            report_summary = serialize_report_for_review(chapters, self._data_registry)
            conflicts_summary = self._data_registry.serialize_conflicts()
            review = await self._global_reviewer.review(
                ReviewInput(
                    framework_config=framework_config,
                    report_summary=report_summary,
                    conflicts_summary=conflicts_summary,
                )
            )
            if review.issues:
                verified = await self._global_reviewer.verify_issues(review.issues, chapters)
                review.issues = verified

            current_score = review.overall_score
            quality_report.convergence_rounds = round_idx + 1
            quality_report.overall_score = current_score

            if current_score > best_score:
                best_chapters = list(chapters)
                best_score = current_score

            if current_score >= RetryPolicy.TARGET_SCORE:
                quality_report.converged = True
                logger.info(f"Converged at round {round_idx + 1}, score={current_score:.1f}")
                break

            improvement = current_score - prev_score
            if improvement < RetryPolicy.get_min_improvement(round_idx):
                logger.info(f"Convergence stalled at round {round_idx + 1}, improvement={improvement:.1f}")
                break

            prev_score = current_score

        quality_report.overall_score = best_score
        if not quality_report.chapter_diagnostics:
            for ch in best_chapters:
                quality_report.chapter_diagnostics.append(
                    ChapterDiagnostic(
                        chapter_id=ch.chapter_id,
                        score=best_score,
                        source_layer="convergence",
                    )
                )

        return best_chapters, quality_report

    async def _phase4_fix_and_optimize(
        self,
        chapters: List[ChapterWriteOutput],
        review: ReviewOutput,
        framework_config: Dict,
        topic: str,
    ) -> List[ChapterWriteOutput]:
        data_gaps = []
        patch_chapter_ids: Set[str] = set()
        rewrite_chapter_ids: Set[str] = set()
        structured_data_repairs: Dict[str, List[Dict[str, Any]]] = {}

        # A3: AnalysisQualityChecker programmatic pre-check
        _checker = AnalysisQualityChecker()
        for ch in chapters:
            checker_result = _checker.check({"content": ch.content})
            if checker_result.score < 60:
                if ch.chapter_id not in (patch_chapter_ids | rewrite_chapter_ids):
                    patch_chapter_ids.add(ch.chapter_id)

        for issue in review.issues:
            resolved_id = self._resolve_chapter_id(issue.location, chapters)
            raw_summary = ""
            if resolved_id:
                ch_spec = self._find_section_spec(resolved_id, framework_config)
                _, raw_summary = self._extract_chapter_data(
                    self._aggregated_result,
                    ch_spec.get("parent_section_id", resolved_id) if ch_spec else resolved_id,
                    ch_spec.get("content_dependency", []) if ch_spec else [],
                    sub_section_id=ch_spec.get("sub_section_id", "") if ch_spec else "",
                    skill_registry=self._skill_registry,
                )

            chapter_issue = ChapterIssue(
                category=issue.dimension,
                severity=issue.severity,
                location=issue.location,
                description=issue.description,
                suggestion=issue.evidence if hasattr(issue, 'evidence') and issue.evidence else issue.description[:100],
            )
            diagnosis = self._diagnose_issue_source(chapter_issue, raw_summary)

            if issue.dimension == "data_consistency":
                if resolved_id:
                    patch_chapter_ids.add(resolved_id)
            elif diagnosis.source_layer == "L2_omitted":
                if resolved_id:
                    patch_chapter_ids.add(resolved_id)
            elif diagnosis.source_layer == "L1_missing":
                metric = self._extract_metric(issue.description)
                data_gaps.append(DataGap(
                    chapter_id=resolved_id or issue.location,
                    metric=metric,
                    context=issue.description,
                    search_keywords=self._build_search_keywords(issue.description, topic),
                ))
                if resolved_id:
                    patch_chapter_ids.add(resolved_id)
                stock_code = None
                try:
                    from src.core.entity_resolver import get_entity_resolver
                    resolver = get_entity_resolver()
                    entities = await resolver.resolve(topic)
                    for ent in entities:
                        if ent.resolved_code:
                            stock_code = ent.resolved_code
                            break
                except Exception:
                    pass
                try:
                    fill_result = await self._try_fill_data_gap(metric, topic, stock_code=stock_code)
                    if fill_result:
                        structured_data_repairs.setdefault(resolved_id or issue.location, []).append(fill_result)
                except Exception as e:
                    logger.warning(f"Structured data repair failed for {metric}: {e}")
            elif diagnosis.source_layer == "L2_fabricated":
                if resolved_id:
                    patch_chapter_ids.add(resolved_id)
            elif issue.severity in ("CRITICAL", "HIGH") and resolved_id:
                rewrite_chapter_ids.add(resolved_id)

        data_conflicts = self._data_registry.get_conflicts()

        repair_task = self._acquire_evidence_batch(
            data_gaps, topic, scope="report_revision",
        )
        resolve_tasks = [self._conflict_resolver.resolve(c, topic) for c in data_conflicts]

        repair_results, *resolution_results = await asyncio.gather(
            repair_task, *resolve_tasks,
        )
        self._repair_results.extend(
            result for result in repair_results if result.found
        )

        chapters, patched_chapter_ids = await self._apply_data_repairs(
            chapters, repair_results, resolution_results, framework_config,
        )

        # A structured repair can produce several metrics for one chapter.
        # Patch that chapter once so a large audit result cannot turn into one
        # LLM call per metric.  The individual repairs remain available below
        # for their evidence and provenance to be registered separately.
        for ch_id, repairs in structured_data_repairs.items():
            patch_instructions = [
                f"补充结构化数据（来源：{repair['source']}）："
                f"{json.dumps(repair['data'], ensure_ascii=False, indent=2)[:500]}"
                for repair in repairs
            ]
            ch_idx = next((i for i, c in enumerate(chapters) if c.chapter_id == ch_id), None)
            if ch_idx is not None and patch_instructions:
                patched = await self._chapter_writer.patch_data(
                    chapter=chapters[ch_idx],
                    patch_instructions=patch_instructions,
                    framework_config=framework_config,
                )
                chapters[ch_idx] = patched
                patched_chapter_ids.add(ch_id)

        rewrite_needed = patched_chapter_ids | rewrite_chapter_ids
        patch_needed = patch_chapter_ids - rewrite_chapter_ids
        preceding_summary = self._rebuild_preceding_summary(chapters)

        for i, chapter in enumerate(chapters):
            if chapter.chapter_id not in (patch_needed | rewrite_needed):
                continue
            chapter_spec = self._find_section_spec(chapter.chapter_id, framework_config)
            re_chapter_data, re_raw_summary = self._extract_chapter_data(
                self._aggregated_result,
                chapter_spec.get("parent_section_id", chapter.chapter_id) if chapter_spec else chapter.chapter_id,
                chapter_spec.get("content_dependency", []) if chapter_spec else [],
                sub_section_id=chapter_spec.get("sub_section_id", "") if chapter_spec else "",
                skill_registry=self._skill_registry,
            )

            if chapter.chapter_id in patch_needed:
                relevant_issues = [
                    iss for iss in review.issues
                    if self._resolve_chapter_id(iss.location, chapters) == chapter.chapter_id
                    and iss.dimension == "data_consistency"
                ]
                anchoring_issues = [
                    iss for iss in review.issues
                    if self._resolve_chapter_id(iss.location, chapters) == chapter.chapter_id
                    and iss.dimension in ("data_anchoring", "data_support")
                    and iss.severity in ("CRITICAL", "HIGH")
                ]
                all_patch_issues = relevant_issues + anchoring_issues
                patch_instructions = self._build_anchor_patch_instructions(
                    all_patch_issues, re_chapter_data, raw_data_summary=re_raw_summary,
                )
                if patch_instructions:
                    patched = await self._chapter_writer.patch_data(
                        chapter=chapter,
                        patch_instructions=patch_instructions,
                        framework_config=framework_config,
                    )
                    patch_review = await self._chapter_reviewer.review(
                        ChapterReviewInput(
                            framework_config=framework_config,
                            chapter_spec=chapter_spec,
                            chapter_content=patched.content,
                            preceding_summary=preceding_summary,
                            used_metrics_summary=self._data_registry.serialize_used_metrics(),
                            topic=self._task_structure.get('topic', ''),
                            chapter_data=re_chapter_data,
                        )
                    )
                    if patch_review.score >= 60:
                        chapters[i] = patched
                    validated_dps = self._extract_and_validate_data_points(chapters[i])
                    for dp in validated_dps:
                        self._data_registry.register(
                            metric=dp.metric, value=dp.value, unit=dp.unit,
                            chapter_id=chapters[i].chapter_id, source=dp.source,
                            evidence_id=dp.evidence_id, provenance_id=dp.provenance_id,
                            source_url=dp.source_url, period=dp.period,
                            geographic_scope=dp.geographic_scope, population=dp.population,
                        )

            if chapter.chapter_id in rewrite_chapter_ids:
                relevant_issues = [
                    iss for iss in review.issues
                    if self._resolve_chapter_id(iss.location, chapters) == chapter.chapter_id
                    and iss.severity in ("CRITICAL", "HIGH")
                    and iss.dimension != "data_consistency"
                ]
                if relevant_issues or chapter.chapter_id in patched_chapter_ids:
                    re_review = await self._chapter_reviewer.review(
                        ChapterReviewInput(
                            framework_config=framework_config,
                            chapter_spec=chapter_spec,
                            chapter_content=chapters[i].content,
                            preceding_summary=preceding_summary,
                            used_metrics_summary=self._data_registry.serialize_used_metrics(),
                            topic=self._task_structure.get('topic', ''),
                            chapter_data=re_chapter_data,
                        )
                    )

                    if not re_review.passed:
                        global_issues = [
                            ChapterIssue(
                                category=iss.dimension, severity=iss.severity,
                                location=iss.location, description=iss.description,
                                suggestion=iss.evidence if hasattr(iss, 'evidence') and iss.evidence else iss.description[:100],
                            )
                            for iss in relevant_issues
                        ]
                        combined_issues = list(re_review.issues) + global_issues
                        combined_review = ChapterReviewOutput(
                            passed=re_review.passed,
                            score=re_review.score,
                            issues=combined_issues,
                        )
                        rewritten = await self._chapter_writer.rewrite(
                            original_chapter=chapters[i],
                            review_feedback=combined_review,
                            framework_config=framework_config,
                            chapter_spec=chapter_spec,
                            preceding_summary=preceding_summary,
                            chapter_data=re_chapter_data,
                        )
                        rewrite_review = await self._chapter_reviewer.review(
                            ChapterReviewInput(
                                framework_config=framework_config,
                                chapter_spec=chapter_spec,
                                chapter_content=rewritten.content,
                                preceding_summary=preceding_summary,
                                used_metrics_summary=self._data_registry.serialize_used_metrics(),
                                topic=self._task_structure.get('topic', ''),
                                chapter_data=re_chapter_data,
                            )
                        )
                        if rewrite_review.score > re_review.score:
                            chapters[i] = rewritten

        preceding_summary = self._rebuild_preceding_summary(chapters)
        propagation = self._propagate_canonical_updates(chapters, rewrite_needed)
        consistency = self._verify_downstream_consistency(chapters, rewrite_needed)
        self._last_downstream_consistency = {
            "propagation": propagation,
            "consistency": consistency,
        }

        return chapters

    async def _apply_data_repairs(
        self,
        chapters: List[ChapterWriteOutput],
        repair_results: List[DataRepairResult],
        conflict_resolutions: List[DataConflictResolution],
        framework_config: Dict,
    ) -> Tuple[List[ChapterWriteOutput], Set[str]]:
        chapter_updates: Dict[str, List[Dict]] = {}

        for result in repair_results:
            if result.found:
                chapter_updates.setdefault(result.gap.chapter_id, []).append({
                    "type": "gap_filled",
                    "metric": result.gap.metric,
                    "new_value": result.value,
                    "unit": result.unit,
                    "source": result.source,
                })

        for resolution in conflict_resolutions:
            if not isinstance(resolution, DataConflictResolution):
                logger.warning("Skipping invalid conflict resolution result: %r", resolution)
                continue
            for chapter_id in resolution.chapters_to_update:
                chapter_updates.setdefault(chapter_id, []).append({
                    "type": "conflict_resolved",
                    "metric": resolution.conflict.metric,
                    "canonical_value": resolution.canonical_value,
                    "canonical_unit": resolution.canonical_unit,
                    "canonical_source": resolution.canonical_source,
                    "reason": resolution.reason,
                })

        patched_chapter_ids: Set[str] = set()

        for i, chapter in enumerate(chapters):
            updates = chapter_updates.get(chapter.chapter_id, [])
            if not updates:
                continue

            patch_instructions = []
            for update in updates:
                if update["type"] == "gap_filled":
                    patch_instructions.append(
                        f"补充缺失数据：{update['metric']} = {update['new_value']} {update['unit']}"
                        f"（来源：{update['source']}）"
                    )
                elif update["type"] == "conflict_resolved":
                    patch_instructions.append(
                        f"数据冲突修正：{update['metric']} 统一为 {update['canonical_value']} "
                        f"{update['canonical_unit']}（来源：{update['canonical_source']}，"
                        f"理由：{update['reason']}）"
                    )

            patched_chapter = await self._chapter_writer.patch_data(
                chapter=chapter,
                patch_instructions=patch_instructions,
                framework_config=framework_config,
            )
            if (
                not isinstance(patched_chapter, ChapterWriteOutput)
                or str(patched_chapter.status or "ready").lower() != "ready"
                or not str(patched_chapter.content or "").strip()
            ):
                logger.warning(
                    "Skipping failed/empty data patch for chapter %s; preserving original content",
                    chapter.chapter_id,
                )
                continue
            chapters[i] = patched_chapter
            # Preserve the structured evidence chain returned by the repair
            # agent.  Text instructions alone are insufficient for L3: the
            # data point itself must carry the URL and provenance identities.
            for result in repair_results:
                if not result.found or result.gap.chapter_id != chapter.chapter_id:
                    continue
                for data_point in chapters[i].data_points_used or []:
                    metric = data_point.get("metric") if isinstance(data_point, dict) else data_point.metric
                    if metric != result.gap.metric:
                        continue
                    target = data_point if isinstance(data_point, dict) else vars(data_point)
                    for field_name in (
                        "value", "unit", "source", "source_url", "evidence_id",
                        "provenance_id", "evidence_excerpt", "locator", "task_id",
                        "request_id", "retrieved_at", "geographic_scope", "period",
                        "population", "epistemic_level",
                    ):
                        value = getattr(result, field_name, None)
                        if value not in (None, ""):
                            target[field_name] = value
                    target["evidence_status"] = (
                        "verified"
                        if target.get("source_url")
                        and target.get("evidence_id")
                        and target.get("provenance_id")
                        and (target.get("evidence_excerpt") or target.get("locator"))
                        else "unverified"
                    )
                    break
            patched_chapter_ids.add(chapter.chapter_id)

            for update in updates:
                if update["type"] == "conflict_resolved":
                    self._data_registry.set_canonical_value(
                        metric=update["metric"],
                        value=update["canonical_value"],
                        source=update["canonical_source"],
                    )

        return chapters, patched_chapter_ids

    @staticmethod
    def _iter_report_chapter_specs(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Expand configured sub-sections into independently writable chapters."""
        expanded: List[Dict[str, Any]] = []
        # Synthesis chapters (摘要/总结/展望) must be written after all
        # analytical chapters.  Their content is derived from completed
        # sibling chapters and must never enter the data-collection queue.
        ordered_sections = sorted(
            sections or [],
            key=lambda item: (
                1 if str(item.get("section_role", "")).lower() == "synthesis" else 0,
                item.get("execution_order", 10**9),
            ),
        )
        for parent in ordered_sections:
            parent_id = str(parent.get("section_id", "")).strip()
            sub_sections = parent.get("sub_section_requirements", parent.get("sub_sections", [])) or []
            if not sub_sections:
                expanded.append(dict(parent, execution_order=parent.get("execution_order", len(expanded))))
                continue
            for index, sub in enumerate(sub_sections, 1):
                if not isinstance(sub, dict):
                    continue
                sub_id = str(
                    sub.get("sub_section_id") or sub.get("id") or f"sub_{index}"
                ).strip()
                sub_name = str(sub.get("name") or sub_id).strip()
                child = dict(parent)
                child["parent_section_id"] = parent_id
                child["section_id"] = f"{parent_id}::{sub_id}"
                child["section_name"] = f"{parent.get('section_name', parent_id)} - {sub_name}"
                child["sub_section_id"] = sub_id
                child["sub_sections"] = [dict(sub, sub_section_id=sub_id)]
                child["sub_section_requirements"] = [dict(sub, sub_section_id=sub_id)]
                child["config"] = {
                    **(parent.get("config", {}) or {}),
                    "description": sub.get("description") or sub_name,
                }
                child["execution_order"] = parent.get("execution_order", len(expanded))
                expanded.append(child)
        return expanded

    @staticmethod
    def _build_chapter_requirement(section_spec: Dict[str, Any]) -> ChapterRequirement:
        """Normalize legacy section specs into the coverage contract."""
        requirements = section_spec.get("requirements", {}) or {}
        sub_specs = section_spec.get("sub_section_requirements", section_spec.get("sub_sections", [])) or []
        sub_topics = [str(item.get("name", "")) for item in sub_specs if isinstance(item, dict) and item.get("name")]
        sub_metrics = [
            str(metric) for item in sub_specs if isinstance(item, dict)
            for metric in (item.get("required_metrics", item.get("points", [])) or [])
            if str(metric).strip()
        ]
        required_topics = requirements.get("required_topics", section_spec.get("required_topics", [])) or []
        required_metrics = requirements.get(
            "required_metrics", section_spec.get("required_metrics", section_spec.get("data_needs", [])),
        ) or []
        return ChapterRequirement(
            section_id=str(section_spec.get("section_id", "")),
            sub_section_id=str(section_spec.get("sub_section_id", "")),
            required_topics=list(dict.fromkeys([*required_topics, *sub_topics])),
            required_metrics=list(dict.fromkeys([*required_metrics, *sub_metrics])),
            claim_scope=str(requirements.get("claim_scope", section_spec.get("claim_scope", "")) or ""),
            exclude_topics=list(
                requirements.get("exclude_topics", section_spec.get("exclude_topics", [])) or []
            ),
            evidence_level=str(
                requirements.get("evidence_level", section_spec.get("evidence_level", "factual"))
                or "factual"
            ),
        )

    @staticmethod
    def _read_aggregate_field(aggregated_result: Any, name: str, default: Any = None) -> Any:
        """Read fields from both current aggregate objects and old dict snapshots."""
        if isinstance(aggregated_result, dict):
            return aggregated_result.get(name, default)
        return getattr(aggregated_result, name, default)

    @staticmethod
    def _build_evidence_context(
        aggregated_result: Any, task_structure: Dict[str, Any], task_id: str = "report",
    ) -> ReportEvidenceContext:
        """Build a backward-compatible, report-wide evidence view."""
        raw_results = list(
            ReportOrchestrator._read_aggregate_field(
                aggregated_result, "raw_search_results", [],
            ) or []
        )
        sources = list(
            ReportOrchestrator._read_aggregate_field(aggregated_result, "sources", []) or []
        )
        if not raw_results:
            raw_results = [dict(item) for item in sources if isinstance(item, dict)]
        catalog = ReportOrchestrator._ensure_source_evidence_identity(
            raw_results, task_id=task_id,
        )
        registry = dict(
            ReportOrchestrator._read_aggregate_field(
                aggregated_result, "evidence_registry", {},
            ) or {}
        )
        for item in catalog:
            evidence_id = str(item.get("evidence_id") or "").strip()
            if evidence_id:
                registry.setdefault(evidence_id, item)
        section_index = {
            "sections": [
                {
                    "section_id": spec.get("section_id", ""),
                    "section_name": spec.get("section_name", ""),
                    "sub_section_id": spec.get("sub_section_id", ""),
                    "sub_sections": spec.get("sub_sections", spec.get("sub_section_requirements", [])),
                }
                for spec in task_structure.get("sections", [])
            ],
            "siblings": [],
        }
        section_index["siblings"] = list(section_index["sections"])
        return ReportEvidenceContext(
            structured_data=ReportOrchestrator._read_aggregate_field(
                aggregated_result, "data", {},
            ) or {},
            raw_search_results=catalog,
            source_catalog=catalog,
            evidence_registry=registry,
            section_index=section_index,
        )

    async def _acquire_evidence_batch(
        self, gaps: List[DataGap], topic: str, scope: str,
    ) -> List[DataRepairResult]:
        """Search and extract evidence under the report workflow's budget."""
        if not gaps:
            return []
        # Compatibility adapter for callers restoring an old orchestrator
        # with an injected repair agent. Production constructors no longer
        # inject one; all new searches use the report-owned acquirer below.
        if self._search_gateway is None and self._data_repair_agent is not None:
            return await self._data_repair_agent.repair_batch(gaps, topic)
        results: List[DataRepairResult] = []
        pending: List[DataGap] = []
        for gap in gaps:
            reused = self._reuse_existing_evidence(gap)
            if reused is not None:
                results.append(reused)
            else:
                pending.append(gap)

        before_searches = self._gateway_scope_searches(scope)
        if pending:
            results.extend(await asyncio.gather(*(
                self._evidence_acquirer.acquire(gap, topic, scope=scope)
                for gap in pending
            )))
        after_searches = self._gateway_scope_searches(scope)
        if before_searches is not None and after_searches is not None:
            self._evidence_search_count += max(0, after_searches - before_searches)
        elif pending:
            # Test doubles and legacy gateways may not expose statistics. In
            # that case count attempted gateway requests, not reused evidence.
            self._evidence_search_count += len(pending)

        for result in results:
            if not result.found or not result.source_url:
                continue
            evidence = {
                "title": result.source_title or result.source or result.source_url,
                "url": result.source_url,
                "evidence_excerpt": result.evidence_excerpt,
                "evidence_id": result.evidence_id,
                "provenance_id": result.provenance_id,
                "locator": result.locator,
            }
            if result.evidence_id:
                self._evidence_context.evidence_registry[result.evidence_id] = evidence
            if not any(item.get("url") == result.source_url for item in self._evidence_context.raw_search_results):
                self._evidence_context.raw_search_results.append(evidence)
        return results

    @staticmethod
    def _classify_evidence_search_actions(
        actions: List[Dict], results: List[DataRepairResult],
    ) -> tuple[List[Dict], List[Dict]]:
        """Attribute each search action to its own evidence-repair result.

        A batch can contain several gaps.  Treating one successful result as
        proof that every search action succeeded made the L1-L5 audit history
        claim repairs that never happened.  ``DataRepairResult.gap`` is the
        stable correlation key even when the batch completes out of order.
        """
        result_by_gap = {
            (str(result.gap.chapter_id), str(result.gap.metric)): result
            for result in results or []
            if result is not None and getattr(result, "gap", None) is not None
        }
        successful: List[Dict] = []
        failed: List[Dict] = []
        for action in actions or []:
            key = (str(action.get("chapter_id", "")), str(action.get("metric", "")))
            result = result_by_gap.get(key)
            (successful if result is not None and result.found else failed).append(action)
        return successful, failed

    def _gateway_scope_searches(self, scope: str) -> Optional[int]:
        """Return actual gateway reservations for a scope when available."""
        if self._search_gateway is None:
            return None
        get_stats = getattr(self._search_gateway, "get_stats", None)
        if not callable(get_stats):
            return None
        stats = get_stats() or {}
        return int((stats.get("scope_used_searches") or {}).get(scope, 0))

    def _reuse_existing_evidence(self, gap: DataGap) -> Optional[DataRepairResult]:
        """Reuse an existing report data point and its raw evidence before searching."""
        chapter = next(
            (item for item in self._chapters if item.chapter_id == gap.chapter_id), None,
        )
        data_points = list(getattr(chapter, "data_points_used", []) or []) if chapter else []
        data_point = next(
            (
                item for item in data_points
                if (item.get("metric") if isinstance(item, dict) else item.metric) == gap.metric
            ),
            None,
        )
        if data_point is None:
            return None

        def value(name: str, default: Any = "") -> Any:
            return data_point.get(name, default) if isinstance(data_point, dict) else getattr(data_point, name, default)

        existing_url = str(value("source_url") or "").strip()
        existing_evidence_id = str(value("evidence_id") or "").strip()
        metric_text = gap.metric.lower()
        candidates = self._evidence_context.raw_search_results
        evidence = next(
            (
                item for item in candidates
                if isinstance(item, dict)
                and (
                    (existing_evidence_id and item.get("evidence_id") == existing_evidence_id)
                    or (existing_url and item.get("url") == existing_url)
                    or metric_text in self._evidence_text(item).lower()
                )
            ),
            None,
        )
        if not evidence or not evidence.get("url"):
            return None
        return DataRepairResult(
            gap=gap,
            found=True,
            value=value("value"),
            unit=value("unit"),
            source=value("source") or evidence.get("source") or evidence.get("title"),
            source_title=evidence.get("title") or value("source"),
            confidence=float(value("confidence", 1.0) or 1.0),
            source_url=evidence.get("url", ""),
            evidence_id=evidence.get("evidence_id", ""),
            provenance_id=evidence.get("provenance_id", ""),
            evidence_excerpt=evidence.get("evidence_excerpt") or evidence.get("excerpt") or evidence.get("snippet", ""),
            locator=evidence.get("locator") or evidence.get("url", ""),
            task_id=evidence.get("task_id", ""),
            request_id=evidence.get("request_id", ""),
            retrieved_at=evidence.get("retrieved_at"),
            geographic_scope=value("geographic_scope"),
            period=value("period"),
            population=value("population"),
            epistemic_level=value("epistemic_level") or "factual",
        )

    @staticmethod
    def _evidence_text(item: Dict[str, Any]) -> str:
        return " ".join(
            str(item.get(key) or "")
            for key in ("metric", "title", "snippet", "excerpt", "evidence_excerpt", "body", "content")
        )

    @staticmethod
    def _extract_chapter_data(
        aggregated_result: Any, section_id: str, content_dependencies: List[str],
        sub_section_id: str = "", skill_registry=None,
    ) -> Tuple[Dict[str, Any], str]:
        layered_content = getattr(aggregated_result, 'layered_content', {})
        content_provenance = getattr(aggregated_result, 'content_provenance', {})

        raw_value = None
        matched_key = section_id
        for key, provenance in content_provenance.items():
            if hasattr(provenance, 'section_target'):
                target = provenance.section_target
            elif isinstance(provenance, dict):
                target = provenance.get("section_target", "")
            else:
                continue
            if _canonical_section_id(target) == _canonical_section_id(section_id):
                for stage_content in layered_content.values():
                    if key in stage_content:
                        raw_value = stage_content[key]
                        matched_key = key
                        break
                if raw_value is not None:
                    break

        if raw_value is None:
            for stage_name, stage_data in layered_content.items():
                if not isinstance(stage_data, dict):
                    continue
                for key, value in stage_data.items():
                    if section_id in key or any(dep in key for dep in content_dependencies):
                        raw_value = value
                        matched_key = key
                        break
                if raw_value is not None:
                    break

        if raw_value is None:
            enriched = ReportOrchestrator._try_enrich_from_skill_cache(
                section_id, skill_registry,
            )
            if enriched is not None:
                return enriched
            return {}, ""

        refined, raw_summary = ReportOrchestrator._split_chapter_data(raw_value, matched_key, layered_content)
        if sub_section_id and isinstance(refined.get("upstream_data_points"), list):
            points = refined["upstream_data_points"]
            scoped_points = [
                point for point in points
                if isinstance(point, dict)
                and str(point.get("sub_section_id", "") or "") == sub_section_id
            ]
            # Older analysis outputs do not carry subsection identity. Keep
            # those points as shared parent evidence instead of silently
            # dropping all usable data during migration.
            if scoped_points:
                refined["upstream_data_points"] = scoped_points
                raw_summary = ReportOrchestrator._extract_raw_summary(
                    {"data_points": scoped_points},
                )
        return refined, raw_summary

    @staticmethod
    def _try_enrich_from_skill_cache(
        section_id: str, skill_registry,
    ) -> Optional[Tuple[Dict[str, Any], str]]:
        if not skill_registry:
            return None
        try:
            stock_skill = skill_registry.get("stock_data") if hasattr(skill_registry, 'get') else None
            if stock_skill is None:
                return None
            cache = getattr(stock_skill, '_memory_cache', None)
            if not cache or not isinstance(cache, dict):
                return None
            all_data_points = []
            for (_symbol, _action), cached_result in cache.items():
                if not isinstance(cached_result, dict) or not cached_result.get("success"):
                    continue
                data = cached_result.get("data", [])
                if isinstance(data, list):
                    all_data_points.extend(data)
            if not all_data_points:
                return None
            refined = {"upstream_data_points": all_data_points}
            raw_summary = ReportOrchestrator._extract_raw_summary({"data_points": all_data_points})
            return refined, raw_summary
        except Exception:
            return None

    @staticmethod
    def _split_chapter_data(
        raw_data: Any, matched_key: str, layered_content: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], str]:
        if not isinstance(raw_data, dict):
            content = raw_data if isinstance(raw_data, str) else str(raw_data)
            raw_summary = ""
            meta_key = f"{matched_key}__meta"
            for stage_data in layered_content.values():
                if not isinstance(stage_data, dict):
                    continue
                meta = stage_data.get(meta_key)
                if meta and isinstance(meta, dict):
                    raw_summary = ReportOrchestrator._extract_raw_summary(meta)
                    break
            return {"content": content}, raw_summary

        refined = {}
        for k, v in raw_data.items():
            if k == "data_points" and isinstance(v, list):
                refined["upstream_data_points"] = v
            elif isinstance(v, str) and len(v) > 8000:
                refined[k] = v[:8000]
            else:
                refined[k] = v

        meta_key = f"{matched_key}__meta"
        raw_summary = ""
        for stage_data in layered_content.values():
            if not isinstance(stage_data, dict):
                continue
            meta = stage_data.get(meta_key)
            if meta and isinstance(meta, dict):
                raw_summary = ReportOrchestrator._extract_raw_summary(meta)
                break

        if not raw_summary and "data_points" in raw_data:
            raw_summary = ReportOrchestrator._extract_raw_summary({"data_points": raw_data["data_points"]})

        return refined, raw_summary

    @staticmethod
    def _extract_raw_summary(meta: Dict[str, Any]) -> str:
        data_points = meta.get("data_points", [])
        if not data_points or not isinstance(data_points, list):
            return ""

        MAX_RAW_ITEMS = 40
        lines = []
        for i, dp in enumerate(data_points):
            if i >= MAX_RAW_ITEMS:
                lines.append(f"... (共{len(data_points)}条，已截取前{MAX_RAW_ITEMS}条)")
                break
            if isinstance(dp, dict):
                metric = dp.get("metric", dp.get("title", ""))
                value = dp.get("value", "")
                unit = dp.get("unit", "")
                source = dp.get("source", "")
                if metric and value:
                    line = f"- {metric}: {value}"
                    if unit:
                        line += f" ({unit})"
                    if source:
                        line += f" [来源: {source}]"
                    lines.append(line)
                elif dp.get("title"):
                    title = str(dp["title"])
                    body = dp.get("content", dp.get("body", ""))
                    if not isinstance(body, str):
                        body = str(body) if body else ""
                    if len(body) > 150:
                        body = body[:150] + "..."
                    lines.append(f"- {title}: {body}" if body else f"- {title}")
        return "\n".join(lines)

    @staticmethod
    def _extract_and_validate_data_points(chapter: ChapterWriteOutput) -> List[DataPoint]:
        """Return only data points explicitly declared by the chapter writer.

        Numeric mentions in prose are intentionally *not* promoted to
        ``DataPoint`` objects.  A prose number has no reliable metric, scope,
        period, or evidence binding; promoting it here creates an apparently
        structured but untraceable fact.  The evidence/quality pipeline is
        responsible for reporting unbound numeric mentions separately.
        """
        return list(chapter.data_points_used)

    @staticmethod
    def _diagnose_issue_source(issue: ChapterIssue, raw_data_summary: str) -> QualityIssueDiagnosis:
        desc = issue.description
        metric = ReportOrchestrator._extract_metric(desc) if desc else ""
        if issue.category in ("logic", "reasoning", "structure", "coherence"):
            return QualityIssueDiagnosis(
                issue_description=desc,
                source_layer="L3_report",
                remediation="修正逻辑问题",
            )
        if "编造" in desc or "无据" in desc or "未在" in desc:
            return QualityIssueDiagnosis(
                issue_description=desc,
                source_layer="L2_fabricated",
                remediation="删除编造断言或替换为真实数据",
            )
        if "模糊" in desc or "来源" in desc:
            extracted = ReportOrchestrator._extract_omitted_data(metric, raw_data_summary)
            if extracted:
                return QualityIssueDiagnosis(
                    issue_description=desc,
                    source_layer="L2_vague_source",
                    remediation=f"替换为具体来源数据: {extracted}",
                )
            return QualityIssueDiagnosis(
                issue_description=desc,
                source_layer="L2_vague_source",
                remediation="补充具体来源",
            )
        if "缺乏" in desc or "缺失" in desc or "未标注" in desc or "缺口" in desc \
           or "未提供" in desc or "不足" in desc or "欠缺" in desc or "缺少" in desc:
            keywords = re.sub(r'^(缺乏|缺失|未标注|缺口|无数据|缺少)', '', desc)
            keywords = re.sub(r'(数据|指标|金额|信息|金额)$', '', keywords).strip()
            extracted = ReportOrchestrator._extract_omitted_data(metric, raw_data_summary)
            if not extracted and keywords:
                extracted = ReportOrchestrator._extract_omitted_data(keywords, raw_data_summary)
            if extracted:
                return QualityIssueDiagnosis(
                    issue_description=desc,
                    source_layer="L2_omitted",
                    remediation=f"补充已有数据: {extracted}",
                )
            return QualityIssueDiagnosis(
                issue_description=desc,
                source_layer="L1_missing",
                remediation="需搜索补充数据",
            )
        return QualityIssueDiagnosis(
            issue_description=desc,
            source_layer="L3_report",
            remediation="修正报告层问题",
        )

    @staticmethod
    def _extract_omitted_data(metric: str, raw_data_summary: str) -> Optional[str]:
        if not metric or not raw_data_summary:
            return None
        metric_core = re.sub(r'(金额|数据|指标|投入|费用)$', '', metric)
        for line in raw_data_summary.split("\n"):
            line = line.strip()
            if not line:
                continue
            if metric_core and metric_core in line:
                return line.lstrip("- ")
        for line in raw_data_summary.split("\n"):
            line = line.strip()
            if not line:
                continue
            if metric and len(metric) >= 2 and metric[:2] in line:
                return line.lstrip("- ")
        return None

    async def _try_fill_data_gap(
        self, gap_metric: str, entity_name: str, stock_code: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        attempts = await self._structured_data_repair.repair_gap(
            gap_metric, entity_name, stock_code,
        )
        for attempt in attempts:
            if attempt.found and attempt.data:
                return {"source": attempt.source, "data": attempt.data}
        return None

    @staticmethod
    def _lookup_precise_value_in_chapter_data(
        metric_core: str, chapter_data: Dict[str, Any],
    ) -> Optional[str]:
        if not chapter_data or not metric_core:
            return None
        upstream = chapter_data.get("upstream_data_points")
        if isinstance(upstream, list):
            for dp in upstream:
                if not isinstance(dp, dict):
                    continue
                dp_metric = dp.get("metric", "")
                if metric_core in dp_metric or dp_metric in metric_core:
                    parts = [f"{dp.get('value', '')}{dp.get('unit', '')}"]
                    src = dp.get("source", "")
                    if src:
                        parts.append(f"(来源: {src})")
                    return " ".join(parts)
        for k, v in chapter_data.items():
            if k in ("content", "upstream_data_points", "raw_data_summary"):
                continue
            if metric_core in str(k) and isinstance(v, str):
                return v
        return None

    @staticmethod
    def _build_anchor_patch_instructions(
        anchoring_issues: List, chapter_data: Dict[str, Any],
        raw_data_summary: str = "",
    ) -> List[str]:
        instructions = []
        for iss in anchoring_issues:
            desc = iss.description
            suggestion = iss.suggestion if hasattr(iss, 'suggestion') and iss.suggestion else ""
            metric = ReportOrchestrator._extract_metric(desc) if desc else ""
            keywords = re.sub(r'^(缺乏|缺失|未标注|缺口|无数据|缺少)', '', desc) if desc else ""
            keywords = re.sub(r'(数据|指标|金额|信息|金额)$', '', keywords).strip() if keywords else ""
            omitted_data = ReportOrchestrator._extract_omitted_data(metric, raw_data_summary) if raw_data_summary else None
            if not omitted_data and keywords:
                omitted_data = ReportOrchestrator._extract_omitted_data(keywords, raw_data_summary)
            lookup_key = keywords if keywords else metric
            precise_from_chapter = ReportOrchestrator._lookup_precise_value_in_chapter_data(
                lookup_key, chapter_data,
            )
            if not precise_from_chapter and metric and metric != keywords:
                precise_from_chapter = ReportOrchestrator._lookup_precise_value_in_chapter_data(
                    metric, chapter_data,
                )
            if not omitted_data and precise_from_chapter:
                omitted_data = precise_from_chapter
            if "编造" in desc or "无据" in desc or "未在" in desc:
                instructions.append(
                    f"删除无据断言：{desc[:100]}。"
                    f"{'修正建议：' + suggestion[:100] if suggestion else '如无数据支撑，改为标注数据缺口。'}"
                )
            elif "模糊" in desc or "来源" in desc:
                if omitted_data:
                    instructions.append(
                        f"补充已有数据替换模糊来源：{desc[:100]}。可用数据：{omitted_data}。"
                        f"{'修正建议：' + suggestion[:100] if suggestion else '将模糊来源替换为可用数据中的具体来源。'}"
                    )
                else:
                    instructions.append(
                        f"补充具体来源：{desc[:100]}。"
                        f"{'修正建议：' + suggestion[:100] if suggestion else '将模糊来源替换为可用数据中的具体来源。'}"
                    )
            elif ("缺乏" in desc or "缺失" in desc or "未标注" in desc or "缺口" in desc):
                if omitted_data:
                    instructions.append(
                        f"补充已有数据：{desc[:100]}。原始数据中存在：{omitted_data}。请将此数据补充到报告中。"
                    )
                else:
                    instructions.append(
                        f"标注数据缺口：{desc[:100]}。"
                        f"{'修正建议：' + suggestion[:100] if suggestion else '在断言后添加数据缺口标注。'}"
                    )
            else:
                instructions.append(
                    f"修正数据锚定问题：{desc[:100]}。"
                    f"{'修正建议：' + suggestion[:100] if suggestion else ''}"
                )
        return instructions

    @staticmethod
    def _rebuild_preceding_summary(chapters: List[ChapterWriteOutput]) -> str:
        return "\n".join(
            f"【{ch.title}】{'; '.join(str(c) for c in ch.key_conclusions)}" for ch in chapters
        )

    def _append_preceding_summary(self, existing: str, chapter: ChapterWriteOutput) -> str:
        new_entry = f"\n【{chapter.title}】{'; '.join(str(c) for c in chapter.key_conclusions)}"
        result = existing + new_entry
        if len(result) > self._MAX_PRECEDING_SUMMARY_LENGTH:
            lines = result.split("\n")
            while len(result) > self._MAX_PRECEDING_SUMMARY_LENGTH and len(lines) > 2:
                lines = lines[1:]
                result = "\n".join(lines)
        return result

    @staticmethod
    def _verify_downstream_consistency(
        chapters: List[ChapterWriteOutput], patched_chapter_ids: Set[str],
    ) -> Dict[str, Any]:
        """Detect stale downstream chapters and return a blocking result.

        This method deliberately does not rewrite content.  Callers must use
        the returned dependency information to schedule precise replacement
        or chapter regeneration before export.
        """
        stale_chapter_ids: Set[str] = set()
        stale_references: List[Dict[str, str]] = []
        for chapter in chapters:
            if chapter.chapter_id in patched_chapter_ids:
                continue
            for patched_id in patched_chapter_ids:
                patched_ch = next(
                    (c for c in chapters if c.chapter_id == patched_id), None
                )
                if not patched_ch:
                    continue
                for dp in patched_ch.data_points_used:
                    if dp.metric and dp.metric in chapter.content:
                        pattern = re.compile(
                            re.escape(str(dp.value)) + r'\s*' + re.escape(str(dp.unit))
                        )
                        if not pattern.search(chapter.content):
                            logger.warning(
                                f"Chapter {chapter.chapter_id} references '{dp.metric}' "
                                f"with outdated value after patch of chapter {patched_id}"
                            )
                            stale_chapter_ids.add(chapter.chapter_id)
                            stale_references.append({
                                "chapter_id": chapter.chapter_id,
                                "patched_chapter_id": patched_id,
                                "metric": dp.metric,
                                "expected_value": str(dp.value),
                                "unit": str(dp.unit),
                            })
        return {
            "blocking": bool(stale_chapter_ids),
            "stale_chapter_ids": sorted(stale_chapter_ids),
            "stale_references": stale_references,
        }

    @staticmethod
    def _propagate_canonical_updates(
        chapters: List[ChapterWriteOutput], patched_chapter_ids: Set[str],
    ) -> Dict[str, Any]:
        """Safely replace downstream metric values when an exact anchor exists."""
        patched = [c for c in chapters if c.chapter_id in patched_chapter_ids]
        unresolved: Set[str] = set()
        applied: List[Dict[str, str]] = []
        for chapter in chapters:
            if chapter.chapter_id in patched_chapter_ids:
                continue
            for source_chapter in patched:
                for dp in source_chapter.data_points_used:
                    if not dp.metric or dp.metric not in chapter.content:
                        continue
                    pattern = re.compile(
                        re.escape(dp.metric)
                        + r"(?P<between>.{0,60}?)(?P<old>-?\d[\d,.]*)\s*"
                        + re.escape(str(dp.unit or "")),
                        re.DOTALL,
                    )
                    match = pattern.search(chapter.content)
                    if not match:
                        if str(dp.value) + str(dp.unit) not in chapter.content:
                            unresolved.add(chapter.chapter_id)
                        continue
                    old = match.group("old")
                    new_value = str(dp.value)
                    chapter.content = (
                        chapter.content[:match.start("old")]
                        + new_value
                        + chapter.content[match.end("old"):]
                    )
                    applied.append({
                        "chapter_id": chapter.chapter_id,
                        "metric": dp.metric,
                        "old_value": old,
                        "new_value": new_value,
                        "unit": str(dp.unit),
                    })
        return {
            "applied": applied,
            "unresolved_chapter_ids": sorted(unresolved),
            "blocking": bool(unresolved),
        }

    def _find_section_spec(self, section_id: str, framework_config: Dict) -> Dict:
        for sec in self._report_chapter_specs(self._task_structure):
            if sec.get("section_id") == section_id:
                return sec
        return {"section_id": section_id, "section_name": section_id, "section_role": "analysis"}

    @staticmethod
    def _extract_metric(description: str) -> str:
        match = re.search(r'["「](.+?)["」]', description)
        return match.group(1) if match else description[:20]

    _METRIC_EN_MAP = {
        "营收": "revenue", "收入": "revenue", "营业收入": "operating revenue",
        "利润": "profit", "净利润": "net profit", "毛利": "gross profit",
        "研发": "R&D", "研发费用": "R&D expense", "研发投入": "R&D investment",
        "净利率": "net profit margin", "毛利率": "gross margin",
        "市盈率": "PE ratio", "市净率": "PB ratio",
        "资产负债率": "debt ratio", "现金流": "cash flow",
        "增长率": "growth rate", "增速": "growth rate",
        "市值": "market cap", "股价": "stock price",
        "产量": "production", "销量": "sales volume", "交付量": "deliveries",
        "单车利润": "profit per unit", "渗透率": "penetration rate",
        "份额": "market share", "市占率": "market share",
    }

    @staticmethod
    def _build_search_keywords(description: str, topic: str) -> List[str]:
        keywords = []
        core_metric = re.sub(r'^(缺乏|缺失|未标注|缺口|无数据|缺少)', '', description) if description else ""
        core_metric = re.sub(r'(数据|指标|金额|信息|百分比)$', '', core_metric).strip()

        if topic:
            keywords.append(topic)
        if core_metric:
            keywords.append(core_metric)

        for zh, en in ReportOrchestrator._METRIC_EN_MAP.items():
            if zh in core_metric or zh in description:
                en_kw = f"{topic} {en}" if topic else en
                if en_kw not in keywords:
                    keywords.append(en_kw)
                break

        if core_metric and len(core_metric) >= 2:
            short = core_metric[:2]
            if short not in keywords and short not in (topic or ""):
                keywords.append(short)

        return keywords[:5]

    async def _call_llm_tracked(self, prompt: str, max_tokens: int = 8192, temperature: float = 0.7, phase: str = "") -> Dict[str, Any]:
        self._llm_call_count += 1
        result = await call_llm(prompt=prompt, max_tokens=max_tokens, temperature=temperature)
        trace_entry = {
            "call_id": self._llm_call_count,
            "phase": phase,
            "max_tokens": max_tokens,
            "success": result.get("success", False),
        }
        if result.get("success"):
            usage = result.get("usage", {})
            self._total_tokens_used += usage.get("total_tokens", 0)
            trace_entry["total_tokens"] = usage.get("total_tokens", 0)
        self._llm_trace.append(trace_entry)
        return result

    @staticmethod
    def _is_non_retryable_error(error: Exception) -> bool:
        error_str = str(error).lower()
        for pattern in RetryPolicy.NON_RETRYABLE_ERRORS:
            if pattern.lower() in error_str:
                return True
        if "402" in error_str or "insufficient" in error_str:
            return True
        return False

    async def _generate_exec_summary(
        self, chapters: List[ChapterWriteOutput],
        task_structure: Dict, topic: str,
    ) -> str:
        all_conclusions = []
        for ch in chapters:
            all_conclusions.extend(str(c) for c in ch.key_conclusions)

        conflict_descriptions = []
        for c in self._data_registry.get_conflicts():
            values_str = ", ".join(
                f'{e["value"]}{e["unit"]}（来源:{e["source"]}）' for e in c.entries
            )
            conflict_descriptions.append(f"{c.metric}: {values_str}")

        prompt = self._prompts.get(
            "exec_summary",
            topic=topic,
            all_conclusions=chr(10).join(f'- {c}' for c in all_conclusions),
            conflict_descriptions=(
                chr(10).join(f'- {d}' for d in conflict_descriptions)
                if conflict_descriptions else '无'
            ),
        )

        # 引擎化（带健全性解析钩子）：exec summary 曾是最后一个未设防的
        # LLM 面——推理型模型把"写作计划思考"直接当摘要输出并流入
        # key_findings（ses_1e1abd67 实证）。元思考输出不再采纳，改为
        # 确定性兜底：用章节核心结论组装（永不输出垃圾）。
        # I1 迁移：元思考检测与长度/残留检查统一走 content_contract。
        def _summary_parse(raw: str):
            from src.core.llm_retry import ParseOutcome
            text = (raw or "").strip()
            if not text:
                return ParseOutcome(False, "degenerate")
            if "摘要生成失败" in text:
                return ParseOutcome(False, "degenerate")
            # check_content 的 C1 限定 chapter kind；summary 面单独保留开头
            # 元思考硬检测（与旧行为一致，检测器已迁移至统一模块）。
            if content_opens_meta(text):
                return ParseOutcome(False, "degenerate")
            verdict = check_content(text, kind="summary", min_length=80,
                                    language=current_report_language())
            if not verdict.passed:
                return ParseOutcome(False, "degenerate")
            return ParseOutcome(True, value=text)

        try:
            from src.core.llm_client import call_llm_ex
            from src.core.llm_retry import Budget, LLMBudgetExhausted
            content = await call_llm_ex(
                lambda variations: prompt,
                output_contract="prose",
                expected_output_chars=1200,
                budget=Budget(max_calls=3, max_seconds=240),
                parse=_summary_parse,
                task_tag="exec_summary",
            )
            return content
        except LLMBudgetExhausted as exhausted:
            logger.error(
                "Exec summary engine budget exhausted (%s); using deterministic "
                "conclusion-based summary", exhausted.classification.error_class.value,
            )
        except Exception as summary_error:
            logger.error("Exec summary engine call failed: %s", summary_error)
        return self._deterministic_exec_summary(chapters, topic)

    @staticmethod
    def _deterministic_exec_summary(
        chapters: List[ChapterWriteOutput], topic: str,
    ) -> str:
        """LLM-free summary assembled from verified chapter conclusions."""
        lines = [f"《{topic}》核心结论摘录（自动汇编）：", ""]
        for ch in chapters:
            conclusions = [str(c).strip() for c in (ch.key_conclusions or [])
                           if str(c).strip()]
            if not conclusions:
                continue
            lines.append(f"## {ch.title}")
            for c in conclusions[:4]:
                lines.append(f"- {c}")
        if len(lines) <= 2:
            lines.append("各章节暂无可核验结论。")
        return "\n".join(lines)

    _HEADING_PATTERN = re.compile(
        r'^(.{0,20}(核心发现|关键发现|核心结论|执行摘要|主要发现|总结|概述|结论|要点|摘要'
        r'|概览|Key\s*Findings|Summary|Conclusion|Overview))\s*[:：]?\s*$',
        re.IGNORECASE,
    )
    _SUBHEADING_PATTERN = re.compile(
        r'^[一二三四五六七八九十]+[、.．]\s*.{2,30}$',
    )
    _TITLE_LIKE_PATTERN = re.compile(
        r'^.{4,25}[：:]\s*.{2,25}$',
    )

    @staticmethod
    def _clean_key_findings(raw_summary: str) -> List[str]:
        lines = raw_summary.split("\n")
        cleaned = []
        _NUM_LIST_PATTERN = re.compile(r'^\d+[.、]\s+')  # "1. xxx" or "1、xxx" numbered items
        for line in lines[:20]:
            line = line.strip()
            if not line:
                continue
            if re.match(r'^-{3,}$', line):
                continue
            # Markdown table fragments leak into the findings list when the
            # exec-summary model emits a table (observed: '| 数据 | 来源章节 |').
            if line.startswith('|') or line.endswith('|') or line.startswith('+--'):
                continue
            line = re.sub(r'^#+\s*', '', line)
            # F4（格式标准 2026-10-18）：剥离单个行首列表标记（ses_92c64980
            # 中发现以 "- " 前缀流入 findings 渲染为 "2. - 全球AI…"）。
            line = re.sub(r'^[-•·*]\s*', '', line)
            line = re.sub(r'\*{1,2}', '', line)
            if ReportOrchestrator._HEADING_PATTERN.match(line.strip()):
                continue
            if ReportOrchestrator._SUBHEADING_PATTERN.match(line.strip()):
                continue
            if ReportOrchestrator._TITLE_LIKE_PATTERN.match(line.strip()) and len(line.strip()) < 30:
                continue
            if len(line) < 8:
                continue
            # I1 一行式检查：元思考行/合同残留行不得进入 key_findings
            # （ses_1e1abd67：exec summary 思考文本曾流入发现列表）。
            if not check_finding_line(line):
                continue
            # 只过滤3+连续编号行（列表而非独立发现）
            cleaned.append(line)
        # 后处理：删除连续3+编号行（表示是列表子项而非独立发现）
        _NUM_SEQ = re.compile(r'^\d+[.、]\s+')
        num_indices = [i for i, line in enumerate(cleaned) if _NUM_SEQ.match(line)]
        if len(num_indices) >= 3:
            remove_set = set()
            start = 0
            while start < len(num_indices):
                end = start + 1
                while end < len(num_indices) and num_indices[end] == num_indices[end-1] + 1:
                    end += 1
                if end - start >= 3:
                    for j in range(start, end):
                        remove_set.add(num_indices[j])
                start = end
            cleaned = [line for i, line in enumerate(cleaned) if i not in remove_set]
        return cleaned

    @staticmethod
    def _flatten_section_data_points(
        sections: Optional[List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        """F1（格式标准 2026-10-18）：顶层 data_points = 报告定量主干。

        ses_92c64980：终稿 dict 原本没有顶层 data_points 字段，持久层因此
        保留了研究阶段 checkpoint 的搜索证据空壳（title/content/url，
        metric/value 双空）。此处按章节顺序扁平聚合各章 grounded 数据点，
        按 (metric, value, 源身份) 去重；证据形状条目一律不入主干。
        """
        flattened: List[Dict[str, Any]] = []
        seen = set()
        for section in sections or []:
            if not isinstance(section, dict):
                continue
            for dp in section.get("data_points") or []:
                if not isinstance(dp, dict):
                    continue
                metric = str(dp.get("metric") or "").strip()
                value = dp.get("value")
                if not metric or value in (None, "", [], {}):
                    continue
                identity = (
                    metric,
                    str(value),
                    str(dp.get("source_url") or dp.get("source") or dp.get("url") or ""),
                )
                if identity in seen:
                    continue
                seen.add(identity)
                flattened.append(dp)
        return flattened

    _DECLARATION_PATTERN = re.compile(
        r"统计口径|口径不同|不将两者直接合并比较|不直接合并比较"
    )

    @staticmethod
    def _dedupe_methodology_declarations(sections):
        """D1（格式标准 2026-10-18）：口径声明全文档去重。

        ses_92c64980 实证：同一口径声明在 7 章中重复出现 4 次，读感像
        免责 boilerplate。保留文档首次出现（原位），后续重复句删除，唯一
        声明收集为 methodology_notes（渲染层前置"口径、假设与方法"呈现）。
        表格行永不改写；小数点保护同 G10。
        """
        seen = set()
        notes = []
        for section in sections or []:
            if not isinstance(section, dict):
                continue
            content = section.get("content") or ""
            if not content:
                continue
            lines = content.split("\n")
            rebuilt_lines = []
            changed = False
            for line in lines:
                if line.lstrip().startswith("|"):
                    rebuilt_lines.append(line)
                    continue
                if not ReportOrchestrator._DECLARATION_PATTERN.search(line):
                    rebuilt_lines.append(line)
                    continue
                protected = re.sub(r"(?<=\d)\.(?=\d)", "\x00", line)
                parts = re.split(r"([。！？.!?])", protected)
                sentences = []
                buf = ""
                for part in parts:
                    buf += part
                    if part in ("。", "！", "？", ".", "!", "?"):
                        sentences.append(buf)
                        buf = ""
                if buf.strip():
                    sentences.append(buf)
                kept = []
                for sentence in sentences:
                    if not ReportOrchestrator._DECLARATION_PATTERN.search(sentence):
                        kept.append(sentence)
                        continue
                    norm = re.sub(r"[\s，,。！？.!?；;：:*]+", "", sentence)
                    if norm not in seen:
                        seen.add(norm)
                        notes.append(sentence.strip().replace("\x00", "."))
                        kept.append(sentence)
                    # else: 重复声明句删除
                new_line = "".join(kept).replace("\x00", ".")
                if new_line != line:
                    changed = True
                rebuilt_lines.append(new_line)
            if changed:
                cleaned = []
                for line in rebuilt_lines:
                    if line.strip() == "" and cleaned and cleaned[-1].strip() == "":
                        continue
                    cleaned.append(line)
                section["content"] = "\n".join(cleaned)
        return sections, notes

    @staticmethod
    def _normalize_emission_artifacts(sections):
        """清扫 writer emission 伪影（ses_ea193fac 实证三类）。

        1. 英文方括号认知标签 → 中文括号式标记；未闭合变体（如
           "[speculative；出"）按句界还原，修复吞句。
        2. 裸链接伪影（"...较大[inferential]（https://zhihu...）。"经
           剥离后残留 "zhihu.com/p/xxx）。"）整体移除——来源已在数据
           支撑表，正文行内链接属冗余。
        3. 未闭合 ** 粗体标记修复：顺序配对，落单的 closer/opener 剔除
           （保留成对粗体，如 Exhibit 题注）。
        """
        tag_map = {
            "factual": "事实性判断", "inferential": "推理性判断",
            "speculative": "推测性判断", "analytical": "分析性判断",
        }
        # 闭合标签：[inferential] → （推理性判断）
        re_closed = re.compile(
            r"\[(" + "|".join(tag_map) + r")\]"
        )
        # 未闭合标签后接句界（；;/，,）：吞句修复
        re_unclosed = re.compile(
            r"\[(" + "|".join(tag_map) + r")\s*[；;，,]\s*"
        )
        re_naked_url = re.compile(
            r"(?<![\w/\"（(（>])(?:https?://)?"
            r"(?:[a-z0-9-]+\.(?:com|cn|net|org|io)/[^\s）)】。，,；;]{0,120})"
            r"\s*[）)](?=[。，,；;\n]|$)"
        )
        for section in sections or []:
            if not isinstance(section, dict):
                continue
            content = section.get("content") or ""
            if not content:
                continue
            original = content
            content = re_closed.sub(
                lambda m: f"（{tag_map[m.group(1)]}）", content,
            )
            content = re_unclosed.sub(
                lambda m: f"（{tag_map[m.group(1)]}）。", content,
            )
            content = re_naked_url.sub("", content)
            # 未闭合 ** 最小风险修复：仅当计数为奇（必有毒落单标记）时，
            # 优先剔除"后跟空白"的 stray-closer 签名（"** "，实证损伤形态
            # "比较。** 从"）；无该签名则退化为剔除最后一个。
            if content.count("**") % 2 == 1:
                stray = None
                for m in re.finditer(r"\*\*\s", content):
                    stray = m
                    break
                if stray is not None:
                    content = content[:stray.start()] + content[stray.end():]
                else:
                    last = content.rfind("**")
                    content = content[:last] + content[last + 2:]
            if content != original:
                section["content"] = content
        return sections

    @staticmethod
    def _apply_exhibit_numbering(sections):
        """D2（格式标准 2026-10-18）：数据表 Exhibit 全局编号。

        按章节顺序扫描 markdown 表格块（连续以"|"开头、含表头+分隔行的
        行块），块前插入全局编号题注（**Exhibit N｜章节标题**）。已带题注
        的表格跳过（幂等，revise/regenerate 流程安全）。
        """
        counter = 0
        for section in sections or []:
            if not isinstance(section, dict):
                continue
            content = section.get("content") or ""
            if "|" not in content:
                continue
            title = str(section.get("title") or "").strip() or "数据表"
            lines = content.split("\n")
            out_lines = []
            i = 0
            changed = False
            while i < len(lines):
                line = lines[i]
                if line.lstrip().startswith("|"):
                    block_start = i
                    while i < len(lines) and lines[i].lstrip().startswith("|"):
                        i += 1
                    block_len = i - block_start
                    prev_nonblank = ""
                    for pl in reversed(out_lines):
                        if pl.strip():
                            prev_nonblank = pl
                            break
                    if block_len >= 2 and "**Exhibit" not in prev_nonblank:
                        counter += 1
                        out_lines.append(f"**Exhibit {counter}｜{title}**")
                        out_lines.append("")
                        changed = True
                    out_lines.extend(lines[block_start:i])
                    continue
                out_lines.append(line)
                i += 1
            if changed:
                section["content"] = "\n".join(out_lines)
        return sections

    @staticmethod
    def _ground_data_point_sources(
        data_points: List[Dict[str, Any]],
        available_sources: List[Dict[str, Any]],
        chapter_id: str = "",
    ) -> List[Dict[str, Any]]:
        if not available_sources:
            grounded = []
            for item in data_points:
                dp = dict(item)
                dp["chapter_id"] = dp.get("chapter_id") or chapter_id
                if not dp.get("source") or _is_vague_source(str(dp.get("source", ""))):
                    dp["source"] = ""
                dp["source_url"] = ""
                dp["evidence_status"] = "unverified"
                grounded.append(dp)
            return grounded
        source_names = [s.get("title", s.get("url", s.get("href", ""))) for s in available_sources if s.get("title") or s.get("url") or s.get("href")]
        grounded = []
        _SOURCE_INDEX_PATTERN = re.compile(r'^来源(\d+)$')
        for dp in data_points:
            dp = dict(dp)
            dp["chapter_id"] = dp.get("chapter_id") or chapter_id
            raw_dp_src = dp.get("source", "")
            if isinstance(raw_dp_src, (list, tuple, set)):
                dp_src = "；".join(
                    str(item).strip() for item in raw_dp_src if str(item).strip()
                )
                dp["source"] = dp_src
            else:
                dp_src = str(raw_dp_src or "").strip()
                dp["source"] = dp_src
            source_url = str(dp.get("source_url", "") or "").strip()
            source_id = str(dp.get("source_id", "") or "").strip()
            evidence_id = str(dp.get("evidence_id", "") or "").strip()
            provenance_id = str(dp.get("provenance_id", "") or "").strip()
            evidence_identity_mismatch = False
            matched_source = next(
                (item for item in available_sources
                 if source_url and str(item.get("url", "") or item.get("href", "")).strip() == source_url),
                None,
            )
            if matched_source is None:
                matched_source = next(
                    (item for item in available_sources
                 if source_id and str(item.get("source_id", "")).strip() == source_id),
                    None,
                )
            if matched_source is None and evidence_id:
                matched_source = next(
                    (item for item in available_sources
                     if str(item.get("evidence_id", "")).strip() == evidence_id),
                    None,
                )
            if matched_source is not None:
                catalog_evidence_id = str(matched_source.get("evidence_id", "") or "").strip()
                catalog_provenance_id = str(matched_source.get("provenance_id", "") or "").strip()
                evidence_identity_mismatch = bool(
                    (evidence_id and catalog_evidence_id and evidence_id != catalog_evidence_id)
                    or (provenance_id and catalog_provenance_id and provenance_id != catalog_provenance_id)
                )
                dp["source"] = str(
                    matched_source.get("title") or matched_source.get("url")
                    or matched_source.get("href") or ""
                )
                dp["source_url"] = str(
                    matched_source.get("url") or matched_source.get("href") or ""
                ).strip()
                dp["evidence_id"] = "" if evidence_identity_mismatch else evidence_id or catalog_evidence_id
                dp["provenance_id"] = "" if evidence_identity_mismatch else provenance_id or catalog_provenance_id
                dp["evidence_excerpt"] = str(
                    matched_source.get("evidence_excerpt")
                    or matched_source.get("excerpt")
                    or matched_source.get("content")
                    or matched_source.get("text")
                    or ""
                ).strip()
            # D3: check "来源N" pattern first (fuzzy index, not a real source)
            idx_match = (
                _SOURCE_INDEX_PATTERN.match(dp_src.strip())
                if dp_src and matched_source is None else None
            )
            if idx_match:
                dp = dict(dp)
                idx = int(idx_match.group(1)) - 1
                if 0 <= idx < len(source_names):
                    dp["source"] = source_names[idx]
                else:
                    # An out-of-range alias is not a source.  Do not keep it
                    # as if it were a resolved citation.
                    dp["source"] = ""
            else:
                # Never attach an unrelated source as a fallback.  An
                # unresolved source is a blocking evidence condition.
                if not dp_src or _is_vague_source(dp_src):
                    dp["source"] = ""
            # Resolve a source title only when the catalog has one unique
            # candidate.  This also transfers the catalog's evidence and
            # provenance identities to the data point; a URL alone is not a
            # complete audit trail.
            if matched_source is None and dp.get("source"):
                source_norm = str(dp["source"]).strip().lower()
                candidates = []
                for item in available_sources:
                    title_norm = str(item.get("title", "") or "").strip().lower()
                    url = str(item.get("url", "") or item.get("href", "") or "").strip()
                    if not url or not title_norm:
                        continue
                    if source_norm == title_norm:
                        candidates.append(item)
                if len(candidates) == 1:
                    matched_source = candidates[0]
                    catalog_evidence_id = str(matched_source.get("evidence_id", "") or "").strip()
                    catalog_provenance_id = str(matched_source.get("provenance_id", "") or "").strip()
                    evidence_identity_mismatch = bool(
                        (evidence_id and catalog_evidence_id and evidence_id != catalog_evidence_id)
                        or (provenance_id and catalog_provenance_id and provenance_id != catalog_provenance_id)
                    )
                    dp["source"] = str(
                        matched_source.get("title")
                        or matched_source.get("url")
                        or matched_source.get("href")
                        or ""
                    )
                    dp["evidence_id"] = "" if evidence_identity_mismatch else str(
                        dp.get("evidence_id") or catalog_evidence_id or ""
                    ).strip()
                    dp["provenance_id"] = "" if evidence_identity_mismatch else str(
                        dp.get("provenance_id") or catalog_provenance_id or ""
                    ).strip()
            catalog_url = _source_url_for(dp.get("source", ""), available_sources)
            if catalog_url and not dp.get("evidence_excerpt"):
                catalog_item = next(
                    (item for item in available_sources
                     if str(item.get("url", "") or item.get("href", "")).strip() == catalog_url),
                    None,
                )
                if catalog_item:
                    dp["evidence_excerpt"] = str(
                        catalog_item.get("evidence_excerpt")
                        or catalog_item.get("excerpt")
                        or catalog_item.get("content")
                        or catalog_item.get("text")
                        or ""
                    ).strip()
            candidate_url = str(dp.get("source_url", "") or "").strip()
            allowed_urls = {
                str(item.get("url", "") or item.get("href", "")).strip()
                for item in available_sources
                if item.get("url") or item.get("href")
            }
            # A model-provided URL is accepted only when it is present in the
            # task's source catalog.  This prevents fabricated or cross-task
            # provenance from bypassing L3.
            # A URL is trusted only when it came from a source-id/evidence-id
            # match, a catalog title match, or is explicitly present in the
            # task-local allowlist.  Never let an arbitrary model URL win by
            # being evaluated before the allowlist.
            bound_url = str(dp.get("source_url", "") or "").strip()
            if bound_url not in allowed_urls:
                bound_url = ""
            dp["source_url"] = catalog_url or bound_url or (
                candidate_url if candidate_url in allowed_urls else ""
            )
            has_evidence = bool(
                str(dp.get("evidence_excerpt", "") or "").strip()
                or str(dp.get("locator", "") or "").strip()
            )
            dp["evidence_status"] = (
                "verified"
                if dp.get("source_url")
                and has_evidence
                and str(dp.get("evidence_id", "") or "").strip()
                and str(dp.get("provenance_id", "") or "").strip()
                and not evidence_identity_mismatch
                else "unverified"
            )
            if evidence_identity_mismatch:
                dp["evidence_binding_error"] = "provided_evidence_identity_mismatch"
            # P0-B（真根因治理，ses_baf7a884）：证据目录自带的时间/地域
            # 信息确定性回填到数据点元数据。只在目录确实携带时回填，
            # 绝不臆造默认值——这是 L2 元数据缺失的正向通路，而非降级。
            if matched_source is not None:
                for meta_key, source_keys in (
                    ("period", ("period", "published_at", "publish_time", "date")),
                    ("geographic_scope", ("geographic_scope", "region", "country")),
                    ("population", ("population",)),
                ):
                    if not str(dp.get(meta_key) or "").strip():
                        for sk in source_keys:
                            sv = str(matched_source.get(sk) or "").strip()
                            if sv:
                                dp[meta_key] = sv
                                break
            grounded.append(dp)
        return grounded

    @staticmethod
    def _assemble_final_report(
        chapters: List[ChapterWriteOutput],
        exec_summary: str,
        review: ReviewOutput,
        topic: str,
        original_sources: List[Dict[str, Any]] = None,
        quality_report: QualityReport = None,
        conflicts_summary: str = "",
        llm_trace: List[Dict[str, Any]] = None,
        task_id: str = "report",
    ) -> Dict[str, Any]:
        all_sources = ReportOrchestrator._ensure_source_evidence_identity(
            original_sources, task_id=task_id,
        )
        # I1 组装口终检（最后保护边界）：元思考独白、合同残留、占位符空壳、
        # 语言纯度等由统一内容契约判定，命中即以失败占位符替换。

        chapter_sources = [
            {"title": s.get("title", ""), "url": s.get("url", s.get("href", "")), "type": s.get("type", "web")}
            for s in all_sources
        ] if all_sources else []

        all_conclusions = []
        for chapter in chapters:
            all_conclusions.extend(
                str(conclusion).strip()
                for conclusion in (chapter.key_conclusions or [])
                if str(conclusion or "").strip()
            )

        sections = []
        for ch in chapters:
            chapter_status = str(getattr(ch, "status", "ready") or "ready")
            chapter_content = str(ch.content or "").strip()
            if not chapter_content:
                # Final assembly is the last protection boundary.  A failed
                # writer/recovery path must never serialize an empty chapter,
                # while the explicit failed status keeps coverage/audit from
                # mistaking this controlled notice for valid research.
                chapter_status = "failed"
                chapter_content = _CHAPTER_FAILED_PLACEHOLDER
            else:
                # min_length=37：既有占位符长度（空壳章节不得替代终检——
                # 真章节级 400 下限在 rescue 口把关，此处防的是污染与空壳）。
                verdict = check_content(chapter_content, kind="chapter", min_length=37,
                                        language=current_report_language())
                if not verdict.passed:
                    logger.warning(
                        "Assembly sanity gate replaced polluted content for %s: %s",
                        ch.chapter_id, verdict.fail_codes,
                    )
                    chapter_status = "failed"
                    chapter_content = _CHAPTER_FAILED_PLACEHOLDER
            raw_dp = [asdict(dp) for dp in ch.data_points_used]
            grounded_dp = ReportOrchestrator._ground_data_point_sources(
                raw_dp, all_sources, chapter_id=ch.chapter_id,
            )
            sections.append({
                "id": ch.chapter_id,
                # Keep both report-native ``id`` and the legacy result-store
                # field.  Replanning, preview adapters and older checkpoints
                # join chapters through ``section_id``.
                "section_id": ch.chapter_id,
                "title": ch.title,
                "content": chapter_content,
                "sub_section_id": ch.sub_section_id,
                "subsections": [],
                "charts": [],
                "data_points": grounded_dp,
                # Keep the full source catalog for compatibility, but data
                # points now carry their own URL and verification status.
                "sources": chapter_sources,
                "key_conclusions": ch.key_conclusions,
                "status": chapter_status,
                "error": getattr(ch, "error", ""),
            })

        # Phase R（格式标准 2026-10-18）：D1 口径声明去重（收集
        # methodology_notes 前置呈现）+ D2 数据表 Exhibit 全局编号。
        sections, methodology_notes = (
            ReportOrchestrator._dedupe_methodology_declarations(sections)
        )
        sections = ReportOrchestrator._apply_exhibit_numbering(sections)
        # 清扫 writer emission 伪影（英文标签/裸链接/落单粗体）
        sections = ReportOrchestrator._normalize_emission_artifacts(sections)

        result = {
            "topic": topic,
            "title": topic,
            "aspects": [ch.title for ch in chapters],
            "sections": sections,
            "sources": all_sources,
            # D1：全文档唯一口径/假设声明（渲染层在正文前呈现）。
            "methodology_notes": methodology_notes,
            # F1: 顶层 data_points = 全章节 grounded 数据点的扁平聚合
            # （报告定量主干）。研究阶段的证据空壳不再经存储合并驻留。
            "data_points": ReportOrchestrator._flatten_section_data_points(sections),
            # Keep synthesis in the manifest-declared top-level slots as well
            # as the legacy key_findings field.  The HTML/document layer and
            # manifest validator consume the dedicated slots; omitting them
            # made a generated executive summary look like missing coverage.
            "exec_summary": str(exec_summary or "").strip(),
            "conclusion": "\n".join(
                f"- {conclusion}"
                for conclusion in all_conclusions
                if str(conclusion or "").strip()
            ),
            "key_findings": ReportOrchestrator._clean_key_findings(exec_summary),
        }
        defense_audit = ReportDefenseAudit().audit(
            result,
            registry_conflicts=conflicts_summary,
        )
        integrity = ReportIntegrityChecker().check(result)
        result["claims"] = integrity["claims"]
        if integrity["issues"]:
            defense_audit["issues"].extend(integrity["issues"])
            defense_audit["layers"]["L4"] = True
            defense_audit["passed"] = False
            defense_audit["score"] = max(
                0.0, float(defense_audit.get("score", 100.0)) - len(integrity["issues"]) * 5.0,
            )
        # The report-upgrade registry is the authoritative conflict input.  A
        # failed audit must remain visible in the artifact and cannot be
        # mistaken for a successful final report.
        result["defense_audit"] = defense_audit
        result["quality_gate_status"] = (
            "passed"
            if defense_audit.get("passed", False)
            else (
                "blocked"
                if defense_audit.get("layers", {}).get("L5")
                else "degraded"
            )
        )
        result["formal_complete"] = bool(defense_audit.get("passed", False))
        if quality_report is not None:
            quality_report.converged = bool(quality_report.converged and defense_audit["passed"])
            quality_report.overall_score = min(
                float(quality_report.overall_score or 0),
                float(defense_audit["score"]),
            )
            result["quality_report"] = {
                "overall_score": quality_report.overall_score,
                "target_score": quality_report.target_score,
                "convergence_rounds": quality_report.convergence_rounds,
                "converged": quality_report.converged,
                "chapter_diagnostics": [
                    {
                        "chapter_id": cd.chapter_id,
                        "score": cd.score,
                        "source_layer": cd.source_layer,
                        "gaps": cd.gaps,
                        "remediations": cd.remediations,
                    }
                    for cd in quality_report.chapter_diagnostics
                ],
                "defense_audit": defense_audit,
            }
        if llm_trace:
            result["llm_trace"] = llm_trace
        # I5 交付签名（终审 P1#3）：签名是唯一事实源——放在所有质量
        # 信息齐备之后签署，formal_complete / quality_gate_status 一律
        # 由签名派生，下游旧消费者（存储分级、html 横幅）自动继承。
        from src.core.delivery_signer import DeliverySigner
        quality_snapshot = None
        if quality_report is not None:
            quality_snapshot = {
                "converged": bool(getattr(quality_report, "converged", False)),
                "overall_score": getattr(quality_report, "overall_score", None),
            }
        result["delivery_signature"] = DeliverySigner().sign(
            sections,
            defense_audit=defense_audit,
            quality_check=quality_snapshot,
        )
        result["formal_complete"] = bool(result["delivery_signature"]["formal_complete"])
        result["quality_gate_status"] = str(result["delivery_signature"]["quality_gate"])
        return result

    async def _checkpoint_chapter(self, task_id: str, chapter: ChapterWriteOutput) -> None:
        checkpoint_root = getattr(self, "_checkpoint_dir", None)
        checkpoint_dir = (
            checkpoint_root / "checkpoints"
            if checkpoint_root is not None
            else Path("data") / task_id / "checkpoints"
        )

        chapter_data = {
            "chapter_id": chapter.chapter_id,
            "title": chapter.title,
            "content": chapter.content,
            "data_points_used": [asdict(dp) for dp in chapter.data_points_used],
            "key_conclusions": chapter.key_conclusions,
            "self_check_passed": chapter.self_check_passed,
            "self_check_issues": chapter.self_check_issues,
            "status": chapter.status,
            "error": chapter.error,
            "sub_section_id": chapter.sub_section_id,
            "data_registry_snapshot": self._data_registry.to_snapshot(),
            "timestamp": datetime.now().isoformat(),
        }

        checkpoint_path = checkpoint_dir / _checkpoint_filename(chapter.chapter_id)

        def _write_checkpoint():
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            checkpoint_path.write_text(
                json.dumps(chapter_data, ensure_ascii=False, indent=2), "utf-8",
            )

        await asyncio.to_thread(_write_checkpoint)

    @staticmethod
    async def _restore_from_checkpoint(
        task_id: str,
        allowed_section_ids: Optional[Set[str]] = None,
        checkpoint_root: Optional[Path] = None,
    ):
        checkpoint_dir = (
            Path(checkpoint_root) / "checkpoints"
            if checkpoint_root is not None
            else Path("data") / task_id / "checkpoints"
        )
        if not checkpoint_dir.exists():
            return None

        def _read_checkpoints():
            results = []
            for path in sorted(checkpoint_dir.glob("chapter_*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    chapter_id = str(data.get("chapter_id", ""))
                    if allowed_section_ids is not None and chapter_id not in allowed_section_ids:
                        logger.info(
                            "Ignoring checkpoint for unrequested section %s", chapter_id,
                        )
                        continue
                    results.append(data)
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Failed to restore checkpoint {path}: {e}")
            return results

        checkpoint_data_list = await asyncio.to_thread(_read_checkpoints)

        chapters = []
        registry_snapshot = {}
        for data in checkpoint_data_list:
            # Failed/empty checkpoints are recovery evidence, not completed
            # chapters. They must be retried instead of entering the completed
            # set and suppressing the next generation attempt.
            checkpoint_status = str(data.get("status") or "ready").lower()
            if checkpoint_status != "ready" or not str(data.get("content") or "").strip():
                continue
            chapter = ChapterWriteOutput(
                chapter_id=data["chapter_id"],
                title=data["title"],
                content=data["content"],
                sub_section_id=str(data.get("sub_section_id", "") or ""),
                data_points_used=[
                    DataPoint(**{k: str(v) if k in _DP_STR_KEYS else v
                                 for k, v in dp.items() if k in DATAPOINT_FIELDS})
                    for dp in data.get("data_points_used", [])
                ],
                key_conclusions=[str(c) for c in data.get("key_conclusions", [])],
                self_check_passed=data.get("self_check_passed", True),
                self_check_issues=[str(i) for i in data.get("self_check_issues", [])],
                status=checkpoint_status,
                error=str(data.get("error") or ""),
            )
            chapters.append(chapter)
            registry_snapshot = data.get("data_registry_snapshot", {})

        return (chapters, registry_snapshot) if chapters else None

    def _parse_location_result(self, raw: str, fallback_request: str) -> "RevisionLocation":
        from .revision_models import RevisionLocation, RevisionTarget, RevisionComplexity
        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
                targets = [
                    RevisionTarget(
                        chapter_id=t.get("chapter_id", ""),
                        chapter_title=t.get("chapter_title", ""),
                        revision_type=t.get("revision_type", "modify"),
                        revision_description=t.get("revision_description", fallback_request),
                        data_patches=t.get("data_patches", []),
                    )
                    for t in data.get("targets", [])
                ]
                return RevisionLocation(
                    complexity=RevisionComplexity(data.get("complexity", "standard")),
                    targets=targets,
                    data_gaps=data.get("data_gaps", []),
                    data_conflicts=data.get("data_conflicts", []),
                    preceding_summary=data.get("preceding_summary", ""),
                )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to parse revision location: {e}")
        return RevisionLocation(
            complexity=RevisionComplexity.STANDARD,
            targets=[RevisionTarget(
                chapter_id="", chapter_title="",
                revision_type="modify",
                revision_description=fallback_request,
            )],
        )

    def _append_revision_preceding_summary(self, current: str, result) -> str:
        from .revision_models import ChapterRewriteResult
        conclusions = ""
        if result.revised_content:
            conclusions = result.revised_content[:500]
        if current and conclusions:
            max_len = self._MAX_PRECEDING_SUMMARY_LENGTH if hasattr(self, '_MAX_PRECEDING_SUMMARY_LENGTH') else 3000
            return current[-(max_len - 500):] + "\n" + conclusions
        return conclusions or current

    async def _execute_chapter_revision(
        self,
        target,
        preceding_summary: str,
    ):
        from .revision_models import RevisionTarget, ChapterRewriteResult

        target_chapter = next(
            (c for c in self._chapters if c.chapter_id == target.chapter_id), None
        )
        if not target_chapter:
            return ChapterRewriteResult(
                chapter_id=target.chapter_id,
                original_content="", revised_content="",
                review_passed=False, review_score=0.0,
            )

        original_content = target_chapter.content

        review_feedback = ChapterReviewOutput(
            passed=False, score=0.0,
            issues=[
                ChapterIssue(
                    category="user_revision", severity="HIGH",
                    location=f"chapter:{target.chapter_id}",
                    description=target.revision_description,
                    suggestion=target.revision_description,
                )
            ],
        )

        chapter_data = {"data_points": [dp.__dict__ for dp in target_chapter.data_points_used]} \
            if target_chapter.data_points_used else None

        rewritten = await self._chapter_writer.rewrite(
            original_chapter=target_chapter,
            review_feedback=review_feedback,
            framework_config=self._framework_config,
            chapter_spec={"section_id": target.chapter_id, "section_name": target.chapter_title},
            preceding_summary=preceding_summary,
            chapter_data=chapter_data,
        )

        # A failed/empty rewrite is not a candidate. Keep the last known-good
        # chapter so a transient LLM timeout cannot destroy valid content.
        best_chapter = (
            rewritten
            if isinstance(rewritten, ChapterWriteOutput)
            and str(rewritten.status or "ready").lower() == "ready"
            and str(rewritten.content or "").strip()
            else target_chapter
        )
        best_score = 0.0

        review_chapter_data = {"data_points": [dp.__dict__ for dp in target_chapter.data_points_used]} \
            if target_chapter.data_points_used else None

        for review_round in range(2):
            review = await self._chapter_reviewer.review(
                ChapterReviewInput(
                    framework_config=self._framework_config,
                    chapter_spec={"section_id": target.chapter_id, "section_name": target.chapter_title},
                    chapter_content=best_chapter.content,
                    preceding_summary=preceding_summary,
                    used_metrics_summary=self._data_registry.serialize_used_metrics(),
                    topic=self._task_structure.get('topic', ''),
                    writer_self_check_issues=best_chapter.self_check_issues,
                    chapter_data=review_chapter_data,
                )
            )
            if getattr(review, "parse_failed", False):
                # Reviewer output unparseable: no usable feedback to rewrite
                # against; skip the rewrite this round (round still counted).
                logger.warning(
                    "Chapter %s review parse failed; skipping rewrite this round",
                    target.chapter_id,
                )
                continue
            if review.passed:
                best_score = review.score
                break
            if review.score > best_score:
                best_score = review.score
            rewritten = await self._chapter_writer.rewrite(
                original_chapter=best_chapter,
                review_feedback=review,
                framework_config=self._framework_config,
                chapter_spec={"section_id": target.chapter_id, "section_name": target.chapter_title},
                preceding_summary=preceding_summary,
                chapter_data=chapter_data,
            )
            if (
                isinstance(rewritten, ChapterWriteOutput)
                and str(rewritten.status or "ready").lower() == "ready"
                and str(rewritten.content or "").strip()
            ):
                best_chapter = rewritten

        validated_dps = self._extract_and_validate_data_points(best_chapter)
        best_chapter.data_points_used = validated_dps
        for dp in validated_dps:
            self._data_registry.register(
                metric=dp.metric, value=dp.value, unit=dp.unit,
                chapter_id=best_chapter.chapter_id, source=dp.source,
            )

        idx = next(
            (i for i, c in enumerate(self._chapters) if c.chapter_id == target.chapter_id), None
        )
        if idx is not None and str(best_chapter.content or "").strip():
            self._chapters[idx] = best_chapter

        return ChapterRewriteResult(
            chapter_id=target.chapter_id,
            original_content=original_content,
            revised_content=best_chapter.content,
            review_passed=best_score >= 60,
            review_score=best_score,
            rewrite_rounds=review_round + 1,
        )

    async def _fix_global_issues(self, issues, fix_suggestions):
        fix_context = ""
        if fix_suggestions:
            fix_context = "\n".join(
                f"- {fs.fix_instruction}" for fs in fix_suggestions[:5]
                if hasattr(fs, 'fix_instruction')
            )
        for issue in issues[:5]:
            raw_location = issue.location
            if isinstance(raw_location, (list, tuple, set)):
                locations = [str(item or "").strip() for item in raw_location if str(item or "").strip()]
                location_text = locations[0] if locations else ""
            else:
                location_text = str(raw_location or "")
            chapter_id = location_text.split(":")[-1] if ":" in location_text else location_text
            target_chapter = next(
                (c for c in self._chapters if c.chapter_id == chapter_id), None
            )
            if not target_chapter:
                continue
            suggestion_text = issue.evidence
            if fix_context:
                suggestion_text = f"{issue.evidence}\n全局修正建议：\n{fix_context}" if issue.evidence else f"全局修正建议：\n{fix_context}"
            review_feedback = ChapterReviewOutput(
                passed=False, score=0.0,
                issues=[
                    ChapterIssue(
                        category=issue.dimension, severity=issue.severity,
                        location=issue.location, description=issue.description,
                        suggestion=suggestion_text,
                    )
                ],
            )
            chapter_data = {"data_points": [dp.__dict__ for dp in target_chapter.data_points_used]} \
                if target_chapter.data_points_used else None
            rewritten = await self._chapter_writer.rewrite(
                original_chapter=target_chapter,
                review_feedback=review_feedback,
                framework_config=self._framework_config,
                chapter_spec={"section_id": target_chapter.chapter_id, "section_name": target_chapter.title},
                preceding_summary="",
                chapter_data=chapter_data,
            )
            if rewritten.content:
                validated_dps = self._extract_and_validate_data_points(rewritten)
                rewritten.data_points_used = validated_dps
                for dp in validated_dps:
                    self._data_registry.register(
                        metric=dp.metric, value=dp.value, unit=dp.unit,
                        chapter_id=rewritten.chapter_id, source=dp.source,
                    )
                idx = next(
                    (i for i, c in enumerate(self._chapters) if c.chapter_id == chapter_id), None
                )
                if idx is not None:
                    self._chapters[idx] = rewritten

    async def _apply_lightweight_revision(self, location) -> Dict:
        from .revision_models import RevisionLocation
        for target in location.targets:
            for ch in self._chapters:
                if ch.chapter_id == target.chapter_id:
                    result = await call_llm(
                        prompt=f"对以下章节内容进行轻量修改：{target.revision_description}\n\n当前内容：\n{ch.content[:3000]}\n\n只修改涉及的部分，保持其他内容不变。",
                        max_tokens=4096, temperature=0.3,
                    )
                    if result.get("success") and result.get("content"):
                        ch.content = result["content"]
                        validated_dps = self._extract_and_validate_data_points(ch)
                        ch.data_points_used = validated_dps
                        for dp in validated_dps:
                            self._data_registry.register(
                                metric=dp.metric, value=dp.value, unit=dp.unit,
                                chapter_id=ch.chapter_id, source=dp.source,
                            )
                    break
        return {
            "chapter_results": [],
            "global_review_score": 0,
            "global_review_passed": True,
            "data_registry_snapshot": self._data_registry.to_snapshot(),
        }

    async def _locate_revision_target(
        self,
        user_request: str,
        quality_issues: Optional[List[Dict]] = None,
    ):
        from .revision_models import RevisionLocation, RevisionComplexity
        chapter_index = "\n".join(
            f"- [{c.chapter_id}] {c.title}"
            for c in self._chapters
        )
        data_index = self._data_registry.serialize_used_metrics()
        issues_context = ""
        if quality_issues:
            issues_context = "\n".join(
                f"- [{iss.get('severity', '')}] {iss.get('section', '')}: {iss.get('message', '')}"
                for iss in quality_issues[:20]
            )

        prompt = self._prompts.get(
            "revision_locate",
            topic=self._task_structure.get('topic', ''),
            chapter_index=chapter_index,
            data_index=data_index,
            issues_context=issues_context or '无',
            user_request=user_request,
        )

        result = await call_llm(prompt=prompt, max_tokens=4096, temperature=0.3)
        if not result.get("success"):
            return RevisionLocation(complexity=RevisionComplexity.STANDARD)
        return self._parse_location_result(result["content"], user_request)

    async def revision(
        self,
        user_request: str,
        quality_issues: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        from .revision_models import RevisionComplexity

        location = await self._locate_revision_target(user_request, quality_issues)

        if location.complexity == RevisionComplexity.LIGHTWEIGHT:
            return await self._apply_lightweight_revision(location)

        preceding_summary = ""
        chapter_results = []
        for target in location.targets:
            result = await self._execute_chapter_revision(target, preceding_summary)
            chapter_results.append(result)
            if result.review_passed:
                preceding_summary = self._append_revision_preceding_summary(preceding_summary, result)

        global_review = await self._global_reviewer.review(
            ReviewInput(
                framework_config=self._framework_config,
                report_summary=serialize_report_for_review(self._chapters, self._data_registry),
                conflicts_summary=self._data_registry.serialize_conflicts(),
            )
        )
        verified_issues = await self._global_reviewer.verify_issues(global_review.issues, self._chapters)

        if global_review.overall_score < 80 and verified_issues:
            await self._fix_global_issues(verified_issues, global_review.fix_suggestions)
            global_review = await self._global_reviewer.review(
                ReviewInput(
                    framework_config=self._framework_config,
                    report_summary=serialize_report_for_review(self._chapters, self._data_registry),
                    conflicts_summary=self._data_registry.serialize_conflicts(),
                )
            )

        return {
            "chapter_results": chapter_results,
            "global_review_score": global_review.overall_score,
            "global_review_passed": global_review.overall_score >= 80,
            "data_registry_snapshot": self._data_registry.to_snapshot(),
        }
