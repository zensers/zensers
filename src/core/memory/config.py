# -*- coding: utf-8 -*-
"""
知识管理配置模块

集中管理所有知识管理相关的配置参数，包括：
- Layer 1 限制
- 晋升阈值
- Dream Mode 配置
- 数据库配置
- 功能开关

设计理念：
- 单一配置源
- 类型安全
- 可验证
- 易于扩展
"""

__all__ = ["KnowledgeConfig", "get_default_config"]

from dataclasses import dataclass, field
from typing import Optional, List
import os


@dataclass
class KnowledgeConfig:
    """
    知识管理配置
    
    集中管理所有知识管理相关的配置参数。
    
    使用方式：
        # 使用默认配置
        config = KnowledgeConfig()
        
        # 自定义配置
        config = KnowledgeConfig(
            max_top_entities=30,
            enable_knowledge_compiler=False
        )
        
        # 从环境变量加载
        config = KnowledgeConfig.from_env()
    
    Attributes:
        # Layer 1 限制
        max_top_entities: 高频实体最大数量
        max_core_needs: 核心需求最大数量
        max_learned_patterns: 学习结晶最大数量
        layer1_size_limit: Layer 1 大小限制（字节）
        
        # 晋升阈值
        entity_promotion_threshold: 实体晋升阈值（mention_count）
        need_promotion_threshold: 需求晋升阈值（frequency）
        pattern_promotion_threshold: 模式晋升阈值（recurrence_count）
        learning_promotion_threshold: 学习晋升阈值（recurrence_count）
        min_sessions_for_promotion: 晋升最小会话数
        
        # Dream Mode
        dream_interval_hours: Dream Mode 触发间隔（小时）
        layer1_threshold: Layer 1 触发 Dream Mode 的阈值（字节）
        
        # 数据库
        db_path: 数据库路径（None 表示使用默认路径）
        enable_wal: 是否启用 WAL 模式
        connection_timeout: 连接超时（秒）
        
        # 功能开关
        enable_knowledge_compiler: 是否启用知识编译
        enable_contradiction_detector: 是否启用矛盾检测
        enable_dream_mode: 是否启用 Dream Mode
        enable_metrics: 是否启用性能指标收集
        log_level: 日志级别
    """
    
    # ==================== Layer 1 限制 ====================
    
    max_top_entities: int = 20
    """高频实体最大数量"""
    
    max_core_needs: int = 10
    """核心需求最大数量"""
    
    max_learned_patterns: int = 15
    """学习结晶最大数量"""
    
    layer1_size_limit: int = 10 * 1024  # 10KB
    """Layer 1 大小限制（字节）"""
    
    # ==================== 晋升阈值 ====================
    
    entity_promotion_threshold: int = 5
    """实体晋升阈值（mention_count >= 此值时晋升到 Layer 1）"""
    
    need_promotion_threshold: int = 3
    """需求晋升阈值（frequency >= 此值时晋升到 Layer 1）"""
    
    pattern_promotion_threshold: int = 3
    """模式晋升阈值（recurrence_count >= 此值时晋升到 Layer 1）"""
    
    learning_promotion_threshold: int = 3
    """学习晋升阈值（recurrence_count >= 此值时晋升到 CoreMemory）"""
    
    min_sessions_for_promotion: int = 2
    """晋升最小会话数（跨此数量会话才可晋升）"""
    
    # ==================== Dream Mode ====================
    
    dream_interval_hours: int = 24
    """Dream Mode 定时触发间隔（小时）"""
    
    layer1_threshold: int = 8 * 1024  # 8KB
    """Layer 1 触发 Dream Mode 的阈值（字节）"""
    
    # ==================== 数据库 ====================
    
    db_path: Optional[str] = None
    """数据库路径（None 表示使用默认路径 data/knowledge_bank_{user_id}.db）"""
    
    enable_wal: bool = True
    """是否启用 WAL 模式（提升并发性能）"""
    
    connection_timeout: float = 5.0
    """数据库连接超时（秒）"""
    
    # ==================== 功能开关 ====================
    
    enable_knowledge_compiler: bool = True
    """是否启用知识编译器（自动编译研究内容为知识页）"""
    
    enable_contradiction_detector: bool = True
    """是否启用矛盾检测器（自动检测知识矛盾）"""
    
    enable_dream_mode: bool = True
    """是否启用 Dream Mode（后台记忆整合）"""
    
    enable_metrics: bool = False
    """是否启用性能指标收集"""
    
    log_level: str = "INFO"
    """日志级别（DEBUG, INFO, WARNING, ERROR）"""
    
    # ==================== 高级配置 ====================
    
    cache_size: int = 1000
    """缓存大小（用于 LRU 缓存）"""
    
    search_limit: int = 100
    """默认搜索结果限制"""
    
    import_max_workers: int = 4
    """知识导入最大并发数"""
    
    import_max_file_size: int = 50 * 1024 * 1024  # 50MB
    """导入文件最大大小（字节）"""
    
    def validate(self) -> bool:
        """
        验证配置是否有效
        
        Returns:
            配置是否有效
            
        Raises:
            AssertionError: 配置无效时抛出
        """
        # Layer 1 限制验证
        assert self.max_top_entities > 0, "max_top_entities must be positive"
        assert self.max_core_needs > 0, "max_core_needs must be positive"
        assert self.max_learned_patterns > 0, "max_learned_patterns must be positive"
        assert self.layer1_size_limit > 0, "layer1_size_limit must be positive"
        
        # 晋升阈值验证
        assert self.entity_promotion_threshold > 0, "entity_promotion_threshold must be positive"
        assert self.need_promotion_threshold > 0, "need_promotion_threshold must be positive"
        assert self.pattern_promotion_threshold > 0, "pattern_promotion_threshold must be positive"
        assert self.learning_promotion_threshold > 0, "learning_promotion_threshold must be positive"
        assert self.min_sessions_for_promotion > 0, "min_sessions_for_promotion must be positive"
        
        # Dream Mode 验证
        assert self.dream_interval_hours > 0, "dream_interval_hours must be positive"
        assert self.layer1_threshold > 0, "layer1_threshold must be positive"
        
        # 数据库验证
        assert self.connection_timeout > 0, "connection_timeout must be positive"
        
        # 日志级别验证
        valid_log_levels = ("DEBUG", "INFO", "WARNING", "ERROR")
        assert self.log_level.upper() in valid_log_levels, \
            f"log_level must be one of {valid_log_levels}"
        
        # 高级配置验证
        assert self.cache_size > 0, "cache_size must be positive"
        assert self.search_limit > 0, "search_limit must be positive"
        assert self.import_max_workers > 0, "import_max_workers must be positive"
        assert self.import_max_file_size > 0, "import_max_file_size must be positive"
        
        return True
    
    @classmethod
    def from_env(cls) -> "KnowledgeConfig":
        """
        从环境变量加载配置
        
        环境变量命名规则：
        - KNOWLEDGE_MAX_TOP_ENTITIES
        - KNOWLEDGE_LOG_LEVEL
        - 等等
        
        Returns:
            KnowledgeConfig 实例
        """
        def get_env_int(key: str, default: int) -> int:
            value = os.getenv(key)
            return int(value) if value else default
        
        def get_env_float(key: str, default: float) -> float:
            value = os.getenv(key)
            return float(value) if value else default
        
        def get_env_bool(key: str, default: bool) -> bool:
            value = os.getenv(key)
            if value is None:
                return default
            return value.lower() in ("true", "1", "yes")
        
        def get_env_str(key: str, default: Optional[str] = None) -> Optional[str]:
            return os.getenv(key, default)
        
        return cls(
            # Layer 1 限制
            max_top_entities=get_env_int("KNOWLEDGE_MAX_TOP_ENTITIES", 20),
            max_core_needs=get_env_int("KNOWLEDGE_MAX_CORE_NEEDS", 10),
            max_learned_patterns=get_env_int("KNOWLEDGE_MAX_LEARNED_PATTERNS", 15),
            layer1_size_limit=get_env_int("KNOWLEDGE_LAYER1_SIZE_LIMIT", 10 * 1024),
            
            # 晋升阈值
            entity_promotion_threshold=get_env_int("KNOWLEDGE_ENTITY_PROMOTION_THRESHOLD", 5),
            need_promotion_threshold=get_env_int("KNOWLEDGE_NEED_PROMOTION_THRESHOLD", 3),
            pattern_promotion_threshold=get_env_int("KNOWLEDGE_PATTERN_PROMOTION_THRESHOLD", 3),
            learning_promotion_threshold=get_env_int("KNOWLEDGE_LEARNING_PROMOTION_THRESHOLD", 3),
            min_sessions_for_promotion=get_env_int("KNOWLEDGE_MIN_SESSIONS_FOR_PROMOTION", 2),
            
            # Dream Mode
            dream_interval_hours=get_env_int("KNOWLEDGE_DREAM_INTERVAL_HOURS", 24),
            layer1_threshold=get_env_int("KNOWLEDGE_LAYER1_THRESHOLD", 8 * 1024),
            
            # 数据库
            db_path=get_env_str("KNOWLEDGE_DB_PATH", None),
            enable_wal=get_env_bool("KNOWLEDGE_ENABLE_WAL", True),
            connection_timeout=get_env_float("KNOWLEDGE_CONNECTION_TIMEOUT", 5.0),
            
            # 功能开关
            enable_knowledge_compiler=get_env_bool("KNOWLEDGE_ENABLE_COMPILER", True),
            enable_contradiction_detector=get_env_bool("KNOWLEDGE_ENABLE_CONTRADICTION_DETECTOR", True),
            enable_dream_mode=get_env_bool("KNOWLEDGE_ENABLE_DREAM_MODE", True),
            enable_metrics=get_env_bool("KNOWLEDGE_ENABLE_METRICS", False),
            log_level=get_env_str("KNOWLEDGE_LOG_LEVEL", "INFO") or "INFO",
        )
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            # Layer 1 限制
            "max_top_entities": self.max_top_entities,
            "max_core_needs": self.max_core_needs,
            "max_learned_patterns": self.max_learned_patterns,
            "layer1_size_limit": self.layer1_size_limit,
            
            # 晋升阈值
            "entity_promotion_threshold": self.entity_promotion_threshold,
            "need_promotion_threshold": self.need_promotion_threshold,
            "pattern_promotion_threshold": self.pattern_promotion_threshold,
            "learning_promotion_threshold": self.learning_promotion_threshold,
            "min_sessions_for_promotion": self.min_sessions_for_promotion,
            
            # Dream Mode
            "dream_interval_hours": self.dream_interval_hours,
            "layer1_threshold": self.layer1_threshold,
            
            # 数据库
            "db_path": self.db_path,
            "enable_wal": self.enable_wal,
            "connection_timeout": self.connection_timeout,
            
            # 功能开关
            "enable_knowledge_compiler": self.enable_knowledge_compiler,
            "enable_contradiction_detector": self.enable_contradiction_detector,
            "enable_dream_mode": self.enable_dream_mode,
            "enable_metrics": self.enable_metrics,
            "log_level": self.log_level,
            
            # 高级配置
            "cache_size": self.cache_size,
            "search_limit": self.search_limit,
            "import_max_workers": self.import_max_workers,
            "import_max_file_size": self.import_max_file_size,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeConfig":
        """从字典创建配置"""
        return cls(**{
            k: v for k, v in data.items()
            if k in cls.__dataclass_fields__
        })


def get_default_config() -> KnowledgeConfig:
    """
    获取默认配置
    
    Returns:
        默认的 KnowledgeConfig 实例
    """
    return KnowledgeConfig()
