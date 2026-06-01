"""
批次管理数据结构

定义Agent批量创建和执行所需的数据结构。

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/AGENT_LIFECYCLE_AND_DATA_MANAGEMENT.md
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.agents.generic_agent import GenericAgent
    from src.core.agents.agent_session import AgentSession


class BatchStatus(Enum):
    """批次执行状态"""
    PENDING = "pending"      # 待执行
    RUNNING = "running"      # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 失败
    PARTIAL = "partial"      # 部分完成（有失败）


@dataclass
class BatchCreationResult:
    """
    批次创建结果
    
    Factory.create_batch() 的返回值。
    
    Attributes:
        batch_index: 批次索引（从0开始）
        agents: 创建的Agent实例列表
        sessions: 对应的Session列表
        created_at: 创建时间
    """
    batch_index: int
    agents: List["GenericAgent"] = field(default_factory=list)
    sessions: List["AgentSession"] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    
    def __len__(self) -> int:
        """返回Agent数量"""
        return len(self.agents)
    
    def get_agent_ids(self) -> List[str]:
        """获取所有Agent ID"""
        return [a.agent_id for a in self.agents]
    
    def get_session_ids(self) -> List[str]:
        """获取所有Session ID"""
        return [s.session_id for s in self.sessions]


@dataclass
class AgentExecutionRecord:
    """
    Agent执行记录
    
    记录单个Agent在批次中的执行情况。
    
    Attributes:
        session_id: Session唯一标识
        agent_id: Agent唯一标识
        batch_index: 所属批次索引
        aspect: 研究维度
        
        status: 执行状态
        progress: 执行进度（0.0-1.0）
        
        task_input: 任务输入
        task_output: 任务输出
        error: 错误信息
        
        created_at: 创建时间
        started_at: 开始时间
        completed_at: 完成时间
        
        raw_data_ref: 原始数据引用ID
        analysis_ref: 分析结果引用ID
    """
    # 标识
    session_id: str
    agent_id: str
    batch_index: int
    aspect: str
    
    # 状态
    status: BatchStatus = BatchStatus.PENDING
    progress: float = 0.0
    
    # 输入输出
    task_input: Dict[str, Any] = field(default_factory=dict)
    task_output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # 数据引用
    raw_data_ref: Optional[str] = None
    analysis_ref: Optional[str] = None
    
    def start(self) -> None:
        """标记开始执行"""
        self.status = BatchStatus.RUNNING
        self.started_at = datetime.now()
    
    def complete(self, result: Dict[str, Any]) -> None:
        """标记成功完成"""
        self.status = BatchStatus.COMPLETED
        self.task_output = result
        self.progress = 1.0
        self.completed_at = datetime.now()
    
    def fail(self, error: str) -> None:
        """标记失败"""
        self.status = BatchStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()
    
    def update_progress(self, progress: float) -> None:
        """更新进度"""
        self.progress = max(0.0, min(1.0, progress))
    
    def set_raw_data_ref(self, ref: str) -> None:
        """设置原始数据引用"""
        self.raw_data_ref = ref
    
    def set_analysis_ref(self, ref: str) -> None:
        """设置分析结果引用"""
        self.analysis_ref = ref
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "batch_index": self.batch_index,
            "aspect": self.aspect,
            "status": self.status.value,
            "progress": self.progress,
            "task_input": self.task_input,
            "task_output": self.task_output,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "raw_data_ref": self.raw_data_ref,
            "analysis_ref": self.analysis_ref,
        }


@dataclass
class BatchExecutionResult:
    """
    批次执行结果
    
    记录整个批次的执行情况。
    
    Attributes:
        batch_index: 批次索引
        task_id: 所属任务ID
        aspects: 研究维度列表
        agent_records: Agent执行记录字典
        
        status: 批次状态
        started_at: 开始时间
        completed_at: 完成时间
        
        total_agents: Agent总数
        completed_agents: 成功数量
        failed_agents: 失败数量
    """
    # 标识
    batch_index: int
    task_id: str
    
    # 批次信息
    aspects: List[str] = field(default_factory=list)
    agent_records: Dict[str, AgentExecutionRecord] = field(default_factory=dict)
    
    # 状态
    status: BatchStatus = BatchStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # 统计
    total_agents: int = 0
    completed_agents: int = 0
    failed_agents: int = 0
    
    def add_agent_record(self, record: AgentExecutionRecord) -> None:
        """添加Agent执行记录"""
        self.agent_records[record.agent_id] = record
        self.total_agents += 1
    
    def start_batch(self) -> None:
        """标记批次开始"""
        self.status = BatchStatus.RUNNING
        self.started_at = datetime.now()
    
    def complete_batch(self) -> None:
        """标记批次完成"""
        self._update_stats()
        
        if self.failed_agents == 0:
            self.status = BatchStatus.COMPLETED
        elif self.completed_agents > 0:
            self.status = BatchStatus.PARTIAL
        else:
            self.status = BatchStatus.FAILED
        
        self.completed_at = datetime.now()
    
    def _update_stats(self) -> None:
        """更新统计信息"""
        self.completed_agents = sum(
            1 for r in self.agent_records.values()
            if r.status == BatchStatus.COMPLETED
        )
        self.failed_agents = sum(
            1 for r in self.agent_records.values()
            if r.status == BatchStatus.FAILED
        )
    
    def get_successful_results(self) -> List[Dict[str, Any]]:
        """获取成功的结果列表"""
        return [
            r.task_output for r in self.agent_records.values()
            if r.status == BatchStatus.COMPLETED and r.task_output
        ]
    
    def get_failed_agents(self) -> List[str]:
        """获取失败的Agent ID列表"""
        return [
            r.agent_id for r in self.agent_records.values()
            if r.status == BatchStatus.FAILED
        ]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "batch_index": self.batch_index,
            "task_id": self.task_id,
            "aspects": self.aspects,
            "agent_records": {
                agent_id: record.to_dict()
                for agent_id, record in self.agent_records.items()
            },
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_agents": self.total_agents,
            "completed_agents": self.completed_agents,
            "failed_agents": self.failed_agents,
        }