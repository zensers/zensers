"""
任务分发器

职责：
- 任务准备（验证、参数补全）
- Agent匹配
- 任务优先级管理
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.agents.base import BaseAgent
    from src.core.agents.protocol import IAgent

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """任务优先级"""
    LOW = 0
    NORMAL = 5
    HIGH = 10
    URGENT = 20


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskOptions:
    """
    任务执行选项
    
    Attributes:
        timeout: 超时时间（秒）
        max_retries: 最大重试次数
        priority: 优先级
        fallback_chain: 降级链
        metadata: 元数据
    """
    timeout: float = 300.0
    max_retries: int = 3
    priority: TaskPriority = TaskPriority.NORMAL
    fallback_chain: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PreparedTask:
    """
    准备好的任务
    
    Attributes:
        task_id: 任务ID
        task: 任务数据
        agent_id: 目标Agent ID
        options: 执行选项
        prepared_at: 准备时间
        dependencies: 依赖任务ID列表
    """
    task_id: str
    task: Dict[str, Any]
    agent_id: str
    options: TaskOptions
    prepared_at: datetime = field(default_factory=datetime.now)
    dependencies: List[str] = field(default_factory=list)
    
    # 验证结果
    validation_errors: List[str] = field(default_factory=list)
    
    def is_valid(self) -> bool:
        """检查任务是否有效"""
        return len(self.validation_errors) == 0


class TaskDispatcher:
    """
    任务分发器
    
    职责：
    - 任务准备（验证、参数补全）
    - Agent匹配
    - 任务优先级管理
    
    使用示例:
        dispatcher = TaskDispatcher()
        
        prepared = dispatcher.prepare_task(
            task={"action": "analyze", "data": {...}},
            agent=agent,
            options=TaskOptions(timeout=60.0)
        )
        
        if prepared.is_valid():
            # 分发任务
            await coordinator.dispatch(prepared)
    """
    
    # 必需的任务字段
    REQUIRED_TASK_FIELDS = ["action"]
    
    # Agent能力匹配规则
    CAPABILITY_KEYWORDS = {
        "data_collection": ["search", "collect", "fetch", "crawl", "scrape"],
        "analysis": ["analyze", "process", "compute", "calculate", "evaluate"],
        "report": ["report", "document", "write", "generate", "format"],
        "quality_check": ["validate", "check", "verify", "audit", "review"],
    }
    
    def __init__(self):
        # 任务队列
        self._pending_tasks: Dict[str, PreparedTask] = {}
        
        # 统计
        self._total_dispatched = 0
        self._total_failed = 0
    
    def prepare_task(
        self,
        task: Dict[str, Any],
        agent: "IAgent",
        options: Optional[TaskOptions] = None,
        task_id: Optional[str] = None,
    ) -> PreparedTask:
        """
        准备任务
        
        Args:
            task: 任务数据
            agent: 目标Agent
            options: 执行选项
            task_id: 自定义任务ID
            
        Returns:
            PreparedTask: 准备好的任务
        """
        import uuid
        task_id = task_id or f"task_{uuid.uuid4().hex[:8]}"
        options = options or TaskOptions()
        
        validation_errors = []
        
        # 1. 验证任务结构
        for field_name in self.REQUIRED_TASK_FIELDS:
            if field_name not in task:
                validation_errors.append(f"Missing required field: {field_name}")
        
        # 2. 验证Agent
        if not agent:
            validation_errors.append("No agent provided")
        
        # 3. 补全任务参数
        task = self._complete_task_params(task, agent)
        
        # 4. 创建准备好的任务
        prepared = PreparedTask(
            task_id=task_id,
            task=task,
            agent_id=agent.agent_id if agent else "unknown",
            options=options,
            validation_errors=validation_errors,
        )
        
        # 5. 注册到待分发队列
        if prepared.is_valid():
            self._pending_tasks[task_id] = prepared
        
        return prepared
    
    def _complete_task_params(
        self,
        task: Dict[str, Any],
        agent: "IAgent",
    ) -> Dict[str, Any]:
        """
        补全任务参数
        
        Args:
            task: 原始任务
            agent: 目标Agent
            
        Returns:
            补全后的任务
        """
        completed = dict(task)
        
        # 添加Agent上下文
        if "agent_id" not in completed:
            completed["agent_id"] = agent.agent_id
        
        if "agent_type" not in completed and hasattr(agent, "agent_type"):
            completed["agent_type"] = agent.agent_type
        
        # 添加时间戳
        if "created_at" not in completed:
            completed["created_at"] = datetime.now().isoformat()
        
        return completed
    
    def match_agent(
        self,
        task: Dict[str, Any],
        available_agents: List["IAgent"],
    ) -> Optional["IAgent"]:
        """
        根据任务匹配最佳Agent
        
        Args:
            task: 任务数据
            available_agents: 可用Agent列表
            
        Returns:
            最佳匹配的Agent，无匹配返回None
        """
        if not available_agents:
            return None
        
        # 提取任务关键词
        action = task.get("action", "").lower()
        
        # 计算每个Agent的匹配分数
        best_agent = None
        best_score = -1
        
        for agent in available_agents:
            score = self._calculate_match_score(action, agent)
            if score > best_score:
                best_score = score
                best_agent = agent
        
        return best_agent
    
    def _calculate_match_score(
        self,
        action: str,
        agent: "IAgent",
    ) -> float:
        """
        计算Agent匹配分数
        
        Args:
            action: 任务动作
            agent: Agent实例
            
        Returns:
            匹配分数（0-1）
        """
        score = 0.0
        
        # 获取Agent配置
        config = getattr(agent, "config", {}) or {}
        agent_name = config.get("name", "").lower()
        skills = config.get("skills", [])
        
        # 1. 检查动作关键词匹配
        for capability, keywords in self.CAPABILITY_KEYWORDS.items():
            if any(kw in action for kw in keywords):
                if capability in agent_name:
                    score += 0.5
                if any(kw in str(skills).lower() for kw in keywords):
                    score += 0.3
        
        # 2. 检查Agent名称匹配
        if action in agent_name:
            score += 0.2
        
        return min(score, 1.0)
    
    def get_pending_task(self, task_id: str) -> Optional[PreparedTask]:
        """获取待分发任务"""
        return self._pending_tasks.get(task_id)
    
    def remove_pending_task(self, task_id: str) -> bool:
        """移除待分发任务"""
        if task_id in self._pending_tasks:
            del self._pending_tasks[task_id]
            return True
        return False
    
    def get_pending_count(self) -> int:
        """获取待分发任务数量"""
        return len(self._pending_tasks)
    
    def get_pending_by_priority(self) -> List[PreparedTask]:
        """按优先级获取待分发任务"""
        tasks = list(self._pending_tasks.values())
        tasks.sort(key=lambda t: t.options.priority.value, reverse=True)
        return tasks
    
    def record_dispatch(self, task_id: str) -> None:
        """记录任务分发"""
        self._total_dispatched += 1
        self.remove_pending_task(task_id)
    
    def record_failure(self, task_id: str, reason: str) -> None:
        """记录任务失败"""
        self._total_failed += 1
        logger.warning(f"Task {task_id} failed: {reason}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "pending_tasks": len(self._pending_tasks),
            "total_dispatched": self._total_dispatched,
            "total_failed": self._total_failed,
        }
