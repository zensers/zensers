# -*- coding: utf-8 -*-
"""
FTS5 全文索引模块

提供 SQLite FTS5 全文搜索功能，提升知识库搜索性能。

使用方式：
    from src.core.memory.fts import FTSIndexer, FTSSearcher
    
    # 创建索引
    indexer = FTSIndexer(db)
    indexer.create_all_indexes()
    
    # 搜索
    searcher = FTSSearcher(db)
    results = searcher.search_entities("特斯拉")
"""

__all__ = ["FTSIndexer", "FTSSearcher", "FTSManager"]

import sqlite3
import re
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class FTSIndexer:
    """
    FTS5 索引创建器
    
    负责创建和维护 FTS5 全文索引。
    """
    
    def __init__(self, db: sqlite3.Connection):
        """
        初始化索引器
        
        Args:
            db: SQLite 数据库连接
        """
        self.db = db
    
    def create_all_indexes(self) -> None:
        """创建所有 FTS5 索引"""
        self.create_entities_index()
        self.create_relations_index()
        self.create_data_points_index()
        self.create_insights_index()
        logger.info("All FTS5 indexes created")
    
    def create_entities_index(self) -> None:
        """创建实体 FTS5 索引"""
        # 检查是否已存在
        cursor = self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='entities_fts'"
        )
        if cursor.fetchone():
            logger.debug("entities_fts already exists")
            return
        
        # 创建 FTS5 虚拟表
        self.db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
                entity_id,
                name,
                description,
                aliases,
                entity_type,
                content='entities',
                content_rowid='rowid'
            )
        """)
        
        # 填充索引
        self.db.execute("""
            INSERT INTO entities_fts(rowid, entity_id, name, description, aliases, entity_type)
            SELECT rowid, entity_id, name, description, 
                   COALESCE(aliases, ''), entity_type
            FROM entities
        """)
        
        # 创建触发器：插入
        self.db.execute("""
            CREATE TRIGGER IF NOT EXISTS entities_ai AFTER INSERT ON entities BEGIN
                INSERT INTO entities_fts(rowid, entity_id, name, description, aliases, entity_type)
                VALUES (new.rowid, new.entity_id, new.name, new.description, 
                        COALESCE(new.aliases, ''), new.entity_type);
            END
        """)
        
        # 创建触发器：删除
        self.db.execute("""
            CREATE TRIGGER IF NOT EXISTS entities_ad AFTER DELETE ON entities BEGIN
                INSERT INTO entities_fts(entities_fts, rowid, entity_id, name, description, aliases, entity_type)
                VALUES('delete', old.rowid, old.entity_id, old.name, old.description,
                       COALESCE(old.aliases, ''), old.entity_type);
            END
        """)
        
        # 创建触发器：更新
        self.db.execute("""
            CREATE TRIGGER IF NOT EXISTS entities_au AFTER UPDATE ON entities BEGIN
                INSERT INTO entities_fts(entities_fts, rowid, entity_id, name, description, aliases, entity_type)
                VALUES('delete', old.rowid, old.entity_id, old.name, old.description,
                       COALESCE(old.aliases, ''), old.entity_type);
                INSERT INTO entities_fts(rowid, entity_id, name, description, aliases, entity_type)
                VALUES (new.rowid, new.entity_id, new.name, new.description,
                        COALESCE(new.aliases, ''), new.entity_type);
            END
        """)
        
        logger.info("Created entities_fts index")
    
    def create_relations_index(self) -> None:
        """创建关系 FTS5 索引"""
        cursor = self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='relations_fts'"
        )
        if cursor.fetchone():
            logger.debug("relations_fts already exists")
            return
        
        self.db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS relations_fts USING fts5(
                relation_id,
                source_entity,
                target_entity,
                relation_type,
                context,
                content='relations',
                content_rowid='rowid'
            )
        """)
        
        self.db.execute("""
            INSERT INTO relations_fts(rowid, relation_id, source_entity, target_entity, relation_type, context)
            SELECT rowid, relation_id, source_entity, target_entity, relation_type, COALESCE(context, '')
            FROM relations
        """)
        
        # 触发器
        self.db.execute("""
            CREATE TRIGGER IF NOT EXISTS relations_ai AFTER INSERT ON relations BEGIN
                INSERT INTO relations_fts(rowid, relation_id, source_entity, target_entity, relation_type, context)
                VALUES (new.rowid, new.relation_id, new.source_entity, new.target_entity, 
                        new.relation_type, COALESCE(new.context, ''));
            END
        """)
        
        self.db.execute("""
            CREATE TRIGGER IF NOT EXISTS relations_ad AFTER DELETE ON relations BEGIN
                INSERT INTO relations_fts(relations_fts, rowid, relation_id, source_entity, target_entity, relation_type, context)
                VALUES('delete', old.rowid, old.relation_id, old.source_entity, old.target_entity,
                       old.relation_type, COALESCE(old.context, ''));
            END
        """)
        
        self.db.execute("""
            CREATE TRIGGER IF NOT EXISTS relations_au AFTER UPDATE ON relations BEGIN
                INSERT INTO relations_fts(relations_fts, rowid, relation_id, source_entity, target_entity, relation_type, context)
                VALUES('delete', old.rowid, old.relation_id, old.source_entity, old.target_entity,
                       old.relation_type, COALESCE(old.context, ''));
                INSERT INTO relations_fts(rowid, relation_id, source_entity, target_entity, relation_type, context)
                VALUES (new.rowid, new.relation_id, new.source_entity, new.target_entity,
                        new.relation_type, COALESCE(new.context, ''));
            END
        """)
        
        logger.info("Created relations_fts index")
    
    def create_data_points_index(self) -> None:
        """创建数据点 FTS5 索引"""
        cursor = self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='data_points_fts'"
        )
        if cursor.fetchone():
            logger.debug("data_points_fts already exists")
            return
        
        self.db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS data_points_fts USING fts5(
                data_id,
                entity_id,
                metric_name,
                metric_value,
                source,
                content='data_points',
                content_rowid='rowid'
            )
        """)
        
        self.db.execute("""
            INSERT INTO data_points_fts(rowid, data_id, entity_id, metric_name, metric_value, source)
            SELECT rowid, data_id, entity_id, metric_name, metric_value, COALESCE(source, '')
            FROM data_points
        """)
        
        # 触发器
        self.db.execute("""
            CREATE TRIGGER IF NOT EXISTS data_points_ai AFTER INSERT ON data_points BEGIN
                INSERT INTO data_points_fts(rowid, data_id, entity_id, metric_name, metric_value, source)
                VALUES (new.rowid, new.data_id, new.entity_id, new.metric_name, 
                        new.metric_value, COALESCE(new.source, ''));
            END
        """)
        
        self.db.execute("""
            CREATE TRIGGER IF NOT EXISTS data_points_ad AFTER DELETE ON data_points BEGIN
                INSERT INTO data_points_fts(data_points_fts, rowid, data_id, entity_id, metric_name, metric_value, source)
                VALUES('delete', old.rowid, old.data_id, old.entity_id, old.metric_name,
                       old.metric_value, COALESCE(old.source, ''));
            END
        """)
        
        self.db.execute("""
            CREATE TRIGGER IF NOT EXISTS data_points_au AFTER UPDATE ON data_points BEGIN
                INSERT INTO data_points_fts(data_points_fts, rowid, data_id, entity_id, metric_name, metric_value, source)
                VALUES('delete', old.rowid, old.data_id, old.entity_id, old.metric_name,
                       old.metric_value, COALESCE(old.source, ''));
                INSERT INTO data_points_fts(rowid, data_id, entity_id, metric_name, metric_value, source)
                VALUES (new.rowid, new.data_id, new.entity_id, new.metric_name,
                        new.metric_value, COALESCE(new.source, ''));
            END
        """)
        
        logger.info("Created data_points_fts index")
    
    def create_insights_index(self) -> None:
        """创建洞察 FTS5 索引"""
        cursor = self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='insights_fts'"
        )
        if cursor.fetchone():
            logger.debug("insights_fts already exists")
            return
        
        self.db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS insights_fts USING fts5(
                insight_id,
                research_id,
                content,
                topic,
                tags,
                content='insights',
                content_rowid='rowid'
            )
        """)
        
        self.db.execute("""
            INSERT INTO insights_fts(rowid, insight_id, research_id, content, topic, tags)
            SELECT rowid, insight_id, COALESCE(research_id, ''), content, 
                   COALESCE(topic, ''), COALESCE(tags, '')
            FROM insights
        """)
        
        # 触发器
        self.db.execute("""
            CREATE TRIGGER IF NOT EXISTS insights_ai AFTER INSERT ON insights BEGIN
                INSERT INTO insights_fts(rowid, insight_id, research_id, content, topic, tags)
                VALUES (new.rowid, new.insight_id, COALESCE(new.research_id, ''), 
                        new.content, COALESCE(new.topic, ''), COALESCE(new.tags, ''));
            END
        """)
        
        self.db.execute("""
            CREATE TRIGGER IF NOT EXISTS insights_ad AFTER DELETE ON insights BEGIN
                INSERT INTO insights_fts(insights_fts, rowid, insight_id, research_id, content, topic, tags)
                VALUES('delete', old.rowid, old.insight_id, COALESCE(old.research_id, ''),
                       old.content, COALESCE(old.topic, ''), COALESCE(old.tags, ''));
            END
        """)
        
        self.db.execute("""
            CREATE TRIGGER IF NOT EXISTS insights_au AFTER UPDATE ON insights BEGIN
                INSERT INTO insights_fts(insights_fts, rowid, insight_id, research_id, content, topic, tags)
                VALUES('delete', old.rowid, old.insight_id, COALESCE(old.research_id, ''),
                       old.content, COALESCE(old.topic, ''), COALESCE(old.tags, ''));
                INSERT INTO insights_fts(rowid, insight_id, research_id, content, topic, tags)
                VALUES (new.rowid, new.insight_id, COALESCE(new.research_id, ''),
                        new.content, COALESCE(new.topic, ''), COALESCE(new.tags, ''));
            END
        """)
        
        logger.info("Created insights_fts index")
    
    def drop_all_indexes(self) -> None:
        """删除所有 FTS5 索引"""
        for table in ['entities_fts', 'relations_fts', 'data_points_fts', 'insights_fts']:
            try:
                self.db.execute(f"DROP TABLE IF EXISTS {table}")
            except sqlite3.OperationalError:
                pass
        
        # 删除触发器
        triggers = [
            'entities_ai', 'entities_ad', 'entities_au',
            'relations_ai', 'relations_ad', 'relations_au',
            'data_points_ai', 'data_points_ad', 'data_points_au',
            'insights_ai', 'insights_ad', 'insights_au'
        ]
        for trigger in triggers:
            try:
                self.db.execute(f"DROP TRIGGER IF EXISTS {trigger}")
            except sqlite3.OperationalError:
                pass
        
        logger.info("Dropped all FTS5 indexes")
    
    def rebuild_all_indexes(self) -> None:
        """重建所有 FTS5 索引"""
        self.drop_all_indexes()
        self.create_all_indexes()
        logger.info("Rebuilt all FTS5 indexes")


class FTSSearcher:
    """
    FTS5 搜索器
    
    提供高性能全文搜索功能。
    """
    
    def __init__(self, db: sqlite3.Connection):
        """
        初始化搜索器
        
        Args:
            db: SQLite 数据库连接
        """
        self.db = db
    
    def _is_fts_available(self, table: str) -> bool:
        """检查 FTS 索引是否可用"""
        cursor = self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (f"{table}_fts",)
        )
        return cursor.fetchone() is not None
    
    def search_entities(
        self,
        query: str,
        entity_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        搜索实体
        
        Args:
            query: 搜索关键词
            entity_type: 过滤实体类型
            limit: 最大返回数量
        
        Returns:
            匹配的实体列表
        """
        # 空查询返回所有
        if not query:
            if entity_type:
                cursor = self.db.execute("""
                    SELECT * FROM entities 
                    WHERE entity_type = ?
                    ORDER BY mention_count DESC
                    LIMIT ?
                """, (entity_type, limit))
            else:
                cursor = self.db.execute("""
                    SELECT * FROM entities 
                    ORDER BY mention_count DESC
                    LIMIT ?
                """, (limit,))
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        if not self._is_fts_available('entities'):
            # 回退到 LIKE 搜索
            return self._fallback_search_entities(query, entity_type, limit)
        
        # FTS5 搜索
        fts_query = self._build_fts_query(query)
        
        if entity_type:
            cursor = self.db.execute("""
                SELECT e.* FROM entities e
                JOIN entities_fts fts ON e.entity_id = fts.entity_id
                WHERE entities_fts MATCH ?
                AND e.entity_type = ?
                ORDER BY e.mention_count DESC
                LIMIT ?
            """, (fts_query, entity_type, limit))
        else:
            cursor = self.db.execute("""
                SELECT e.* FROM entities e
                JOIN entities_fts fts ON e.entity_id = fts.entity_id
                WHERE entities_fts MATCH ?
                ORDER BY e.mention_count DESC
                LIMIT ?
            """, (fts_query, limit))
        
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def _fallback_search_entities(
        self,
        query: str,
        entity_type: Optional[str],
        limit: int
    ) -> List[Dict[str, Any]]:
        """回退到 LIKE 搜索"""
        if entity_type:
            cursor = self.db.execute("""
                SELECT * FROM entities 
                WHERE (name LIKE ? OR description LIKE ?)
                AND entity_type = ?
                ORDER BY mention_count DESC
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", entity_type, limit))
        else:
            cursor = self.db.execute("""
                SELECT * FROM entities 
                WHERE name LIKE ? OR description LIKE ?
                ORDER BY mention_count DESC
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", limit))
        
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def search_relations(
        self,
        query: str,
        relation_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        搜索关系
        
        Args:
            query: 搜索关键词
            relation_type: 过滤关系类型
            limit: 最大返回数量
        
        Returns:
            匹配的关系列表
        """
        if not self._is_fts_available('relations'):
            return self._fallback_search_relations(query, relation_type, limit)
        
        fts_query = self._build_fts_query(query)
        
        if relation_type:
            cursor = self.db.execute("""
                SELECT r.* FROM relations r
                JOIN relations_fts fts ON r.relation_id = fts.relation_id
                WHERE relations_fts MATCH ?
                AND r.relation_type = ?
                LIMIT ?
            """, (fts_query, relation_type, limit))
        else:
            cursor = self.db.execute("""
                SELECT r.* FROM relations r
                JOIN relations_fts fts ON r.relation_id = fts.relation_id
                WHERE relations_fts MATCH ?
                LIMIT ?
            """, (fts_query, limit))
        
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def _fallback_search_relations(
        self,
        query: str,
        relation_type: Optional[str],
        limit: int
    ) -> List[Dict[str, Any]]:
        """回退到 LIKE 搜索"""
        if relation_type:
            cursor = self.db.execute("""
                SELECT * FROM relations 
                WHERE context LIKE ?
                AND relation_type = ?
                LIMIT ?
            """, (f"%{query}%", relation_type, limit))
        else:
            cursor = self.db.execute("""
                SELECT * FROM relations 
                WHERE context LIKE ?
                LIMIT ?
            """, (f"%{query}%", limit))
        
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def search_data_points(
        self,
        query: str,
        entity_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        搜索数据点
        
        Args:
            query: 搜索关键词
            entity_id: 过滤实体ID
            limit: 最大返回数量
        
        Returns:
            匹配的数据点列表
        """
        if not self._is_fts_available('data_points'):
            return self._fallback_search_data_points(query, entity_id, limit)
        
        fts_query = self._build_fts_query(query)
        
        if entity_id:
            cursor = self.db.execute("""
                SELECT d.* FROM data_points d
                JOIN data_points_fts fts ON d.data_id = fts.data_id
                WHERE data_points_fts MATCH ?
                AND d.entity_id = ?
                LIMIT ?
            """, (fts_query, entity_id, limit))
        else:
            cursor = self.db.execute("""
                SELECT d.* FROM data_points d
                JOIN data_points_fts fts ON d.data_id = fts.data_id
                WHERE data_points_fts MATCH ?
                LIMIT ?
            """, (fts_query, limit))
        
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def _fallback_search_data_points(
        self,
        query: str,
        entity_id: Optional[str],
        limit: int
    ) -> List[Dict[str, Any]]:
        """回退到 LIKE 搜索"""
        if entity_id:
            cursor = self.db.execute("""
                SELECT * FROM data_points 
                WHERE (metric_name LIKE ? OR metric_value LIKE ? OR source LIKE ?)
                AND entity_id = ?
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", f"%{query}%", entity_id, limit))
        else:
            cursor = self.db.execute("""
                SELECT * FROM data_points 
                WHERE metric_name LIKE ? OR metric_value LIKE ? OR source LIKE ?
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", f"%{query}%", limit))
        
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def search_insights(
        self,
        query: str,
        research_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        搜索洞察
        
        Args:
            query: 搜索关键词
            research_id: 过滤研究ID
            limit: 最大返回数量
        
        Returns:
            匹配的洞察列表
        """
        if not self._is_fts_available('insights'):
            return self._fallback_search_insights(query, research_id, limit)
        
        fts_query = self._build_fts_query(query)
        
        if research_id:
            cursor = self.db.execute("""
                SELECT i.* FROM insights i
                JOIN insights_fts fts ON i.insight_id = fts.insight_id
                WHERE insights_fts MATCH ?
                AND i.research_id = ?
                ORDER BY i.created_at DESC
                LIMIT ?
            """, (fts_query, research_id, limit))
        else:
            cursor = self.db.execute("""
                SELECT i.* FROM insights i
                JOIN insights_fts fts ON i.insight_id = fts.insight_id
                WHERE insights_fts MATCH ?
                ORDER BY i.created_at DESC
                LIMIT ?
            """, (fts_query, limit))
        
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def _fallback_search_insights(
        self,
        query: str,
        research_id: Optional[str],
        limit: int
    ) -> List[Dict[str, Any]]:
        """回退到 LIKE 搜索"""
        if research_id:
            cursor = self.db.execute("""
                SELECT * FROM insights 
                WHERE (content LIKE ? OR topic LIKE ?)
                AND research_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", research_id, limit))
        else:
            cursor = self.db.execute("""
                SELECT * FROM insights 
                WHERE content LIKE ? OR topic LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", limit))
        
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def global_search(
        self,
        query: str,
        limit: int = 50
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        全局搜索（搜索所有类型）
        
        Args:
            query: 搜索关键词
            limit: 每种类型的最大返回数量
        
        Returns:
            包含所有类型结果的字典
        """
        return {
            "entities": self.search_entities(query, limit=limit),
            "relations": self.search_relations(query, limit=limit),
            "data_points": self.search_data_points(query, limit=limit),
            "insights": self.search_insights(query, limit=limit)
        }
    
    def _build_fts_query(self, query: str) -> str:
        """
        构建 FTS5 查询字符串
        
        支持中文分词（使用 jieba）和英文搜索。
        """
        # 处理特殊字符
        query = query.replace('"', '""')
        
        # 检测中文，走 jieba 分词路径
        if re.search(r'[\u4e00-\u9fff]', query):
            try:
                import jieba
                tokens = [t for t in jieba.lcut(query) if t.strip()]
                if tokens:
                    return f'"{" ".join(tokens)}"'
            except ImportError:
                pass
        
        # 如果查询包含空格，使用短语搜索
        if ' ' in query:
            return f'"{query}"'
        
        # 否则使用前缀搜索
        return f'{query}*'


class FTSManager:
    """
    FTS5 管理器
    
    提供统一的 FTS5 索引和搜索接口。
    """
    
    def __init__(self, db: sqlite3.Connection):
        """
        初始化管理器
        
        Args:
            db: SQLite 数据库连接
        """
        self.db = db
        self.indexer = FTSIndexer(db)
        self.searcher = FTSSearcher(db)
    
    def initialize(self) -> None:
        """初始化 FTS5 索引"""
        self.indexer.create_all_indexes()
    
    def search(self, query: str, limit: int = 50) -> Dict[str, List[Dict[str, Any]]]:
        """
        执行全局搜索
        
        Args:
            query: 搜索关键词
            limit: 每种类型的最大返回数量
        
        Returns:
            搜索结果
        """
        return self.searcher.global_search(query, limit)
    
    def rebuild(self) -> None:
        """重建所有索引"""
        self.indexer.rebuild_all_indexes()
    
    def is_available(self) -> bool:
        """检查 FTS5 是否可用"""
        try:
            cursor = self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='entities_fts'"
            )
            return cursor.fetchone() is not None
        except sqlite3.OperationalError:
            return False
