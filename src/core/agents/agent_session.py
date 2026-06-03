"""
Agent Session 层级管理模块

提供 Agent 的执行上下文追踪机制，解决以下架构缺陷：
1. Agent创建后没有独立Session
2. 无法追踪父子Session关系
3. 主控无法知道子Agent执行进度
4. 无法实现事件驱动的结果聚合

Phase 3.10 新增:
5. Session 持久化与崩溃恢复

设计文档: docs/AGENT_SESSION_MANAGEMENT.md, docs/SESSION_PERSISTENCE_DESIGN.md
"""
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from enum import Enum
import json
import uuid


class AgentSessionStatus(Enum):
    """
    Agent Session状态
    
    状态流转: PENDING -> RUNNING -> COMPLETED/FAILED/CANCELLED
    生命周期扩展: HIBERNATED -> RESUMING -> RUNNING
    """
    PENDING = "pending"       # 待执行
    RUNNING = "running"       # 执行中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"         # 失败
    CANCELLED = "cancelled"   # 已取消
    HIBERNATED = "hibernated" # 已休眠（v2.2新增）
    RESUMING = "resuming"     # 恢复中（v2.2新增）


class SessionOrigin(Enum):
    """
    Session来源类型
    
    参考: OMO session_origins (direct/appended)
    """
    PRIMARY = "primary"       # 主控Session（用户直接创建）
    SPAWNED = "spawned"       # 主控创建的子Session
    BACKGROUND = "background" # 后台任务Session


@dataclass
class AgentSession:
    """
    Agent Session - Agent的执行上下文
    
    每个Agent有独立的Session，与父Session形成层级关系。
    参考: OMO TaskSessionState
    
    Phase 3.10 新增: 持久化与崩溃恢复支持
    
    Attributes:
        session_id: Session唯一标识
        agent_id: 关联的Agent ID
        parent_session_id: 父Session ID（子Agent时设置）
        origin: Session来源类型
        status: 当前状态
        progress: 执行进度 (0.0-1.0)
        result: 执行结果
        task: 分配的任务定义
        context: 执行上下文
        created_at: 创建时间
        started_at: 开始执行时间
        completed_at: 完成时间
        updated_at: 更新时间
        error: 错误信息（失败时）
        checkpoint_data: 检查点数据（用于崩溃恢复）
        last_checkpoint_at: 上次检查点时间
    """
    session_id: str
    agent_id: str
    parent_session_id: Optional[str] = None
    origin: SessionOrigin = SessionOrigin.PRIMARY
    
    # 状态
    status: AgentSessionStatus = AgentSessionStatus.PENDING
    progress: float = 0.0
    result: Optional[Dict[str, Any]] = None
    
    # 任务信息
    task: Optional[Dict[str, Any]] = None
    context: Dict[str, Any] = field(default_factory=dict)
    
    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: datetime = field(default_factory=datetime.now)
    
    # 错误信息
    error: Optional[str] = None
    
    # 检查点数据（Phase 3.10）
    checkpoint_data: Optional[Dict[str, Any]] = None
    last_checkpoint_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典（用于序列化）
        
        Returns:
            包含所有属性的字典
        """
        result_for_dict = self.result
        if isinstance(result_for_dict, dict):
            result_for_dict = dict(result_for_dict)
            if "data_points" in result_for_dict:
                dp = result_for_dict.pop("data_points")
                result_for_dict["data_points_count"] = len(dp) if isinstance(dp, list) else 0
            if "sources" in result_for_dict:
                src = result_for_dict.pop("sources")
                result_for_dict["sources_count"] = len(src) if isinstance(src, list) else 0
        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "parent_session_id": self.parent_session_id,
            "origin": self.origin.value,
            "status": self.status.value,
            "progress": self.progress,
            "result": result_for_dict,
            "task": self.task,
            "context": self.context,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "error": self.error,
            "checkpoint_data": self.checkpoint_data,
            "last_checkpoint_at": self.last_checkpoint_at.isoformat() if self.last_checkpoint_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentSession":
        """
        从字典创建Session（用于反序列化）
        
        Args:
            data: 包含Session属性的字典
            
        Returns:
            AgentSession实例
        """
        # 解析枚举值
        origin = SessionOrigin(data.get("origin", "primary"))
        status = AgentSessionStatus(data.get("status", "pending"))
        
        # 解析时间戳
        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now()
        started_at = datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None
        completed_at = datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None
        updated_at = datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now()
        last_checkpoint_at = datetime.fromisoformat(data["last_checkpoint_at"]) if data.get("last_checkpoint_at") else None
        
        return cls(
            session_id=data["session_id"],
            agent_id=data["agent_id"],
            parent_session_id=data.get("parent_session_id"),
            origin=origin,
            status=status,
            progress=data.get("progress", 0.0),
            result=data.get("result"),
            task=data.get("task"),
            context=data.get("context", {}),
            created_at=created_at,
            started_at=started_at,
            completed_at=completed_at,
            updated_at=updated_at,
            error=data.get("error"),
            checkpoint_data=data.get("checkpoint_data"),
            last_checkpoint_at=last_checkpoint_at,
        )
    
    def start(self) -> None:
        """开始执行"""
        self.status = AgentSessionStatus.RUNNING
        self.started_at = datetime.now()
    
    def complete(self, result: Optional[Dict[str, Any]] = None) -> None:
        """完成执行"""
        self.status = AgentSessionStatus.COMPLETED
        self.progress = 1.0
        self.result = result
        self.completed_at = datetime.now()
    
    def fail(self, error: str) -> None:
        """执行失败"""
        self.status = AgentSessionStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()
    
    def cancel(self) -> None:
        """取消执行"""
        self.status = AgentSessionStatus.CANCELLED
        self.completed_at = datetime.now()
    
    def update_progress(self, progress: float) -> None:
        """更新进度"""
        self.progress = max(0.0, min(1.0, progress))
        self.updated_at = datetime.now()
    
    # === 持久化方法（Phase 3.10）===
    
    def save(self, storage_path: Path) -> Path:
        """
        保存 Session 到文件
        
        Args:
            storage_path: 存储根目录
            
        Returns:
            保存的文件路径
        """
        self.updated_at = datetime.now()
        data = self.to_dict()
        
        # 构建保存路径
        path = storage_path / "sessions" / "agents" / f"{self.session_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入文件
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        
        return path
    
    @classmethod
    def load(cls, path: Path) -> "AgentSession":
        """
        从文件加载 Session
        
        Args:
            path: Session 文件路径
            
        Returns:
            AgentSession 实例
            
        Raises:
            FileNotFoundError: 文件不存在
        """
        if not path.exists():
            raise FileNotFoundError(f"Session file not found: {path}")
        
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)
    
    def create_checkpoint(self, data: Dict[str, Any]) -> None:
        """
        创建检查点
        
        检查点用于崩溃恢复，保存当前执行状态。
        
        Args:
            data: 检查点数据（如：已处理的项目、当前步骤等）
        """
        self.checkpoint_data = data
        self.last_checkpoint_at = datetime.now()
        self.updated_at = datetime.now()
    
    def restore_from_checkpoint(self) -> Optional[Dict[str, Any]]:
        """
        从检查点恢复
        
        Returns:
            检查点数据，不存在返回 None
        """
        return self.checkpoint_data


@dataclass
class AgentSessionRegistry:
    """
    Agent Session注册表
    
    追踪主控Session下的所有子Agent Session。
    参考: OMO BoulderState.session_ids + session_origins
    
    Attributes:
        parent_session_id: 主控Session ID
        child_sessions: 子Session映射表
    """
    parent_session_id: str
    child_sessions: Dict[str, AgentSession] = field(default_factory=dict)
    
    def register(self, session: AgentSession) -> None:
        """
        注册子Session
        
        Args:
            session: 要注册的AgentSession
        """
        # 设置父Session ID
        session.parent_session_id = self.parent_session_id
        self.child_sessions[session.session_id] = session
    
    def unregister(self, session_id: str) -> bool:
        """
        注销Session
        
        Args:
            session_id: Session ID
            
        Returns:
            是否成功注销
        """
        if session_id in self.child_sessions:
            del self.child_sessions[session_id]
            return True
        return False
    
    def get_session(self, session_id: str) -> Optional[AgentSession]:
        """
        获取Session
        
        Args:
            session_id: Session ID
            
        Returns:
            AgentSession实例，不存在返回None
        """
        return self.child_sessions.get(session_id)
    
    def get_by_agent(self, agent_id: str) -> Optional[AgentSession]:
        """
        根据Agent ID获取Session
        
        Args:
            agent_id: Agent ID
            
        Returns:
            AgentSession实例，不存在返回None
        """
        for session in self.child_sessions.values():
            if session.agent_id == agent_id:
                return session
        return None
    
    def update_status(
        self,
        session_id: str,
        status: AgentSessionStatus,
        progress: Optional[float] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> bool:
        """
        更新Session状态
        
        Args:
            session_id: Session ID
            status: 新状态
            progress: 进度（可选）
            result: 结果（可选）
            error: 错误信息（可选）
            
        Returns:
            是否成功更新
        """
        session = self.child_sessions.get(session_id)
        if not session:
            return False
        
        session.status = status
        
        if progress is not None:
            session.update_progress(progress)
        
        if result is not None:
            session.result = result
        
        if error is not None:
            session.error = error
        
        # 更新时间戳
        if status == AgentSessionStatus.RUNNING and not session.started_at:
            session.started_at = datetime.now()
        
        if status in (AgentSessionStatus.COMPLETED, AgentSessionStatus.FAILED, AgentSessionStatus.CANCELLED):
            session.completed_at = datetime.now()
        
        # 更新时间戳
        session.updated_at = datetime.now()
        
        return True
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有Session状态摘要
        
        Returns:
            Session ID -> 状态摘要的映射
        """
        return {
            sid: {
                "agent_id": s.agent_id,
                "status": s.status.value,
                "progress": s.progress,
                "has_result": s.result is not None,
                "error": s.error,
            }
            for sid, s in self.child_sessions.items()
        }
    
    def get_pending(self) -> List[AgentSession]:
        """获取待执行的Session列表"""
        return [
            s for s in self.child_sessions.values()
            if s.status == AgentSessionStatus.PENDING
        ]
    
    def get_running(self) -> List[AgentSession]:
        """获取执行中的Session列表"""
        return [
            s for s in self.child_sessions.values()
            if s.status == AgentSessionStatus.RUNNING
        ]
    
    def get_completed(self) -> List[AgentSession]:
        """获取已完成的Session列表"""
        return [
            s for s in self.child_sessions.values()
            if s.status == AgentSessionStatus.COMPLETED
        ]
    
    def get_failed(self) -> List[AgentSession]:
        """获取失败的Session列表"""
        return [
            s for s in self.child_sessions.values()
            if s.status == AgentSessionStatus.FAILED
        ]
    
    def clear(self) -> None:
        """清空所有Session"""
        self.child_sessions.clear()
    
    def count(self) -> int:
        """获取Session数量"""
        return len(self.child_sessions)
    
    def count_by_status(self, status: AgentSessionStatus) -> int:
        """
        按状态统计Session数量
        
        Args:
            status: Session状态
            
        Returns:
            该状态的Session数量
        """
        return sum(1 for s in self.child_sessions.values() if s.status == status)
    
    # === 持久化方法（Phase 3.10）===
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典（用于序列化）
        
        Returns:
            包含所有 Session 的字典
        """
        return {
            "parent_session_id": self.parent_session_id,
            "child_sessions": {
                sid: session.to_dict()
                for sid, session in self.child_sessions.items()
            },
            "saved_at": datetime.now().isoformat(),
        }
    
    def save(self, storage_path: Path) -> Path:
        """
        保存 Registry 到文件
        
        Args:
            storage_path: 存储根目录
            
        Returns:
            保存的文件路径
        """
        data = self.to_dict()
        
        # 构建保存路径
        path = storage_path / "registries" / f"{self.parent_session_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入文件
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        
        return path
    
    @classmethod
    def load(cls, path: Path) -> "AgentSessionRegistry":
        """
        从文件加载 Registry
        
        Args:
            path: Registry 文件路径
            
        Returns:
            AgentSessionRegistry 实例
        """
        if not path.exists():
            raise FileNotFoundError(f"Registry file not found: {path}")
        
        data = json.loads(path.read_text(encoding="utf-8"))
        
        registry = cls(parent_session_id=data["parent_session_id"])
        
        for sid, session_data in data.get("child_sessions", {}).items():
            session = AgentSession.from_dict(session_data)
            registry.child_sessions[sid] = session
        
        return registry
    
    @classmethod
    def find_interrupted(cls, storage_path: Path) -> List["AgentSessionRegistry"]:
        """
        查找中断的 Session（崩溃恢复入口）
        
        扫描存储目录，找出包含 RUNNING 或 PENDING 状态 Session 的 Registry。
        
        Args:
            storage_path: 存储根目录
            
        Returns:
            中断的 Registry 列表
        """
        interrupted = []
        registries_dir = storage_path / "registries"
        
        if not registries_dir.exists():
            return interrupted
        
        for registry_file in registries_dir.glob("*.json"):
            try:
                registry = cls.load(registry_file)
                
                # 检查是否有未完成的 Session
                running = registry.get_running()
                pending = registry.get_pending()
                
                if running or pending:
                    interrupted.append(registry)
                    
            except Exception as e:
                # 跳过损坏的文件
                print(f"Warning: Failed to load registry {registry_file}: {e}")
                continue
        
        return interrupted


def generate_session_id(prefix: str = "session") -> str:
    """
    生成唯一的Session ID
    
    Args:
        prefix: ID前缀
        
    Returns:
        格式: {prefix}_{8位hex}
    """
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def create_agent_session(
    agent_id: str,
    parent_session_id: Optional[str] = None,
    origin: SessionOrigin = SessionOrigin.PRIMARY,
    task: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> AgentSession:
    """
    创建Agent Session的便捷函数
    
    Args:
        agent_id: Agent ID
        parent_session_id: 父Session ID
        origin: Session来源
        task: 任务定义
        context: 上下文
        
    Returns:
        新创建的AgentSession
    """
    return AgentSession(
        session_id=generate_session_id(),
        agent_id=agent_id,
        parent_session_id=parent_session_id,
        origin=origin,
        task=task,
        context=context or {},
    )