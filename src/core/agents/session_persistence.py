"""
Session 持久化管理器

统一管理所有 Session 的持久化、恢复和清理。

Phase 3.10: Session 持久化与崩溃恢复

设计文档: docs/SESSION_PERSISTENCE_DESIGN.md
"""
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime
import json
import logging

from src.core.agents.agent_session import (
    AgentSession,
    AgentSessionRegistry,
    AgentSessionStatus,
)


logger = logging.getLogger(__name__)


class SessionPersistenceManager:
    """
    Session 持久化管理器
    
    统一管理所有 Session 的持久化、恢复和清理。
    
    Attributes:
        storage_path: 存储根目录
        sessions_dir: Session 文件目录
        registries_dir: Registry 文件目录
        results_dir: 结果文件目录
        checkpoints_dir: 检查点目录
    """
    
    def __init__(self, storage_path: Path = None, registries_dir: Path = None):
        """
        初始化持久化管理器
        
        Args:
            storage_path: 存储根目录（旧参数，保留兼容）
            registries_dir: Registry 目录（新参数，优先使用）
        """
        # 优先使用明确的 registries_dir
        if registries_dir is not None:
            self.registries_dir = Path(registries_dir)
            self.storage_path = self.registries_dir.parent
        elif storage_path is not None:
            self.storage_path = Path(storage_path)
            self.registries_dir = self.storage_path / "registries"
        else:
            # 从配置读取
            try:
                from src.config import settings
                registries_path = getattr(settings.system, 'registries_dir', 'data/registries')
                self.registries_dir = Path(registries_path)
                self.storage_path = self.registries_dir.parent
            except Exception:
                self.storage_path = Path("data")
                self.registries_dir = self.storage_path / "registries"
        
        self.sessions_dir = self.storage_path / "sessions" / "agents"
        self.results_dir = self.storage_path / "results"
        self.checkpoints_dir = self.storage_path / "checkpoints"
        
        # 确保目录存在
        for d in [self.sessions_dir, self.registries_dir, 
                  self.results_dir, self.checkpoints_dir]:
            d.mkdir(parents=True, exist_ok=True)
    
    # === 保存操作 ===
    
    def save_session(self, session: AgentSession) -> Path:
        """
        保存单个 Session
        
        Args:
            session: AgentSession 实例
            
        Returns:
            保存的文件路径
        """
        path = session.save(self.storage_path)
        logger.debug(f"Session saved: {session.session_id}")
        return path
    
    def save_registry(self, registry: AgentSessionRegistry) -> Path:
        """
        保存 Registry
        
        Args:
            registry: AgentSessionRegistry 实例
            
        Returns:
            保存的文件路径
        """
        path = registry.save(self.storage_path)
        logger.info(f"Registry saved: {registry.parent_session_id} ({registry.count()} sessions)")
        return path
    
    def save_result(self, session_id: str, result: Dict[str, Any]) -> Path:
        """
        保存执行结果
        
        Args:
            session_id: Session ID
            result: 执行结果
            
        Returns:
            保存的文件路径
        """
        result_data = {
            "session_id": session_id,
            "result": result,
            "saved_at": datetime.now().isoformat(),
        }
        
        path = self.results_dir / f"{session_id}_result.json"
        path.write_text(json.dumps(result_data, ensure_ascii=False, indent=2), encoding="utf-8")
        
        logger.debug(f"Result saved: {session_id}")
        return path
    
    # === 加载操作 ===
    
    def load_session(self, session_id: str) -> Optional[AgentSession]:
        """
        加载 Session
        
        Args:
            session_id: Session ID
            
        Returns:
            AgentSession 实例，不存在返回 None
        """
        path = self.sessions_dir / f"{session_id}.json"
        if path.exists():
            return AgentSession.load(path)
        return None
    
    def load_registry(self, parent_session_id: str) -> Optional[AgentSessionRegistry]:
        """
        加载 Registry
        
        Args:
            parent_session_id: 父 Session ID
            
        Returns:
            AgentSessionRegistry 实例，不存在返回 None
        """
        path = self.registries_dir / f"{parent_session_id}.json"
        if path.exists():
            return AgentSessionRegistry.load(path)
        return None
    
    def load_result(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        加载执行结果
        
        Args:
            session_id: Session ID
            
        Returns:
            结果数据，不存在返回 None
        """
        path = self.results_dir / f"{session_id}_result.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("result")
        return None
    
    # === 恢复操作 ===
    
    def find_interrupted_sessions(self) -> List[AgentSessionRegistry]:
        """
        查找中断的 Session（崩溃恢复入口）
        
        Returns:
            中断的 Registry 列表
        """
        return AgentSessionRegistry.find_interrupted(self.storage_path)
    
    def get_recovery_info(self, registry: AgentSessionRegistry) -> Dict[str, Any]:
        """
        获取恢复信息
        
        Args:
            registry: AgentSessionRegistry 实例
            
        Returns:
            恢复信息摘要
        """
        return {
            "parent_session_id": registry.parent_session_id,
            "total_sessions": registry.count(),
            "running_count": len(registry.get_running()),
            "pending_count": len(registry.get_pending()),
            "completed_count": len(registry.get_completed()),
            "failed_count": len(registry.get_failed()),
            "can_resume": len(registry.get_running()) > 0 or len(registry.get_pending()) > 0,
        }
    
    def get_recovery_summary(self) -> Dict[str, Any]:
        """
        获取所有中断任务的恢复摘要
        
        Returns:
            恢复摘要
        """
        interrupted = self.find_interrupted_sessions()
        
        return {
            "interrupted_count": len(interrupted),
            "sessions": [
                self.get_recovery_info(r) for r in interrupted
            ],
        }
    
    # === 清理操作 ===

    def delete_session(self, session_id: str) -> bool:
        """
        删除指定 session 的持久化文件。

        Args:
            session_id: Session ID

        Returns:
            是否成功删除了至少一个文件
        """
        deleted = False

        session_path = self.sessions_dir / f"{session_id}.json"
        if session_path.exists():
            try:
                session_path.unlink()
                logger.debug(f"Deleted hibernate session file: {session_id}")
                deleted = True
            except OSError as e:
                logger.warning(f"Failed to delete session file {session_id}: {e}")

        result_path = self.results_dir / f"{session_id}_result.json"
        if result_path.exists():
            try:
                result_path.unlink()
                logger.debug(f"Deleted hibernate result file: {session_id}")
                deleted = True
            except OSError as e:
                logger.warning(f"Failed to delete result file {session_id}: {e}")

        legacy_dir = self.results_dir / session_id
        if legacy_dir.exists():
            try:
                import shutil
                shutil.rmtree(legacy_dir)
                logger.debug(f"Deleted legacy results dir: {session_id}")
                deleted = True
            except OSError as e:
                logger.warning(f"Failed to delete legacy results {session_id}: {e}")

        return deleted

    def cleanup_completed_session(self, parent_session_id: str) -> bool:
        """
        清理已完成的 Session 文件
        
        Args:
            parent_session_id: 父 Session ID
            
        Returns:
            是否成功清理
        """
        # 加载 Registry 获取子 Session ID
        registry = self.load_registry(parent_session_id)
        if not registry:
            return False
        
        # 删除子 Session 文件
        for session in registry.child_sessions.values():
            session_path = self.sessions_dir / f"{session.session_id}.json"
            if session_path.exists():
                session_path.unlink()
                logger.debug(f"Deleted session file: {session.session_id}")
        
        # 删除 Registry 文件
        registry_path = self.registries_dir / f"{parent_session_id}.json"
        if registry_path.exists():
            registry_path.unlink()
            logger.info(f"Deleted registry: {parent_session_id}")
        
        # 删除结果文件
        result_dir = self.results_dir / parent_session_id
        if result_dir.exists():
            import shutil
            shutil.rmtree(result_dir)
            logger.debug(f"Deleted result directory: {parent_session_id}")
        
        return True
    
    def cleanup_all_completed(self) -> int:
        """
        清理所有已完成的 Session
        
        Returns:
            清理的数量
        """
        count = 0
        
        for registry_file in self.registries_dir.glob("*.json"):
            try:
                registry = AgentSessionRegistry.load(registry_file)
                
                # 检查是否所有 Session 都已完成
                all_done = all(
                    s.status in (AgentSessionStatus.COMPLETED, AgentSessionStatus.FAILED, AgentSessionStatus.CANCELLED)
                    for s in registry.child_sessions.values()
                )
                
                if all_done:
                    self.cleanup_completed_session(registry.parent_session_id)
                    count += 1
                    
            except Exception as e:
                logger.warning(f"Failed to cleanup {registry_file}: {e}")
        
        return count
    
    # === 统计信息 ===
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取持久化统计信息
        
        Returns:
            统计信息
        """
        registry_files = list(self.registries_dir.glob("*.json"))
        session_files = list(self.sessions_dir.glob("*.json"))
        result_files = list(self.results_dir.glob("*.json"))
        
        interrupted = self.find_interrupted_sessions()
        
        return {
            "storage_path": str(self.storage_path),
            "registry_count": len(registry_files),
            "session_count": len(session_files),
            "result_count": len(result_files),
            "interrupted_count": len(interrupted),
        }