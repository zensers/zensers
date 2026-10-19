# -*- coding: utf-8 -*-
"""
用户知识银行模块

让系统在服务用户的过程中自动变强

v1.2 新增：
- KnowledgeManager: 知识管理统一入口
- KnowledgeConfig: 集中配置管理
"""

from .knowledge_bank import UserKnowledgeBank
from .knowledge_manager import KnowledgeManager
from .config import KnowledgeConfig, get_default_config
from .core.core_memory import (
    CoreMemory,
    UserProfile,
    TopEntity,
    CoreNeed,
    LearnedPattern
)

__all__ = [
    # 核心类
    "KnowledgeManager",       # 统一入口（推荐）
    "UserKnowledgeBank",      # 知识银行（底层）
    "CoreMemory",             # 核心记忆（Layer 1）
    
    # 配置
    "KnowledgeConfig",        # 集中配置
    "get_default_config",     # 获取默认配置
    
    # 数据模型
    "UserProfile",
    "TopEntity",
    "CoreNeed",
    "LearnedPattern",
    
    # Retrieval module (lazy import)
    # from .retrieval import VectorStore, SemanticSearch, HybridSearch
]