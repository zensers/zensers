# -*- coding: utf-8 -*-
"""
Learning 模块 - 自我学习机制

Phase 3.7 核心功能: 系统从用户交互中学习，持续改进

模块组成:
- LearningStore: 学习记录存储
- ErrorTracker: 错误追踪
- FeatureRequestStore: 功能请求管理
- LearningManager: 学习晋升机制
"""

from .learning_store import LearningStore, LearningRecord
from .error_tracker import ErrorTracker, ErrorRecord
from .feature_request_store import FeatureRequestStore, FeatureRequest
from .learning_manager import LearningManager

__all__ = [
    # 学习记录
    "LearningStore",
    "LearningRecord",
    
    # 错误追踪
    "ErrorTracker",
    "ErrorRecord",
    
    # 功能请求
    "FeatureRequestStore",
    "FeatureRequest",
    
    # 学习管理
    "LearningManager",
]