# -*- coding: utf-8 -*-
"""
Dream Mode - 做梦模式模块

实现研究资料的异步知识提取：
- 不阻塞主任务
- 主任务优先
- 自动学习新实体
- 渐进式增强

核心组件：
- DreamMode: CoreMemory 整合服务
- DreamModeScheduler: 做梦模式调度器
- RawResearchDataStore: 研究资料暂存区
- KnowledgeExtractionPhase: 知识提取阶段
- OrchestratorWithDreamMode: Orchestrator 集成包装器

使用方式：
```python
# 快速创建所有组件
from src.core.memory.dream import create_dream_mode_components

components = create_dream_mode_components(user_id="user_001")
dream_scheduler = components["dream_scheduler"]

# 或者手动创建
from src.core.memory.dream import (
    DreamModeScheduler,
    RawResearchDataStore,
    OrchestratorWithDreamMode
)

# 集成到 Orchestrator
orchestrator = OrchestratorWithDreamMode(
    orchestrator=base_orchestrator,
    dream_scheduler=dream_scheduler,
    knowledge_bank=knowledge_bank
)
```
"""

from .dream_mode import DreamMode, SessionSignal, DreamReport
from .dream_scheduler import DreamModeScheduler, DreamModeState, DreamModeConfig
from .raw_data_store import RawResearchDataStore, RawResearchData, ExtractionStatus
from .knowledge_extraction_phase import KnowledgeExtractionPhase, ExtractionResult
from .integration import OrchestratorWithDreamMode, create_dream_mode_components

__all__ = [
    # CoreMemory 整合
    "DreamMode",
    "SessionSignal",
    "DreamReport",
    
    # 做梦模式调度
    "DreamModeScheduler",
    "DreamModeState",
    "DreamModeConfig",
    
    # 研究资料暂存
    "RawResearchDataStore",
    "RawResearchData",
    "ExtractionStatus",
    
    # 知识提取阶段
    "KnowledgeExtractionPhase",
    "ExtractionResult",
    
    # Orchestrator 集成
    "OrchestratorWithDreamMode",
    "create_dream_mode_components"
]