# -*- coding: utf-8 -*-
"""
修订类型推断器

Phase 3.2: 解决 U10 revision_type 硬编码问题

职责:
- 根据用户输入动态推断 revision_type
- 支持多种推断策略
- 结合 LLM 判断和规则匹配
- 提供置信度评估

revision_type 类型:
- "minor": 小修改 (错别字、措辞调整)
- "section": 章节修订 (数据更新、内容重写)
- "full": 全量修订 (结构重组、新增章节)
"""

__all__ = [
    "RevisionTypeInferrer",
    "RevisionTypeInferenceResult",
]

import re
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RevisionTypeInferenceResult:
    """
    修订类型推断结果
    
    Attributes:
        revision_type: 推断的修订类型 (minor/section/full)
        confidence: 推断置信度 (0-1)
        reason: 推断原因
        matched_rules: 匹配的规则列表
        llm_override: 是否被 LLM 判断覆盖
    """
    revision_type: str = "section"
    confidence: float = 0.5
    reason: str = "default"
    matched_rules: List[str] = field(default_factory=list)
    llm_override: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "revision_type": self.revision_type,
            "confidence": self.confidence,
            "reason": self.reason,
            "matched_rules": self.matched_rules,
            "llm_override": self.llm_override,
        }


class RevisionTypeInferrer:
    """
    修订类型推断器
    
    根据用户输入动态推断 revision_type，替代硬编码默认值。
    
    推断策略:
    1. 规则匹配 (关键词、模式)
    2. LLM 判断 (可选)
    3. 置信度评估
    
    使用方式:
        inferrer = RevisionTypeInferrer()
        result = inferrer.infer(
            user_input="修正错别字",
            aspects=["市场规模"],
            llm_suggestion="minor"  # 可选
        )
        # 返回: RevisionTypeInferenceResult(revision_type="minor", confidence=0.9)
    """
    
    # 规则定义
    RULES = {
        "minor": {
            "keywords": [
                # 错别字/措辞
                r"错别字", r"错字", r"拼写错误", r"typo",
                r"措辞", r"表达", r"用词", r"语法",
                r"格式", r"标点", r"符号",
                # 小修改
                r"小修改", r"微调", r"调整一下",
                r"修正.{0,5}错误", r"修改.{0,5}错",
            ],
            "patterns": [
                r"^.{1,10}错.{1,5}$",  # 短文本 + 错
            ],
            "confidence": 0.9,
        },
        "section": {
            "keywords": [
                # 数据更新
                r"更新数据", r"修改数据", r"最新数据",
                r"补充数据", r"核实数据",
                # 内容修订
                r"重写", r"改写", r"重新写",
                r"详细", r"更详细", r"详细说明",
                r"修改.{1,10}章节", r"修订.{1,10}部分",
                # 分析调整
                r"分析", r"研究", r"评估",
            ],
            "patterns": [
                r".{2,10}(数据|内容|分析).{2,10}(更新|修改|调整)",
            ],
            "confidence": 0.85,
        },
        "full": {
            "keywords": [
                # 结构调整
                r"新增章节", r"添加章节", r"新章节",
                r"删除章节", r"移除章节",
                r"结构调整", r"重组",
                # 大范围修改
                r"全面修订", r"整体修改", r"全部重写",
                r"重新分析", r"重新研究",
                # 多章节
                r"所有章节", r"全部章节", r"整个报告",
            ],
            "patterns": [
                r"(新增|添加|删除|移除).{1,10}章节",
                r".{2,10}(全面|整体|全部).{2,10}(修订|修改|重写)",
            ],
            "confidence": 0.9,
        },
    }
    
    # 章节数量阈值 (用于判断 full)
    MULTI_SECTION_THRESHOLD = 3
    
    def __init__(
        self,
        use_llm: bool = False,
        llm_weight: float = 0.6,
    ):
        """
        初始化修订类型推断器
        
        Args:
            use_llm: 是否使用 LLM 判断
            llm_weight: LLM 判断权重 (0-1)
        """
        self.use_llm = use_llm
        self.llm_weight = llm_weight
        
        logger.info(
            f"[RevisionTypeInferrer] Initialized with use_llm={use_llm}, "
            f"llm_weight={llm_weight}"
        )
    
    def infer(
        self,
        user_input: str,
        aspects: Optional[List[str]] = None,
        llm_suggestion: Optional[str] = None,
    ) -> RevisionTypeInferenceResult:
        """
        推断修订类型
        
        Args:
            user_input: 用户输入文本
            aspects: 涉及的章节列表 (可选)
            llm_suggestion: LLM 建议的修订类型 (可选)
            
        Returns:
            RevisionTypeInferenceResult: 推断结果
        """
        if not user_input:
            return RevisionTypeInferenceResult(
                revision_type="section",
                confidence=0.5,
                reason="empty_input",
            )
        
        # Step 1: 规则匹配
        rule_result = self._match_rules(user_input)
        
        # Step 2: 章节数量判断
        aspect_result = self._check_aspects(aspects)
        
        # Step 3: 合并规则结果
        combined_result = self._combine_results(rule_result, aspect_result)
        
        # Step 4: LLM 判断 (可选)
        if llm_suggestion and self.use_llm:
            combined_result = self._apply_llm_suggestion(
                combined_result, llm_suggestion
            )
        
        logger.info(
            f"[RevisionTypeInferrer] Inferred: {combined_result.revision_type} "
            f"(confidence={combined_result.confidence:.2f}, reason={combined_result.reason})"
        )
        
        return combined_result
    
    def _match_rules(self, text: str) -> RevisionTypeInferenceResult:
        """规则匹配"""
        matched_rules = []
        best_type = "section"
        best_confidence = 0.5
        
        for rev_type, rules in self.RULES.items():
            # 关键词匹配
            for keyword in rules.get("keywords", []):
                if re.search(keyword, text, re.IGNORECASE):
                    matched_rules.append(f"keyword:{keyword}")
                    if rules.get("confidence", 0.5) > best_confidence:
                        best_type = rev_type
                        best_confidence = rules.get("confidence", 0.5)
            
            # 模式匹配
            for pattern in rules.get("patterns", []):
                if re.search(pattern, text, re.IGNORECASE):
                    matched_rules.append(f"pattern:{pattern}")
                    if rules.get("confidence", 0.5) > best_confidence:
                        best_type = rev_type
                        best_confidence = rules.get("confidence", 0.5)
        
        return RevisionTypeInferenceResult(
            revision_type=best_type,
            confidence=best_confidence,
            reason="rule_match" if matched_rules else "no_match",
            matched_rules=matched_rules,
        )
    
    def _check_aspects(self, aspects: Optional[List[str]]) -> RevisionTypeInferenceResult:
        """检查章节数量"""
        if not aspects:
            return RevisionTypeInferenceResult(
                revision_type="section",
                confidence=0.5,
                reason="no_aspects",
            )
        
        aspect_count = len(aspects)
        
        # 多章节 → full
        if aspect_count >= self.MULTI_SECTION_THRESHOLD:
            return RevisionTypeInferenceResult(
                revision_type="full",
                confidence=0.8,
                reason=f"multi_sections_{aspect_count}",
                matched_rules=[f"aspect_count:{aspect_count}"],
            )
        
        # 单章节 → section
        return RevisionTypeInferenceResult(
            revision_type="section",
            confidence=0.7,
            reason=f"single_section_{aspect_count}",
            matched_rules=[f"aspect_count:{aspect_count}"],
        )
    
    def _combine_results(
        self,
        rule_result: RevisionTypeInferenceResult,
        aspect_result: RevisionTypeInferenceResult,
    ) -> RevisionTypeInferenceResult:
        """合并规则结果"""
        # 优先级: full > minor > section
        type_priority = {"full": 3, "minor": 2, "section": 1}
        
        # 选择优先级更高的类型
        if type_priority.get(rule_result.revision_type, 0) >= type_priority.get(aspect_result.revision_type, 0):
            primary = rule_result
            secondary = aspect_result
        else:
            primary = aspect_result
            secondary = rule_result
        
        # 合并置信度
        combined_confidence = max(primary.confidence, secondary.confidence * 0.8)
        
        # 合并匹配规则
        matched_rules = list(set(primary.matched_rules + secondary.matched_rules))
        
        return RevisionTypeInferenceResult(
            revision_type=primary.revision_type,
            confidence=combined_confidence,
            reason=f"combined_{primary.reason}",
            matched_rules=matched_rules,
        )
    
    def _apply_llm_suggestion(
        self,
        current_result: RevisionTypeInferenceResult,
        llm_suggestion: str,
    ) -> RevisionTypeInferenceResult:
        """应用 LLM 建议"""
        if llm_suggestion not in ["minor", "section", "full"]:
            return current_result
        
        # 如果 LLM 建议与当前结果不同
        if llm_suggestion != current_result.revision_type:
            # 根据权重调整
            if current_result.confidence < self.llm_weight:
                # 规则置信度低，采用 LLM 建议
                return RevisionTypeInferenceResult(
                    revision_type=llm_suggestion,
                    confidence=self.llm_weight,
                    reason="llm_override",
                    matched_rules=current_result.matched_rules,
                    llm_override=True,
                )
            else:
                # 规则置信度高，保持原结果但降低置信度
                return RevisionTypeInferenceResult(
                    revision_type=current_result.revision_type,
                    confidence=current_result.confidence * 0.9,
                    reason=f"{current_result.reason}_llm_disagreed",
                    matched_rules=current_result.matched_rules,
                    llm_override=False,
                )
        
        return current_result
    
    def get_revision_type_description(self, revision_type: str) -> str:
        """获取修订类型描述"""
        descriptions = {
            "minor": "小修改 (错别字、措辞调整)",
            "section": "章节修订 (数据更新、内容重写)",
            "full": "全量修订 (结构重组、新增章节)",
        }
        return descriptions.get(revision_type, "未知类型")
