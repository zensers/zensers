# -*- coding: utf-8 -*-
"""
CoreMemory - Layer 1 核心记忆

实现 CONTEXT_COMPRESSION.md 中的 Layer 1 设计规范：
- 存储用户核心偏好和积累的知识结晶
- 大小限制: < 10KB
- 加载时间: < 10ms
- 晋升条件: mention_count >= 5, frequency >= 3, recurrence_count >= 3

Phase 3.6 新增:
- 专业能力画像 (ExpertiseProfile)
- 支持快速进化模式

Phase 3.7 新增:
- 核心学习记录集成 (core_learnings)
- 支持自我学习机制晋升
"""

__all__ = [
    "CoreMemory",
    "UserProfile",
    "TopEntity",
    "CoreNeed",
    "LearnedPattern",
    "ExpertiseProfile"
]

import json
import logging
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from threading import Lock

logger = logging.getLogger(__name__)

# 导入专业画像
from .expertise_profile import ExpertiseProfile


# ========== 数据类 ==========

@dataclass
class UserProfile:
    """用户偏好"""
    preferences: Dict[str, Any] = field(default_factory=lambda: {
        "output_format": "markdown",
        "language": "zh-CN"
    })
    focus_areas: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TopEntity:
    """高频实体"""
    name: str
    type: str  # company/person/product/metric/time
    mention_count: int = 1
    last_mentioned: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CoreNeed:
    """核心需求"""
    topic: str
    frequency: int = 1
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LearnedPattern:
    """学习结晶"""
    pattern_key: str
    content: str
    recurrence_count: int = 1
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ========== CoreMemory 主类 ==========

class CoreMemory:
    """
    Layer 1 核心记忆
    
    职责: 存储用户的核心偏好和积累的知识结晶
    
    设计规范:
    - 大小限制: < 10KB
    - 加载时间: < 10ms
    - 晋升条件:
      - 高频实体: mention_count >= 5
      - 核心需求: frequency >= 3
      - 学习结晶: recurrence_count >= 3
    
    数据结构:
    - user_profile: 用户偏好和关注领域
    - top_entities: 高频实体列表（最多20个）
    - core_needs: 核心需求列表（最多10个）
    - learned_patterns: 学习结晶列表（最多15个）
    """
    
    # 常量
    VERSION = "1.0"
    MAX_TOP_ENTITIES = 20
    MAX_CORE_NEEDS = 10
    MAX_LEARNED_PATTERNS = 15
    SIZE_LIMIT_BYTES = 10 * 1024  # 10KB
    
    # 晋升阈值
    ENTITY_PROMOTION_THRESHOLD = 5  # mention_count >= 5
    NEED_PROMOTION_THRESHOLD = 3     # frequency >= 3
    PATTERN_PROMOTION_THRESHOLD = 3  # recurrence_count >= 3
    
    def __init__(
        self,
        user_id: str,
        storage_path: Optional[str] = None
    ):
        """
        初始化核心记忆
        
        Args:
            user_id: 用户ID
            storage_path: 存储路径，默认为 data/users/{user_id}/memory_core.json
        """
        self.user_id = user_id
        self.version = self.VERSION
        self._lock = Lock()  # 多线程并发保护锁
        
        # 设置存储路径
        if storage_path is None:
            storage_path = f"data/users/{user_id}"
        self.storage_path = Path(storage_path)
        self._file_path = self.storage_path / "memory_core.json"
        
        # 初始化数据结构
        self.user_profile = UserProfile()
        self.top_entities: List[TopEntity] = []
        self.core_needs: List[CoreNeed] = []
        self.learned_patterns: List[LearnedPattern] = []
        
        # Phase 3.6 新增: 专业能力画像
        self.expertise_profile = ExpertiseProfile()
        
        # 元数据
        self.last_updated: datetime = datetime.now()
        self.size_bytes: int = 0
        
        # 尝试加载已有数据
        self._load_if_exists()
        
        logger.debug(f"CoreMemory initialized for user {user_id}")
    
    def _load_if_exists(self):
        """如果文件存在，加载已有数据"""
        if self._file_path.exists():
            try:
                self.load()
                logger.debug(f"CoreMemory loaded from {self._file_path}")
            except Exception as e:
                logger.warning(f"Failed to load CoreMemory: {e}, using defaults")
    
    # ========== 用户偏好管理 ==========
    
    def set_preference(self, key: str, value: Any) -> None:
        """设置用户偏好"""
        self.user_profile.preferences[key] = value
        self._update_timestamp()
    
    def get_preference(self, key: str, default: Any = None) -> Any:
        """获取用户偏好"""
        return self.user_profile.preferences.get(key, default)
    
    def add_focus_area(self, area: str) -> None:
        """添加关注领域"""
        if area not in self.user_profile.focus_areas:
            self.user_profile.focus_areas.append(area)
        self._update_timestamp()
    
    def remove_focus_area(self, area: str) -> None:
        """移除关注领域"""
        if area in self.user_profile.focus_areas:
            self.user_profile.focus_areas.remove(area)
        self._update_timestamp()
    
    # ========== 高频实体管理 ==========
    
    def add_top_entity(self, entity_data: Dict[str, Any]) -> None:
        """
        添加高频实体
        
        Args:
            entity_data: 实体数据，包含 name, type, mention_count 等
        """
        name = entity_data.get("name")
        if name is None:
            raise ValueError("entity_data must contain 'name' field")
        
        entity = TopEntity(
            name=name,
            type=entity_data.get("type", "unknown"),
            mention_count=entity_data.get("mention_count", 1),
            last_mentioned=entity_data.get("last_mentioned", datetime.now().strftime("%Y-%m-%d"))
        )
        
        # 检查是否已存在
        existing = self._find_entity(entity.name)
        if existing:
            # 更新已存在的实体
            existing.mention_count = max(existing.mention_count, entity.mention_count)
            existing.last_mentioned = entity.last_mentioned
        else:
            # 添加新实体
            self.top_entities.append(entity)
        
        # 排序并限制数量
        self._sort_and_limit_entities()
        self._update_timestamp()
    
    def _find_entity(self, name: str) -> Optional[TopEntity]:
        """查找实体"""
        for entity in self.top_entities:
            if entity.name == name:
                return entity
        return None
    
    def _sort_and_limit_entities(self) -> None:
        """排序并限制实体数量"""
        # 按 mention_count 降序排序
        self.top_entities.sort(key=lambda e: e.mention_count, reverse=True)
        
        # 限制数量
        if len(self.top_entities) > self.MAX_TOP_ENTITIES:
            self.top_entities = self.top_entities[:self.MAX_TOP_ENTITIES]
    
    def update_entity_mention(self, name: str, increment: int = 1) -> None:
        """更新实体提及次数"""
        entity = self._find_entity(name)
        if entity:
            entity.mention_count += increment
            entity.last_mentioned = datetime.now().strftime("%Y-%m-%d")
            self._sort_and_limit_entities()
            self._update_timestamp()
    
    def can_promote_entity(self, entity: Dict[str, Any] | TopEntity) -> bool:
        """检查实体是否可以晋升"""
        if isinstance(entity, dict):
            mention_count = entity.get("mention_count", 0)
        else:
            mention_count = entity.mention_count
        return mention_count >= self.ENTITY_PROMOTION_THRESHOLD
    
    # ========== 核心需求管理 ==========
    
    def add_core_need(self, topic: str) -> None:
        """添加核心需求"""
        # 检查是否已存在
        existing = self._find_need(topic)
        if existing:
            existing.frequency += 1
        else:
            need = CoreNeed(topic=topic, frequency=1)
            self.core_needs.append(need)
        
        # 排序并限制数量
        self._sort_and_limit_needs()
        self._update_timestamp()
    
    def _find_need(self, topic: str) -> Optional[CoreNeed]:
        """查找需求"""
        for need in self.core_needs:
            if need.topic == topic:
                return need
        return None
    
    def _sort_and_limit_needs(self) -> None:
        """排序并限制需求数量"""
        # 按 frequency 降序排序
        self.core_needs.sort(key=lambda n: n.frequency, reverse=True)
        
        # 限制数量
        if len(self.core_needs) > self.MAX_CORE_NEEDS:
            self.core_needs = self.core_needs[:self.MAX_CORE_NEEDS]
    
    def update_need_frequency(self, topic: str, increment: int = 1) -> None:
        """更新需求频率"""
        need = self._find_need(topic)
        if need:
            need.frequency += increment
            self._sort_and_limit_needs()
            self._update_timestamp()
    
    def can_promote_need(self, need: Dict[str, Any] | CoreNeed) -> bool:
        """检查需求是否可以晋升"""
        if isinstance(need, dict):
            frequency = need.get("frequency", 0)
        else:
            frequency = need.frequency
        return frequency >= self.NEED_PROMOTION_THRESHOLD
    
    # ========== 学习结晶管理 ==========
    
    def add_learned_pattern(self, pattern_data: Dict[str, Any]) -> None:
        """
        添加学习结晶
        
        Args:
            pattern_data: 模式数据，包含 pattern_key, content, recurrence_count
        """
        pattern_key = pattern_data.get("pattern_key")
        if pattern_key is None:
            raise ValueError("pattern_data must contain 'pattern_key' field")
        
        pattern = LearnedPattern(
            pattern_key=pattern_key,
            content=pattern_data.get("content", ""),
            recurrence_count=pattern_data.get("recurrence_count", 1)
        )
        
        # 检查是否已存在（按 pattern_key）
        existing = self._find_pattern(pattern.pattern_key)
        if existing:
            # 合并：更新重复次数
            existing.recurrence_count = max(existing.recurrence_count, pattern.recurrence_count)
        else:
            # 添加新模式
            self.learned_patterns.append(pattern)
        
        # 排序并限制数量
        self._sort_and_limit_patterns()
        self._update_timestamp()
    
    def _find_pattern(self, pattern_key: str) -> Optional[LearnedPattern]:
        """查找模式"""
        for pattern in self.learned_patterns:
            if pattern.pattern_key == pattern_key:
                return pattern
        return None
    
    def _sort_and_limit_patterns(self) -> None:
        """排序并限制模式数量"""
        # 按 recurrence_count 降序排序
        self.learned_patterns.sort(key=lambda p: p.recurrence_count, reverse=True)
        
        # 限制数量
        if len(self.learned_patterns) > self.MAX_LEARNED_PATTERNS:
            self.learned_patterns = self.learned_patterns[:self.MAX_LEARNED_PATTERNS]
    
    def update_pattern_recurrence(self, pattern_key: str, increment: int = 1) -> None:
        """更新模式重复次数"""
        pattern = self._find_pattern(pattern_key)
        if pattern:
            pattern.recurrence_count += increment
            self._sort_and_limit_patterns()
            self._update_timestamp()
    
    def can_promote_pattern(self, pattern: Dict[str, Any] | LearnedPattern) -> bool:
        """检查模式是否可以晋升"""
        if isinstance(pattern, dict):
            recurrence_count = pattern.get("recurrence_count", 0)
        else:
            recurrence_count = pattern.recurrence_count
        return recurrence_count >= self.PATTERN_PROMOTION_THRESHOLD
    
    # ========== Phase 3.7: 自我学习集成 ==========
    
    def add_core_learning(self, learning: Dict[str, Any]) -> None:
        """
        添加核心学习记录（来自 LearningManager 晋升）
        
        这是 LearningManager.promote_learning() 的目标接口。
        学习记录晋升后存储到 learned_patterns。
        
        Args:
            learning: 学习记录字典，包含:
                - learning_id: 学习ID
                - category: 学习类别
                - pattern_key: 模式键
                - content: 学习内容
                - recurrence_count: 重复次数
                - promoted_at: 晋升时间
        """
        # 转换为 learned_pattern 格式
        pattern_data = {
            "pattern_key": learning.get("pattern_key") or learning.get("learning_id"),
            "content": learning.get("content", ""),
            "recurrence_count": learning.get("recurrence_count", 1)
        }
        
        # 使用现有的 add_learned_pattern 方法
        self.add_learned_pattern(pattern_data)
        
        logger.info(
            f"Core learning added: {pattern_data['pattern_key']}, "
            f"category={learning.get('category')}, "
            f"recurrence={pattern_data['recurrence_count']}"
        )
    
    def get_core_learnings(self) -> List[Dict[str, Any]]:
        """
        获取所有核心学习记录
        
        Returns:
            核心学习记录列表
        """
        return [p.to_dict() for p in self.learned_patterns]
    
    def find_core_learning(self, pattern_key: str) -> Optional[Dict[str, Any]]:
        """
        查找核心学习记录
        
        Args:
            pattern_key: 模式键
            
        Returns:
            学习记录字典，未找到返回 None
        """
        pattern = self._find_pattern(pattern_key)
        if pattern:
            return pattern.to_dict()
        return None
    
    def remove_core_learning(self, pattern_key: str) -> bool:
        """
        移除核心学习记录
        
        Args:
            pattern_key: 模式键
            
        Returns:
            是否成功移除
        """
        pattern = self._find_pattern(pattern_key)
        if pattern:
            self.learned_patterns.remove(pattern)
            self._update_timestamp()
            logger.info(f"Core learning removed: {pattern_key}")
            return True
        return False
    
    # ========== Phase 3.6: 专业画像管理 ==========
    
    def add_primary_domain(self, domain: str) -> None:
        """添加主要专业领域"""
        self.expertise_profile.add_primary_domain(domain)
        self._update_timestamp()
    
    def add_secondary_domain(self, domain: str) -> None:
        """添加次要专业领域"""
        self.expertise_profile.add_secondary_domain(domain)
        self._update_timestamp()
    
    def set_domain_depth(self, domain: str, depth: str) -> None:
        """设置领域深度"""
        self.expertise_profile.set_domain_depth(domain, depth)
        self._update_timestamp()
    
    def add_expertise_entity(
        self,
        name: str,
        importance: float = 0.5,
        mention_count: int = 1
    ) -> None:
        """添加专业实体到画像"""
        self.expertise_profile.add_core_entity(name, importance, mention_count)
        self._update_timestamp()
    
    def add_terminology(self, term: str, definition: str) -> None:
        """添加专业术语"""
        self.expertise_profile.add_terminology(term, definition)
        self._update_timestamp()
    
    def set_expertise_focus_areas(self, areas: List[str]) -> None:
        """设置专业关注点"""
        self.expertise_profile.set_focus_areas(areas)
        self._update_timestamp()
    
    # ========== 序列化 ==========
    
    def to_dict(self) -> Dict[str, Any]:
        """导出为字典"""
        return {
            "version": self.version,
            "user_id": self.user_id,
            "last_updated": self.last_updated.isoformat(),
            "size": f"{self.size_bytes / 1024:.2f}KB",
            "user_profile": self.user_profile.to_dict(),
            "top_entities": [e.to_dict() for e in self.top_entities],
            "core_needs": [n.to_dict() for n in self.core_needs],
            "learned_patterns": [p.to_dict() for p in self.learned_patterns],
            "expertise_profile": self.expertise_profile.to_dict()
        }
    
    def to_json(self) -> str:
        """导出为JSON"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    def _update_timestamp(self) -> None:
        """更新时间戳"""
        self.last_updated = datetime.now()
        self._calculate_size()
    
    def _calculate_size(self) -> None:
        """计算当前大小"""
        json_str = self.to_json()
        self.size_bytes = len(json_str.encode('utf-8'))
    
    # ========== 加载与保存 ==========
    
    def load(self) -> None:
        """从文件加载"""
        if not self._file_path.exists():
            logger.debug(f"CoreMemory file not found: {self._file_path}")
            return
        
        with open(self._file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 验证版本
        if data.get("version") != self.VERSION:
            logger.warning(f"CoreMemory version mismatch: {data.get('version')} vs {self.VERSION}")
        
        # 加载用户偏好
        profile_data = data.get("user_profile", {})
        self.user_profile = UserProfile(
            preferences=profile_data.get("preferences", {}),
            focus_areas=profile_data.get("focus_areas", [])
        )
        
        # 加载高频实体
        self.top_entities = [
            TopEntity(**e) for e in data.get("top_entities", [])
        ]
        
        # 加载核心需求
        self.core_needs = [
            CoreNeed(**n) for n in data.get("core_needs", [])
        ]
        
        # 加载学习结晶
        self.learned_patterns = [
            LearnedPattern(**p) for p in data.get("learned_patterns", [])
        ]
        
        # Phase 3.6: 加载专业画像
        expertise_data = data.get("expertise_profile", {})
        self.expertise_profile = ExpertiseProfile.from_dict(expertise_data)
        
        # 加载元数据
        last_updated_str = data.get("last_updated")
        if last_updated_str:
            try:
                self.last_updated = datetime.fromisoformat(last_updated_str)
            except ValueError:
                self.last_updated = datetime.now()
        
        self._calculate_size()
        
        logger.debug(f"CoreMemory loaded: {len(self.top_entities)} entities, {len(self.core_needs)} needs")
    
    def save(self) -> None:
        """保存到文件"""
        # 确保目录存在
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # 检查大小限制
        self._calculate_size()
        if self.size_bytes > self.SIZE_LIMIT_BYTES:
            logger.warning(f"CoreMemory exceeds size limit: {self.size_bytes} bytes > {self.SIZE_LIMIT_BYTES}")
            # 触发修剪（后续实现）
        
        # 保存
        with open(self._file_path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())
        
        logger.debug(f"CoreMemory saved to {self._file_path}, size: {self.size_bytes} bytes")
    
    def get_file_path(self) -> Path:
        """获取文件路径"""
        return self._file_path