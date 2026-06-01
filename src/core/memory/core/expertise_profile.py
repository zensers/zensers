# -*- coding: utf-8 -*-
"""
ExpertiseProfile - 专业画像数据结构

Phase 3.6 新增: CoreMemory 专业能力画像
支持快速进化模式，记录用户的专业领域、核心实体和术语。
"""

__all__ = [
    "ExpertiseProfile",
    "ExpertiseEntity"
]

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional


@dataclass
class ExpertiseEntity:
    """专业实体"""
    name: str
    importance: float = 0.5
    mention_count: int = 1
    last_seen: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "importance": self.importance,
            "mention_count": self.mention_count,
            "last_seen": self.last_seen
        }


@dataclass
class ExpertiseProfile:
    """
    专业能力画像
    
    Attributes:
        primary_domains: 主要专业领域
        secondary_domains: 次要专业领域
        domain_depth: 领域深度 (expert/intermediate/novice)
        core_entities: 核心实体列表
        terminology: 术语词典 {术语: 定义}
        focus_areas: 关注点
        last_evolution: 最后进化时间
    """
    primary_domains: List[str] = field(default_factory=list)
    secondary_domains: List[str] = field(default_factory=list)
    domain_depth: Dict[str, str] = field(default_factory=dict)
    core_entities: List[Dict[str, Any]] = field(default_factory=list)
    terminology: Dict[str, str] = field(default_factory=dict)
    focus_areas: List[str] = field(default_factory=list)
    last_evolution: Optional[str] = None
    
    def add_primary_domain(self, domain: str) -> None:
        """添加主要领域"""
        if domain not in self.primary_domains:
            self.primary_domains.append(domain)
            if domain not in self.domain_depth:
                self.domain_depth[domain] = "intermediate"
        self._update_timestamp()
    
    def add_secondary_domain(self, domain: str) -> None:
        """添加次要领域"""
        if domain not in self.secondary_domains and domain not in self.primary_domains:
            self.secondary_domains.append(domain)
            if domain not in self.domain_depth:
                self.domain_depth[domain] = "novice"
        self._update_timestamp()
    
    def set_domain_depth(self, domain: str, depth: str) -> None:
        """设置领域深度"""
        if depth not in ["expert", "intermediate", "novice"]:
            raise ValueError(f"Invalid depth: {depth}. Must be expert/intermediate/novice")
        self.domain_depth[domain] = depth
        self._update_timestamp()
    
    def add_core_entity(self, name: str, importance: float = 0.5, mention_count: int = 1) -> None:
        """添加核心实体"""
        # 检查是否已存在
        for entity in self.core_entities:
            if entity.get("name") == name:
                # 更新
                entity["importance"] = max(entity.get("importance", 0.5), importance)
                entity["mention_count"] = entity.get("mention_count", 0) + mention_count
                entity["last_seen"] = datetime.now().strftime("%Y-%m-%d")
                self._sort_entities()
                self._update_timestamp()
                return
        
        # 添加新实体
        self.core_entities.append({
            "name": name,
            "importance": importance,
            "mention_count": mention_count,
            "last_seen": datetime.now().strftime("%Y-%m-%d")
        })
        self._sort_entities()
        self._update_timestamp()
    
    def _sort_entities(self) -> None:
        """按重要性排序实体，限制数量"""
        self.core_entities.sort(key=lambda e: e.get("importance", 0), reverse=True)
        # 最多保留 20 个核心实体
        if len(self.core_entities) > 20:
            self.core_entities = self.core_entities[:20]
    
    def add_terminology(self, term: str, definition: str) -> None:
        """添加术语"""
        self.terminology[term] = definition
        self._update_timestamp()
    
    def set_focus_areas(self, areas: List[str]) -> None:
        """设置关注点"""
        self.focus_areas = areas
        self._update_timestamp()
    
    def _update_timestamp(self) -> None:
        """更新时间戳"""
        self.last_evolution = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """导出为字典"""
        return {
            "primary_domains": self.primary_domains,
            "secondary_domains": self.secondary_domains,
            "domain_depth": self.domain_depth,
            "core_entities": self.core_entities,
            "terminology": self.terminology,
            "focus_areas": self.focus_areas,
            "last_evolution": self.last_evolution
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExpertiseProfile":
        """从字典创建"""
        return cls(
            primary_domains=data.get("primary_domains", []),
            secondary_domains=data.get("secondary_domains", []),
            domain_depth=data.get("domain_depth", {}),
            core_entities=data.get("core_entities", []),
            terminology=data.get("terminology", {}),
            focus_areas=data.get("focus_areas", []),
            last_evolution=data.get("last_evolution")
        )