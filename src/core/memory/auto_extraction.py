# -*- coding: utf-8 -*-
"""
自动知识提取

从研究过程中自动提取实体、关系和数据点
"""

import re
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class KnowledgeExtractor:
    """
    知识提取器
    
    从研究内容中自动提取实体、关系和数据点
    """
    
    # 公司名称模式
    COMPANY_PATTERNS = [
        r'([\u4e00-\u9fa5]{2,10}(?:集团|公司|科技|技术|电子|网络|互联网|通信|汽车|能源|电池))',
        r'(腾讯|阿里巴巴|百度|京东|美团|字节跳动|拼多多|网易|小米|华为|宁德时代|比亚迪|特斯拉|苹果|谷歌|微软|亚马逊)',
    ]
    
    # 行业关键词
    INDUSTRY_KEYWORDS = [
        '电商', '互联网', '金融', '教育', '医疗', '汽车', '新能源', 
        '半导体', '人工智能', '云计算', '大数据', '物联网', '电池'
    ]
    
    # 关系关键词
    RELATION_PATTERNS = {
        'competitor': ['竞争', '对手', '竞争者', '竞品'],
        'partner': ['合作', '伙伴', '战略合作'],
        'supplier': ['供应商', '供应', '供货'],
        'customer': ['客户', '买家', '采购'],
        'investor': ['投资', '股东', '入股'],
    }
    
    # 数据指标模式
    DATA_PATTERNS = [
        (r'营收(?:达到|为|约)?([\d.]+(?:万亿|千亿|百亿|亿|万))', '营收'),
        (r'市场份额(?:达到|为|约)?([\d.]+%)', '市场份额'),
        (r'增长率(?:达到|为|约)?([\d.]+%)', '增长率'),
        (r'市值(?:达到|为|约)?([\d.]+(?:万亿|千亿|百亿|亿))', '市值'),
        (r'用户数(?:达到|为|约)?([\d.]+(?:亿|万))', '用户数'),
    ]
    
    def __init__(self, knowledge_bank: Optional[Any] = None):
        """
        初始化知识提取器
        
        Args:
            knowledge_bank: 用户知识银行实例
        """
        self.knowledge_bank = knowledge_bank
    
    def extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """
        从文本中提取实体
        
        Args:
            text: 输入文本
        
        Returns:
            实体列表
        """
        entities = []
        seen_names = set()
        
        # 提取公司实体
        for pattern in self.COMPANY_PATTERNS:
            matches = re.findall(pattern, text)
            for match in matches:
                name = match if isinstance(match, str) else match[0]
                if name not in seen_names:
                    entities.append({
                        "name": name,
                        "entity_type": "company",
                        "confidence": 0.8
                    })
                    seen_names.add(name)
        
        # 提取行业实体
        for keyword in self.INDUSTRY_KEYWORDS:
            if keyword in text and keyword not in seen_names:
                entities.append({
                    "name": keyword,
                    "entity_type": "industry",
                    "confidence": 0.7
                })
                seen_names.add(keyword)
        
        return entities
    
    def extract_relations(
        self,
        text: str,
        entities: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        从文本中提取关系
        
        Args:
            text: 输入文本
            entities: 已提取的实体列表
        
        Returns:
            关系列表
        """
        relations = []
        
        if len(entities) < 2:
            return relations
        
        # 检查关系关键词
        for relation_type, keywords in self.RELATION_PATTERNS.items():
            for keyword in keywords:
                if keyword in text:
                    # 简单规则：如果文本包含关系关键词，假设前两个实体有关系
                    for i in range(len(entities) - 1):
                        relations.append({
                            "source_entity": entities[i]["name"],
                            "target_entity": entities[i + 1]["name"],
                            "relation_type": relation_type,
                            "context": text[:100],  # 取前100字符作为上下文
                            "confidence": 0.6
                        })
                    break
        
        return relations
    
    def extract_data_points(
        self,
        text: str,
        entities: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        从文本中提取数据点
        
        Args:
            text: 输入文本
            entities: 相关实体列表
        
        Returns:
            数据点列表
        """
        data_points = []
        
        # 提取时间信息
        year_match = re.search(r'(\d{4})年', text)
        time_period = year_match.group(1) if year_match else None
        
        # 提取各类数据指标
        for pattern, metric_name in self.DATA_PATTERNS:
            matches = re.findall(pattern, text)
            for match in matches:
                value = match if isinstance(match, str) else match[0]
                data_point = {
                    "metric_name": metric_name,
                    "metric_value": value,
                    "confidence": 0.7
                }
                
                if time_period:
                    data_point["time_period"] = time_period
                
                if entities and len(entities) > 0:
                    data_point["entity_name"] = entities[0]["name"]
                
                data_points.append(data_point)
        
        return data_points
    
    async def extract_from_research(
        self,
        research_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        从研究结果中提取知识
        
        Args:
            research_result: 研究结果字典
        
        Returns:
            提取的知识
        """
        # 合并所有文本内容
        texts = []
        
        if research_result.get("content"):
            texts.append(research_result["content"])
        
        if research_result.get("sections"):
            for section in research_result["sections"]:
                if section.get("content"):
                    texts.append(section["content"])
        
        full_text = " ".join(texts)
        
        # 提取实体
        entities = self.extract_entities(full_text)
        
        # 提取关系
        relations = self.extract_relations(full_text, entities)
        
        # 提取数据点
        data_points = self.extract_data_points(full_text, entities)
        
        return {
            "entities": entities,
            "relations": relations,
            "data_points": data_points
        }
    
    async def deposit_entities(
        self,
        entities: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        将实体存入知识银行
        
        Args:
            entities: 实体列表
        
        Returns:
            存入结果统计
        """
        if not self.knowledge_bank:
            return {"added": 0, "error": "No knowledge bank"}
        
        added = 0
        for entity in entities:
            try:
                self.knowledge_bank.entities.add_entity(
                    entity_type=entity.get("entity_type", "unknown"),
                    name=entity["name"],
                    description=entity.get("description", "")
                )
                added += 1
            except Exception as e:
                logger.error(f"Failed to add entity {entity['name']}: {e}")
        
        return {"added": added}
    
    async def deposit_relations(
        self,
        relations: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        将关系存入知识银行
        
        Args:
            relations: 关系列表
        
        Returns:
            存入结果统计
        """
        if not self.knowledge_bank:
            return {"added": 0, "error": "No knowledge bank"}
        
        added = 0
        for relation in relations:
            try:
                self.knowledge_bank.relations.add_relation(
                    source_entity=relation["source_entity"],
                    target_entity=relation["target_entity"],
                    relation_type=relation["relation_type"],
                    context=relation.get("context", ""),
                    confidence=relation.get("confidence", 1.0)
                )
                added += 1
            except Exception as e:
                logger.error(f"Failed to add relation: {e}")
        
        return {"added": added}
    
    async def deposit_data_points(
        self,
        data_points: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        将数据点存入知识银行
        
        Args:
            data_points: 数据点列表
        
        Returns:
            存入结果统计
        """
        if not self.knowledge_bank:
            return {"added": 0, "error": "No knowledge bank"}
        
        added = 0
        for data in data_points:
            try:
                entity_id = data.get("entity_id", "unknown")
                self.knowledge_bank.data_points.add_data_point(
                    entity_id=entity_id,
                    metric_name=data["metric_name"],
                    metric_value=data["metric_value"],
                    time_period=data.get("time_period", "")
                )
                added += 1
            except Exception as e:
                logger.error(f"Failed to add data point: {e}")
        
        return {"added": added}