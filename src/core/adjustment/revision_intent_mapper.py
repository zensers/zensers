# -*- coding: utf-8 -*-
"""
修订意图映射器

Phase 1.1: 三级映射架构核心组件

职责:
- Level 1 → Level 2: IntentType → RevisionIntentType 映射
- Level 2 → Level 3: RevisionIntentType → Route 决策
- 支持关键词匹配和复杂度修正

架构:
    IntentType (通用意图)
        │ SemanticIntentAnalyzer
        ▼
    RevisionIntentType (修订专用意图)
        │ RevisionIntentMapper
        ▼
    Route (执行路径: lightweight/incremental/hybrid)
"""

__all__ = [
    "RevisionIntentMapper",
    "RouteDecision",
]

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple, List

from ..intent_types import IntentType, TaskComplexity, RevisionIntentType

logger = logging.getLogger(__name__)


@dataclass
class RouteDecision:
    """
    路由决策结果
    
    Attributes:
        route: 执行路径 (lightweight/incremental/hybrid)
        type: 修订类型 (minor/section/full)
        skip_phases: 跳过的阶段列表
        reason: 路由原因说明
    """
    route: str = "incremental"
    type: str = "section"
    skip_phases: List[str] = field(default_factory=list)
    reason: str = "default"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "route": self.route,
            "type": self.type,
            "skip_phases": self.skip_phases,
            "reason": self.reason,
        }


class RevisionIntentMapper:
    """
    修订意图映射器
    
    三级映射架构核心组件：
    - Level 1: IntentType (通用意图: FIX/EVALUATION/RESEARCH/INVESTIGATION)
    - Level 2: RevisionIntentType (修订专用意图: 数据级/文本级/结构级/分析级)
    - Level 3: Route (执行路径: lightweight/incremental/hybrid)
    
    使用方式:
        mapper = RevisionIntentMapper()
        revision_intent, route_decision = mapper.map(
            primary_intent=IntentType.FIX,
            complexity=TaskComplexity.SINGLE,
            user_input="修正错别字"
        )
    """
    
    # Level 1 → Level 2 映射规则
    INTENT_TO_REVISION_MAP: Dict[IntentType, Dict[str, Any]] = {
        IntentType.FIX: {
            "keywords": {
                # 文本级操作
                r"错别字|错字|拼写|措辞|表达": RevisionIntentType.CORRECT_ERROR,
                r"重写|改写|重新写": RevisionIntentType.REWRITE_TEXT,
                r"更详细|更清晰|更清楚|详细说明": RevisionIntentType.IMPROVE_CLARITY,
                # 数据级操作
                r"修正数据|更正数据|修改数据": RevisionIntentType.UPDATE_DATA,
            },
            "default": RevisionIntentType.CORRECT_ERROR,
        },
        IntentType.EVALUATION: {
            "keywords": {
                # 数据级操作
                r"核实|验证|检查|确认|核对": RevisionIntentType.VERIFY_DATA,
                r"更新数据|修改数据|最新数据": RevisionIntentType.UPDATE_DATA,
                # 分析级操作
                r"对比|比较|差异": RevisionIntentType.COMPARE_SECTIONS,
                r"一致性|矛盾|冲突": RevisionIntentType.CHECK_CONSISTENCY,
            },
            "default": RevisionIntentType.VERIFY_DATA,
        },
        IntentType.RESEARCH: {
            "keywords": {
                # 数据级操作
                r"新增|添加|补充|增加": RevisionIntentType.ADD_DATA,
                r"更新|最新|刷新": RevisionIntentType.UPDATE_DATA,
                # 结构级操作
                r"新增章节|添加章节|新章节": RevisionIntentType.ADD_SECTION,
            },
            "default": RevisionIntentType.UPDATE_DATA,
        },
        IntentType.INVESTIGATION: {
            "keywords": {
                # 分析级操作
                r"对比|比较": RevisionIntentType.COMPARE_SECTIONS,
                r"一致性|矛盾": RevisionIntentType.CHECK_CONSISTENCY,
                # 数据级操作
                r"核实|验证": RevisionIntentType.VERIFY_DATA,
            },
            "default": RevisionIntentType.VERIFY_DATA,
        },
    }
    
    # Level 2 → Level 3 路由映射
    REVISION_TO_ROUTE_MAP: Dict[RevisionIntentType, Dict[str, Any]] = {
        # 文本级操作 → lightweight
        RevisionIntentType.CORRECT_ERROR: {
            "route": "lightweight",
            "type": "minor",
            "skip_phases": [],
            "reason": "text_correction",
        },
        RevisionIntentType.REWRITE_TEXT: {
            "route": "lightweight",
            "type": "section",
            "skip_phases": [],
            "reason": "text_rewrite",
        },
        RevisionIntentType.IMPROVE_CLARITY: {
            "route": "lightweight",
            "type": "section",
            "skip_phases": [],
            "reason": "clarity_improvement",
        },
        # 数据级操作 → incremental (部分跳过数据收集)
        RevisionIntentType.VERIFY_DATA: {
            "route": "incremental",
            "type": "section",
            "skip_phases": ["data_collection"],  # 跳过数据收集，仅验证
            "reason": "data_verification",
        },
        RevisionIntentType.UPDATE_DATA: {
            "route": "incremental",
            "type": "section",
            "skip_phases": [],
            "reason": "data_update",
        },
        RevisionIntentType.ADD_DATA: {
            "route": "incremental",
            "type": "section",
            "skip_phases": [],
            "reason": "data_addition",
        },
        # 结构级操作 → incremental
        RevisionIntentType.ADD_SECTION: {
            "route": "incremental",
            "type": "full",
            "skip_phases": [],
            "reason": "section_addition",
        },
        RevisionIntentType.REMOVE_SECTION: {
            "route": "lightweight",
            "type": "section",
            "skip_phases": [],
            "reason": "section_removal",
        },
        # 分析级操作 → incremental
        RevisionIntentType.COMPARE_SECTIONS: {
            "route": "incremental",
            "type": "section",
            "skip_phases": ["data_collection"],
            "reason": "section_comparison",
        },
        RevisionIntentType.CHECK_CONSISTENCY: {
            "route": "incremental",
            "type": "section",
            "skip_phases": ["data_collection"],
            "reason": "consistency_check",
        },
    }
    
    def map(
        self,
        primary_intent: IntentType,
        complexity: TaskComplexity,
        user_input: str,
    ) -> Tuple[RevisionIntentType, RouteDecision]:
        """
        三级映射主入口
        
        Args:
            primary_intent: Level 1 通用意图
            complexity: 任务复杂度
            user_input: 用户输入文本
            
        Returns:
            (RevisionIntentType, RouteDecision): Level 2 意图 + Level 3 路由决策
        """
        # Step 1: Level 1 → Level 2 映射
        revision_intent = self._map_to_revision(primary_intent, user_input)
        logger.debug(
            f"[RevisionIntentMapper] Intent={primary_intent.value} → "
            f"RevisionIntent={revision_intent.value}"
        )
        
        # Step 2: 复杂度修正 (TRIVIAL 强制 lightweight)
        if complexity == TaskComplexity.TRIVIAL:
            logger.debug(
                f"[RevisionIntentMapper] TRIVIAL complexity override → lightweight"
            )
            return revision_intent, RouteDecision(
                route="lightweight",
                type="minor",
                skip_phases=[],
                reason="trivial_complexity_override",
            )
        
        # Step 3: Level 2 → Level 3 映射
        route_config = self.REVISION_TO_ROUTE_MAP.get(
            revision_intent,
            {"route": "incremental", "type": "section", "skip_phases": [], "reason": "default"}
        )
        
        route_decision = RouteDecision(**route_config)
        
        # Step 4: 复杂度调整路由
        if complexity == TaskComplexity.COMPLEX:
            # COMPLEX 任务强制 incremental
            route_decision.route = "incremental"
            route_decision.reason = f"{route_decision.reason}_complex_override"
            logger.debug(
                f"[RevisionIntentMapper] COMPLEX complexity override → incremental"
            )
        
        return revision_intent, route_decision
    
    def _map_to_revision(
        self,
        primary_intent: IntentType,
        user_input: str,
    ) -> RevisionIntentType:
        """
        Level 1 → Level 2 映射
        
        Args:
            primary_intent: Level 1 通用意图
            user_input: 用户输入文本
            
        Returns:
            RevisionIntentType: Level 2 修订专用意图
        """
        config = self.INTENT_TO_REVISION_MAP.get(primary_intent)
        
        if not config:
            logger.warning(
                f"[RevisionIntentMapper] Unknown intent: {primary_intent}, using default"
            )
            return RevisionIntentType.CORRECT_ERROR
        
        # 关键词匹配
        keywords_map = config.get("keywords", {})
        for pattern, revision_type in keywords_map.items():
            try:
                if re.search(pattern, user_input, re.IGNORECASE):
                    logger.debug(
                        f"[RevisionIntentMapper] Pattern '{pattern}' matched → {revision_type.value}"
                    )
                    return revision_type
            except re.error as e:
                logger.warning(f"[RevisionIntentMapper] Invalid regex pattern '{pattern}': {e}")
                continue
        
        # 默认值
        default_revision = config.get("default", RevisionIntentType.CORRECT_ERROR)
        logger.debug(
            f"[RevisionIntentMapper] No pattern matched, using default: {default_revision.value}"
        )
        return default_revision
    
    def get_route_for_revision(
        self,
        revision_intent: RevisionIntentType,
    ) -> RouteDecision:
        """
        直接从 RevisionIntentType 获取路由决策
        
        Args:
            revision_intent: Level 2 修订专用意图
            
        Returns:
            RouteDecision: Level 3 路由决策
        """
        route_config = self.REVISION_TO_ROUTE_MAP.get(
            revision_intent,
            {"route": "incremental", "type": "section", "skip_phases": [], "reason": "default"}
        )
        return RouteDecision(**route_config)
