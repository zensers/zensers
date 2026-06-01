# -*- coding: utf-8 -*-
"""
用户知识银行

核心理念：
- 每次研究自动存入知识
- 下次研究自动复用知识
- 用户越用越强

Phase 3.6 新增:
- 知识编译器 (KnowledgeCompiler)
- 矛盾检测器 (ContradictionDetector)
- 知识导入器 (KnowledgeImporter)
- 快速进化器 (RapidEvolver)

Phase 3.7 新增:
- 学习记录存储 (LearningStore)
- 错误追踪器 (ErrorTracker)
- 功能请求存储 (FeatureRequestStore)
- 学习管理器 (LearningManager)

Phase 10 重构:
- 使用 ConnectionManager 统一管理连接
- 使用 SchemaRegistry 统一管理 Schema
- 所有 Store 继承 SQLiteStore 基类
"""

import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any, List, Union, TYPE_CHECKING
from datetime import datetime
import logging

if TYPE_CHECKING:
    from src.core.storage.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)


class UserKnowledgeBank:
    """
    用户知识银行
    
    核心理念：
    - 每次研究自动存入知识
    - 下次研究自动复用知识
    - 用户越用越强
    
    Phase 10 重构：
    - 使用 ConnectionManager 统一管理连接
    - Schema 由 SchemaRegistry 统一管理
    """
    
    def __init__(
        self,
        user_id: str,
        db_path: Optional[Union[str, Path]] = None,
        *,
        connection_manager: Optional['ConnectionManager'] = None,
        connection_name: str = "knowledge_bank"
    ):
        """
        初始化用户知识银行
        
        Args:
            user_id: 用户ID
            db_path: 数据库路径，默认为 data/knowledge_bank_{user_id}.db
            connection_manager: 连接管理器（推荐）
            connection_name: 连接名称
        """
        self.user_id = user_id
        self._connection_name = connection_name
        
        # 设置数据库路径
        if db_path is None:
            db_path = f"data/knowledge_bank_{user_id}.db"
        
        self.db_path = Path(db_path)
        
        # 确定连接模式
        if connection_manager is not None:
            # 模式 1：ConnectionManager 注入（推荐）
            self._connection_manager = connection_manager
            self._owns_connection = False
            self.db = connection_manager.get_connection(connection_name, shared=True)
        else:
            # 模式 2：自管理连接（兼容模式）
            self._connection_manager = None
            self._owns_connection = True
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(str(self.db_path))
        
        # 设置 row_factory
        self.db.row_factory = sqlite3.Row
        
        # 初始化 Schema（使用 SchemaRegistry）
        self._init_schema()
        
        # 初始化子存储
        try:
            from .stores import EntityStore, RelationStore, DataPointStore, InsightStore
            self.entities = EntityStore(db=self.db)
            self.relations = RelationStore(db=self.db)
            self.data_points = DataPointStore(db=self.db)
            self.insights = InsightStore(db=self.db)
        except Exception as e:
            self.close()
            logger.error(f"Failed to initialize stores: {e}")
            raise
        
        # 初始化时间知识和来源追溯（v2.0 新增）
        # 使用 try-except 确保资源正确释放
        self.temporal = None
        self.provenance = None
        try:
            from .knowledge import TemporalKnowledge, ProvenanceStore
            temporal_db_path = str(self.db_path).replace('.db', '_temporal.db')
            provenance_db_path = str(self.db_path).replace('.db', '_provenance.db')
            self.temporal = TemporalKnowledge(temporal_db_path, user_id)
            self.provenance = ProvenanceStore(provenance_db_path, user_id)
        except Exception as e:
            self.close()
            logger.error(f"Failed to initialize knowledge modules: {e}")
            raise
        
        # Phase 3.6: 初始化知识编译器
        self._compiler = None
        knowledge_root = self.db_path.parent / "knowledge"
        self._knowledge_root = knowledge_root
        
        # Phase 3.6: 初始化矛盾检测器
        self._contradiction_detector = None
        contradiction_db_path = str(self.db_path).replace('.db', '_contradictions.db')
        self._contradiction_db_path = contradiction_db_path
        
        # Phase 3.6: 初始化知识导入器
        self._importer = None
        
        # Phase 3.6: 初始化快速进化器
        self._rapid_evolver = None
        
        # Phase 3.7: 初始化自我学习模块
        self._learning_store = None
        self._error_tracker = None
        self._feature_request_store = None
        self._learning_manager = None
        learning_db_path = str(self.db_path).replace('.db', '_learning.db')
        self._learning_db_path = learning_db_path
        
        logger.info(f"用户知识银行初始化完成: user_id={user_id}, db_path={db_path}")
    
    def _init_schema(self):
        """初始化数据库 Schema（使用 SchemaRegistry）"""
        from src.core.storage.schemas import register_all_schemas
        from src.core.storage.schema_registry import SchemaRegistry
        
        # 注册所有 Schema
        register_all_schemas()
        
        # 创建所有表
        SchemaRegistry.create_all(self.db)
    
    async def deposit_from_research(
        self,
        research_id: str,
        research_process: Dict
    ) -> Dict:
        """
        从研究过程中自动存入知识
        
        设计理念：
        - 不阻塞主任务：立即返回，知识提取在"做梦模式"中异步执行
        - 主任务优先：用户发起新需求时暂停知识提取
        
        注意：
        - 此方法仅记录研究完成事件
        - 实际的知识提取由 DreamModeScheduler 异步执行
        - 如果需要立即提取，请使用 DreamModeScheduler.run_now()
        
        Args:
            research_id: 研究ID
            research_process: 研究过程数据，包含：
                - content: 研究内容文本
                - topic: 研究主题
                - source_info: 来源信息
                - domain: 研究领域
        
        Returns:
            存储状态（立即返回，不等待提取完成）
        """
        # 记录研究历史
        import json
        from datetime import datetime
        
        try:
            # 存储研究历史
            self.db.execute("""
                INSERT OR REPLACE INTO research_history 
                (research_id, title, topic, entities, insights, framework, created_at, report_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                research_id,
                research_process.get("title", ""),
                research_process.get("topic", ""),
                json.dumps(research_process.get("entities", [])),
                json.dumps(research_process.get("insights", [])),
                json.dumps(research_process.get("framework", {})),
                datetime.now().isoformat(),
                research_process.get("report_path", "")
            ))
            self.db.commit()
            
            logger.info(f"Research history recorded: {research_id}")
            
            return {
                "status": "queued",
                "research_id": research_id,
                "message": "Research data queued for async knowledge extraction in dream mode"
            }
            
        except Exception as e:
            logger.error(f"Failed to deposit research: {e}")
            return {
                "status": "error",
                "research_id": research_id,
                "error": str(e)
            }
    
    async def get_relevant_knowledge(
        self,
        query: str,
        max_items: int = 10
    ) -> Dict:
        """
        获取与当前查询相关的已有知识
        
        Args:
            query: 查询字符串
            max_items: 最大返回数量
        
        Returns:
            相关知识
        """
        # 搜索相关实体（使用新方法名）
        entities = self.entities.search_entities(query, limit=max_items)
        
        # 搜索相关关系（使用新方法名）
        relations = self.relations.search_relations(query, limit=max_items)
        
        # 搜索相关数据（使用新方法名）
        data_points = self.data_points.search_data_points(query, limit=max_items)
        
        return {
            "entities": entities,
            "relations": relations,
            "data_points": data_points,
            "past_research": [],
            "summary": f"您已积累 {len(entities)} 个相关实体，{len(relations)} 条关系"
        }
    
    async def get_knowledge_summary(self) -> Dict:
        """
        获取知识概览（客观展示，不贴标签）
        
        Returns:
            知识统计
        """
        # 统计知识量
        cursor = self.db.execute("SELECT COUNT(*) FROM entities")
        entity_count = cursor.fetchone()[0]
        
        cursor = self.db.execute("SELECT COUNT(*) FROM relations WHERE valid_until IS NULL")
        relation_count = cursor.fetchone()[0]
        
        cursor = self.db.execute("SELECT COUNT(*) FROM insights")
        insight_count = cursor.fetchone()[0]
        
        cursor = self.db.execute("SELECT COUNT(*) FROM research_history")
        research_count = cursor.fetchone()[0]
        
        return {
            "stats": {
                "total_research": research_count,
                "entities_known": entity_count,
                "relations_understood": relation_count,
                "insights_gained": insight_count,
            },
            "growth": {
                "last_30_days": {
                    "new_entities": 0,  # TODO: 实现时间范围查询
                    "new_relations": 0,
                    "new_insights": 0,
                }
            },
            "suggestions": [],
            "updates": []
        }
    
    # ===== 综合检索方法 =====
    
    def search_all(self, query: str, limit: int = 100) -> Dict[str, List[Dict]]:
        """综合搜索所有知识"""
        entities = self.entities.search_entities(query, limit=limit)
        relations = self.relations.search_relations(query, limit=limit)
        data_points = self.data_points.search_data_points(query, limit=limit)
        
        return {
            "entities": entities,
            "relations": relations,
            "data_points": data_points
        }
    
    def get_entities_summary(self) -> Dict[str, Any]:
        """获取实体概览"""
        cursor = self.db.execute(
            """SELECT entity_type, COUNT(*) as count 
               FROM entities 
               GROUP BY entity_type"""
        )
        
        by_type = {}
        for row in cursor.fetchall():
            by_type[row[0]] = row[1]
        
        total = sum(by_type.values())
        
        return {"by_type": by_type, "total": total}
    
    def get_top_entities(self, limit: int = 10) -> List[Dict]:
        """获取高频实体"""
        cursor = self.db.execute(
            """SELECT entity_id, entity_type, name, mention_count 
               FROM entities 
               ORDER BY mention_count DESC
               LIMIT ?""",
            (limit,)
        )
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "entity_id": row[0],
                "entity_type": row[1],
                "name": row[2],
                "mention_count": row[3]
            })
        
        return results
    
    # ===== 导出方法 =====
    
    def export_to_dict(self) -> Dict[str, Any]:
        """导出所有知识为字典"""
        entities = self.entities.search_entities("")
        relations = self.relations.search_relations("")
        data_points = self.data_points.search_data_points("")
        
        cursor = self.db.execute("SELECT * FROM insights")
        insights = []
        for row in cursor.fetchall():
            insights.append({
                "insight_id": row[0],
                "research_id": row[1],
                "topic": row[2],
                "content": row[3]
            })
        
        return {
            "user_id": self.user_id,
            "entities": entities,
            "relations": relations,
            "data_points": data_points,
            "insights": insights
        }
    
    def export_to_json(self, file_path: str):
        """导出所有知识为JSON文件"""
        import json
        
        data = self.export_to_dict()
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def export_entities(self, file_path: str):
        """仅导出实体"""
        import json
        
        entities = self.entities.search_entities("")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump({"entities": entities}, f, ensure_ascii=False, indent=2)
    
    # ===== 清空方法 =====
    
    def clear_all(self):
        """清空所有知识"""
        self.db.execute("DELETE FROM entities")
        self.db.execute("DELETE FROM relations")
        self.db.execute("DELETE FROM data_points")
        self.db.execute("DELETE FROM insights")
        self.db.commit()
    
    def clear_entities(self):
        """清空实体"""
        self.db.execute("DELETE FROM entities")
        self.db.commit()
    
    def clear_data_points(self):
        """清空数据点"""
        self.db.execute("DELETE FROM data_points")
        self.db.commit()
    
    # ===== v2.0 混合知识管理方法 =====
    
    def store_temporal_fact(
        self,
        entity_name: str,
        attribute: str,
        value: str,
        as_of: str,
        source: str = "",
        source_type: str = "research",
        confidence: float = 0.8
    ) -> Dict[str, str]:
        """
        存储带时间戳的事实（v2.0 新增）
        
        Args:
            entity_name: 实体名称
            attribute: 属性名
            value: 值
            as_of: 事实时间点（如 "2024-Q3"）
            source: 来源描述
            source_type: 来源类型
            confidence: 置信度
        
        Returns:
            {"fact_id": "...", "provenance_id": "..."}
        """
        # 确保模块已初始化
        if not self.temporal or not self.provenance:
            raise RuntimeError("Knowledge modules not initialized")
        
        # 存储时间事实
        fact_id = self.temporal.store_fact(
            entity_name=entity_name,
            attribute=attribute,
            value=value,
            as_of=as_of,
            source=source,
            confidence=confidence
        )
        
        # 记录来源
        provenance_id = self.provenance.record_source(
            entity_name=entity_name,
            attribute=attribute,
            value=value,
            source_type=source_type,
            source_ref=source,
            confidence=confidence,
            fact_id=fact_id
        )
        
        return {
            "fact_id": fact_id,
            "provenance_id": provenance_id
        }
    
    def get_temporal_value(
        self,
        entity_name: str,
        attribute: str,
        as_of: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        获取带时间的值（v2.0 新增）
        
        Args:
            entity_name: 实体名称
            attribute: 属性名
            as_of: 时间点（None 表示最新）
        
        Returns:
            事实字典或 None
        """
        if not self.temporal:
            return None
        return self.temporal.get_value(entity_name, attribute, as_of)
    
    def get_fact_history(
        self,
        entity_name: str,
        attribute: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        获取事实历史版本（v2.0 新增）
        
        Args:
            entity_name: 实体名称
            attribute: 属性名
            limit: 最大返回数量
        
        Returns:
            历史事实列表
        """
        if not self.temporal:
            return []
        return self.temporal.get_history(entity_name, attribute, limit)
    
    def get_fact_sources(
        self,
        entity_name: str,
        attribute: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取事实来源（v2.0 新增）
        
        Args:
            entity_name: 实体名称
            attribute: 属性名（可选）
        
        Returns:
            来源记录列表
        """
        if not self.provenance:
            return []
        return self.provenance.get_sources(entity_name, attribute)
    
    def get_trust_summary(
        self,
        entity_name: str
    ) -> Dict[str, Any]:
        """
        获取实体来源可信度摘要（v2.0 新增）
        
        Args:
            entity_name: 实体名称
        
        Returns:
            可信度摘要
        """
        if not self.provenance:
            return {"entity_name": entity_name, "error": "Provenance module not initialized"}
        return self.provenance.get_trust_summary(entity_name)
    
    def get_audit_trail(
        self,
        entity_name: str,
        attribute: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        获取审计追踪（v2.0 新增）
        
        Args:
            entity_name: 实体名称
            attribute: 属性名（可选）
            limit: 最大返回数量
        
        Returns:
            审计条目列表
        """
        if not self.provenance:
            return []
        return self.provenance.get_audit_trail(entity_name, attribute, limit)
    
    def check_expired_facts(
        self,
        current_time: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        检查过期事实（v2.0 新增）
        
        Args:
            current_time: 当前时间（None 使用系统时间）
        
        Returns:
            过期的事实列表
        """
        if not self.temporal:
            return []
        return self.temporal.check_expired(current_time)
    
    def get_knowledge_stats(self) -> Dict[str, Any]:
        """
        获取知识统计（v2.0 增强）
        
        Returns:
            完整的统计信息
        """
        base_stats = {
            "entities": self.entities.count(),
            "relations": len(self.relations.search_relations("")),
            "data_points": len(self.data_points.search_data_points("")),
        }
        
        temporal_stats = self.temporal.get_stats() if self.temporal else {"error": "Not initialized"}
        provenance_stats = self.provenance.get_stats() if self.provenance else {"error": "Not initialized"}
        
        return {
            "user_id": self.user_id,
            "base": base_stats,
            "temporal": temporal_stats,
            "provenance": provenance_stats
        }
    
    # ===== Phase 3.6: KnowledgeCompiler 集成 =====
    
    @property
    def compiler(self):
        """延迟加载知识编译器"""
        if self._compiler is None:
            from .knowledge.compiler import KnowledgeCompiler
            self._compiler = KnowledgeCompiler(
                knowledge_root=self._knowledge_root,
                user_id=self.user_id
            )
        return self._compiler
    
    def compile_research(
        self,
        raw_content: str,
        source_info: Optional[Dict] = None
    ):
        """
        编译研究内容
        
        Args:
            raw_content: 原始研究内容
            source_info: 来源信息
        
        Returns:
            CompiledKnowledge: 编译结果
        """
        return self.compiler.compile_research(raw_content, source_info)
    
    def save_compiled_knowledge(self, knowledge) -> None:
        """
        保存编译后的知识
        
        Args:
            knowledge: CompiledKnowledge 对象
        """
        self.compiler.save_knowledge(knowledge)
        logger.info(f"Saved compiled knowledge: {knowledge.get_stats()}")
    
    # ===== Phase 3.6: ContradictionDetector 集成 =====
    
    @property
    def contradiction_detector(self):
        """延迟加载矛盾检测器"""
        if self._contradiction_detector is None:
            from .knowledge.contradiction_detector import ContradictionDetector
            self._contradiction_detector = ContradictionDetector(
                db_path=self._contradiction_db_path,
                user_id=self.user_id
            )
        return self._contradiction_detector
    
    def detect_contradictions(self) -> List:
        """
        检测知识矛盾
        
        Returns:
            矛盾列表
        """
        temporal_db_path = str(self.db_path).replace('.db', '_temporal.db')
        return self.contradiction_detector.detect_contradictions(temporal_db_path)
    
    def get_contradiction_stats(self) -> Dict[str, Any]:
        """
        获取矛盾统计
        
        Returns:
            统计信息
        """
        return self.contradiction_detector.get_stats()
    
    def resolve_contradiction(
        self,
        contradiction_id: str,
        resolution: str,
        note: str = "",
        preferred_value: Optional[str] = None
    ) -> None:
        """
        解决矛盾
        
        Args:
            contradiction_id: 矛盾ID
            resolution: 解决状态
            note: 解决说明
            preferred_value: 选择保留的值
        """
        from .knowledge.contradiction_detector import ResolutionStatus
        status = ResolutionStatus(resolution)
        self.contradiction_detector.resolve_contradiction(
            contradiction_id, status, note, preferred_value
        )
    
    # ===== Phase 3.6: KnowledgeImporter 集成 =====
    
    @property
    def importer(self):
        """延迟加载知识导入器"""
        if self._importer is None:
            from .knowledge.importer import KnowledgeImporter
            self._importer = KnowledgeImporter(
                knowledge_root=self._knowledge_root,
                user_id=self.user_id
            )
        return self._importer
    
    def import_file(
        self,
        file_path: str,
        auto_extract: bool = True,
        source_info: Optional[Dict] = None,
        skip_if_imported: bool = True,
        *,
        store_to_bank: bool = True,
    ):
        """
        导入文件
        
        Args:
            file_path: 文件路径
            auto_extract: 是否自动提取知识
            source_info: 来源信息
            skip_if_imported: 是否跳过已导入的文件
            store_to_bank: 是否将编译结果写入 SQLite（仅关键字参数）
        
        Returns:
            ImportResult: 导入结果
        """
        result = self.importer.import_file(
            file_path,
            auto_extract=auto_extract,
            source_info=source_info,
            skip_if_imported=skip_if_imported
        )
        if store_to_bank and result.status in ("success", "partial") and result.compiled_knowledge:
            self._store_compiled_to_bank(result.compiled_knowledge)
        return result

    def import_url(
        self,
        url: str,
        auto_extract: bool = True,
        timeout: int = 30,
        max_size: int = 10485760,
        retries: int = 3,
        *,
        store_to_bank: bool = True,
    ):
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
        result = self.importer.import_url(
            url,
            auto_extract=auto_extract,
            timeout=timeout,
            max_size=max_size,
            retries=retries,
        )
        if store_to_bank and result.status == "success" and result.compiled_knowledge:
            self._store_compiled_to_bank(result.compiled_knowledge)
        return result

    def import_directory(
        self,
        directory_path: str,
        auto_extract: bool = True,
        recursive: bool = True,
        progress_callback=None,
        max_workers: int = 4,
        skip_if_imported: bool = True
    ) -> List:
        """
        批量导入目录
        
        Args:
            directory_path: 目录路径
            auto_extract: 是否自动提取知识
            recursive: 是否递归子目录
            progress_callback: 进度回调
            max_workers: 最大并发数
            skip_if_imported: 是否跳过已导入的文件
        
        Returns:
            导入结果列表
        """
        return self.importer.import_directory(
            directory_path,
            auto_extract=auto_extract,
            recursive=recursive,
            progress_callback=progress_callback,
            max_workers=max_workers,
            skip_if_imported=skip_if_imported
        )
    
    def get_import_stats(self) -> Dict[str, Any]:
        """
        获取导入统计
        
        Returns:
            统计信息
        """
        return self.importer.get_stats()

    def _store_compiled_to_bank(self, knowledge) -> None:
        """将已有编译结果写入 SQLite（不重新编译）"""
        for page in knowledge.entities:
            self.entities.add_entity(
                entity_type=page.metadata.get("entity_type", "generic"),
                name=page.title,
                description=page.content[:500],
            )
        for page in knowledge.concepts:
            self.entities.add_entity(
                entity_type="concept",
                name=page.title,
                description=page.content[:500],
            )
        for page in knowledge.relations:
            source = page.metadata.get("source_entity", "")
            target = page.metadata.get("target_entity", "")
            if source and target:
                self.relations.add_relation(
                    source_entity=source,
                    target_entity=target,
                    relation_type=page.metadata.get("relation_type", "related_to"),
                    context=page.content[:300],
                )
    
    # ===== Phase 3.6: RapidEvolver 快速进化 =====
    
    @property
    def rapid_evolver(self):
        """延迟加载快速进化器"""
        if self._rapid_evolver is None:
            from .core.rapid_evolver import RapidEvolver
            self._rapid_evolver = RapidEvolver()
        return self._rapid_evolver
    
    def rapid_evolve(self, import_result, core_memory) -> Dict[str, Any]:
        """
        从导入结果快速进化
        
        Args:
            import_result: 导入结果
            core_memory: CoreMemory 实例
        
        Returns:
            进化结果
        """
        if not import_result.content:
            return {"domains": [], "entities": []}
        
        # 执行快速进化
        evolution = self.rapid_evolver.evolve_from_content(import_result.content)
        
        # 更新 CoreMemory
        if evolution.domains:
            for domain in evolution.domains[:2]:
                core_memory.add_primary_domain(domain)
        
        if evolution.core_entities:
            for entity in evolution.core_entities:
                core_memory.add_expertise_entity(
                    name=entity["name"],
                    importance=entity["importance"],
                    mention_count=entity["mention_count"]
                )
        
        if evolution.terminology:
            for term, definition in evolution.terminology.items():
                core_memory.add_terminology(term, definition)
        
        if evolution.focus_areas:
            core_memory.set_expertise_focus_areas(evolution.focus_areas)
        
        logger.info(f"Rapid evolution complete: {len(evolution.domains)} domains, {len(evolution.core_entities)} entities")
        
        return evolution.to_dict()
    
    def detect_domains(self, content: str) -> List[str]:
        """
        检测专业领域
        
        Args:
            content: 文本内容
        
        Returns:
            领域列表
        """
        return self.rapid_evolver.detect_domains(content)
    
    def extract_core_entities(self, content: str, top_n: int = 10) -> List[Dict[str, Any]]:
        """
        提取核心实体
        
        Args:
            content: 文本内容
            top_n: 返回数量
        
        Returns:
            核心实体列表
        """
        return self.rapid_evolver.extract_core_entities(content, top_n)
    
    # ===== Phase 3.7: 自我学习模块集成 =====
    
    @property
    def learning_store(self):
        """延迟加载学习记录存储"""
        if self._learning_store is None:
            from .learning import LearningStore
            self._learning_store = LearningStore(self._learning_db_path, self.user_id)
        return self._learning_store
    
    @property
    def error_tracker(self):
        """延迟加载错误追踪器"""
        if self._error_tracker is None:
            from .learning import ErrorTracker
            error_db_path = str(self.db_path).replace('.db', '_errors.db')
            self._error_tracker = ErrorTracker(error_db_path, self.user_id)
        return self._error_tracker
    
    @property
    def feature_request_store(self):
        """延迟加载功能请求存储"""
        if self._feature_request_store is None:
            from .learning import FeatureRequestStore
            fr_db_path = str(self.db_path).replace('.db', '_feature_requests.db')
            self._feature_request_store = FeatureRequestStore(fr_db_path, self.user_id)
        return self._feature_request_store
    
    def get_learning_manager(self, core_memory=None):
        """
        获取学习管理器
        
        Args:
            core_memory: CoreMemory 实例（可选）
        
        Returns:
            LearningManager 实例
        """
        from .learning import LearningManager
        return LearningManager(self.learning_store, core_memory)
    
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
        record = self.learning_store.record_learning(
            category=category,
            content=content,
            session_id=session_id,
            priority=priority
        )
        return record.to_dict()
    
    def record_error(
        self,
        error_type: str,
        error_message: str,
        session_id: Optional[str] = None,
        severity: str = "medium"
    ) -> Dict[str, Any]:
        """
        记录错误
        
        Args:
            error_type: 错误类型
            error_message: 错误信息
            session_id: 会话ID
            severity: 严重程度
        
        Returns:
            错误记录
        """
        record = self.error_tracker.record_error(
            error_type=error_type,
            error_message=error_message,
            session_id=session_id,
            severity=severity
        )
        return record.to_dict()
    
    def record_feature_request(
        self,
        capability: str,
        user_context: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        记录功能请求
        
        Args:
            capability: 能力描述
            user_context: 用户上下文
            session_id: 会话ID
        
        Returns:
            功能请求记录
        """
        request = self.feature_request_store.record_request(
            capability=capability,
            user_context=user_context,
            session_id=session_id
        )
        return request.to_dict()
    
    def get_learning_stats(self) -> Dict[str, Any]:
        """
        获取学习统计
        
        Returns:
            学习统计信息
        """
        return {
            "learnings": self.learning_store.get_stats(),
            "errors": self.error_tracker.get_stats(),
            "feature_requests": self.feature_request_store.get_stats()
        }
    
    def auto_promote_learnings(self, core_memory) -> List[Dict[str, Any]]:
        """
        自动晋升学习记录到 CoreMemory
        
        Args:
            core_memory: CoreMemory 实例
        
        Returns:
            晋升的学习记录列表
        """
        manager = self.get_learning_manager(core_memory)
        promoted = manager.auto_promote()
        return [p.to_dict() for p in promoted]
    
    def close(self):
        """关闭所有数据库连接"""
        # 仅关闭自己拥有的连接
        if self._owns_connection and self.db:
            self.db.close()
        # 关闭时间知识和来源追溯
        if hasattr(self, 'temporal') and self.temporal:
            self.temporal.close()
        if hasattr(self, 'provenance') and self.provenance:
            self.provenance.close()
        # Phase 3.6: 关闭矛盾检测器
        if self._contradiction_detector:
            self._contradiction_detector.close()
        # Phase 3.6: 关闭知识导入器
        if self._importer and hasattr(self._importer, 'close'):
            self._importer.close()
        # Phase 3.7: 关闭学习模块
        if self._learning_store:
            self._learning_store.close()
        if self._error_tracker:
            self._error_tracker.close()
        if self._feature_request_store:
            self._feature_request_store.close()
        
        logger.info(f"UserKnowledgeBank closed: user_id={self.user_id}")
    
    @property
    def owns_connection(self) -> bool:
        """是否拥有数据库连接所有权"""
        return self._owns_connection