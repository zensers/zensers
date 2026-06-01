"""
分析层模块

包含：
- IntentType/TaskComplexity: 意图类型定义
- WisdomStore: 经验存储
- IntelligentRoutingAdapter: 智能路由适配器

Phase 4: 传统路由已移除，使用智能路由替代。

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/ORCHESTRATOR_REDESIGN.md
"""

# 类型定义从 intent_types.py 导入
from src.core.intent_types import (
    IntentType,
    TaskComplexity,
    AgentCreationStrategy,
    IntentAnalysisResult,
)

# 智能路由适配器
from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter

# 经验存储
from src.core.wisdom import (
    WisdomStore,
    WisdomEntry,
    WisdomAggregation,
)

__all__ = [
    # 意图类型定义
    "IntentType",
    "TaskComplexity",
    "AgentCreationStrategy",
    "IntentAnalysisResult",
    
    # 智能路由
    "IntelligentRoutingAdapter",
    
    # 经验存储
    "WisdomStore",
    "WisdomEntry",
    "WisdomAggregation",
]
