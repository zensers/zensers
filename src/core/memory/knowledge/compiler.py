# -*- coding: utf-8 -*-
"""
KnowledgeCompiler - 知识编译器

将原始研究资料编译为结构化知识页，实现知识的规范化存储。

核心功能：
- 实体识别与知识页生成
- 概念定义提取
- 关系图谱构建
- 引用关联管理

目录结构：
data/users/{user_id}/knowledge/
├── concepts/     # 概念定义页
├── entities/     # 实体百科页
└── relations/    # 关系图谱页

使用方式：
```python
compiler = KnowledgeCompiler(knowledge_root="data/users/test/knowledge")
knowledge = compiler.compile_research(raw_content)
compiler.save_knowledge(knowledge)
```
"""

__all__ = [
    "KnowledgeCompiler",
    "KnowledgePage",
    "CompiledKnowledge",
    "PageType",
    "BacklinkSystem"
]

import re
import json
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class PageType(Enum):
    """知识页类型"""
    CONCEPT = "concept"      # 概念定义
    ENTITY = "entity"        # 实体百科
    RELATION = "relation"    # 关系图谱


@dataclass
class KnowledgePage:
    """
    知识页数据结构
    
    Attributes:
        page_type: 页面类型
        title: 页面标题
        content: Markdown 内容
        slug: 文件名（可自定义）
        metadata: 元数据（来源、时间等）
        backlinks: 引用来源列表
        created_at: 创建时间
        updated_at: 更新时间
    """
    page_type: PageType
    title: str
    content: str
    slug: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    backlinks: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        """初始化后处理"""
        if self.slug is None:
            self.slug = self.title
    
    def to_markdown(self) -> str:
        """转换为完整 Markdown 文档"""
        lines = [self.content]
        
        # 添加元数据部分
        if self.metadata:
            lines.append("\n---\n")
            lines.append("## 元数据\n")
            for key, value in self.metadata.items():
                lines.append(f"- **{key}**: {value}")
        
        # 添加引用来源部分
        if self.backlinks:
            lines.append("\n---\n")
            lines.append("## 被引用于\n")
            for ref in self.backlinks:
                lines.append(f"- [[{ref}]]")
        
        # 添加时间戳
        lines.append("\n---\n")
        lines.append(f"*创建于: {self.created_at.strftime('%Y-%m-%d %H:%M')}*")
        lines.append(f"*更新于: {self.updated_at.strftime('%Y-%m-%d %H:%M')}*")
        
        return "\n".join(lines)
    
    def add_backlink(self, source: str):
        """添加引用来源"""
        if source not in self.backlinks:
            self.backlinks.append(source)
            self.updated_at = datetime.now()


@dataclass
class CompiledKnowledge:
    """
    编译结果容器
    
    包含编译生成的所有知识页。
    """
    concepts: List[KnowledgePage] = field(default_factory=list)
    entities: List[KnowledgePage] = field(default_factory=list)
    relations: List[KnowledgePage] = field(default_factory=list)
    compilation_time: datetime = field(default_factory=datetime.now)
    
    def add_concept(self, page: KnowledgePage):
        """添加概念页"""
        if page.page_type != PageType.CONCEPT:
            raise ValueError("Page must be CONCEPT type")
        self.concepts.append(page)
    
    def add_entity(self, page: KnowledgePage):
        """添加实体页"""
        if page.page_type != PageType.ENTITY:
            raise ValueError("Page must be ENTITY type")
        self.entities.append(page)
    
    def add_relation(self, page: KnowledgePage):
        """添加关系页"""
        if page.page_type != PageType.RELATION:
            raise ValueError("Page must be RELATION type")
        self.relations.append(page)
    
    def get_all_pages(self) -> List[KnowledgePage]:
        """获取所有页面"""
        return self.concepts + self.entities + self.relations
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return {
            "concepts": len(self.concepts),
            "entities": len(self.entities),
            "relations": len(self.relations),
            "total": len(self.get_all_pages())
        }


class KnowledgeCompiler:
    """
    知识编译器
    
    将原始研究资料编译为结构化知识页。
    
    Attributes:
        knowledge_root: 知识库根目录
        entity_patterns: 实体识别正则模式
        concept_patterns: 概念识别正则模式
    """
    
    # per-directory 写锁，防止多线程并发写入同一知识库目录
    _save_locks: Dict[str, threading.Lock] = {}
    _lock_lock = threading.Lock()
    
    # 实体识别模式（公司、人物、产品）
    ENTITY_PATTERNS = {
        "company": [
            r'([\u4e00-\u9fa5]{2,8})(公司|集团|有限|股份)',
            r'(宁德时代|比亚迪|特斯拉|蔚来|小鹏|理想|长城|吉利)',
        ],
        "person": [
            r'(马斯克|王传福|李斌|何小鹏|李想)',
        ],
        "product": [
            r'(Model\s*[3YXS]|刀片电池|麒麟电池)',
        ]
    }
    
    # 概念关键词
    CONCEPT_KEYWORDS = [
        "新能源汽车", "动力电池", "电动汽车", "市场份额",
        "营收", "净利润", "增长率", "产能", "供应链"
    ]
    
    # 关系关键词
    RELATION_KEYWORDS = {
        "竞争": ["竞争", "对手", "竞品"],
        "供应": ["供应", "采购", "供应商"],
        "投资": ["投资", "入股", "持股"],
        "合作": ["合作", "联合", "战略"]
    }
    
    def __init__(
        self,
        knowledge_root: Path,
        user_id: Optional[str] = None
    ):
        """
        初始化编译器
        
        Args:
            knowledge_root: 知识库根目录
            user_id: 用户ID（可选）
        """
        self.knowledge_root = Path(knowledge_root)
        self.user_id = user_id
        
        # 创建目录结构
        self._init_directories()
        
        logger.info(f"KnowledgeCompiler initialized: knowledge_root={knowledge_root}")
    
    def _init_directories(self):
        """初始化目录结构"""
        for subdir in ["concepts", "entities", "relations"]:
            dir_path = self.knowledge_root / subdir
            dir_path.mkdir(parents=True, exist_ok=True)
    
    def compile_research(
        self,
        raw_content: str,
        source_info: Optional[Dict] = None
    ) -> CompiledKnowledge:
        """
        编译研究内容
        
        Args:
            raw_content: 原始研究内容
            source_info: 来源信息
        
        Returns:
            CompiledKnowledge: 编译结果
        """
        knowledge = CompiledKnowledge()
        
        # 1. 提取实体
        entities = self._extract_entities(raw_content)
        for entity_name, entity_type in entities.items():
            context = self._extract_entity_context(raw_content, entity_name)
            page = self._generate_entity_page(entity_name, context, entity_type)
            knowledge.add_entity(page)
        
        # 2. 提取概念
        concepts = self._extract_concepts(raw_content)
        for concept_name in concepts:
            definition = self._extract_definition(raw_content, concept_name)
            page = self._generate_concept_page(concept_name, definition)
            knowledge.add_concept(page)
        
        # 3. 提取关系
        relations = self._extract_relations(raw_content)
        for relation in relations:
            page = self._generate_relation_page(relation)
            knowledge.add_relation(page)
        
        # 4. 添加来源信息
        if source_info:
            for page in knowledge.get_all_pages():
                page.metadata["source"] = source_info.get("title", "研究报告")
                page.metadata["compiled_at"] = datetime.now().isoformat()
        
        logger.info(f"Compiled research: {knowledge.get_stats()}")
        return knowledge
    
    def _extract_entities(self, text: str) -> Dict[str, str]:
        """
        提取实体
        
        Args:
            text: 输入文本
        
        Returns:
            Dict[实体名, 实体类型]
        """
        entities: Dict[str, str] = {}
        
        for entity_type, patterns in self.ENTITY_PATTERNS.items():
            for pattern in patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    # 处理元组匹配（正则分组）
                    if isinstance(match, tuple):
                        entity_name = match[0]
                    else:
                        entity_name = match
                    
                    if entity_name and len(entity_name) >= 2:
                        entities[entity_name] = entity_type
        
        return entities
    
    def _extract_entity_context(
        self,
        text: str,
        entity_name: str,
        context_length: int = 200
    ) -> str:
        """
        提取实体上下文
        
        Args:
            text: 输入文本
            entity_name: 实体名
            context_length: 上下文长度
        
        Returns:
            包含实体的上下文片段
        """
        # 找到实体位置
        pos = text.find(entity_name)
        if pos == -1:
            return ""
        
        # 提取前后文
        start = max(0, pos - context_length // 2)
        end = min(len(text), pos + len(entity_name) + context_length // 2)
        
        return text[start:end].strip()
    
    def _extract_concepts(self, text: str) -> Set[str]:
        """
        提取概念
        
        Args:
            text: 输入文本
        
        Returns:
            概念集合
        """
        concepts: Set[str] = set()
        
        for keyword in self.CONCEPT_KEYWORDS:
            if keyword in text:
                concepts.add(keyword)
        
        return concepts
    
    def _extract_definition(
        self,
        text: str,
        concept_name: str,
        max_length: int = 150
    ) -> str:
        """
        提取概念定义
        
        Args:
            text: 输入文本
            concept_name: 概念名
            max_length: 最大长度
        
        Returns:
            定义文本
        """
        # 查找概念附近的定义性语句
        pos = text.find(concept_name)
        if pos == -1:
            return f"{concept_name} 相关概念"
        
        # 提取后续内容
        start = pos + len(concept_name)
        end = min(len(text), start + max_length)
        
        definition = text[start:end].strip()
        
        # 清理定义文本
        if definition.startswith(("是指", "是一种", "包括", "代表")):
            definition = definition[:max_length]
        else:
            definition = f"{concept_name} 相关概念"
        
        return definition
    
    def _extract_relations(self, text: str) -> List[Dict[str, str]]:
        """
        提取关系
        
        Args:
            text: 输入文本
        
        Returns:
            关系列表 [{source, target, relation_type}]
        """
        relations: List[Dict[str, str]] = []
        
        # 已识别的实体
        entities = list(self._extract_entities(text).keys())
        
        for relation_type, keywords in self.RELATION_KEYWORDS.items():
            for keyword in keywords:
                # 查找包含关系关键词的句子
                pattern = r'([^.!?]*' + keyword + r'[^.!?]*)'
                matches = re.findall(pattern, text)
                
                for match in matches:
                    # 查找句子中的实体
                    source = None
                    target = None
                    
                    for entity in entities:
                        if entity in match:
                            if source is None:
                                source = entity
                            elif target is None and entity != source:
                                target = entity
                    
                    if source and target:
                        relations.append({
                            "source": source,
                            "target": target,
                            "relation_type": relation_type,
                            "context": match.strip()
                        })
        
        return relations
    
    def _generate_entity_page(
        self,
        entity_name: str,
        context: str,
        entity_type: str = "company"
    ) -> KnowledgePage:
        """
        生成实体页面
        
        Args:
            entity_name: 实体名
            context: 上下文
            entity_type: 实体类型
        
        Returns:
            KnowledgePage
        """
        content = f"""# {entity_name}

## 基本信息

- **类型**: {entity_type}

## 描述

{context if context else f"{entity_name} 是研究中的重要实体。"}

## 相关数据

（待补充）
"""
        
        return KnowledgePage(
            page_type=PageType.ENTITY,
            title=entity_name,
            content=content,
            metadata={
                "entity_type": entity_type,
                "extracted_at": datetime.now().isoformat()
            }
        )
    
    def _generate_concept_page(
        self,
        concept_name: str,
        definition: str
    ) -> KnowledgePage:
        """
        生成概念页面
        
        Args:
            concept_name: 概念名
            definition: 定义
        
        Returns:
            KnowledgePage
        """
        content = f"""# {concept_name}

## 定义

{definition}

## 相关实体

（待补充）

## 应用场景

（待补充）
"""
        
        return KnowledgePage(
            page_type=PageType.CONCEPT,
            title=concept_name,
            content=content,
            metadata={
                "concept_type": "domain",
                "extracted_at": datetime.now().isoformat()
            }
        )
    
    def _generate_relation_page(
        self,
        relation: Dict[str, str]
    ) -> KnowledgePage:
        """
        生成关系页面
        
        Args:
            relation: 关系信息
        
        Returns:
            KnowledgePage
        """
        source = relation.get("source", "")
        target = relation.get("target", "")
        rel_type = relation.get("relation_type", "")
        context = relation.get("context", "")
        
        title = f"{source} → {target}"
        
        content = f"""# {title}

## 关系类型

**{rel_type}**

## 详情

{context}

## 源实体

- [[{source}]]

## 目标实体

- [[{target}]]
"""
        
        return KnowledgePage(
            page_type=PageType.RELATION,
            title=title,
            content=content,
            metadata={
                "relation_type": rel_type,
                "source_entity": source,
                "target_entity": target,
                "extracted_at": datetime.now().isoformat()
            }
        )
    
    def _get_lock(self) -> threading.Lock:
        """获取当前 knowledge_root 的专用锁"""
        key = str(self.knowledge_root.resolve())
        with self._lock_lock:
            if key not in self._save_locks:
                self._save_locks[key] = threading.Lock()
            return self._save_locks[key]

    def save_knowledge(self, knowledge: CompiledKnowledge):
        """
        保存知识页到文件
        
        Args:
            knowledge: 编译结果
        """
        lock = self._get_lock()
        with lock:
            for page in knowledge.concepts:
                self._save_page(page, "concepts")
            for page in knowledge.entities:
                self._save_page(page, "entities")
            for page in knowledge.relations:
                self._save_page(page, "relations")
        
        logger.info(f"Saved knowledge: {knowledge.get_stats()}")
    
    def _save_page(self, page: KnowledgePage, subdir: str):
        """
        保存单个页面
        
        Args:
            page: 知识页
            subdir: 子目录名
        """
        file_path = self.knowledge_root / subdir / f"{page.slug}.md"
        
        # 如果文件已存在，合并内容
        if file_path.exists():
            existing = file_path.read_text(encoding='utf-8')
            page = self._merge_pages(existing, page)
        
        # 写入文件
        file_path.write_text(page.to_markdown(), encoding='utf-8')
    
    def _merge_pages(self, existing: str, new: KnowledgePage) -> KnowledgePage:
        """
        合并已存在页面和新页面
        
        Args:
            existing: 已存在内容
            new: 新页面
        
        Returns:
            合并后的页面
        """
        # 简单合并：保留新内容，但保留旧的引用来源
        # 解析旧内容的引用
        backlink_pattern = r'\[\[([^\]]+)\]\]'
        old_backlinks = set(re.findall(backlink_pattern, existing))
        
        # 合并引用
        for link in old_backlinks:
            if link not in new.backlinks:
                new.backlinks.append(link)
        
        new.updated_at = datetime.now()
        return new
    
    def load_page(
        self,
        title: str,
        page_type: PageType
    ) -> Optional[KnowledgePage]:
        """
        加载已存在的页面
        
        Args:
            title: 页面标题
            page_type: 页面类型
        
        Returns:
            KnowledgePage 或 None
        """
        subdir = page_type.value
        file_path = self.knowledge_root / subdir / f"{title}.md"
        
        if not file_path.exists():
            return None
        
        content = file_path.read_text(encoding='utf-8')
        
        # 解析元数据（简化版本）
        metadata = {}
        if "---" in content:
            parts = content.split("---")
            if len(parts) >= 2:
                meta_section = parts[-2]
                # 解析元数据行
                for line in meta_section.split("\n"):
                    if line.startswith("- **"):
                        match = re.match(r'- \*\*([^*]+)\*\*: (.+)', line)
                        if match:
                            metadata[match.group(1)] = match.group(2)
        
        return KnowledgePage(
            page_type=page_type,
            title=title,
            content=content.split("---")[0].strip(),
            metadata=metadata
        )
    
    def get_all_entities(self) -> List[str]:
        """获取所有实体名称"""
        entity_dir = self.knowledge_root / "entities"
        return [f.stem for f in entity_dir.glob("*.md")]
    
    def get_all_concepts(self) -> List[str]:
        """获取所有概念名称"""
        concept_dir = self.knowledge_root / "concepts"
        return [f.stem for f in concept_dir.glob("*.md")]


class BacklinkSystem:
    """
    引用关联系统
    
    管理知识页之间的引用关系。
    
    功能：
    - 检测页面引用
    - 自动更新引用来源
    - 维护引用索引
    """
    
    # 知识页链接格式 [[页面名]]
    KNOWLEDGE_LINK_PATTERN = r'\[\[([^\]]+)\]\]'
    
    def __init__(self, knowledge_root: Path):
        """
        初始化引用关联系统
        
        Args:
            knowledge_root: 知识库根目录
        """
        self.knowledge_root = Path(knowledge_root)
        self.compiler = KnowledgeCompiler(knowledge_root)
        
        logger.info(f"BacklinkSystem initialized: knowledge_root={knowledge_root}")
    
    def detect_references(self, content: str) -> Set[str]:
        """
        检测内容中的引用
        
        Args:
            content: 知识页内容
        
        Returns:
            引用的页面名集合
        """
        refs = set(re.findall(self.KNOWLEDGE_LINK_PATTERN, content))
        return refs
    
    def update_backlinks(self):
        """
        更新所有页面的引用来源
        
        遍历所有知识页，检测引用，并更新被引用页面的引用来源。
        """
        # 1. 构建引用索引
        reference_index: Dict[str, List[str]] = {}
        
        for page_type in [PageType.ENTITY, PageType.CONCEPT, PageType.RELATION]:
            subdir = page_type.value
            page_dir = self.knowledge_root / subdir
            
            if not page_dir.exists():
                continue
            
            for page_file in page_dir.glob("*.md"):
                page_name = page_file.stem
                content = page_file.read_text(encoding='utf-8')
                
                # 检测该页面引用的其他页面
                refs = self.detect_references(content)
                
                for ref in refs:
                    if ref not in reference_index:
                        reference_index[ref] = []
                    reference_index[ref].append(page_name)
        
        # 2. 更新被引用页面的引用来源
        for target, sources in reference_index.items():
            self._update_page_backlinks(target, sources)
        
        logger.info(f"Updated backlinks: {len(reference_index)} targets")
    
    def _update_page_backlinks(
        self,
        page_name: str,
        sources: List[str]
    ):
        """
        更新页面的引用来源
        
        Args:
            page_name: 页面名
            sources: 引用来源列表
        """
        # 尝试在不同目录找到页面
        for subdir in ["entities", "concepts", "relations"]:
            page_file = self.knowledge_root / subdir / f"{page_name}.md"
            
            if page_file.exists():
                content = page_file.read_text(encoding='utf-8')
                
                # 生成引用来源部分
                backlink_section = self._generate_backlink_section(sources)
                
                # 更新内容
                if "## 被引用于" in content:
                    # 替换已有的引用来源部分
                    content = re.sub(
                        r'## 被引用于\n.*',
                        backlink_section,
                        content
                    )
                else:
                    # 添加新的引用来源部分
                    content += "\n\n" + backlink_section
                
                # 更新时间戳
                content = re.sub(
                    r'\*更新于: [^*]+\*',
                    f"*更新于: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
                    content
                )
                
                page_file.write_text(content, encoding='utf-8')
                break
    
    def _generate_backlink_section(self, sources: List[str]) -> str:
        """
        生成引用来源部分
        
        Args:
            sources: 引用来源列表
        
        Returns:
            Markdown 格式的引用来源部分
        """
        lines = ["## 被引用于"]
        
        for source in sources:
            lines.append(f"- [[{source}]]")
        
        return "\n".join(lines)
    
    def get_backlinks(self, page_name: str) -> List[str]:
        """
        获取页面的引用来源
        
        Args:
            page_name: 页面名
        
        Returns:
            引用该页面的页面列表
        """
        for subdir in ["entities", "concepts", "relations"]:
            page_file = self.knowledge_root / subdir / f"{page_name}.md"
            
            if page_file.exists():
                content = page_file.read_text(encoding='utf-8')
                
                if "## 被引用于" in content:
                    # 解析引用来源
                    backlink_section = content.split("## 被引用于")[1]
                    refs = re.findall(self.KNOWLEDGE_LINK_PATTERN, backlink_section)
                    return list(refs)
        
        return []