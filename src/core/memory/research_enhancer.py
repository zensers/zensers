# -*- coding: utf-8 -*-
"""
研究增强

使用知识银行增强研究过程
"""

from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class ResearchEnhancer:
    """
    研究增强器
    
    使用知识银行增强研究过程：
    - 在研究开始时提供相关知识
    - 在研究结束时存储新知识
    """
    
    def __init__(self, knowledge_bank: Optional[Any] = None):
        """
        初始化研究增强器
        
        Args:
            knowledge_bank: 用户知识银行实例
        """
        self.knowledge_bank = knowledge_bank
    
    async def enrich_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        使用知识银行增强研究请求
        
        Args:
            request: 原始研究请求
        
        Returns:
            增强后的请求
        """
        enriched = request.copy()
        
        if not self.knowledge_bank:
            return enriched
        
        topic = request.get("topic", "")
        
        # 搜索相关知识
        relevant_knowledge = await self.knowledge_bank.get_relevant_knowledge(
            topic, max_items=10
        )
        
        enriched["relevant_knowledge"] = relevant_knowledge
        
        # 添加上下文
        if relevant_knowledge.get("entities"):
            entity_names = [e.get("name", "") for e in relevant_knowledge["entities"][:3]]
            enriched["context"] = {
                "known_entities": entity_names,
                "knowledge_summary": relevant_knowledge.get("summary", "")
            }
        
        return enriched
    
    async def store_results(self, result: Dict[str, Any]) -> Dict[str, int]:
        """
        存储研究结果到知识银行
        
        Args:
            result: 研究结果
        
        Returns:
            存储统计
        """
        if not self.knowledge_bank:
            return {
                "entities_added": 0,
                "relations_added": 0,
                "data_points_added": 0
            }
        
        stats = {
            "entities_added": 0,
            "relations_added": 0,
            "data_points_added": 0
        }
        
        # 存储实体
        if result.get("entities"):
            for entity in result["entities"]:
                try:
                    self.knowledge_bank.entities.add_entity(
                        entity_type=entity.get("type", "unknown"),
                        name=entity["name"],
                        description=entity.get("description", "")
                    )
                    stats["entities_added"] += 1
                except Exception as e:
                    logger.error(f"Failed to store entity: {e}")
        
        # 存储关系
        if result.get("relations"):
            for relation in result["relations"]:
                try:
                    self.knowledge_bank.relations.add_relation(
                        source_entity=relation["source"],
                        target_entity=relation["target"],
                        relation_type=relation["type"],
                        context=relation.get("context", "")
                    )
                    stats["relations_added"] += 1
                except Exception as e:
                    logger.error(f"Failed to store relation: {e}")
        
        # 存储数据点
        if result.get("data_points"):
            for data in result["data_points"]:
                try:
                    self.knowledge_bank.data_points.add_data_point(
                        entity_id=data.get("entity_id", "unknown"),
                        metric_name=data.get("metric", ""),
                        metric_value=data.get("value", ""),
                        time_period=data.get("year", "")
                    )
                    stats["data_points_added"] += 1
                except Exception as e:
                    logger.error(f"Failed to store data point: {e}")
        
        return stats
    
    async def generate_research_context(self, topic: str) -> Dict[str, Any]:
        """
        为研究主题生成上下文
        
        Args:
            topic: 研究主题
        
        Returns:
            研究上下文
        """
        context = {
            "topic": topic,
            "entities": [],
            "relations": [],
            "data_points": []
        }
        
        if not self.knowledge_bank:
            return context
        
        # 搜索相关实体
        entities = self.knowledge_bank.entities.search_entities(topic, limit=5)
        context["entities"] = entities
        
        # 搜索相关关系
        relations = self.knowledge_bank.relations.search_relations(topic, limit=5)
        context["relations"] = relations
        
        # 搜索相关数据点
        data_points = self.knowledge_bank.data_points.search_data_points(topic, limit=5)
        context["data_points"] = data_points
        
        return context
    
    async def suggest_related_topics(self, current_topic: str) -> List[str]:
        """
        根据当前主题建议相关主题
        
        Args:
            current_topic: 当前主题
        
        Returns:
            相关主题建议
        """
        suggestions = []
        
        if not self.knowledge_bank:
            return suggestions
        
        # 搜索相关实体
        entities = self.knowledge_bank.entities.search_entities(current_topic, limit=5)
        
        for entity in entities:
            # 添加实体名称作为建议
            if entity.get("name") and entity["name"] != current_topic:
                suggestions.append(entity["name"])
            
            # 如果实体有描述，提取关键词
            if entity.get("description"):
                # 简单的关键词提取
                desc = entity["description"]
                if len(desc) > 10:
                    # 取描述的前部分作为建议
                    suggestions.append(desc[:20])
        
        # 去重并限制数量
        suggestions = list(dict.fromkeys(suggestions))[:5]
        
        return suggestions
    
    async def get_research_suggestions(self, topic: str) -> Dict[str, Any]:
        """
        获取研究建议
        
        Args:
            topic: 研究主题
        
        Returns:
            研究建议
        """
        suggestions = {
            "topic": topic,
            "related_entities": [],
            "related_topics": [],
            "historical_data": []
        }
        
        if not self.knowledge_bank:
            return suggestions
        
        # 获取相关实体
        entities = self.knowledge_bank.entities.search_entities(topic, limit=5)
        suggestions["related_entities"] = [
            {"name": e.get("name", ""), "type": e.get("entity_type", "")}
            for e in entities
        ]
        
        # 获取相关主题
        suggestions["related_topics"] = await self.suggest_related_topics(topic)
        
        # 获取历史数据
        data_points = self.knowledge_bank.data_points.search_data_points(topic, limit=5)
        suggestions["historical_data"] = [
            {
                "metric": d.get("metric_name", ""),
                "value": d.get("metric_value", ""),
                "period": d.get("time_period", "")
            }
            for d in data_points
        ]
        
        return suggestions