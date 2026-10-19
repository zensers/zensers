# -*- coding: utf-8 -*-
"""
实体提取器

从原始文本中提取结构化实体：
- 公司 (Company)
- 人物 (Person)
- 产品 (Product)
- 指标 (Metric)
- 时间 (Time)

支持：
- 中文和英文实体识别
- 正则模式和关键词匹配
- 实体去重与合并
- 置信度计算

设计参考: CONTEXT_COMPRESSION.md 第 11 节
"""

__all__ = ["EntityExtractor"]

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_DICT_PATH = Path(__file__).resolve().parents[4] / "data" / "knowledge" / "methodology" / "entity_dictionary.yaml"


@dataclass
class Entity:
    """实体数据类"""
    entity_id: str
    entity_type: str
    name: str
    aliases: List[str] = field(default_factory=list)
    confidence: float = 0.8
    mention_count: int = 1
    position: Optional[Tuple[int, int]] = None
    context: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)
    source: Optional[Dict[str, Any]] = None


class EntityExtractor:
    """
    实体提取器
    
    核心功能：
    - 从文本中提取结构化实体
    - 支持多种实体类型
    - 自动去重与合并
    - 置信度计算
    
    实体类型：
    - company: 公司
    - person: 人物
    - product: 产品
    - metric: 指标
    - time: 时间
    
    参考：CONTEXT_COMPRESSION.md 第 11.2 节
    """
    
    # 默认配置
    DEFAULT_CONFIG = {
        "confidence_threshold": 0.5,
        "company_patterns": ["公司", "集团", "企业", "科技", "股份"],
        "company_suffixes": ["Inc", "Corp", "Ltd", "LLC"],
        "person_patterns": ["先生", "女士", "总", "CEO", "CTO", "CFO", "董事长", "总裁"],
        "product_patterns": ["车型", "电池", "芯片", "系统", "平台"],
        "metric_patterns": ["份额", "营收", "利润", "增长", "市值", "估值"],
        "time_patterns": ["年", "月", "季度", "Q1", "Q2", "Q3", "Q4", "上半年", "下半年"],
    }
    
    # 常见公司别名映射
    COMPANY_ALIASES = {
        "CATL": "宁德时代",
        "BYD": "比亚迪",
        "宁德时代": "宁德时代",
        "比亚迪": "比亚迪",
        "特斯拉": "特斯拉",
        "Tesla": "特斯拉",
    }
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化实体提取器
        
        Args:
            config: 配置字典，覆盖默认配置
        """
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}
        
        # 初始化正则模式
        self._init_patterns()
        
        # 加载外部词典（合并到已知列表）
        self._dict_companies: List[str] = []
        self._dict_persons: List[str] = []
        self._dict_products: List[str] = []
        self._dict_metrics: List[str] = []
        self._dict_aliases: Dict[str, str] = dict(self.COMPANY_ALIASES)
        
        dict_path = self.config.get("dictionary_path", str(_DICT_PATH))
        self._load_dictionary(dict_path)
        
        logger.info(f"EntityExtractor initialized with config: {self.config.keys()}")
    
    def _init_patterns(self):
        """初始化正则模式"""
        # 公司模式
        company_pattern = "|".join(self.config["company_patterns"])
        self.company_re = re.compile(
            rf'([\u4e00-\u9fa5]{{2,10}}(?:{company_pattern}))'
        )
        
        # 英文公司模式
        suffix_pattern = "|".join(self.config["company_suffixes"])
        self.company_en_re = re.compile(
            rf'([A-Z][a-zA-Z]+\s+(?:{suffix_pattern})\.?)',
            re.IGNORECASE
        )
        
        # 人物模式
        person_pattern = "|".join(self.config["person_patterns"])
        self.person_re = re.compile(
            rf'([\u4e00-\u9fa5]{{2,4}}(?:{person_pattern})?)'
        )
        
        # 时间模式
        self.time_re = re.compile(
            r'(\d{4}年|\d{4}年\d{1,2}月|Q[1-4]|上?半年|去年|今年)'
        )
        
        # 指标模式
        metric_pattern = "|".join(self.config["metric_patterns"])
        self.metric_re = re.compile(
            rf'([\u4e00-\u9fa5]{{2,6}}(?:{metric_pattern}))'
        )
    
    def _load_dictionary(self, path: str):
        """从 YAML 词典加载实体，合并到已知列表"""
        try:
            import yaml
            p = Path(path)
            if not p.exists():
                logger.debug(f"Dictionary file not found: {path}")
                return
            with open(p, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data:
                return
            for entry in data.get("companies", []):
                name = entry.get("name", "")
                if name and name not in self._dict_companies:
                    self._dict_companies.append(name)
                for alias in entry.get("aliases", []):
                    if alias and alias not in self._dict_aliases:
                        self._dict_aliases[alias] = name
            for entry in data.get("persons", []):
                name = entry.get("name", "")
                if name and name not in self._dict_persons:
                    self._dict_persons.append(name)
                for alias in entry.get("aliases", []):
                    if alias and alias not in self._dict_persons:
                        self._dict_persons.append(alias)
                    if alias and alias not in self._dict_aliases:
                        self._dict_aliases[alias] = name
            for entry in data.get("products", []):
                name = entry.get("name", "")
                if name and name not in self._dict_products:
                    self._dict_products.append(name)
                for alias in entry.get("aliases", []):
                    if alias and alias not in self._dict_products:
                        self._dict_products.append(alias)
                    if alias and alias not in self._dict_aliases:
                        self._dict_aliases[alias] = name
            for entry in data.get("metrics", []):
                name = entry.get("name", "")
                if name and name not in self._dict_metrics:
                    self._dict_metrics.append(name)
                for alias in entry.get("aliases", []):
                    if alias and alias not in self._dict_metrics:
                        self._dict_metrics.append(alias)
                    if alias and alias not in self._dict_aliases:
                        self._dict_aliases[alias] = name
            logger.info(
                f"Loaded dictionary: {len(self._dict_companies)} companies, "
                f"{len(self._dict_persons)} persons, "
                f"{len(self._dict_products)} products, "
                f"{len(self._dict_metrics)} metrics"
            )
        except Exception as e:
            logger.warning(f"Failed to load dictionary {path}: {e}")
    
    # ========== 主接口 ==========
    
    def extract(
        self,
        text: str,
        source: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        从文本中提取实体
        
        Args:
            text: 输入文本
            source: 来源信息
            
        Returns:
            实体列表
        """
        if not text:
            return []
        
        entities = []
        
        # 提取各类实体
        entities.extend(self._extract_companies(text, source))
        entities.extend(self._extract_persons(text, source))
        entities.extend(self._extract_products(text, source))
        entities.extend(self._extract_metrics(text, source))
        entities.extend(self._extract_times(text, source))
        
        # 去重与合并
        entities = self._deduplicate(entities)
        
        return [self._entity_to_dict(e) for e in entities]
    
    # ========== 各类型提取 ==========
    
    def _extract_companies(
        self,
        text: str,
        source: Optional[Dict[str, Any]]
    ) -> List[Entity]:
        """提取公司实体"""
        entities = []
        
        # 中文公司
        for match in self.company_re.finditer(text):
            name = match.group(1)
            entity = self._create_entity(
                entity_type="company",
                name=name,
                position=(match.start(), match.end()),
                context=self._get_context(text, match.start(), match.end()),
                source=source,
                confidence=0.85
            )
            entities.append(entity)
        
        # 英文公司
        for match in self.company_en_re.finditer(text):
            name = match.group(1)
            entity = self._create_entity(
                entity_type="company",
                name=name.strip(),
                position=(match.start(), match.end()),
                context=self._get_context(text, match.start(), match.end()),
                source=source,
                confidence=0.85
            )
            entities.append(entity)
        
        # 已知公司名称（字典 + 硬编码后备）
        known_companies = list(set(self._dict_companies + ["宁德时代", "比亚迪", "特斯拉", "CATL", "BYD", "Tesla"]))
        for company in known_companies:
            if company in text:
                # 检查是否已经提取
                if not any(e.name == company or company in e.aliases for e in entities):
                    pos = text.find(company)
                    entity = self._create_entity(
                        entity_type="company",
                        name=self._dict_aliases.get(company, company),
                        aliases=[company] if company != self._dict_aliases.get(company, company) else [],
                        position=(pos, pos + len(company)),
                        context=self._get_context(text, pos, pos + len(company)),
                        source=source,
                        confidence=0.95
                    )
                    entities.append(entity)
        
        return entities
    
    def _extract_persons(
        self,
        text: str,
        source: Optional[Dict[str, Any]]
    ) -> List[Entity]:
        """提取人物实体"""
        entities = []
        
        # 已知人物名称（字典 + 硬编码后备）
        known_persons = list(set(self._dict_persons + ["马斯克", "王传福", "曾毓群"]))
        for person in known_persons:
            if person in text:
                pos = text.find(person)
                entity = self._create_entity(
                    entity_type="person",
                    name=person,
                    position=(pos, pos + len(person)),
                    context=self._get_context(text, pos, pos + len(person)),
                    source=source,
                    confidence=0.9
                )
                entities.append(entity)
        
        # 基于职位标识提取
        for match in self.person_re.finditer(text):
            name = match.group(1)
            # 过滤太短或太长的
            if len(name) < 2 or len(name) > 10:
                continue
            # 避免重复
            if any(e.name == name for e in entities):
                continue
            
            entity = self._create_entity(
                entity_type="person",
                name=name,
                position=(match.start(), match.end()),
                context=self._get_context(text, match.start(), match.end()),
                source=source,
                confidence=0.7
            )
            entities.append(entity)
        
        return entities
    
    def _extract_products(
        self,
        text: str,
        source: Optional[Dict[str, Any]]
    ) -> List[Entity]:
        """提取产品实体"""
        entities = []
        
        # 已知产品名称（字典 + 硬编码后备）
        known_products = list(set(self._dict_products + ["Model 3", "Model Y", "刀片电池", "麒麟电池"]))
        for product in known_products:
            if product in text:
                pos = text.find(product)
                entity = self._create_entity(
                    entity_type="product",
                    name=product,
                    position=(pos, pos + len(product)),
                    context=self._get_context(text, pos, pos + len(product)),
                    source=source,
                    confidence=0.9
                )
                entities.append(entity)
        
        return entities
    
    def _extract_metrics(
        self,
        text: str,
        source: Optional[Dict[str, Any]]
    ) -> List[Entity]:
        """提取指标实体"""
        entities = []
        
        # 常见指标（字典 + 硬编码后备）
        known_metrics = list(set(self._dict_metrics + ["市场份额", "营收", "利润", "增长率", "市值", "估值"]))
        for metric in known_metrics:
            if metric in text:
                pos = text.find(metric)
                entity = self._create_entity(
                    entity_type="metric",
                    name=metric,
                    position=(pos, pos + len(metric)),
                    context=self._get_context(text, pos, pos + len(metric)),
                    source=source,
                    confidence=0.85
                )
                entities.append(entity)
        
        return entities
    
    def _extract_times(
        self,
        text: str,
        source: Optional[Dict[str, Any]]
    ) -> List[Entity]:
        """提取时间实体"""
        entities = []
        
        for match in self.time_re.finditer(text):
            time_str = match.group(1)
            entity = self._create_entity(
                entity_type="time",
                name=time_str,
                position=(match.start(), match.end()),
                context=self._get_context(text, match.start(), match.end()),
                source=source,
                confidence=0.9
            )
            entities.append(entity)
        
        return entities
    
    # ========== 辅助方法 ==========
    
    def _create_entity(
        self,
        entity_type: str,
        name: str,
        position: Tuple[int, int],
        context: str,
        source: Optional[Dict[str, Any]],
        confidence: float,
        aliases: Optional[List[str]] = None
    ) -> Entity:
        """创建实体对象"""
        import uuid
        
        return Entity(
            entity_id=str(uuid.uuid4()),
            entity_type=entity_type,
            name=name,
            aliases=aliases or [],
            confidence=confidence,
            position=position,
            context=context,
            source=source,
            properties={}
        )
    
    def _get_context(
        self,
        text: str,
        start: int,
        end: int,
        window: int = 20
    ) -> str:
        """获取实体的上下文"""
        context_start = max(0, start - window)
        context_end = min(len(text), end + window)
        return text[context_start:context_end]
    
    def _deduplicate(self, entities: List[Entity]) -> List[Entity]:
        """去重与合并实体 — 按 (normalized_name, entity_type) 分组"""
        key_to_entity: Dict[Tuple[str, str], Entity] = {}
        
        for entity in entities:
            normalized_name = self._dict_aliases.get(entity.name, entity.name)
            key = (normalized_name, entity.entity_type)
            
            if key in key_to_entity:
                existing = key_to_entity[key]
                existing.mention_count += 1
                if entity.name != normalized_name and entity.name not in existing.aliases:
                    existing.aliases.append(entity.name)
                existing.confidence = max(existing.confidence, entity.confidence)
            else:
                if entity.name != normalized_name:
                    entity.aliases.append(entity.name)
                    entity.name = normalized_name
                key_to_entity[key] = entity
        
        # 跨类型冲突：同一名称多种类型时，保留置信度最高的
        name_best: Dict[str, Entity] = {}
        for (name, etype), entity in key_to_entity.items():
            if name not in name_best or entity.confidence > name_best[name].confidence:
                name_best[name] = entity
        
        return list(name_best.values())
    
    def _entity_to_dict(self, entity: Entity) -> Dict[str, Any]:
        """将实体转换为字典"""
        result = {
            "entity_id": entity.entity_id,
            "entity_type": entity.entity_type,
            "name": entity.name,
            "aliases": entity.aliases,
            "confidence": entity.confidence,
            "mention_count": entity.mention_count,
            "properties": entity.properties
        }
        
        if entity.position:
            result["start"] = entity.position[0]
            result["end"] = entity.position[1]
        
        if entity.context:
            result["context"] = entity.context
        
        if entity.source:
            result["source"] = entity.source
        
        return result