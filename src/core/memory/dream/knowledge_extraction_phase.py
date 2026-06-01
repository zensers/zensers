# -*- coding: utf-8 -*-
"""
KnowledgeExtractionPhase - 知识提取阶段

作为 DreamMode 的扩展阶段，在"做梦模式"中执行知识提取。

设计理念：
- 集成到 DreamMode 的 6 阶段流程中
- 主任务优先：可随时中断
- 自动学习：从知识银行加载已学习的实体词典
- 领域无关：支持任何行业、任何国家
"""

__all__ = ["KnowledgeExtractionPhase", "ExtractionResult"]

import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """提取结果"""
    data_id: str
    research_id: str
    entities_extracted: int = 0
    relations_extracted: int = 0
    data_points_extracted: int = 0
    insights_extracted: int = 0
    new_entities_learned: int = 0
    errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0


class KnowledgeExtractionPhase:
    """
    知识提取阶段
    
    职责：
    1. 从暂存区获取待提取的研究资料
    2. 执行实体、关系、数据点、洞察提取
    3. 自动学习新实体并更新词典
    4. 存入知识银行
    
    集成方式：
    - 作为 DreamMode 的扩展阶段（Phase 7 或插入到现有阶段）
    - 每次执行处理一批待提取资料
    
    主任务优先机制：
    - 每处理完一条资料检查是否需要中断
    - 支持中断后恢复
    """
    
    def __init__(
        self,
        knowledge_bank: Any,
        raw_data_store: Any,
        entity_extractor: Any = None,
        relation_extractor: Any = None,
        knowledge_extractor: Any = None
    ):
        """
        初始化知识提取阶段
        
        Args:
            knowledge_bank: 知识银行实例
            raw_data_store: 研究资料暂存区实例
            entity_extractor: 实体提取器（可选，使用默认配置）
            relation_extractor: 关系提取器（可选）
            knowledge_extractor: 知识提取器（可选）
        """
        self.knowledge_bank = knowledge_bank
        self.raw_data_store = raw_data_store
        
        # 提取器
        self._entity_extractor = entity_extractor
        self._relation_extractor = relation_extractor
        self._knowledge_extractor = knowledge_extractor
        
        # 已学习的实体词典缓存
        self._learned_entities_cache: Dict[str, Set[str]] = {}
        
        # 中断标志
        self._interrupt_requested = False
        
        # 统计
        self._total_extracted = 0
        self._total_learned = 0
        
        logger.info("KnowledgeExtractionPhase initialized")
    
    # ========== 主任务优先机制 ==========
    
    def request_interrupt(self):
        """请求中断提取"""
        self._interrupt_requested = True
        logger.info("Knowledge extraction interrupt requested")
    
    def clear_interrupt(self):
        """清除中断标志"""
        self._interrupt_requested = False
    
    def should_interrupt(self) -> bool:
        """检查是否需要中断"""
        return self._interrupt_requested
    
    # ========== 已学习实体词典加载 ==========
    
    def load_learned_entities(self, entity_type: str) -> Set[str]:
        """
        从知识银行加载已学习的实体
        
        这是实现"自动学习"的关键：
        - 每次提取前，加载已知实体作为词典
        - 提取到新实体后，存入知识银行
        - 下次提取时，新实体已在词典中
        
        Args:
            entity_type: 实体类型
        
        Returns:
            已学习的实体名称集合
        """
        # 检查缓存
        if entity_type in self._learned_entities_cache:
            return self._learned_entities_cache[entity_type]
        
        # 从知识银行加载
        try:
            entities = self.knowledge_bank.entities.search_entities(
                query="",
                type_filter=entity_type,
                limit=10000
            )
            names = {e.get("name", "") for e in entities if e.get("name")}
            
            # 缓存
            self._learned_entities_cache[entity_type] = names
            
            logger.debug(f"Loaded {len(names)} learned entities for type: {entity_type}")
            return names
            
        except Exception as e:
            logger.warning(f"Failed to load learned entities: {e}")
            return set()
    
    def reload_all_learned_entities(self):
        """重新加载所有已学习的实体词典"""
        self._learned_entities_cache.clear()
        
        # 加载常见实体类型
        for entity_type in ["company", "person", "product", "technology", "location", "industry"]:
            self.load_learned_entities(entity_type)
        
        total = sum(len(v) for v in self._learned_entities_cache.values())
        logger.info(f"Reloaded {total} learned entities across all types")
    
    def invalidate_cache(self, entity_type: Optional[str] = None):
        """使缓存失效"""
        if entity_type:
            self._learned_entities_cache.pop(entity_type, None)
        else:
            self._learned_entities_cache.clear()
    
    # ========== 提取执行 ==========
    
    async def run(self, batch_size: int = 10) -> Dict[str, Any]:
        """
        执行知识提取
        
        Args:
            batch_size: 批量处理大小
        
        Returns:
            提取结果统计
        """
        start_time = datetime.now()
        results: List[ExtractionResult] = []
        
        # 重新加载已学习的实体词典
        self.reload_all_learned_entities()
        
        # 获取待提取资料
        pending_data = self.raw_data_store.get_pending_data(limit=batch_size)
        
        if not pending_data:
            logger.debug("No pending data to extract")
            return {
                "status": "no_data",
                "processed": 0,
                "results": []
            }
        
        logger.info(f"Starting knowledge extraction for {len(pending_data)} items")
        
        # 处理每条资料
        for raw_data in pending_data:
            # 检查是否需要中断
            if self.should_interrupt():
                logger.info("Knowledge extraction interrupted by main task")
                # 取消所有正在进行的提取
                self.raw_data_store.cancel_all_in_progress()
                break
            
            # 标记为正在处理
            self.raw_data_store.mark_in_progress(raw_data.data_id)
            
            # 执行提取
            result = await self._extract_single(raw_data)
            results.append(result)
            
            # 标记完成
            if result.errors:
                self.raw_data_store.mark_failed(
                    raw_data.data_id,
                    "; ".join(result.errors)
                )
            else:
                self.raw_data_store.mark_completed(raw_data.data_id)
        
        # 计算统计
        end_time = datetime.now()
        duration_ms = (end_time - start_time).total_seconds() * 1000
        
        total_entities = sum(r.entities_extracted for r in results)
        total_relations = sum(r.relations_extracted for r in results)
        total_data_points = sum(r.data_points_extracted for r in results)
        total_new = sum(r.new_entities_learned for r in results)
        
        self._total_extracted += len(results)
        self._total_learned += total_new
        
        return {
            "status": "completed" if not self.should_interrupt() else "interrupted",
            "processed": len(results),
            "entities_extracted": total_entities,
            "relations_extracted": total_relations,
            "data_points_extracted": total_data_points,
            "new_entities_learned": total_new,
            "duration_ms": duration_ms,
            "results": [r.__dict__ for r in results]
        }
    
    async def _extract_single(self, raw_data: Any) -> ExtractionResult:
        """
        执行单条资料的知识提取
        
        Args:
            raw_data: RawResearchData 实例
        
        Returns:
            提取结果
        """
        start_time = datetime.now()
        result = ExtractionResult(
            data_id=raw_data.data_id,
            research_id=raw_data.research_id
        )
        
        try:
            content = raw_data.content
            source_info = raw_data.source_info
            domain = raw_data.domain
            
            # 1. 实体提取
            entities = await self._extract_entities(content, source_info, domain)
            result.entities_extracted = len(entities)
            
            # 2. 关系提取
            relations = await self._extract_relations(content, entities, source_info)
            result.relations_extracted = len(relations)
            
            # 3. 数据点提取
            data_points = await self._extract_data_points(content, entities, source_info)
            result.data_points_extracted = len(data_points)
            
            # 4. 洞察提取
            insights = await self._extract_insights(content, source_info)
            result.insights_extracted = len(insights)
            
            # 5. 存入知识银行
            new_entities = await self._store_to_knowledge_bank(
                entities, relations, data_points, insights
            )
            result.new_entities_learned = new_entities
            
        except Exception as e:
            result.errors.append(str(e))
            logger.error(f"Extraction failed for {raw_data.data_id}: {e}")
        
        result.duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        return result
    
    async def _extract_entities(
        self,
        content: str,
        source_info: Dict[str, Any],
        domain: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """提取实体"""
        if self._entity_extractor:
            return self._entity_extractor.extract(content, source_info)
        
        # 使用默认提取器
        from ..extraction.entity_extractor import EntityExtractor
        extractor = EntityExtractor()
        return extractor.extract(content, source_info)
    
    async def _extract_relations(
        self,
        content: str,
        entities: List[Dict[str, Any]],
        source_info: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """提取关系"""
        if self._relation_extractor:
            return self._relation_extractor.extract(content, entities, source_info)
        
        # 使用默认提取器
        from ..extraction.relation_extractor import RelationExtractor
        extractor = RelationExtractor()
        return extractor.extract(content, entities, source_info)
    
    async def _extract_data_points(
        self,
        content: str,
        entities: List[Dict[str, Any]],
        source_info: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """提取数据点"""
        # 简单实现：提取数值指标
        import re
        data_points = []
        
        # 时间信息
        year_match = re.search(r'(\d{4})年', content)
        time_period = year_match.group(1) if year_match else None
        
        # 营收模式
        revenue_patterns = [
            (r'营收(?:达到|为|约)?([\d.]+(?:万亿|千亿|百亿|亿|万))', '营收'),
            (r'市场规模(?:达到|为|约)?([\d.]+(?:万亿|千亿|百亿|亿|万))', '市场规模'),
            (r'市场份额(?:达到|为|约)?([\d.]+%)', '市场份额'),
            (r'增长率(?:达到|为|约)?([\d.]+%)', '增长率'),
            (r'市值(?:达到|为|约)?([\d.]+(?:万亿|千亿|百亿|亿))', '市值'),
        ]
        
        for pattern, metric_name in revenue_patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                dp = {
                    "metric_name": metric_name,
                    "metric_value": match,
                    "confidence": 0.7,
                    "source": source_info.get("source", "")
                }
                if time_period:
                    dp["time_period"] = time_period
                if entities:
                    dp["entity_name"] = entities[0].get("name", "")
                data_points.append(dp)
        
        return data_points
    
    async def _extract_insights(
        self,
        content: str,
        source_info: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """提取洞察"""
        # 简单实现：提取关键结论句
        insights = []
        
        # 关键结论模式
        conclusion_patterns = [
            r'(?:结论|综上|因此|由此可见)[：:，,]?\s*([^.。]+[.。])',
            r'(?:预测|预计|展望)[：:，,]?\s*([^.。]+[.。])',
        ]
        
        import re
        for pattern in conclusion_patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                insights.append({
                    "content": match.strip(),
                    "confidence": 0.6,
                    "source": source_info.get("source", "")
                })
        
        return insights[:5]  # 最多5个洞察
    
    async def _store_to_knowledge_bank(
        self,
        entities: List[Dict[str, Any]],
        relations: List[Dict[str, Any]],
        data_points: List[Dict[str, Any]],
        insights: List[Dict[str, Any]]
    ) -> int:
        """
        存入知识银行
        
        Returns:
            新学习的实体数量
        """
        new_entities = 0
        
        # 存入实体
        for entity in entities:
            try:
                entity_type = entity.get("entity_type", "unknown")
                name = entity.get("name", "")
                
                # 检查是否为新实体
                learned = self._learned_entities_cache.get(entity_type, set())
                is_new = name not in learned
                
                # 存入知识银行
                self.knowledge_bank.entities.add_entity(
                    entity_type=entity_type,
                    name=name,
                    description=entity.get("description", ""),
                )
                
                if is_new:
                    new_entities += 1
                    # 更新缓存
                    self._learned_entities_cache.setdefault(entity_type, set()).add(name)
                    
            except Exception as e:
                logger.warning(f"Failed to store entity: {e}")
        
        # 存入关系
        for relation in relations:
            try:
                self.knowledge_bank.relations.add_relation(
                    source_entity=relation.get("source_entity", ""),
                    target_entity=relation.get("target_entity", ""),
                    relation_type=relation.get("relation_type", "related_to"),
                    context=relation.get("context", ""),
                    confidence=relation.get("confidence", 0.6)
                )
            except Exception as e:
                logger.warning(f"Failed to store relation: {e}")
        
        # 存入数据点
        for dp in data_points:
            try:
                entity_name = dp.get("entity_name", "")
                # 获取实体ID
                entity = self.knowledge_bank.entities.get_entity_by_name(entity_name)
                entity_id = entity.get("entity_id", "") if entity else ""
                
                self.knowledge_bank.data_points.add_data_point(
                    entity_id=entity_id,
                    metric_name=dp.get("metric_name", ""),
                    metric_value=dp.get("metric_value", ""),
                    unit=dp.get("unit", ""),
                    time_period=dp.get("time_period", ""),
                    source=dp.get("source", ""),
                    confidence=dp.get("confidence", 0.7)
                )
            except Exception as e:
                logger.warning(f"Failed to store data point: {e}")
        
        # 存入洞察
        for insight in insights:
            try:
                self.knowledge_bank.insights.create({
                    "research_id": "",
                    "topic": "",
                    "content": insight.get("content", ""),
                    "confidence": insight.get("confidence", "medium")
                })
            except Exception as e:
                logger.warning(f"Failed to store insight: {e}")
        
        return new_entities
    
    # ========== 统计 ==========
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_extracted": self._total_extracted,
            "total_learned": self._total_learned,
            "cached_entity_types": list(self._learned_entities_cache.keys()),
            "cached_entities_count": sum(len(v) for v in self._learned_entities_cache.values())
        }