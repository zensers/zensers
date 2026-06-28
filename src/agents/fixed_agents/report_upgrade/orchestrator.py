import re
import json
import asyncio
import logging
from dataclasses import asdict
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Set, Tuple

from .models import (
    ChapterWriteInput, ChapterWriteOutput, ChapterReviewInput, ChapterReviewOutput,
    ReviewInput, ReviewOutput, DataGap, DataConflict, DataPoint, DataConflictResolution,
    DataRepairResult, QualityIssueDiagnosis, ChapterDiagnostic, QualityReport,
    ChapterIssue,
)
from .data_registry import DataRegistry
from .chapter_writer import ChapterWriter, DATAPOINT_FIELDS

_DP_STR_KEYS = {"metric", "value", "unit", "source", "chapter_id"}
from .chapter_reviewer import ChapterReviewAgent
from .global_reviewer import GlobalReviewAgent, serialize_report_for_review
from .data_repair import DataRepairAgent, ConflictResolver
from .structured_data_repair import StructuredDataRepairAgent
from .prompt_manager import PromptManager
from src.core.quality.checkers import AnalysisQualityChecker
from src.core.llm_client import call_llm

logger = logging.getLogger(__name__)

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


class RetryPolicy:
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

    def __init__(
        self,
        chapter_writer: ChapterWriter,
        chapter_reviewer: ChapterReviewAgent,
        global_reviewer: GlobalReviewAgent,
        data_repair_agent: DataRepairAgent,
        conflict_resolver: ConflictResolver,
        prompt_manager: PromptManager = None,
        skill_registry=None,
        llm_skill=None,  # kept for backward compatibility; agents use call_llm() directly
    ) -> None:
        # self._llm removed - agents use call_llm() from src.core.llm_client directly
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
        self._structured_data_repair = StructuredDataRepairAgent(skill_registry=skill_registry)
        self._llm_trace: List[Dict[str, Any]] = []

    async def generate_report(
        self,
        task_structure: Dict[str, Any],
        framework_config: Dict[str, Any],
        aggregated_result: Any,
        topic: str = "",
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        last_error = None

        for full_attempt in range(RetryPolicy.MAX_FULL_RETRIES + 1):
            try:
                if task_id:
                    restored = await self._restore_from_checkpoint(task_id)
                    if restored:
                        chapters, registry_snapshot = restored
                        self._data_registry = DataRegistry.from_snapshot(registry_snapshot)
                        preceding_summary = self._rebuild_preceding_summary(chapters)
                        completed_section_ids = {ch.chapter_id for ch in chapters}
                        logger.info(f"Restored {len(chapters)} chapters from checkpoint (attempt {full_attempt+1})")
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

                narrative_context = self._understand_framework(task_structure, framework_config)

                for section_spec in task_structure.get("sections", []):
                    section_id = section_spec.get("section_id", "")

                    if section_id in completed_section_ids:
                        continue

                    chapter_data, raw_data_summary = self._extract_chapter_data(
                        aggregated_result, section_id,
                        section_spec.get("content_dependency", []),
                        skill_registry=self._skill_registry,
                    )

                    base_content = chapter_data.get("content", "") if isinstance(chapter_data, dict) else ""
                    upstream_data_points = chapter_data.get("upstream_data_points") if isinstance(chapter_data, dict) else None

                    chapter = None
                    last_chapter_error = None

                    for chapter_attempt in range(RetryPolicy.MAX_CHAPTER_RETRIES):
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
                                )
                            )

                            chapter.content = _enforce_structure_compliance(chapter.content)

                            validated_dps = self._extract_and_validate_data_points(chapter)
                            for dp in validated_dps:
                                self._data_registry.register(
                                    metric=dp.metric, value=dp.value, unit=dp.unit,
                                    chapter_id=chapter.chapter_id, source=dp.source,
                                )

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
                            break

                        except (asyncio.TimeoutError, RuntimeError) as e:
                            last_chapter_error = str(e)
                            if self._is_non_retryable_error(e):
                                logger.error(f"Non-retryable error for chapter {section_id}: {e}")
                                break
                            delay = RetryPolicy.get_delay(chapter_attempt)
                            logger.warning(f"Chapter attempt {chapter_attempt+1} failed: {e}")
                            await asyncio.sleep(delay)

                    if chapter is None:
                        logger.error(f"Chapter {section_id} failed after retries")
                        if last_chapter_error and self._is_non_retryable_error(RuntimeError(last_chapter_error)):
                            raise RuntimeError(f"Non-retryable error, aborting: {last_chapter_error}")
                        continue

                    chapters.append(chapter)
                    preceding_summary = self._append_preceding_summary(
                        preceding_summary, chapter
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

                exec_summary = await self._generate_exec_summary(chapters, task_structure, topic)

                original_sources = getattr(aggregated_result, 'sources', [])
                return self._assemble_final_report(
                    chapters, exec_summary, review, topic, original_sources,
                    quality_report=quality_report,
                    llm_trace=self._llm_trace,
                )

            except Exception as e:
                last_error = e
                if full_attempt < RetryPolicy.MAX_FULL_RETRIES:
                    delay = RetryPolicy.get_delay(full_attempt)
                    logger.warning(f"Full attempt {full_attempt+1} failed: {e}")
                    await asyncio.sleep(delay)

        raise RuntimeError(
            f"Report generation failed after {RetryPolicy.MAX_FULL_RETRIES + 1} attempts. "
            f"Last error: {last_error}"
        )

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

        for round_idx in range(RetryPolicy.MAX_CONVERGENCE_ROUNDS):
            logger.info(f"Convergence round {round_idx + 1}/{RetryPolicy.MAX_CONVERGENCE_ROUNDS}, score={prev_score:.1f}")
            chapters = await self._phase4_fix_and_optimize(
                chapters, review, framework_config, topic,
            )

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
                    self._aggregated_result, resolved_id,
                    ch_spec.get("content_dependency", []) if ch_spec else [],
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

        repair_task = self._data_repair_agent.repair_batch(data_gaps, topic)
        resolve_tasks = [self._conflict_resolver.resolve(c, topic) for c in data_conflicts]

        repair_results, *resolution_results = await asyncio.gather(
            repair_task, *resolve_tasks,
        )

        chapters, patched_chapter_ids = await self._apply_data_repairs(
            chapters, repair_results, resolution_results, framework_config,
        )

        for ch_id, repairs in structured_data_repairs.items():
            for repair in repairs:
                patch_instructions = [
                    f"补充结构化数据（来源：{repair['source']}）：{json.dumps(repair['data'], ensure_ascii=False, indent=2)[:500]}"
                ]
                ch_idx = next((i for i, c in enumerate(chapters) if c.chapter_id == ch_id), None)
                if ch_idx is not None:
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
                self._aggregated_result, chapter.chapter_id,
                chapter_spec.get("content_dependency", []) if chapter_spec else [],
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
        self._verify_downstream_consistency(chapters, rewrite_needed)

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

            chapters[i] = await self._chapter_writer.patch_data(
                chapter=chapter,
                patch_instructions=patch_instructions,
                framework_config=framework_config,
            )
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
    def _extract_chapter_data(
        aggregated_result: Any, section_id: str, content_dependencies: List[str],
        skill_registry=None,
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
            if target == section_id:
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
            return {}, ""

        refined, raw_summary = ReportOrchestrator._split_chapter_data(raw_value, matched_key, layered_content)
        return refined, raw_summary

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
        validated = list(chapter.data_points_used)

        pattern = re.compile(
            r'(\d[\d,.]*)\s*'
            r'(亿元|万元|元|%|亿美元|千万|百万|万亿美元'
            r'|billion|million|trillion|thousand|percent|%\s*)',
            re.IGNORECASE
        )
        for match in pattern.finditer(chapter.content):
            value = match.group(1)
            unit = match.group(2)
            already_reported = any(
                str(dp.value).replace(",", "") == value.replace(",", "") and dp.unit == unit
                for dp in validated
            )
            if not already_reported:
                context_start = max(0, match.start() - 30)
                context = chapter.content[context_start:match.start()].strip()
                validated.append(DataPoint(
                    metric=context[-15:] if context else "未命名指标",
                    value=value, unit=unit, source="",
                    chapter_id=chapter.chapter_id,
                ))

        return validated

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
    ) -> None:
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

    def _find_section_spec(self, section_id: str, framework_config: Dict) -> Dict:
        for sec in self._task_structure.get("sections", []):
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

        result = await self._call_llm_tracked(prompt=prompt, max_tokens=4096, temperature=0.7)
        if result.get("success"):
            return result["content"]
        logger.error(f"Exec summary LLM call failed: {result}")
        return "摘要生成失败。"

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
            line = re.sub(r'^#+\s*', '', line)
            line = re.sub(r'\*{1,2}', '', line)
            if ReportOrchestrator._HEADING_PATTERN.match(line.strip()):
                continue
            if ReportOrchestrator._SUBHEADING_PATTERN.match(line.strip()):
                continue
            if ReportOrchestrator._TITLE_LIKE_PATTERN.match(line.strip()) and len(line.strip()) < 30:
                continue
            if len(line) < 8:
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
    def _ground_data_point_sources(
        data_points: List[Dict[str, Any]],
        available_sources: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not available_sources:
            return data_points
        source_names = [s.get("title", s.get("url", s.get("href", ""))) for s in available_sources if s.get("title") or s.get("url") or s.get("href")]
        fallback_source = source_names[0] if source_names else ""
        grounded = []
        _SOURCE_INDEX_PATTERN = re.compile(r'^来源(\d+)$')
        for dp in data_points:
            dp_src = dp.get("source", "")
            # D3: check "来源N" pattern first (fuzzy index, not a real source)
            idx_match = _SOURCE_INDEX_PATTERN.match(dp_src.strip()) if dp_src else None
            if idx_match:
                dp = dict(dp)
                idx = int(idx_match.group(1)) - 1
                if 0 <= idx < len(source_names):
                    dp["source"] = source_names[idx]
                else:
                    dp["source"] = fallback_source
                grounded.append(dp)
            elif dp_src and not _is_vague_source(dp_src):
                grounded.append(dp)
            else:
                dp = dict(dp)
                dp["source"] = fallback_source
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
        llm_trace: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        all_sources = list(original_sources) if original_sources else []
        chapter_sources = [
            {"title": s.get("title", ""), "url": s.get("url", s.get("href", "")), "type": s.get("type", "web")}
            for s in all_sources
        ] if all_sources else []

        sections = []
        for ch in chapters:
            raw_dp = [asdict(dp) for dp in ch.data_points_used]
            grounded_dp = ReportOrchestrator._ground_data_point_sources(raw_dp, all_sources)
            sections.append({
                "id": ch.chapter_id,
                "title": ch.title,
                "content": ch.content,
                "subsections": [],
                "charts": [],
                "data_points": grounded_dp,
                "sources": chapter_sources,
            })

        result = {
            "topic": topic,
            "title": topic,
            "aspects": [ch.title for ch in chapters],
            "sections": sections,
            "sources": all_sources,
            "key_findings": ReportOrchestrator._clean_key_findings(exec_summary),
        }
        if quality_report is not None:
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
            }
        if llm_trace:
            result["llm_trace"] = llm_trace
        return result

    async def _checkpoint_chapter(self, task_id: str, chapter: ChapterWriteOutput) -> None:
        checkpoint_dir = Path("data") / task_id / "checkpoints"

        chapter_data = {
            "chapter_id": chapter.chapter_id,
            "title": chapter.title,
            "content": chapter.content,
            "data_points_used": [asdict(dp) for dp in chapter.data_points_used],
            "key_conclusions": chapter.key_conclusions,
            "self_check_passed": chapter.self_check_passed,
            "self_check_issues": chapter.self_check_issues,
            "data_registry_snapshot": self._data_registry.to_snapshot(),
            "timestamp": datetime.now().isoformat(),
        }

        checkpoint_path = checkpoint_dir / f"chapter_{chapter.chapter_id}.json"

        def _write_checkpoint():
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            checkpoint_path.write_text(
                json.dumps(chapter_data, ensure_ascii=False, indent=2), "utf-8",
            )

        await asyncio.to_thread(_write_checkpoint)

    @staticmethod
    async def _restore_from_checkpoint(task_id: str):
        checkpoint_dir = Path("data") / task_id / "checkpoints"
        if not checkpoint_dir.exists():
            return None

        def _read_checkpoints():
            results = []
            for path in sorted(checkpoint_dir.glob("chapter_*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    results.append(data)
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Failed to restore checkpoint {path}: {e}")
            return results

        checkpoint_data_list = await asyncio.to_thread(_read_checkpoints)

        chapters = []
        registry_snapshot = {}
        for data in checkpoint_data_list:
            chapter = ChapterWriteOutput(
                chapter_id=data["chapter_id"],
                title=data["title"],
                content=data["content"],
                data_points_used=[
                    DataPoint(**{k: str(v) if k in _DP_STR_KEYS else v
                                 for k, v in dp.items() if k in DATAPOINT_FIELDS})
                    for dp in data.get("data_points_used", [])
                ],
                key_conclusions=[str(c) for c in data.get("key_conclusions", [])],
                self_check_passed=data.get("self_check_passed", True),
                self_check_issues=[str(i) for i in data.get("self_check_issues", [])],
            )
            chapters.append(chapter)
            registry_snapshot = data.get("data_registry_snapshot", {})

        return (chapters, registry_snapshot) if chapters else None
