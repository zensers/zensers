"""
知识编译器

职责：
- 将Agent结果编译为知识页
- 存储到知识库
- 支持知识检索和复用

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/ORCHESTRATOR_REDESIGN.md
"""
import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.memory.knowledge_bank import UserKnowledgeBank
    from src.core.memory.stores.insight_store import Insight

logger = logging.getLogger(__name__)


def _deterministic_hash(content: str) -> str:
    """
    生成确定性哈希值
    
    Args:
        content: 要哈希的内容
        
    Returns:
        16位十六进制哈希字符串
    """
    return hashlib.md5(content.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


class KnowledgeType(Enum):
    """知识类型"""
    ENTITY = "entity"           # 实体知识（公司、产品等）
    DATA_POINT = "data_point"   # 数据点（市场规模、增长率等）
    INSIGHT = "insight"         # 洞察（分析结论）
    RELATION = "relation"       # 关系（竞争关系、供应链等）
    DOCUMENT = "document"       # 文档（报告、文章）


@dataclass
class KnowledgePage:
    """
    知识页
    
    Attributes:
        id: 知识ID
        type: 知识类型
        title: 标题
        content: 内容
        source: 来源（agent_id或外部来源）
        confidence: 置信度
        tags: 标签列表
        metadata: 元数据
        created_at: 创建时间
        updated_at: 更新时间
    """
    id: str
    type: KnowledgeType
    title: str
    content: Dict[str, Any]
    source: str
    confidence: float = 0.8
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "type": self.type.value,
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "confidence": self.confidence,
            "tags": self.tags,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class KnowledgeCompilerConfig:
    """知识编译器配置"""
    min_confidence: float = 0.5      # 最小置信度阈值
    auto_tag: bool = True             # 自动生成标签
    dedup_enabled: bool = True        # 去重
    store_path: Optional[Path] = None  # 存储路径


class KnowledgeCompiler:
    """
    知识编译器
    
    职责：
    - 将Agent结果编译为知识页
    - 存储到知识库
    - 支持知识检索和复用
    
    使用示例:
        compiler = KnowledgeCompiler(config)
        
        # 编译Agent结果
        pages = compiler.compile(
            agent_id="agent_001",
            result={"data": {"market_size": "100亿"}},
            topic="新能源汽车市场"
        )
        
        # 存储到知识库
        await compiler.store(pages, knowledge_bank)
    """
    
    # 知识提取规则
    EXTRACTION_RULES = {
        KnowledgeType.ENTITY: {
            "keys": ["company", "companies", "企业", "公司"],
            "title_template": "{name}",
        },
        KnowledgeType.DATA_POINT: {
            "keys": ["market_size", "growth_rate", "revenue", "市场规模", "增长率", "营收"],
            "title_template": "{key}: {value}",
        },
        KnowledgeType.INSIGHT: {
            "keys": ["insight", "conclusion", "finding", "洞察", "结论", "发现"],
            "title_template": "{key}",
        },
    }
    
    def __init__(self, config: Optional[KnowledgeCompilerConfig] = None):
        self.config = config or KnowledgeCompilerConfig()
        
        # 统计
        self._total_compiled = 0
        self._total_pages = 0
    
    def compile(
        self,
        agent_id: str,
        result: Dict[str, Any],
        topic: str,
        aspect: Optional[str] = None,
    ) -> List[KnowledgePage]:
        """
        编译Agent结果为知识页
        
        Args:
            agent_id: Agent ID
            result: Agent执行结果
            topic: 研究主题
            aspect: 研究维度
            
        Returns:
            知识页列表
        """
        self._total_compiled += 1
        pages = []
        
        data = result.get("data", result)
        if not isinstance(data, dict):
            data = {"content": data}
        
        # 提取置信度
        confidence = result.get("confidence", 0.8)
        if confidence < self.config.min_confidence:
            logger.debug(f"Skipping low confidence result: {confidence}")
            return pages
        
        # 1. 提取实体知识
        entity_pages = self._extract_entities(agent_id, data, topic)
        pages.extend(entity_pages)
        
        # 2. 提取数据点知识
        data_pages = self._extract_data_points(agent_id, data, topic)
        pages.extend(data_pages)
        
        # 3. 提取洞察知识
        insight_pages = self._extract_insights(agent_id, data, topic)
        pages.extend(insight_pages)
        
        # 4. 生成文档知识
        doc_page = self._create_document_page(agent_id, result, topic, aspect)
        if doc_page:
            pages.append(doc_page)
        
        # 5. 自动标签
        if self.config.auto_tag:
            for page in pages:
                page.tags = self._generate_tags(page, topic, aspect)
        
        self._total_pages += len(pages)
        
        logger.debug(f"Compiled {len(pages)} knowledge pages from agent {agent_id}")
        
        return pages
    
    def _extract_entities(
        self,
        agent_id: str,
        data: Dict[str, Any],
        topic: str,
    ) -> List[KnowledgePage]:
        """提取实体知识"""
        pages = []
        rules = self.EXTRACTION_RULES[KnowledgeType.ENTITY]
        
        for key in rules["keys"]:
            if key in data:
                entities = data[key]
                if isinstance(entities, list):
                    for entity in entities:
                        if isinstance(entity, dict):
                            name = entity.get("name", str(entity))
                        else:
                            name = str(entity)
                        
                        page = KnowledgePage(
                            id=f"entity_{_deterministic_hash(name)}",
                            type=KnowledgeType.ENTITY,
                            title=name,
                            content=entity if isinstance(entity, dict) else {"name": entity},
                            source=agent_id,
                            tags=[topic],
                        )
                        pages.append(page)
        
        return pages
    
    def _extract_data_points(
        self,
        agent_id: str,
        data: Dict[str, Any],
        topic: str,
    ) -> List[KnowledgePage]:
        """提取数据点知识"""
        pages = []
        rules = self.EXTRACTION_RULES[KnowledgeType.DATA_POINT]
        
        for key in rules["keys"]:
            if key in data:
                value = data[key]
                
                page = KnowledgePage(
                    id=f"data_{_deterministic_hash(key + str(value))}",
                    type=KnowledgeType.DATA_POINT,
                    title=f"{topic} - {key}",
                    content={
                        "key": key,
                        "value": value,
                        "topic": topic,
                    },
                    source=agent_id,
                    tags=[topic, key],
                )
                pages.append(page)
        
        return pages
    
    def _extract_insights(
        self,
        agent_id: str,
        data: Dict[str, Any],
        topic: str,
    ) -> List[KnowledgePage]:
        """提取洞察知识"""
        pages = []
        rules = self.EXTRACTION_RULES[KnowledgeType.INSIGHT]
        
        for key in rules["keys"]:
            if key in data:
                insights = data[key]
                if isinstance(insights, list):
                    for i, insight in enumerate(insights):
                        page = KnowledgePage(
                            id=f"insight_{_deterministic_hash(str(insight))}",
                            type=KnowledgeType.INSIGHT,
                            title=f"{topic} - 洞察 {i+1}",
                            content={"insight": insight, "topic": topic},
                            source=agent_id,
                            tags=[topic, "insight"],
                        )
                        pages.append(page)
                else:
                    page = KnowledgePage(
                        id=f"insight_{_deterministic_hash(str(insights))}",
                        type=KnowledgeType.INSIGHT,
                        title=f"{topic} - {key}",
                        content={"insight": insights, "topic": topic},
                        source=agent_id,
                        tags=[topic, key],
                    )
                    pages.append(page)
        
        return pages
    
    def _create_document_page(
        self,
        agent_id: str,
        result: Dict[str, Any],
        topic: str,
        aspect: Optional[str],
    ) -> Optional[KnowledgePage]:
        """创建文档知识页"""
        # 检查是否有完整内容
        content = result.get("content") or result.get("report") or result.get("output")
        
        if not content:
            return None
        
        title = f"{topic}"
        if aspect:
            title += f" - {aspect}"
        
        return KnowledgePage(
            id=f"doc_{_deterministic_hash(title)}",
            type=KnowledgeType.DOCUMENT,
            title=title,
            content={
                "full_content": content,
                "topic": topic,
                "aspect": aspect,
            },
            source=agent_id,
            tags=[topic, "document"],
        )
    
    def _generate_tags(
        self,
        page: KnowledgePage,
        topic: str,
        aspect: Optional[str],
    ) -> List[str]:
        """生成标签"""
        tags = [topic]
        
        if aspect:
            tags.append(aspect)
        
        # 从内容中提取关键词
        content_str = str(page.content)
        
        # 简单的关键词提取
        keywords = []
        for word in ["市场", "竞争", "趋势", "规模", "增长", "技术", "政策"]:
            if word in content_str:
                keywords.append(word)
        
        tags.extend(keywords)
        
        return list(set(tags))
    
    async def store(
        self,
        pages: List[KnowledgePage],
        knowledge_bank: "UserKnowledgeBank",
        research_id: Optional[str] = None,
    ) -> int:
        """
        存储知识页到知识库
        
        Args:
            pages: 知识页列表
            knowledge_bank: 用户知识库
            research_id: 研究ID（用于洞察存储）
            
        Returns:
            成功存储的数量
        """
        stored = 0
        research_id = research_id or f"research_{uuid.uuid4().hex[:8]}"
        
        for page in pages:
            try:
                if page.type == KnowledgeType.ENTITY:
                    # 使用 EntityStore.add_entity 接口
                    knowledge_bank.entities.add_entity(
                        entity_type=page.content.get("entity_type", "generic"),
                        name=page.title,
                        description=page.content.get("description", ""),
                    )
                    
                elif page.type == KnowledgeType.DATA_POINT:
                    # 使用 DataPointStore.add_data_point 接口
                    # 需要先获取或创建实体ID
                    entity_name = page.content.get("topic", page.title)
                    entity_id = knowledge_bank.entities.add_entity(
                        entity_type="topic",
                        name=entity_name,
                    )
                    knowledge_bank.data_points.add_data_point(
                        entity_id=entity_id,
                        metric_name=page.content.get("key", page.title),
                        metric_value=str(page.content.get("value", "")),
                        source=page.source,
                        confidence=page.confidence,
                    )
                    
                elif page.type == KnowledgeType.INSIGHT:
                    # 使用 InsightStore.create 接口
                    from src.core.memory.stores.insight_store import Insight
                    insight = Insight(
                        insight_id=page.id,
                        research_id=research_id,
                        topic=page.tags[0] if page.tags else "",
                        content=page.content.get("insight", ""),
                        confidence="high" if page.confidence > 0.8 else "medium",
                    )
                    knowledge_bank.insights.create(insight)
                
                stored += 1
                
            except Exception as e:
                logger.error(f"Failed to store knowledge page {page.id}: {e}")
        
        logger.info(f"Stored {stored}/{len(pages)} knowledge pages")
        
        return stored
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_compiled": self._total_compiled,
            "total_pages": self._total_pages,
            "avg_pages_per_compile": (
                self._total_pages / self._total_compiled
                if self._total_compiled > 0 else 0
            ),
        }
