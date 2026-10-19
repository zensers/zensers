# -*- coding: utf-8 -*-
"""
任务分解模块

提供专业的任务分解策略，遵循研究方法论：
- 数据收集 → 数据验证 → 深度分析 → 综合整合 → 报告生成
"""

from .strategies import (
    # 核心
    TaskDecompositionStrategy,
    DecompositionPlan,
    AgentSpec,
    ResearchPhase,
    
    # 具体策略
    IndustryResearchStrategy,
    CompanyResearchStrategy,
    CompetitorAnalysisStrategy,
    FixTaskStrategy,
    EvaluationTaskStrategy,
    
    # 注册
    STRATEGY_REGISTRY,
    get_strategy,
    register_strategy,
)

__all__ = [
    "TaskDecompositionStrategy",
    "DecompositionPlan",
    "AgentSpec",
    "ResearchPhase",
    "IndustryResearchStrategy",
    "CompanyResearchStrategy",
    "CompetitorAnalysisStrategy",
    "FixTaskStrategy",
    "EvaluationTaskStrategy",
    "STRATEGY_REGISTRY",
    "get_strategy",
    "register_strategy",
]
