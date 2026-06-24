# -*- coding: utf-8 -*-
"""
DreamModeScheduler - 做梦模式调度器

负责协调"做梦模式"的执行：
- 自动触发知识提取
- 主任务优先级检测
- 中断和恢复机制
- 资源管理

设计理念：
- 用户发起需求时立即暂停知识提取
- 利用闲置资源、空闲时间进行知识提取
- 渐进式学习，系统越用越强
"""

__all__ = ["DreamModeScheduler", "DreamModeState", "DreamModeConfig"]

import logging
import asyncio
import json
import time
import concurrent.futures
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List, Set
from dataclasses import dataclass, field
from enum import Enum, auto

from src.core.orchestrator.execution.task_utils import safe_create_task

logger = logging.getLogger(__name__)


class DreamModeState(Enum):
    """做梦模式状态"""
    IDLE = auto()          # 空闲
    RUNNING = auto()       # 正在执行
    PAUSED = auto()        # 已暂停（因主任务）
    COMPLETED = auto()     # 已完成
    ERROR = auto()         # 错误


@dataclass
class DreamModeConfig:
    """做梦模式配置"""
    # 触发条件
    trigger_after_task: bool = True      # 主任务完成后触发
    trigger_on_idle_seconds: int = 30    # 空闲多少秒后触发
    trigger_on_pending_threshold: int = 10  # 暂存数据达到多少条后触发
    
    # 执行控制
    batch_size: int = 10                 # 批量处理大小
    max_duration_seconds: int = 300      # 单次最大执行时间（5分钟）
    min_interval_seconds: int = 60       # 两次执行最小间隔
    
    # 资源控制
    max_concurrent_tasks: int = 1        # 最大并发任务数
    idle_check_interval: int = 10        # 空闲检查间隔（秒）

    # 知识源自动导入
    knowledge_source_dirs: tuple = ()
    """知识源目录列表，逗号分隔的环境变量 DREAM_SOURCE_DIRS"""

    knowledge_scan_interval: int = 300
    """目录扫描间隔（秒），环境变量 DREAM_SCAN_INTERVAL"""

    knowledge_auto_import: bool = True
    """启用自动导入，环境变量 DREAM_AUTO_IMPORT"""

    knowledge_store_to_bank: bool = True
    """导入后写入 SQLite，环境变量 DREAM_STORE_TO_BANK"""

    import_max_workers: int = 2
    """导入并发数，环境变量 DREAM_IMPORT_MAX_WORKERS"""

    @classmethod
    def from_env(cls) -> "DreamModeConfig":
        """从环境变量加载配置（DREAM_* 前缀）"""
        import os

        def _env(key: str, default: str) -> str:
            return os.getenv(f"DREAM_{key}", default)

        def _env_int(key: str, default: int) -> int:
            val = os.getenv(f"DREAM_{key}")
            return int(val) if val else default

        def _env_bool(key: str, default: bool) -> bool:
            val = os.getenv(f"DREAM_{key}")
            if val is None:
                return default
            return val.lower() in ("true", "1", "yes")

        raw_dirs = os.getenv("DREAM_SOURCE_DIRS", "")

        return cls(
            trigger_after_task=_env_bool("TRIGGER_AFTER_TASK", True),
            trigger_on_idle_seconds=_env_int("TRIGGER_ON_IDLE_SECONDS", 30),
            trigger_on_pending_threshold=_env_int("TRIGGER_ON_PENDING_THRESHOLD", 10),
            batch_size=_env_int("BATCH_SIZE", 10),
            max_duration_seconds=_env_int("MAX_DURATION_SECONDS", 300),
            min_interval_seconds=_env_int("MIN_INTERVAL_SECONDS", 60),
            max_concurrent_tasks=_env_int("MAX_CONCURRENT_TASKS", 1),
            idle_check_interval=_env_int("IDLE_CHECK_INTERVAL", 10),
            knowledge_auto_import=_env_bool("AUTO_IMPORT", True),
            knowledge_scan_interval=_env_int("SCAN_INTERVAL", 300),
            knowledge_source_dirs=tuple(
                d.strip() for d in raw_dirs.split(",") if d.strip()
            ),
            knowledge_store_to_bank=_env_bool("STORE_TO_BANK", True),
            import_max_workers=_env_int("IMPORT_MAX_WORKERS", 2),
        )


class DreamModeScheduler:
    """
    做梦模式调度器
    
    核心职责：
    1. 监控主任务状态，在适当时机启动知识提取
    2. 主任务优先：用户发起新需求时立即暂停
    3. 管理后台任务的生命周期
    
    使用方式：
    ```python
    scheduler = DreamModeScheduler(
        knowledge_bank=knowledge_bank,
        raw_data_store=raw_data_store,
        dream_mode=dream_mode
    )
    
    # 主任务完成时调用
    await scheduler.on_main_task_completed(research_id, raw_data)
    
    # 主任务开始时调用
    await scheduler.on_main_task_started()
    ```
    """
    
    def __init__(
        self,
        knowledge_bank: Any,
        raw_data_store: Any,
        dream_mode: Optional[Any] = None,
        config: Optional[DreamModeConfig] = None
    ):
        """
        初始化做梦模式调度器
        
        Args:
            knowledge_bank: 知识银行实例
            raw_data_store: 研究资料暂存区实例
            dream_mode: DreamMode 实例（可选，用于 CoreMemory 整合）
            config: 配置
        """
        self.knowledge_bank = knowledge_bank
        self.raw_data_store = raw_data_store
        self.dream_mode = dream_mode
        
        # 配置
        self.config = config or DreamModeConfig()
        
        # 状态
        self._state = DreamModeState.IDLE
        self._last_run_time: Optional[datetime] = None
        self._last_main_task_time: Optional[datetime] = None
        self._is_main_task_running = False
        
        # 知识提取阶段
        from .knowledge_extraction_phase import KnowledgeExtractionPhase
        self._extraction_phase = KnowledgeExtractionPhase(
            knowledge_bank=knowledge_bank,
            raw_data_store=raw_data_store
        )
        
        # 后台任务
        self._background_task: Optional[asyncio.Task] = None

        # 知识源导入线程池
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.config.import_max_workers,
            thread_name_prefix="dream-import",
        )

        # 目录扫描快照（mtime+size 差集去重）
        self._scan_snapshots: Dict[str, Set[tuple]] = {}
        self._last_scan_time: float = 0.0
        
        # 统计
        self._total_runs = 0
        self._total_items_processed = 0
        self._total_entities_learned = 0
        self._total_interrupts = 0
        
        logger.info(f"DreamModeScheduler initialized with config: {self.config}")
    
    # ========== 状态查询 ==========
    
    @property
    def state(self) -> DreamModeState:
        """获取当前状态"""
        return self._state
    
    @property
    def is_running(self) -> bool:
        """是否正在执行"""
        return self._state == DreamModeState.RUNNING
    
    @property
    def is_main_task_running(self) -> bool:
        """主任务是否正在运行"""
        return self._is_main_task_running
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "state": self._state.name,
            "total_runs": self._total_runs,
            "total_items_processed": self._total_items_processed,
            "total_entities_learned": self._total_entities_learned,
            "total_interrupts": self._total_interrupts,
            "last_run_time": self._last_run_time.isoformat() if self._last_run_time else None,
            "pending_count": self.raw_data_store.get_pending_count(),
            "extraction_stats": self._extraction_phase.get_stats()
        }
    
    # ========== 主任务优先机制 ==========
    
    async def on_main_task_started(self):
        """
        主任务开始时调用
        
        立即暂停知识提取，优先处理主任务
        """
        self._is_main_task_running = True
        self._last_main_task_time = datetime.now()
        
        if self.is_running:
            logger.info("Main task started, pausing dream mode")
            
            # 请求中断知识提取
            self._extraction_phase.request_interrupt()
            
            # 取消正在进行的提取任务
            cancelled = self.raw_data_store.cancel_all_in_progress()
            
            self._total_interrupts += 1
            self._state = DreamModeState.PAUSED
            
            logger.info(f"Dream mode paused, {cancelled} extraction tasks cancelled")
    
    async def on_main_task_completed(
        self,
        research_id: str,
        content: str,
        topic: Optional[str] = None,
        source_info: Optional[Dict[str, Any]] = None,
        domain: Optional[str] = None
    ):
        """
        主任务完成时调用
        
        将研究资料存入暂存区，并在适当时机启动知识提取
        """
        self._is_main_task_running = False
        self._last_main_task_time = datetime.now()
        
        # 存储研究资料到暂存区
        data_id = self.raw_data_store.store_research_data(
            research_id=research_id,
            content=content,
            topic=topic,
            source_info=source_info,
            domain=domain
        )
        
        logger.info(f"Research data stored: {data_id}")
        
        # 检查是否需要触发知识提取
        if self.config.trigger_after_task:
            await self._maybe_trigger_extraction()
    
    # ========== 触发机制 ==========
    
    async def _maybe_trigger_extraction(self):
        """检查是否应该触发知识提取"""
        # 如果主任务正在运行，不触发
        if self._is_main_task_running:
            logger.debug("Main task running, skip extraction")
            return
        
        # 如果已经在运行，不重复触发
        if self.is_running:
            logger.debug("Dream mode already running, skip")
            return
        
        # 检查最小间隔
        if self._last_run_time:
            elapsed = (datetime.now() - self._last_run_time).total_seconds()
            if elapsed < self.config.min_interval_seconds:
                logger.debug(f"Too soon since last run ({elapsed:.0f}s < {self.config.min_interval_seconds}s)")
                return
        
        # 检查暂存数据量
        pending_count = self.raw_data_store.get_pending_count()
        if pending_count < self.config.trigger_on_pending_threshold:
            logger.debug(f"Not enough pending data ({pending_count} < {self.config.trigger_on_pending_threshold})")
            return
        
        # 触发知识提取
        await self._start_extraction()
    
    async def _start_extraction(self):
        """启动知识提取"""
        if self.is_running:
            return
        
        self._state = DreamModeState.RUNNING
        self._last_run_time = datetime.now()
        self._total_runs += 1
        
        # 清除中断标志
        self._extraction_phase.clear_interrupt()
        
        logger.info("Starting dream mode knowledge extraction")
        
        try:
            # 执行知识提取
            result = await self._extraction_phase.run(
                batch_size=self.config.batch_size
            )
            
            # 更新统计
            self._total_items_processed += result.get("processed", 0)
            self._total_entities_learned += result.get("new_entities_learned", 0)
            
            if result.get("status") == "interrupted":
                self._state = DreamModeState.PAUSED
                logger.info(f"Dream mode interrupted after {result.get('duration_ms', 0):.0f}ms")
            else:
                self._state = DreamModeState.COMPLETED
                logger.info(f"Dream mode completed: {result}")
            
            # 同时运行 CoreMemory 整合（如果配置了 DreamMode）
            if self.dream_mode and not self._is_main_task_running:
                try:
                    core_result = self.dream_mode.run(trigger_reason="post_task")
                    logger.debug(f"CoreMemory consolidation: {core_result.get('status')}")
                except Exception as e:
                    logger.warning(f"CoreMemory consolidation failed: {e}")
            
        except Exception as e:
            self._state = DreamModeState.ERROR
            logger.error(f"Dream mode error: {e}")
        
        finally:
            # 如果不是暂停状态，重置为空闲
            if self._state != DreamModeState.PAUSED:
                self._state = DreamModeState.IDLE
    
    # ========== 手动控制 ==========
    
    async def run_now(self, batch_size: Optional[int] = None) -> Dict[str, Any]:
        """
        手动触发知识提取
        
        Args:
            batch_size: 批量处理大小（可选）
        
        Returns:
            提取结果
        """
        if self.is_running:
            return {
                "status": "already_running",
                "message": "Dream mode is already running"
            }
        
        self._state = DreamModeState.RUNNING
        self._last_run_time = datetime.now()
        self._total_runs += 1
        
        # 清除中断标志
        self._extraction_phase.clear_interrupt()
        
        try:
            result = await self._extraction_phase.run(
                batch_size=batch_size or self.config.batch_size
            )
            
            self._total_items_processed += result.get("processed", 0)
            self._total_entities_learned += result.get("new_entities_learned", 0)
            
            self._state = DreamModeState.COMPLETED
            return result
            
        except Exception as e:
            self._state = DreamModeState.ERROR
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def stop(self):
        """停止知识提取"""
        if not self.is_running:
            return
        
        logger.info("Stopping dream mode")
        self._extraction_phase.request_interrupt()
        self.raw_data_store.cancel_all_in_progress()
    
    # ========== 后台循环（可选） ==========
    
    async def start_background_loop(self):
        """
        启动后台循环
        
        定期检查：
        1. 知识源目录扫描（新增）
        2. 研究资料知识提取（已有）
        """
        logger.info("Starting dream mode background loop")
        
        while True:
            try:
                if self._is_main_task_running:
                    await asyncio.sleep(self.config.idle_check_interval)
                    continue

                # [优先级 1] 知识源目录扫描
                await self._maybe_scan_source_dirs()

                # [优先级 2] 研究资料知识提取（已有）
                if self._last_main_task_time:
                    idle_time = (datetime.now() - self._last_main_task_time).total_seconds()
                    if idle_time >= self.config.trigger_on_idle_seconds:
                        pending_count = self.raw_data_store.get_pending_count()
                        if pending_count > 0:
                            await self._start_extraction()

                await asyncio.sleep(self.config.idle_check_interval)

            except asyncio.CancelledError:
                logger.info("Background loop cancelled")
                break
            except Exception as e:
                logger.error(f"Background loop error: {e}")
                await asyncio.sleep(self.config.idle_check_interval)
    
    # ========== 知识源目录自动导入 ==========

    async def _maybe_scan_source_dirs(self):
        """检查并导入知识源目录中的新文件（受 scan_interval 控制）"""
        now = time.monotonic()
        if now - self._last_scan_time < self.config.knowledge_scan_interval:
            return
        self._last_scan_time = now

        dirs = self.config.knowledge_source_dirs
        if not dirs or not self.config.knowledge_auto_import:
            return

        for dir_path in dirs:
            if self._is_main_task_running:
                break

            source_dir = Path(dir_path)
            if not source_dir.is_dir():
                continue

            new_files = self._collect_new_files(source_dir)
            if not new_files:
                continue

            logger.info(f"Auto-importing {len(new_files)} files from {source_dir}")
            loop = asyncio.get_running_loop()

            for f in new_files:
                if self._is_main_task_running:
                    break
                await loop.run_in_executor(
                    self._executor,
                    self.knowledge_bank.import_file,
                    f,
                )

    def _collect_new_files(self, source_dir: Path) -> List[str]:
        """收集新增或变更的文件（mtime+size 快照差集，不做 MD5）"""
        supported_ext = {'.md', '.txt', '.csv', '.json', '.pdf', '.docx', '.xlsx', '.xls'}
        dir_key = str(source_dir.resolve())
        prev = self._scan_snapshots.get(dir_key, set())
        current: Set[tuple] = set()
        new: List[str] = []

        for f in sorted(source_dir.rglob("*")):
            if not f.is_file() or f.suffix.lower() not in supported_ext:
                continue
            stat = f.stat()
            rel = str(f.relative_to(source_dir))
            entry = (rel, stat.st_mtime, stat.st_size)
            current.add(entry)
            if entry not in prev:
                new.append(str(f))

        self._scan_snapshots[dir_key] = current
        return new

    # ========== 后台任务管理 ==========

    def start_background(self):
        """启动后台任务"""
        if self._background_task is None or self._background_task.done():
            self._background_task = safe_create_task(self.start_background_loop(), name="dream_scheduler.background_loop")
            logger.info("Background task started")

    def stop_background(self):
        """停止后台任务"""
        if self._background_task and not self._background_task.done():
            self._background_task.cancel()
            logger.info("Background task stopped")

    async def shutdown(self):
        """关闭调度器，清理线程池"""
        self.stop_background()
        self._executor.shutdown(wait=False)
        logger.info("DreamModeScheduler shut down")