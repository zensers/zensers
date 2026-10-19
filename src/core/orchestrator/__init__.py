"""
Orchestrator 模块

包含：
- ResearchOrchestrator: 研究任务主控调度器
- execution/: 执行层（控制机制 + 协调机制）
- analysis/: 分析层（智能路由 + 经验存储）
- aggregation/: 聚合层（结果聚合 + 知识编译 + 经验记录）
- output/: 输出层（报告生成 + 文档生成 + 存储管理）

Phase 4: 传统路由已移除，使用智能路由替代。
"""

from .research_orchestrator import (
    ResearchOrchestrator,
    ResearchRequirement,
    ResearchResult,
    research,
)
from .smart_clarifier import SmartClarifier, start_smart_clarification, OutputType, UserChoice

# 执行层
from .execution import (
    ExecutionEngine,
    ExecutionConfig,
    ExecutionResult,
    ExecutionStage,
    AgentCategory,
)

# 分析层（Phase 4: 更新为智能路由）
from .analysis import (
    IntentType,
    TaskComplexity,
    AgentCreationStrategy,
    IntentAnalysisResult,
    IntelligentRoutingAdapter,
    WisdomStore,
    WisdomEntry,
    WisdomAggregation,
)

# 聚合层
from .aggregation import (
    ResultAggregator,
    AggregationConfig,
    AggregationResult,
    ConflictResolution,
    KnowledgeCompiler,
    KnowledgePage,
    KnowledgeType,
    WisdomRecorder,
    ExperienceRecord,
)

# 输出层
from .output import (
    ReportGenerator,
    ReportConfig,
    ReportResult,
    ReportFormat,
    DocumentGenerator,
    DocumentConfig,
    DocumentFormat,
    StorageManager,
    StorageConfig,
    ResearchRecord,
)

__all__ = [
    # 主控
    'ResearchOrchestrator',
    'ResearchRequirement',
    'ResearchResult',
    'research',
    
    # 澄清器
    'SmartClarifier',
    'start_smart_clarification',
    'OutputType',
    'UserChoice',
    
    # 执行层
    'ExecutionEngine',
    'ExecutionConfig',
    'ExecutionResult',
    'ExecutionStage',
    'AgentCategory',
    
    # 分析层（Phase 4: 智能路由）
    'IntentType',
    'TaskComplexity',
    'AgentCreationStrategy',
    'IntentAnalysisResult',
    'IntelligentRoutingAdapter',
    'WisdomStore',
    'WisdomEntry',
    'WisdomAggregation',
    
    # 聚合层
    'ResultAggregator',
    'AggregationConfig',
    'AggregationResult',
    'ConflictResolution',
    'KnowledgeCompiler',
    'KnowledgePage',
    'KnowledgeType',
    'WisdomRecorder',
    'ExperienceRecord',
    
    # 输出层
    'ReportGenerator',
    'ReportConfig',
    'ReportResult',
    'ReportFormat',
    'DocumentGenerator',
    'DocumentConfig',
    'DocumentFormat',
    'StorageManager',
    'StorageConfig',
    'ResearchRecord',
]
