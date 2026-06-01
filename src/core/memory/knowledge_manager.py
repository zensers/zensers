# -*- coding: utf-8 -*-
"""
知识管理统一入口

提供简洁的 API 来访问所有知识管理功能。

设计理念：
- 委托模式：委托 UserKnowledgeBank，不重新封装
- 向后兼容：保留旧 API，标记为 deprecated
- 自动集成：在主流程中自动调用 Phase 3.6 功能

使用方式：
    from src.core.memory import KnowledgeManager
    
    # 使用默认配置
    manager = KnowledgeManager(user_id="user_001")
    
    # 自定义配置
    from src.core.memory.config import KnowledgeConfig
    config = KnowledgeConfig(max_top_entities=30)
    manager = KnowledgeManager(user_id="user_001", config=config)
    
    # 存入知识（自动触发编译、矛盾检测）
    result = await manager.deposit(research_id="...", content={...})
    
    # 搜索知识
    results = manager.search("特斯拉")
    
    # 导入文件
    result = manager.import_file("report.pdf")
"""

__all__ = ["KnowledgeManager"]

import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from .config import KnowledgeConfig
from .knowledge_bank import UserKnowledgeBank
from .core.core_memory import CoreMemory

if TYPE_CHECKING:
    from .knowledge.compiler import CompiledKnowledge
    from .knowledge.contradiction_detector import Contradiction
    from .knowledge.importer import ImportResult
    from .dream.dream_mode import DreamReport

logger = logging.getLogger(__name__)


class KnowledgeManager:
    """
    知识管理统一入口
    
    整合所有知识管理功能，提供简洁的 API。
    使用委托模式，不重新封装 UserKnowledgeBank。
    
    Attributes:
        user_id: 用户ID
        config: 知识管理配置
        knowledge_bank: 用户知识银行实例
        core_memory: 核心记忆实例
    
    Examples:
        >>> manager = KnowledgeManager("user_001")
        >>> 
        >>> # 存入知识
        >>> result = await manager.deposit("research_001", {...})
        >>> 
        >>> # 搜索
        >>> results = manager.search("新能源汽车")
        >>> 
        >>> # 获取概览
        >>> summary = manager.get_summary()
    """
    
    def __init__(
        self,
        user_id: str,
        config: Optional[KnowledgeConfig] = None,
        db_path: Optional[str] = None
    ):
        """
        初始化知识管理器
        
        Args:
            user_id: 用户ID
            config: 知识管理配置（None 使用默认配置）
            db_path: 数据库路径（None 使用默认路径）
        """
        self.user_id = user_id
        self.config = config or KnowledgeConfig()
        
        # 设置数据库路径
        if db_path is None:
            db_path = self.config.db_path or f"data/knowledge_bank_{user_id}.db"
        
        # 初始化核心组件
        self._knowledge_bank = UserKnowledgeBank(
            user_id=user_id,
            db_path=db_path
        )
        
        # 初始化核心记忆
        storage_path = Path(db_path).parent / "users" / user_id
        self._core_memory = CoreMemory(
            user_id=user_id,
            storage_path=str(storage_path)
        )

        # 健康状态标记
        self._closed = False
        
        logger.info(f"KnowledgeManager initialized for user {user_id}")
    
    # ========== 属性访问 ==========
    
    @property
    def knowledge_bank(self) -> UserKnowledgeBank:
        """访问用户知识银行"""
        return self._knowledge_bank
    
    @property
    def core_memory(self) -> CoreMemory:
        """访问核心记忆"""
        return self._core_memory
    
    # ========== 知识存取 ==========
    
    async def deposit(
        self,
        research_id: str,
        content: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        存入知识（自动触发编译、矛盾检测）
        
        这是主要的知识存入入口，会自动：
        1. 记录研究历史
        2. 知识编译（如果启用）
        3. 矛盾检测（如果启用）
        
        Args:
            research_id: 研究ID
            content: 研究内容，包含：
                - topic: 研究主题
                - content: 研究内容文本
                - entities: 实体列表
                - insights: 洞察列表
                - report_path: 报告路径
        
        Returns:
            存入结果
        """
        if self._closed:
            logger.warning("KnowledgeManager is closed, cannot deposit")
            return {"status": "error", "message": "KnowledgeManager is closed"}

        result = await self._knowledge_bank.deposit_from_research(
            research_id=research_id,
            research_process=content
        )
        
        # 自动调用 Phase 3.6 功能
        if self.config.enable_knowledge_compiler:
            try:
                raw_content = content.get("content", "")
                if isinstance(raw_content, dict):
                    import json
                    raw_content = json.dumps(raw_content, ensure_ascii=False)
                compiled = self._knowledge_bank.compile_research(
                    raw_content=raw_content,
                    source_info={"research_id": research_id}
                )
                self._knowledge_bank.save_compiled_knowledge(compiled)
                result["compiled"] = True
                logger.info(f"Knowledge compiled for research {research_id}")
            except Exception as e:
                logger.warning(f"Knowledge compilation failed: {e}")
                result["compiled"] = False
                result["compile_error"] = str(e)

        # 同步写入实体
        entities_data = content.get("entities", [])
        if entities_data:
            try:
                for entity_data in entities_data[:20]:  # 限制前 20 个实体
                    name = entity_data.get("name", "")
                    if name:
                        self._knowledge_bank.entities.add_entity(
                            entity_type=entity_data.get("entity_type", "generic"),
                            name=name,
                            description=entity_data.get("description", "")[:500],
                        )
                result["entities_written"] = len(entities_data)
                logger.info(f"Written {len(entities_data)} entities for research {research_id}")
            except Exception as e:
                logger.warning(f"Entity writing failed: {e}")
                result["entities_write_error"] = str(e)

        # 更新 CoreMemory（研究主题作为核心需求）
        topic = content.get("topic", "")
        if topic:
            try:
                self._core_memory.add_core_need(topic)
                self._core_memory.save()
                logger.info(f"CoreMemory updated with topic: {topic}")
            except Exception as e:
                logger.warning(f"CoreMemory update failed: {e}")

        if self.config.enable_contradiction_detector:
            try:
                contradictions = self._knowledge_bank.detect_contradictions()
                if contradictions:
                    result["contradictions"] = len(contradictions)
                    logger.info(f"Found {len(contradictions)} contradictions")
                else:
                    result["contradictions"] = 0
            except Exception as e:
                logger.warning(f"Contradiction detection failed: {e}")
                result["contradiction_error"] = str(e)

        # 触发知识晋升
        try:
            self._knowledge_bank.auto_promote_learnings(self._core_memory)
        except Exception as e:
            logger.warning(f"Knowledge promotion failed: {e}")

        return result
    
    def search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        搜索知识（综合搜索）
        
        同时搜索实体、关系、数据点。
        
        Args:
            query: 搜索关键词
            filters: 过滤条件（可选）
            limit: 最大返回数量
        
        Returns:
            {
                "entities": [...],
                "relations": [...],
                "data_points": [...]
            }
        """
        if self._closed:
            logger.warning("KnowledgeManager is closed, cannot search")
            return {"entities": [], "relations": [], "data_points": []}

        limit = filters.get("limit", limit) if filters else limit
        
        return self._knowledge_bank.search_all(query, limit=limit)
    
    async def get_relevant_knowledge(
        self,
        query: str,
        max_items: int = 10
    ) -> Dict[str, Any]:
        """
        获取与查询相关的已有知识
        
        Args:
            query: 查询字符串
            max_items: 最大返回数量
        
        Returns:
            相关知识
        """
        return await self._knowledge_bank.get_relevant_knowledge(
            query=query,
            max_items=max_items
        )
    
    async def get_summary(self) -> Dict[str, Any]:
        """
        获取知识概览
        
        Returns:
            知识统计信息
        """
        return await self._knowledge_bank.get_knowledge_summary()
    
    # ========== 知识导入 ==========
    
    def import_file(
        self,
        file_path: str,
        auto_extract: bool = True,
        skip_if_imported: bool = True
    ) -> "ImportResult":
        """
        导入文件
        
        Args:
            file_path: 文件路径
            auto_extract: 是否自动提取知识
            skip_if_imported: 是否跳过已导入的文件
        
        Returns:
            导入结果
        """
        return self._knowledge_bank.import_file(
            file_path=file_path,
            auto_extract=auto_extract,
            skip_if_imported=skip_if_imported
        )
    
    def import_directory(
        self,
        directory_path: str,
        recursive: bool = True,
        max_workers: int = 4
    ) -> List["ImportResult"]:
        """
        批量导入目录
        
        Args:
            directory_path: 目录路径
            recursive: 是否递归子目录
            max_workers: 最大并发数
        
        Returns:
            导入结果列表
        """
        return self._knowledge_bank.import_directory(
            directory_path=directory_path,
            recursive=recursive,
            max_workers=max_workers
        )

    def import_url(
        self,
        url: str,
        auto_extract: bool = True,
        timeout: int = 30,
        max_size: int = 10485760,
        retries: int = 3,
        *,
        store_to_bank: bool = True,
    ) -> "ImportResult":
        """
        导入 URL 内容
        
        Args:
            url: 网页 URL
            auto_extract: 是否自动提取知识
            timeout: 超时时间（秒）
            max_size: 最大响应大小（字节）
            retries: 重试次数
            store_to_bank: 是否将编译结果写入 SQLite（仅关键字参数）
        
        Returns:
            ImportResult: 导入结果
        """
        return self._knowledge_bank.import_url(
            url=url,
            auto_extract=auto_extract,
            timeout=timeout,
            max_size=max_size,
            retries=retries,
            store_to_bank=store_to_bank,
        )
    
    # ========== 学习管理 ==========
    
    def record_learning(
        self,
        category: str,
        content: str,
        session_id: Optional[str] = None,
        priority: str = "medium"
    ) -> Dict[str, Any]:
        """
        记录学习
        
        Args:
            category: 学习类别 (correction/error/pattern/preference)
            content: 学习内容
            session_id: 会话ID
            priority: 优先级
        
        Returns:
            学习记录
        """
        return self._knowledge_bank.record_learning(
            category=category,
            content=content,
            session_id=session_id,
            priority=priority
        )
    
    def promote_learnings(self) -> List[Dict[str, Any]]:
        """
        自动晋升学习记录到 CoreMemory
        
        Returns:
            晋升的学习记录列表
        """
        return self._knowledge_bank.auto_promote_learnings(self._core_memory)
    
    # ========== 知识编译 ==========
    
    def compile(
        self,
        content: str,
        source_info: Optional[Dict[str, Any]] = None
    ) -> "CompiledKnowledge":
        """
        编译研究内容为知识页
        
        Args:
            content: 原始研究内容
            source_info: 来源信息
        
        Returns:
            编译结果
        """
        return self._knowledge_bank.compile_research(content, source_info)
    
    def detect_contradictions(self) -> List["Contradiction"]:
        """
        检测知识矛盾
        
        Returns:
            矛盾列表
        """
        return self._knowledge_bank.detect_contradictions()
    
    # ========== 做梦模式 ==========
    
    async def run_dream_mode(self, trigger: str = "manual") -> Dict[str, Any]:
        """
        运行做梦模式（后台记忆整合）
        
        Args:
            trigger: 触发类型 (manual/scheduled/session_end)
        
        Returns:
            Dream Mode 执行报告
        """
        from .dream import DreamMode
        
        dream_mode = DreamMode(
            core_memory=self._core_memory,
            knowledge_bank=self._knowledge_bank
        )
        
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: dream_mode.run(trigger_reason=trigger)
        )
    
    # ========== 导出 ==========
    
    def export(self, format: str = "json") -> Dict[str, Any]:
        """
        导出知识库
        
        Args:
            format: 导出格式 (json/dict)
        
        Returns:
            知识库数据
        """
        return self._knowledge_bank.export_to_dict()
    
    def export_to_file(self, file_path: str) -> None:
        """
        导出知识库到文件
        
        Args:
            file_path: 文件路径
        """
        self._knowledge_bank.export_to_json(file_path)
    
    # ========== 向后兼容 ==========
    
    def __getattr__(self, name: str) -> Any:
        """
        委托到 UserKnowledgeBank
        
        允许直接访问 UserKnowledgeBank 的所有方法和属性。
        """
        return getattr(self._knowledge_bank, name)
    
    # ========== 上下文管理 ==========
    
    def __enter__(self) -> "KnowledgeManager":
        """上下文管理器入口"""
        return self
    
    def __exit__(self, *args) -> None:
        """上下文管理器出口"""
        self.close()
    
    def close(self) -> None:
        """关闭所有资源"""
        self._closed = True
        self._knowledge_bank.close()
        logger.info(f"KnowledgeManager closed for user {self.user_id}")
