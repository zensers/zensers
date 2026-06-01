"""
内容质量管线模块
================

提供结构化的内容清洗和质量检查能力。

核心组件：
- ContentFilter: 过滤器基类
- ContentCleaningPipeline: 清洗管线
- CrossTypeDuplicateDetector: 跨类型去重（标题 vs 段落）
- GlobalDuplicateDetector: 全局跨章节去重
- PromptPatternFilter: Prompt 痕迹清理
- ContentQualityGate: 质量门禁

使用方式：
    pipeline = create_default_pipeline()
    cleaned_sections = pipeline.process_sections(sections)

修订历史：
- v1.0 (2026-04-29): 初始版本，修订 CrossTypeDuplicateDetector 扫描方向 bug
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import logging
import re

logger = logging.getLogger(__name__)


# =============================================================================
# 常量定义
# =============================================================================

# 默认 Prompt 清理模式
DEFAULT_PROMPT_PATTERNS = [
    # === LLM 回复前缀（整行删除）===
    r'^好的，根据您提供的.*',
    r'^好的，遵照您的指示.*',
    r'^好的，.*任务要求.*',
    r'^根据您提供的.*任务要求.*',
    r'^遵照您的指示.*',
    r'^根据您的要求.*',
    r'^按照您的要求.*',
    r'^我将为您.*',
    r'^我为您撰写了.*',
    r'^以下是根据.*撰写.*',
    r'^以下是.*综合分析.*',
    r'^以下是.*分析报告.*',
    # 整行删除模式
    r'^基于您提供的.*数据点.*分析.*',
    r'^基于您提供的所有数据点.*',
    r'.*将对["""].*["""].*维度进行.*',
    r'.*形成一份面向决策层.*',
    r'.*原创性的综合与提炼.*',
    r'^数据来源\s*数据来源\s*$',
    r'^本.*基于.*数据.*分析.*',
    r'.*基于多源数据.*分析.*',
    # 行首清理模式
    r'^原创洞察[：:]\s*',
    r'^原创洞察\s+',
    # 行内清理模式
    r'原创洞察[：:]\s*',
    r'原创洞察\s*[：:]',
    # === 数据来源清理模式 ===
    # 清理各种来源标注格式
    r'（来源[：:][^）]+）',  # （来源：媒体快评，质量分36）
    r'【来源[：:][^】]+】',  # 【来源：XXX】
    r'\(来源[：:][^)]+\)',  # (来源：XXX)
    r'\[来源[：:][^\]]+\]',  # [来源：XXX]
    r'（数据来源[：:][^）]+）',  # （数据来源：XXX）
    r'【数据来源[：:][^】]+】',  # 【数据来源：XXX】
    r'，质量分\d+\.?\d*\)',  # ，质量分36）
    r'，质量分\d+\.?\d*）',  # ，质量分36）
    # === 章节标题重复清理 ===
    # 清理正文内嵌的章节标题（如 "执行摘要"、"市场概况" 作为正文内容）
    r'^<strong>执行摘要</strong>$',
    r'^<strong>市场概况</strong>$',
    r'^<strong>研究结论</strong>$',
    r'^<strong>关键发现</strong>$',
    r'^<strong>结论与建议</strong>$',
]

# 口语化表达清理模式
COLLOQUIAL_PATTERNS = [
    r'值得关注的是[，,]?\s*',
    r'巧合的是[，,]?\s*',
    r'有趣的是[，,]?\s*',
    r'不得不说[，,]?\s*',
    r'让我们看看[，,]?\s*',
    r'想象一下[，,]?\s*',
    r'你知道吗[，,]?\s*',
    r'这就意味着[，,]?\s*',
    r'换句话说[，,]?\s*',
    r'简单来说[，,]?\s*',
]


# =============================================================================
# 数据类
# =============================================================================

class QualityIssueType(Enum):
    """质量问题类型"""
    RESIDUAL_ANALYSIS_LABEL = "residual_analysis_label"
    RESIDUAL_SOURCE_MARKER = "residual_source_marker"
    CROSS_TYPE_DUPLICATE = "cross_type_duplicate"
    CONSECUTIVE_DUPLICATE = "consecutive_duplicate"
    GLOBAL_DUPLICATE = "global_duplicate"
    ORAL_STYLE = "oral_style"


@dataclass
class QualityResult:
    """质量检查结果"""
    passed: bool
    issues: List[QualityIssueType]
    severity: str  # "low", "medium", "high"
    details: Optional[str] = None


# =============================================================================
# 过滤器基类
# =============================================================================

class ContentFilter(ABC):
    """内容过滤器基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """过滤器名称"""
        pass
    
    @abstractmethod
    def apply(self, content: str) -> str:
        """应用过滤器到字符串内容"""
        pass
    
    def apply_to_sections(self, sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        应用过滤器到章节列表
        
        默认实现：对每个章节的 content 字段应用过滤器
        子类可覆盖以实现跨章节处理
        """
        for section in sections:
            if "content" in section and isinstance(section["content"], str):
                section["content"] = self.apply(section["content"])
        return sections


# =============================================================================
# 过滤器实现
# =============================================================================

class PromptPatternFilter(ContentFilter):
    """
    Prompt 痕迹过滤器
    
    清理 LLM 输出中残留的 prompt 文本和分析标签。
    """
    
    @property
    def name(self) -> str:
        return "prompt_pattern_filter"
    
    def __init__(
        self, 
        patterns: Optional[List[str]] = None,
        remove_colloquial: bool = True
    ):
        self._line_patterns: List[str] = []  # 整行删除
        self._inline_patterns: List[str] = []  # 行内替换
        
        # 初始化默认模式
        default_patterns = patterns or DEFAULT_PROMPT_PATTERNS
        for pattern in default_patterns:
            if pattern.startswith('^'):
                self._line_patterns.append(pattern)
            else:
                self._inline_patterns.append(pattern)
        
        # 口语化清理
        if remove_colloquial:
            self._inline_patterns.extend(COLLOQUIAL_PATTERNS)
    
    def apply(self, content: str) -> str:
        """应用过滤器"""
        if not content:
            return content
        
        lines = content.split('\n')
        result = []
        
        for line in lines:
            stripped = line.strip()
            
            # 检查是否需要整行删除
            should_remove = False
            for pattern in self._line_patterns:
                if re.match(pattern, stripped):
                    should_remove = True
                    logger.debug(f"Removed line matching pattern: {pattern[:30]}...")
                    break
            
            if should_remove:
                continue
            
            # 行内替换
            for pattern in self._inline_patterns:
                new_line = re.sub(pattern, '', line)
                if new_line != line:
                    line = new_line
            
            result.append(line)
        
        return '\n'.join(result)
    
    def add_pattern(self, pattern: str, is_line_pattern: bool = False) -> "PromptPatternFilter":
        """运行时添加新模式"""
        if is_line_pattern:
            self._line_patterns.append(pattern)
        else:
            self._inline_patterns.append(pattern)
        return self


class CrossTypeDuplicateDetector(ContentFilter):
    """
    跨类型重复检测器（修订版）
    
    检测标题与紧随其后的段落内容是否高度相似。
    解决：正文首句与子标题使用相同文字的问题。
    
    修订要点：
    1. 修正扫描方向：向前 → 向后（标题在前，段落在后）
    2. 增加多段落检查：检查标题后最多 N 个段落
    3. 保留策略：优先保留段落（信息更完整），删除重复标题
    """
    
    @property
    def name(self) -> str:
        return "cross_type_duplicate_detector"
    
    def __init__(self, threshold: float = 0.75, max_scan_lines: int = 5):
        self.threshold = threshold
        self.max_scan_lines = max_scan_lines
    
    def apply(self, content: str) -> str:
        """应用过滤器"""
        if not content:
            return content
        
        lines = content.split('\n')
        result = []
        i = 0
        removed_count = 0
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # 检查是否是 Markdown 标题
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                heading_text = heading_match.group(2).strip()
                
                # 修订：向后扫描找段落
                found_duplicate = False
                for j in range(i + 1, min(i + 1 + self.max_scan_lines, len(lines))):
                    next_line = lines[j].strip()
                    
                    # 跳过空行
                    if not next_line:
                        continue
                    
                    # 遇到下一个标题，停止扫描
                    if next_line.startswith('#'):
                        break
                    
                    # 检查段落与标题的相似度
                    similarity = self._text_similarity(heading_text, next_line)
                    
                    if similarity > self.threshold:
                        logger.debug(
                            f"Cross-type duplicate: heading '{heading_text[:30]}...' "
                            f"matches paragraph (similarity={similarity:.2f})"
                        )
                        found_duplicate = True
                        removed_count += 1
                        break
                    
                    # 只检查第一个非空段落
                    break
                
                if found_duplicate:
                    # 策略：跳过标题，保留段落（段落信息更完整）
                    i += 1
                    continue
            
            result.append(line)
            i += 1
        
        if removed_count > 0:
            logger.info(f"CrossTypeDuplicateDetector: removed {removed_count} duplicate headings")
        
        return '\n'.join(result)
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度"""
        # 移除标点符号和空白（含中文标点）
        # 使用原始字符串避免转义警告
        pattern = r'[\s,，。、；：""''！？()（）【】\[\]《》—…·]'
        clean1 = re.sub(pattern, '', text1)
        clean2 = re.sub(pattern, '', text2)
        
        # 数字归一化
        clean1 = re.sub(r'\d+', 'N', clean1)
        clean2 = re.sub(r'\d+', 'N', clean2)
        
        if not clean1 or not clean2:
            return 0.0
        
        # Jaccard 相似度
        set1 = set(clean1)
        set2 = set(clean2)
        
        if not set1 or not set2:
            return 0.0
        
        intersection = set1 & set2
        union = set1 | set2
        
        jaccard = len(intersection) / len(union) if union else 0.0
        
        # 包含关系加分
        shorter, longer = (clean1, clean2) if len(clean1) < len(clean2) else (clean2, clean1)
        if shorter in longer:
            containment_ratio = len(shorter) / len(longer)
            return max(jaccard, containment_ratio * 0.9)
        
        return jaccard


class GlobalDuplicateDetector(ContentFilter):
    """
    全局跨章节重复检测器（修订版）
    
    检测不同章节间的内容重复。
    
    修订要点：
    1. 包含关系成立时直接判定为重复
    2. 降低 min_length 以适应中文（30 字符）
    3. 增加 early-exit 优化
    4. 增加章节边界感知
    """
    
    @property
    def name(self) -> str:
        return "global_duplicate_detector"
    
    def __init__(
        self, 
        threshold: float = 0.85, 
        min_length: int = 30,  # 修订：从 50 降到 30，适应中文
        max_paragraphs_per_section: int = 100
    ):
        self.threshold = threshold
        self.min_length = min_length
        self.max_paragraphs = max_paragraphs_per_section
    
    def apply(self, content: str) -> str:
        """应用过滤器"""
        if not content:
            return content
        
        # 按章节分割（保留章节标题）
        sections = re.split(r'(?=^#{1,3}\s)', content, flags=re.MULTILINE)
        
        if len(sections) <= 1:
            return content
        
        seen_paragraphs: List[Tuple[str, str]] = []  # (normalized, original)
        result_sections = []
        total_duplicates = 0
        
        for section_idx, section in enumerate(sections):
            lines = section.split('\n')
            cleaned_lines = []
            
            for line in lines:
                stripped = line.strip()
                
                # 保留标题和空行
                if not stripped or stripped.startswith('#'):
                    cleaned_lines.append(line)
                    continue
                
                # 归一化
                normalized = self._normalize(stripped)
                
                # 短文本跳过
                if len(normalized) < self.min_length:
                    cleaned_lines.append(line)
                    continue
                
                # 性能优化：限制比较次数
                if len(seen_paragraphs) > self.max_paragraphs:
                    compare_pool = seen_paragraphs[-self.max_paragraphs:]
                else:
                    compare_pool = seen_paragraphs
                
                is_duplicate = False
                for seen_norm, seen_orig in compare_pool:
                    similarity = self._calculate_similarity(normalized, seen_norm)
                    
                    if similarity > self.threshold:
                        is_duplicate = True
                        total_duplicates += 1  # 修复：递增计数
                        logger.debug(
                            f"Global duplicate in section {section_idx}: "
                            f"'{stripped[:40]}...' (similarity={similarity:.2f})"
                        )
                        break
                
                if not is_duplicate:
                    seen_paragraphs.append((normalized, stripped))
                    cleaned_lines.append(line)
            
            result_sections.append('\n'.join(cleaned_lines))
        
        if total_duplicates > 0:
            logger.info(f"GlobalDuplicateDetector: removed {total_duplicates} duplicate paragraphs")
        
        return '\n'.join(result_sections)
    
    def apply_to_sections(self, sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        应用过滤器到章节列表（覆盖基类实现）
        
        实现跨章节的全局去重。
        """
        seen_paragraphs: List[Tuple[str, str]] = []
        total_duplicates = 0
        
        for section_idx, section in enumerate(sections):
            if "content" not in section or not isinstance(section["content"], str):
                continue
            
            content = section["content"]
            lines = content.split('\n')
            cleaned_lines = []
            
            for line in lines:
                stripped = line.strip()
                
                # 保留标题和空行
                if not stripped or stripped.startswith('#'):
                    cleaned_lines.append(line)
                    continue
                
                # 归一化
                normalized = self._normalize(stripped)
                
                # 短文本跳过
                if len(normalized) < self.min_length:
                    cleaned_lines.append(line)
                    continue
                
                # 全局比较
                is_duplicate = False
                for seen_norm, seen_orig in seen_paragraphs:
                    similarity = self._calculate_similarity(normalized, seen_norm)
                    
                    if similarity > self.threshold:
                        is_duplicate = True
                        total_duplicates += 1
                        break
                
                if not is_duplicate:
                    seen_paragraphs.append((normalized, stripped))
                    cleaned_lines.append(line)
            
            section["content"] = '\n'.join(cleaned_lines)
        
        if total_duplicates > 0:
            logger.info(f"GlobalDuplicateDetector: removed {total_duplicates} cross-section duplicates")
        
        return sections
    
    def _normalize(self, text: str) -> str:
        """归一化文本"""
        pattern = r'[\s,，。、；：""''！？()（）【】\[\]《》—…·\d]'
        return re.sub(pattern, '', text)
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算相似度（修订版）"""
        if not text1 or not text2:
            return 0.0
        
        # 完全相同
        if text1 == text2:
            return 1.0
        
        shorter, longer = (text1, text2) if len(text1) < len(text2) else (text2, text1)
        
        # 修订：包含关系成立时直接返回高分
        if shorter in longer:
            return 0.95
        
        # Jaccard 相似度
        set1 = set(text1)
        set2 = set(text2)
        intersection = set1 & set2
        union = set1 | set2
        
        return len(intersection) / len(union) if union else 0.0


class ContentQualityGate:
    """
    内容质量门禁
    
    在内容送入渲染引擎前做最终检查。
    """
    
    # 可自动修复的问题
    AUTO_FIXABLE = {
        QualityIssueType.RESIDUAL_ANALYSIS_LABEL,
        QualityIssueType.RESIDUAL_SOURCE_MARKER,
        QualityIssueType.CROSS_TYPE_DUPLICATE,
        QualityIssueType.CONSECUTIVE_DUPLICATE,
        QualityIssueType.GLOBAL_DUPLICATE,
        QualityIssueType.ORAL_STYLE,
    }
    
    # 问题严重程度映射
    SEVERITY_MAP = {
        QualityIssueType.RESIDUAL_ANALYSIS_LABEL: "medium",
        QualityIssueType.RESIDUAL_SOURCE_MARKER: "low",
        QualityIssueType.CROSS_TYPE_DUPLICATE: "high",
        QualityIssueType.CONSECUTIVE_DUPLICATE: "medium",
        QualityIssueType.GLOBAL_DUPLICATE: "high",
        QualityIssueType.ORAL_STYLE: "low",
    }
    
    def __init__(self, max_retries: int = 2, auto_fix_enabled: bool = True):
        self.max_retries = max_retries
        self.auto_fix_enabled = auto_fix_enabled
    
    def check(self, content: str) -> QualityResult:
        """检查内容质量"""
        issues = []
        
        # 检查残留分析标签
        if re.search(r'原创洞察|核心洞察|笔者认为|分析显示|分析师判断', content):
            issues.append(QualityIssueType.RESIDUAL_ANALYSIS_LABEL)
        
        # 检查来源标注（更全面的模式）
        source_patterns = [
            r'（来源[：:]',       # （来源：
            r'【来源[：:]',       # 【来源：
            r'\(来源[：:]',       # (来源：
            r'\[来源[：:]',       # [来源：
            r'（数据来源[：:]',   # （数据来源：
            r'【数据来源[：:]',   # 【数据来源：
            r'质量分\d+\.?\d*\)', # 质量分36）
        ]
        for pattern in source_patterns:
            if re.search(pattern, content):
                issues.append(QualityIssueType.RESIDUAL_SOURCE_MARKER)
                break
        
        # 检查口语化表达
        if re.search(r'值得关注的是|巧合的是|有趣的是|不得不说|让我们看看', content):
            issues.append(QualityIssueType.ORAL_STYLE)
        
        # 检查跨类型重复
        if self._has_cross_type_duplicate(content):
            issues.append(QualityIssueType.CROSS_TYPE_DUPLICATE)
        
        # 检查连续重复
        if self._has_consecutive_duplicate(content):
            issues.append(QualityIssueType.CONSECUTIVE_DUPLICATE)
        
        severity = self._calculate_severity(issues)
        
        return QualityResult(
            passed=len(issues) == 0,
            issues=issues,
            severity=severity,
            details=self._generate_details(issues) if issues else None
        )
    
    def _calculate_severity(self, issues: List[QualityIssueType]) -> str:
        """计算整体严重程度"""
        if not issues:
            return "low"
        
        severities = [self.SEVERITY_MAP.get(i, "medium") for i in issues]
        
        if "high" in severities:
            return "high"
        elif "medium" in severities:
            return "medium"
        return "low"
    
    def _generate_details(self, issues: List[QualityIssueType]) -> str:
        """生成问题详情"""
        issue_names = {
            QualityIssueType.RESIDUAL_ANALYSIS_LABEL: "残留分析标签",
            QualityIssueType.RESIDUAL_SOURCE_MARKER: "残留来源标注",
            QualityIssueType.CROSS_TYPE_DUPLICATE: "跨类型重复",
            QualityIssueType.CONSECUTIVE_DUPLICATE: "连续段落重复",
            QualityIssueType.GLOBAL_DUPLICATE: "跨章节重复",
            QualityIssueType.ORAL_STYLE: "口语化表达",
        }
        return "发现以下问题: " + ", ".join(issue_names.get(i, str(i)) for i in issues)
    
    def _has_cross_type_duplicate(self, content: str) -> bool:
        """检测跨类型重复"""
        lines = content.split('\n')
        for i, line in enumerate(lines):
            heading_match = re.match(r'^#{1,6}\s+(.+)$', line.strip())
            if heading_match:
                heading_text = heading_match.group(1).strip()
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and not next_line.startswith('#'):
                        if next_line.startswith(heading_text):
                            return True
        return False
    
    def _has_consecutive_duplicate(self, content: str) -> bool:
        """检测连续重复段落"""
        paragraphs = re.split(r'\n\s*\n', content)
        for i in range(len(paragraphs) - 1):
            if paragraphs[i].strip() and paragraphs[i] == paragraphs[i + 1]:
                return True
        return False
    
    def can_auto_fix(self, issues: List[QualityIssueType]) -> bool:
        """判断是否可以自动修复"""
        return all(issue in self.AUTO_FIXABLE for issue in issues)
    
    def get_retry_strategy(self, result: QualityResult) -> dict:
        """获取重试策略"""
        if result.passed:
            return {"should_retry": False, "retry_action": "none", "max_attempts": 0}
        
        if self.can_auto_fix(result.issues):
            return {
                "should_retry": True,
                "retry_action": "clean",
                "max_attempts": 1,
            }
        
        return {
            "should_retry": True,
            "retry_action": "regenerate",
            "max_attempts": self.max_retries,
        }


# =============================================================================
# 管线实现
# =============================================================================

class ContentCleaningPipeline:
    """
    标准化内容清洗管线
    
    按注册顺序执行所有过滤器。每个过滤器独立、可配置、可扩展。
    """
    
    def __init__(self):
        self._filters: List[ContentFilter] = []
        self._quality_gate: Optional[ContentQualityGate] = None
    
    def register(self, filter: ContentFilter) -> "ContentCleaningPipeline":
        """注册过滤器"""
        self._filters.append(filter)
        logger.info(f"Registered content filter: {filter.name}")
        return self
    
    def set_quality_gate(self, gate: ContentQualityGate) -> "ContentCleaningPipeline":
        """设置质量门禁"""
        self._quality_gate = gate
        return self
    
    def process(self, content: str) -> str:
        """执行管线（字符串输入）"""
        for filter in self._filters:
            original_len = len(content)
            content = filter.apply(content)
            if len(content) != original_len:
                logger.debug(
                    f"Filter '{filter.name}': {original_len} -> {len(content)} chars "
                    f"({len(content) - original_len:+d})"
                )
        return content
    
    def process_sections(self, sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """执行管线（章节列表输入）"""
        if not sections:
            return sections
        
        # 1. 应用所有过滤器
        for filter in self._filters:
            sections = filter.apply_to_sections(sections)
        
        # 2. 质量门禁检查
        if self._quality_gate:
            all_content = "\n\n".join(
                s.get("content", "") for s in sections if s.get("content")
            )
            result = self._quality_gate.check(all_content)
            
            if not result.passed:
                logger.warning(
                    f"Quality gate check failed: {result.severity} - {result.details}"
                )
                
                strategy = self._quality_gate.get_retry_strategy(result)
                if strategy["should_retry"] and strategy["retry_action"] == "clean":
                    logger.info("Attempting auto-fix via re-cleaning...")
                    for filter in self._filters:
                        sections = filter.apply_to_sections(sections)
        
        return sections
    
    def get_filter_names(self) -> List[str]:
        """获取所有已注册的过滤器名称"""
        return [f.name for f in self._filters]


# =============================================================================
# 工厂函数
# =============================================================================

def create_default_pipeline() -> ContentCleaningPipeline:
    """
    创建默认内容清洗管线
    
    包含所有标准过滤器，按推荐顺序注册。
    """
    pipeline = ContentCleaningPipeline()
    
    # 顺序很重要：
    # 1. 先清理 prompt 痕迹（避免干扰后续检测）
    pipeline.register(PromptPatternFilter())
    
    # 2. 跨类型去重（标题 vs 段落）
    pipeline.register(CrossTypeDuplicateDetector(threshold=0.75))
    
    # 3. 全局跨章节去重
    pipeline.register(GlobalDuplicateDetector(threshold=0.85, min_length=30))
    
    # 4. 设置质量门禁
    pipeline.set_quality_gate(ContentQualityGate())
    
    return pipeline
