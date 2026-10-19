"""
数据链路管理器

追踪数据在Agent之间的流动，支持数据血缘追溯。

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/AGENT_LIFECYCLE_AND_DATA_MANAGEMENT.md
"""
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DataRecord:
    """
    数据记录
    
    记录单个数据单元的创建和传递信息。
    
    Attributes:
        data_id: 数据唯一标识
        agent_id: 创建该数据的Agent ID
        session_id: Agent的Session ID
        batch_index: 所属批次索引
        data_type: 数据类型（raw/analysis/adapted）
        content: 数据内容或引用
        created_at: 创建时间
        transmissions: 传递记录列表
        modifications: 修改记录列表
    """
    data_id: str
    agent_id: str
    session_id: str
    batch_index: int
    data_type: str
    content: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    transmissions: List[Dict[str, Any]] = field(default_factory=list)
    modifications: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "data_id": self.data_id,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "batch_index": self.batch_index,
            "data_type": self.data_type,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "transmissions": self.transmissions,
            "modifications": self.modifications,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DataRecord":
        """从字典创建"""
        return cls(
            data_id=data["data_id"],
            agent_id=data["agent_id"],
            session_id=data["session_id"],
            batch_index=data["batch_index"],
            data_type=data["data_type"],
            content=data.get("content", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            transmissions=data.get("transmissions", []),
            modifications=data.get("modifications", []),
        )


class DataLineageManager:
    """
    数据链路管理器
    
    功能：
    - 记录数据创建
    - 追踪数据传递
    - 查询数据血缘
    - 按Agent查询输出
    
    使用示例：
        manager = DataLineageManager(storage_path)
        
        # 记录数据创建
        data_id = manager.record_creation(
            agent_id="agent_001",
            session_id="session_001",
            batch_index=0,
            data_type="raw",
            content={"value": 100}
        )
        
        # 记录数据传递
        manager.record_transmission(
            data_id=data_id,
            from_agent_id="agent_001",
            to_agent_id="agent_002"
        )
        
        # 查询血缘
        lineage = manager.get_lineage(data_id)
    """
    
    def __init__(self, storage_path: Path):
        """
        初始化数据链路管理器
        
        Args:
            storage_path: 存储根目录
        """
        self.storage_path = Path(storage_path)
        self.lineage_dir = self.storage_path / "lineage"
        self.lineage_dir.mkdir(parents=True, exist_ok=True)
        
        # 内存索引
        self._data_index: Dict[str, DataRecord] = {}
        self._agent_to_data: Dict[str, List[str]] = {}
        self._transmission_index: Dict[str, List[str]] = {}  # to_agent -> data_ids
        
        # 加载已有数据
        self._load_index()
    
    def _load_index(self) -> None:
        """加载已有索引"""
        index_file = self.lineage_dir / "index.json"
        if not index_file.exists():
            return
        
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                index_data = json.load(f)
            
            # 加载数据索引
            for data_id, data_dict in index_data.get("data_index", {}).items():
                self._data_index[data_id] = DataRecord.from_dict(data_dict)
            
            # 加载Agent索引
            self._agent_to_data = index_data.get("agent_to_data", {})
            
            # 加载传递索引
            self._transmission_index = index_data.get("transmission_index", {})
            
            logger.info(f"Loaded {len(self._data_index)} data records from index")
            
        except Exception as e:
            logger.warning(f"Failed to load lineage index: {e}")
    
    def _save_index(self) -> None:
        """保存索引"""
        index_file = self.lineage_dir / "index.json"
        
        try:
            index_data = {
                "data_index": {
                    data_id: record.to_dict()
                    for data_id, record in self._data_index.items()
                },
                "agent_to_data": self._agent_to_data,
                "transmission_index": self._transmission_index,
                "updated_at": datetime.now().isoformat(),
            }
            
            with open(index_file, "w", encoding="utf-8") as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save lineage index: {e}")
    
    def generate_data_id(self, prefix: str = "data") -> str:
        """
        生成数据ID
        
        Args:
            prefix: ID前缀
            
        Returns:
            唯一数据ID
        """
        return f"{prefix}_{uuid.uuid4().hex[:8]}"
    
    def record_creation(
        self,
        agent_id: str,
        session_id: str,
        batch_index: int,
        data_type: str,
        content: Dict[str, Any],
    ) -> str:
        """
        记录数据创建
        
        Args:
            agent_id: 创建Agent ID
            session_id: Agent Session ID
            batch_index: 批次索引
            data_type: 数据类型（raw/analysis/adapted）
            content: 数据内容
            
        Returns:
            数据ID
        """
        data_id = self.generate_data_id(data_type)
        
        record = DataRecord(
            data_id=data_id,
            agent_id=agent_id,
            session_id=session_id,
            batch_index=batch_index,
            data_type=data_type,
            content=content,
        )
        
        # 更新索引
        self._data_index[data_id] = record
        
        if agent_id not in self._agent_to_data:
            self._agent_to_data[agent_id] = []
        self._agent_to_data[agent_id].append(data_id)
        
        # 保存
        self._save_index()
        
        logger.debug(f"Recorded data creation: {data_id} by agent {agent_id}")
        
        return data_id
    
    def record_transmission(
        self,
        data_id: str,
        from_agent_id: str,
        to_agent_id: str,
        transformation: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        记录数据传递
        
        Args:
            data_id: 数据ID
            from_agent_id: 来源Agent ID
            to_agent_id: 目标Agent ID
            transformation: 转换信息（可选）
        """
        if data_id not in self._data_index:
            logger.warning(f"Data {data_id} not found, cannot record transmission")
            return
        
        transmission_record = {
            "from_agent": from_agent_id,
            "to_agent": to_agent_id,
            "timestamp": datetime.now().isoformat(),
        }
        
        if transformation:
            transmission_record["transformation"] = transformation
        
        self._data_index[data_id].transmissions.append(transmission_record)
        
        # 更新传递索引
        if to_agent_id not in self._transmission_index:
            self._transmission_index[to_agent_id] = []
        self._transmission_index[to_agent_id].append(data_id)
        
        # 保存
        self._save_index()
        
        logger.debug(f"Recorded transmission: {data_id} from {from_agent_id} to {to_agent_id}")
    
    def record_modification(
        self,
        data_id: str,
        agent_id: str,
        modification_type: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        记录数据修改
        
        Args:
            data_id: 数据ID
            agent_id: 修改Agent ID
            modification_type: 修改类型
            details: 修改详情
        """
        if data_id not in self._data_index:
            logger.warning(f"Data {data_id} not found, cannot record modification")
            return
        
        modification_record = {
            "agent_id": agent_id,
            "type": modification_type,
            "timestamp": datetime.now().isoformat(),
            "details": details or {},
        }
        
        self._data_index[data_id].modifications.append(modification_record)
        
        # 保存
        self._save_index()
        
        logger.debug(f"Recorded modification: {data_id} by {agent_id}")
    
    def get_lineage(self, data_id: str) -> List[Dict[str, Any]]:
        """
        获取数据血缘
        
        返回数据的完整传递链。
        
        Args:
            data_id: 数据ID
            
        Returns:
            血缘记录列表
        """
        if data_id not in self._data_index:
            return []
        
        record = self._data_index[data_id]
        
        lineage = [{
            "data_id": data_id,
            "agent_id": record.agent_id,
            "data_type": record.data_type,
            "created_at": record.created_at.isoformat(),
            "batch_index": record.batch_index,
        }]
        
        # 追踪传递链
        for transmission in record.transmissions:
            lineage.append({
                "type": "transmission",
                "from_agent": transmission["from_agent"],
                "to_agent": transmission["to_agent"],
                "timestamp": transmission["timestamp"],
            })
        
        return lineage
    
    def get_agent_outputs(self, agent_id: str) -> List[str]:
        """
        获取Agent的所有输出数据ID
        
        Args:
            agent_id: Agent ID
            
        Returns:
            数据ID列表
        """
        return self._agent_to_data.get(agent_id, [])
    
    def get_agent_inputs(self, agent_id: str) -> List[str]:
        """
        获取Agent接收的所有数据ID
        
        Args:
            agent_id: Agent ID
            
        Returns:
            数据ID列表
        """
        return self._transmission_index.get(agent_id, [])
    
    def get_data_record(self, data_id: str) -> Optional[DataRecord]:
        """
        获取数据记录
        
        Args:
            data_id: 数据ID
            
        Returns:
            数据记录，不存在返回None
        """
        return self._data_index.get(data_id)
    
    def get_batch_data(self, batch_index: int) -> List[str]:
        """
        获取批次的所有数据ID
        
        Args:
            batch_index: 批次索引
            
        Returns:
            数据ID列表
        """
        return [
            data_id for data_id, record in self._data_index.items()
            if record.batch_index == batch_index
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            统计字典
        """
        return {
            "total_data_records": len(self._data_index),
            "total_agents_with_data": len(self._agent_to_data),
            "total_transmissions": sum(
                len(record.transmissions)
                for record in self._data_index.values()
            ),
            "data_types": {
                data_type: sum(
                    1 for r in self._data_index.values()
                    if r.data_type == data_type
                )
                for data_type in ["raw", "analysis", "adapted"]
            },
        }
    
    def clear(self) -> None:
        """清空所有数据"""
        self._data_index.clear()
        self._agent_to_data.clear()
        self._transmission_index.clear()
        self._save_index()
        logger.info("Cleared all lineage data")