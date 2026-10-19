# -*- coding: utf-8 -*-
"""
连接管理器
==========

统一管理 SQLite 数据库连接的生命周期。

职责：
- 创建和管理数据库连接
- 支持共享连接和独立连接
- 管理连接生命周期
- 配置连接参数（WAL、外键等）

不负责：
- Schema 创建（由 SchemaRegistry 负责）
- 数据访问（由 Store 负责）
- 业务逻辑（由 Service 负责）

设计原则：
- 单一职责：只管连接
- 依赖注入：Store 接收 ConnectionManager，不直接创建连接
"""

__all__ = [
    "ConnectionManager",
    "ConnectionConfig",
]

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Union, Any
import sqlite3
import threading
import logging
import atexit

logger = logging.getLogger(__name__)


@dataclass
class ConnectionConfig:
    """
    连接配置
    
    定义 SQLite 连接的行为参数。
    """
    enable_wal: bool = True           # 启用 WAL 模式（提升并发）
    enable_foreign_keys: bool = True  # 启用外键约束
    timeout: float = 5.0              # 连接超时（秒）
    check_same_thread: bool = False   # 线程检查（False 允许多线程访问）
    cache_size: int = -64000          # 缓存大小（负值表示 KB）
    temp_store: str = "MEMORY"        # 临时存储位置


class ConnectionManager:
    """
    连接管理器
    
    统一管理 SQLite 数据库连接的生命周期。
    
    支持两种连接模式：
    1. 共享连接：多个 Store 共用同一个连接（默认）
    2. 独立连接：每个 Store 有自己的连接
    
    用法：
        # 方式 1：基础用法
        manager = ConnectionManager(Path("data/users/user_001"))
        conn = manager.get_connection("knowledge_bank")
        
        # 方式 2：共享连接（推荐）
        manager = ConnectionManager(base_path)
        conn = manager.get_connection("knowledge_bank", shared=True)
        
        # 方式 3：从现有连接创建（兼容模式）
        manager = ConnectionManager.from_connection(existing_conn)
        
        # 关闭
        manager.close_all()
    
    线程安全：
        所有连接操作都通过锁保护，支持多线程访问。
    """
    
    def _initialize(
        self,
        base_path: Path,
        config: ConnectionConfig,
        auto_cleanup: bool,
    ) -> None:
        """
        内部初始化方法
        
        将初始化逻辑提取为单独方法，确保 from_connection 也能正确初始化。
        """
        self._base_path = base_path
        self._config = config
        self._auto_cleanup = auto_cleanup
        
        # 连接池
        self._shared_connections: Dict[str, sqlite3.Connection] = {}
        self._independent_connections: Dict[str, sqlite3.Connection] = {}
        
        # 线程安全
        self._lock = threading.RLock()
        
        # 注册清理
        if auto_cleanup:
            atexit.register(self.close_all)
    
    def __init__(
        self,
        base_path: Union[str, Path],
        config: Optional[ConnectionConfig] = None,
        auto_cleanup: bool = True,
    ):
        """
        初始化连接管理器
        
        Args:
            base_path: 数据库文件的基础路径
            config: 连接配置
            auto_cleanup: 是否在程序退出时自动关闭连接
        """
        self._initialize(
            base_path=Path(base_path),
            config=config or ConnectionConfig(),
            auto_cleanup=auto_cleanup,
        )
        if auto_cleanup:
            atexit.register(self.close_all)
        
        logger.debug(f"ConnectionManager initialized: {self._base_path}")
    
    @classmethod
    def from_connection(
        cls,
        connection: sqlite3.Connection,
        name: str = "default",
    ) -> "ConnectionManager":
        """
        从现有连接创建管理器（兼容模式）
        
        用于向后兼容，允许将现有连接包装为 ConnectionManager。
        
        Args:
            connection: 现有的 SQLite 连接
            name: 连接名称
            
        Returns:
            ConnectionManager 实例
        """
        # 创建实例并使用统一的初始化方法
        manager = cls.__new__(cls)
        manager._initialize(
            base_path=Path("."),
            config=ConnectionConfig(),
            auto_cleanup=False,
        )
        # 添加现有连接
        manager._shared_connections = {name: connection}
        
        logger.debug(f"ConnectionManager created from existing connection: {name}")
        return manager
    
    @classmethod
    def from_path(
        cls,
        db_path: Union[str, Path],
        config: Optional[ConnectionConfig] = None,
    ) -> "ConnectionManager":
        """
        从数据库路径创建管理器（单数据库模式）
        
        便捷方法，用于只有一个数据库文件的场景。
        
        Args:
            db_path: 数据库文件路径
            config: 连接配置
            
        Returns:
            ConnectionManager 实例
        """
        db_path = Path(db_path)
        manager = cls(db_path.parent, config)
        # 预创建连接
        manager.get_connection(db_path.stem, shared=True)
        return manager
    
    def get_connection(
        self,
        name: str,
        shared: bool = True,
        config: Optional[ConnectionConfig] = None,
    ) -> sqlite3.Connection:
        """
        获取数据库连接
        
        Args:
            name: 连接名称（不含 .db 扩展名）
            shared: 是否使用共享连接
            config: 连接配置（仅对新连接有效）
            
        Returns:
            SQLite 连接对象
        """
        with self._lock:
            if shared:
                if name not in self._shared_connections:
                    self._shared_connections[name] = self._create_connection(
                        name, config or self._config
                    )
                else:
                    # 健康检查：验证连接是否仍然有效
                    conn = self._shared_connections[name]
                    if not self._is_connection_healthy(conn):
                        logger.warning(f"Connection unhealthy, recreating: {name}")
                        conn.close()
                        self._shared_connections[name] = self._create_connection(
                            name, config or self._config
                        )
                return self._shared_connections[name]
            else:
                # 独立连接：每次都创建新连接
                conn = self._create_connection(name, config or self._config)
                # 存储以便后续清理
                key = f"{name}_{id(conn)}"
                self._independent_connections[key] = conn
                return conn
    
    def _is_connection_healthy(self, conn: sqlite3.Connection) -> bool:
        """
        检查连接是否健康
        
        Args:
            conn: SQLite 连接
            
        Returns:
            是否健康
        """
        try:
            # 执行简单查询测试连接
            conn.execute("SELECT 1")
            return True
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            logger.debug(f"Connection health check failed: {e}")
            return False
    
    def _create_connection(
        self,
        name: str,
        config: ConnectionConfig,
    ) -> sqlite3.Connection:
        """
        创建新的数据库连接
        
        Args:
            name: 连接名称
            config: 连接配置
            
        Returns:
            新的 SQLite 连接
        """
        # 构建数据库路径
        db_path = self._base_path / f"{name}.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 创建连接
        conn = sqlite3.connect(
            str(db_path),
            timeout=config.timeout,
            check_same_thread=config.check_same_thread,
        )
        
        # 设置 row_factory
        conn.row_factory = sqlite3.Row
        
        # 配置连接
        self._configure_connection(conn, config)
        
        logger.info(f"Connection created: {db_path}")
        return conn
    
    def _configure_connection(
        self,
        conn: sqlite3.Connection,
        config: ConnectionConfig,
    ) -> None:
        """
        配置连接参数
        
        Args:
            conn: SQLite 连接
            config: 连接配置
        """
        cursor = conn.cursor()
        
        # WAL 模式（提升并发性能）
        if config.enable_wal:
            cursor.execute("PRAGMA journal_mode = WAL")
        
        # 外键约束
        if config.enable_foreign_keys:
            cursor.execute("PRAGMA foreign_keys = ON")
        
        # 缓存大小（验证为整数）
        if isinstance(config.cache_size, int) and -1048576 <= config.cache_size <= 1048576:
            cursor.execute(f"PRAGMA cache_size = {config.cache_size}")
        
        # 临时存储（验证为预定义值）
        valid_temp_stores = {"DEFAULT", "FILE", "MEMORY", "WAL"}
        if config.temp_store.upper() in valid_temp_stores:
            cursor.execute(f"PRAGMA temp_store = {config.temp_store}")
        
        cursor.close()
    
    def close(self, name: str) -> bool:
        """
        关闭指定连接
        
        Args:
            name: 连接名称
            
        Returns:
            是否成功关闭
        """
        with self._lock:
            closed = False
            
            if name in self._shared_connections:
                try:
                    self._shared_connections[name].close()
                    del self._shared_connections[name]
                    closed = True
                    logger.debug(f"Shared connection closed: {name}")
                except Exception as e:
                    logger.error(f"Failed to close shared connection {name}: {e}")
            
            # 关闭所有同名独立连接
            keys_to_remove = [
                k for k in self._independent_connections 
                if k.startswith(f"{name}_")
            ]
            for key in keys_to_remove:
                try:
                    self._independent_connections[key].close()
                    del self._independent_connections[key]
                    closed = True
                except Exception as e:
                    logger.error(f"Failed to close independent connection {key}: {e}")
            
            return closed
    
    def close_all(self) -> None:
        """关闭所有连接"""
        with self._lock:
            # 关闭共享连接
            for name, conn in list(self._shared_connections.items()):
                try:
                    conn.close()
                    logger.debug(f"Shared connection closed: {name}")
                except Exception as e:
                    logger.error(f"Failed to close connection {name}: {e}")
            self._shared_connections.clear()
            
            # 关闭独立连接
            for key, conn in list(self._independent_connections.items()):
                try:
                    conn.close()
                    logger.debug(f"Independent connection closed: {key}")
                except Exception as e:
                    logger.error(f"Failed to close connection {key}: {e}")
            self._independent_connections.clear()
            
            logger.info("All connections closed")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取连接统计信息
        
        Returns:
            统计信息字典
        """
        with self._lock:
            return {
                "base_path": str(self._base_path),
                "shared_connections": list(self._shared_connections.keys()),
                "shared_count": len(self._shared_connections),
                "independent_count": len(self._independent_connections),
                "total_connections": len(self._shared_connections) + len(self._independent_connections),
                "config": {
                    "wal": self._config.enable_wal,
                    "foreign_keys": self._config.enable_foreign_keys,
                    "timeout": self._config.timeout,
                },
            }
    
    def __enter__(self) -> "ConnectionManager":
        """上下文管理器入口"""
        return self
    
    def __exit__(self, *args) -> None:
        """上下文管理器出口"""
        self.close_all()
    
    def __repr__(self) -> str:
        return (
            f"ConnectionManager(base_path={self._base_path}, "
            f"connections={len(self._shared_connections) + len(self._independent_connections)})"
        )
