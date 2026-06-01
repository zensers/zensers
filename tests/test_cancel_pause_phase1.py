"""
Phase 1 集成测试：取消/暂停/恢复

测试场景 (T1-T6):
T1: 正常取消 — 起 research → cancel → 验证 status=cancelled
T2: 暂停→恢复 — 起 research → pause → resume → 验证任务继续
T3: 暂停中取消 — pause → cancel → 验证 status=cancelled
T4: 取消后恢复 — cancel → resume → 验证返回"任务已取消"
T5: 快速 pause→resume→pause — 验证 Engine 不卡死
T6: Engine 未启动时 cancel — 验证 cancel 标志生效
"""
import asyncio
import pytest
from datetime import datetime

from src.core.orchestrator.execution.coordinator.cancel_manager import (
    CancelManager,
    get_cancel_manager,
)


# ============================================================
# CancelManager 单元测试
# ============================================================


class TestCancelManager:
    """CancelManager 核心逻辑测试"""

    def setup_method(self):
        self.cm = CancelManager()

    # ----- is_cancelled / cancel -----

    def test_cancel_sets_flag(self):
        assert not self.cm.is_cancelled("task_1")
        self.cm.cancel("task_1")
        assert self.cm.is_cancelled("task_1")

    def test_cancel_idempotent(self):
        self.cm.cancel("task_1")
        self.cm.cancel("task_1")  # second call should not raise
        assert self.cm.is_cancelled("task_1")

    def test_cancel_multiple_tasks(self):
        self.cm.cancel("task_a")
        self.cm.cancel("task_b")
        assert self.cm.is_cancelled("task_a")
        assert self.cm.is_cancelled("task_b")

    # ----- is_paused / pause -----

    def test_pause_sets_flag(self):
        assert not self.cm.is_paused("task_1")
        self.cm.pause("task_1")
        assert self.cm.is_paused("task_1")

    def test_pause_idempotent(self):
        self.cm.pause("task_1")
        self.cm.pause("task_1")
        assert self.cm.is_paused("task_1")

    # ----- resume -----

    def test_resume_clears_flag(self):
        self.cm.pause("task_1")
        assert self.cm.is_paused("task_1")
        self.cm.resume("task_1")
        assert not self.cm.is_paused("task_1")

    def test_resume_no_condition(self):
        # resume without prior pause should not raise
        self.cm.resume("task_1")
        assert not self.cm.is_paused("task_1")

    # ----- wait_for_resume_or_cancel (async) -----

    @pytest.mark.asyncio
    async def test_wait_not_paused_returns_immediately(self):
        """Task is not paused → should return immediately"""
        result = await self.cm.wait_for_resume_or_cancel("not_paused")
        assert result == "resumed"

    @pytest.mark.asyncio
    async def test_wait_resume_works(self):
        """Paused → resume → returns 'resumed'"""
        self.cm.pause("task_r")
        async def do_resume():
            await asyncio.sleep(0.05)
            self.cm.resume("task_r")
        asyncio.create_task(do_resume())
        result = await self.cm.wait_for_resume_or_cancel("task_r")
        assert result == "resumed"

    @pytest.mark.asyncio
    async def test_wait_cancel_from_paused(self):
        """Paused → cancel → returns 'cancelled'"""
        self.cm.pause("task_c")
        async def do_cancel():
            await asyncio.sleep(0.05)
            self.cm.cancel("task_c")
        asyncio.create_task(do_cancel())
        result = await self.cm.wait_for_resume_or_cancel("task_c")
        assert result == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_before_wait(self):
        """Cancel before wait_for_resume_or_cancel → immediate cancelled"""
        self.cm.pause("task_cb")
        self.cm.cancel("task_cb")
        result = await self.cm.wait_for_resume_or_cancel("task_cb")
        assert result == "cancelled"

    # ----- cleanup -----

    def test_cleanup_removes_all(self):
        self.cm.cancel("task_1")
        self.cm.pause("task_1")
        self.cm.cleanup("task_1")
        assert not self.cm.is_cancelled("task_1")
        assert not self.cm.is_paused("task_1")

    def test_cleanup_idempotent(self):
        self.cm.cleanup("never_existed")  # should not raise

    def test_cleanup_only_affects_one_task(self):
        self.cm.cancel("a")
        self.cm.cancel("b")
        self.cm.cleanup("a")
        assert not self.cm.is_cancelled("a")
        assert self.cm.is_cancelled("b")

    # ----- 全局单例 -----

    def test_get_cancel_manager_is_singleton(self):
        cm1 = get_cancel_manager()
        cm2 = get_cancel_manager()
        assert cm1 is cm2


# ============================================================
# 集成测试场景 (需要 mock Engine)
# ============================================================


@pytest.mark.asyncio
async def test_t1_normal_cancel():
    """T1: 正常取消"""
    cm = CancelManager()
    # Simulate Engine batch loop
    async def engine():
        for i in range(3):
            await asyncio.sleep(0.05)
            if cm.is_cancelled("t1"):
                return "cancelled"
        return "completed"

    async def user_cancel():
        await asyncio.sleep(0.08)
        cm.cancel("t1")

    result = await asyncio.gather(engine(), user_cancel())
    assert result[0] == "cancelled"


@pytest.mark.asyncio
async def test_t2_pause_resume():
    """T2: 暂停→恢复"""
    cm = CancelManager()
    cm.pause("t2")

    async def engine():
        if cm.is_paused("t2"):
            r = await cm.wait_for_resume_or_cancel("t2")
            return r
        return "running"

    async def user_resume():
        await asyncio.sleep(0.05)
        cm.resume("t2")

    result = await asyncio.gather(engine(), user_resume())
    assert result[0] == "resumed"


@pytest.mark.asyncio
async def test_t3_pause_then_cancel():
    """T3: 暂停中取消"""
    cm = CancelManager()
    cm.pause("t3")

    async def engine():
        r = await cm.wait_for_resume_or_cancel("t3")
        return r

    async def user_cancel():
        await asyncio.sleep(0.05)
        cm.cancel("t3")

    result = await asyncio.gather(engine(), user_cancel())
    assert result[0] == "cancelled"


@pytest.mark.asyncio
async def test_t4_cancel_then_resume():
    """T4: 取消后恢复 → 应返回 cancelled"""
    cm = CancelManager()
    cm.pause("t4")
    cm.cancel("t4")

    # resume should not override cancel
    cm.resume("t4")
    # is_cancelled should still be True
    assert cm.is_cancelled("t4")
    # wait_for should return cancelled
    result = await cm.wait_for_resume_or_cancel("t4")
    assert result == "cancelled"


@pytest.mark.asyncio
async def test_t5_rapid_pause_resume_pause():
    """T5: 快速 pause→resume→pause, Engine 不卡死"""
    cm = CancelManager()
    results = []

    async def engine():
        for i in range(3):
            if cm.is_paused("t5"):
                r = await cm.wait_for_resume_or_cancel("t5")
                results.append(f"batch_{i}_{r}")
            else:
                results.append(f"batch_{i}_running")
        return results

    async def rapid_ops():
        await asyncio.sleep(0.02)
        cm.pause("t5")
        await asyncio.sleep(0.02)
        cm.resume("t5")
        await asyncio.sleep(0.02)
        cm.pause("t5")
        await asyncio.sleep(0.05)
        cm.resume("t5")

    await asyncio.gather(engine(), rapid_ops())
    # Engine should not hang — all 3 batches should complete
    assert len(results) == 3


@pytest.mark.asyncio
async def test_t6_cancel_before_engine_starts():
    """T6: Engine 未启动时 cancel"""
    cm = CancelManager()
    cm.cancel("t6")

    async def engine():
        for i in range(3):
            await asyncio.sleep(0.02)
            if cm.is_cancelled("t6"):
                return "cancelled"
        return "completed"

    result = await engine()
    assert result == "cancelled"
