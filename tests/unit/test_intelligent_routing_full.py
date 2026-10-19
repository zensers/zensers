"""
测试智能路由系统的集成功能

验证：
1. ContentLockManager 扩展方法 (update_dependencies, merge_sections, get_execution_progress)
2. ResearchOrchestrator.replan() 方法
3. ResearchOrchestrator.reanalyze() 方法
4. ExecutionEngine content_lock 支持
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


# 辅助函数：创建 SectionSpec
def make_section(section_id: str, role: str = "analysis", name: str = None, dependencies: list = None):
    """创建 SectionSpec 的辅助函数"""
    from src.core.task_structure import SectionSpec, SectionRole
    
    role_map = {
        "collection": SectionRole.DATA_COLLECTION,
        "analysis": SectionRole.ANALYSIS,
        "synthesis": SectionRole.SYNTHESIS,
        "supporting": SectionRole.SUPPORTING,
    }
    
    return SectionSpec(
        section_id=section_id,
        section_name=name or f"章节_{section_id}",
        section_role=role_map.get(role, SectionRole.ANALYSIS),
        content_dependency=dependencies or [],
    )


# 辅助函数：创建 TaskStructure
def make_task_structure(sections: list, task_id: str = "test_task", topic: str = "测试主题"):
    """创建 TaskStructure 的辅助函数"""
    from src.core.task_structure import TaskStructure
    return TaskStructure(
        task_id=task_id,
        topic=topic,
        sections=sections,
    )


# 辅助函数：创建 ExecutionPlan
def make_execution_plan(task_structure, plan_id: str = "test_plan"):
    """创建 ExecutionPlan 的辅助函数"""
    from src.core.dynamic_orchestrator import ExecutionPlan
    return ExecutionPlan(
        plan_id=plan_id,
        task_structure=task_structure,
        phases=[],
        content_lock_rules=[],
        total_agents=len(task_structure.sections),
        estimated_duration="10m",
    )


# 辅助函数：创建带依赖的 ExecutionPlan
def make_execution_plan_with_deps(task_structure, dependencies: dict, plan_id: str = "test_plan"):
    """
    创建带依赖规则的 ExecutionPlan
    
    Args:
        task_structure: 任务结构
        dependencies: {target_section: [required_sections]} 格式的依赖关系
        plan_id: 计划ID
    """
    from src.core.dynamic_orchestrator import ExecutionPlan, ContentLockRule
    
    rules = []
    for target, required in dependencies.items():
        rules.append(ContentLockRule(
            target_section=target,
            required_sections=required,
            lock_type="completion",
            quality_threshold=0.75,
            lock_reason=f"{target} depends on {required}",
        ))
    
    return ExecutionPlan(
        plan_id=plan_id,
        task_structure=task_structure,
        phases=[],
        content_lock_rules=rules,
        total_agents=len(task_structure.sections),
        estimated_duration="10m",
    )


class TestContentLockManagerExtensions:
    """测试 ContentLockManager 扩展方法"""
    
    def test_update_dependencies_empty_order(self):
        """测试空顺序更新"""
        from src.core.content_lock import ContentLockManager
        
        # 创建简单的执行计划
        section = make_section("section_1", "analysis", "测试章节")
        task_structure = make_task_structure([section])
        plan = make_execution_plan(task_structure)
        
        lock_manager = ContentLockManager(plan)
        
        # 空顺序应该跳过
        lock_manager.update_dependencies([])
        
        # 验证状态未改变
        assert "section_1" in lock_manager._section_statuses
    
    def test_update_dependencies_linear_order(self):
        """测试线性顺序更新"""
        from src.core.content_lock import ContentLockManager, SectionState
        
        # 创建执行计划
        sections = [
            make_section("s1", "analysis", "章节1"),
            make_section("s2", "analysis", "章节2"),
            make_section("s3", "synthesis", "章节3"),
        ]
        task_structure = make_task_structure(sections)
        plan = make_execution_plan(task_structure)
        
        lock_manager = ContentLockManager(plan)
        
        # 更新依赖顺序：s1 → s2 → s3
        lock_manager.update_dependencies(["s1", "s2", "s3"])
        
        # 验证第一个章节被解锁
        status_s1 = lock_manager.get_status("s1")
        assert status_s1.state == SectionState.PENDING
        assert status_s1.content_locked is False
        
        # 验证后续章节被锁定
        status_s2 = lock_manager.get_status("s2")
        assert status_s2.content_locked is True
        
        status_s3 = lock_manager.get_status("s3")
        assert status_s3.content_locked is True
        
        # 验证依赖规则
        assert "s2" in lock_manager._lock_rules
        assert "s3" in lock_manager._lock_rules
    
    def test_merge_sections_with_dict(self):
        """测试合并字典格式的章节"""
        from src.core.content_lock import ContentLockManager, SectionState
        
        # 创建基础计划
        section = make_section("existing", "analysis", "已存在章节")
        task_structure = make_task_structure([section])
        plan = make_execution_plan(task_structure)
        
        lock_manager = ContentLockManager(plan)
        
        # 合并新章节（字典格式）
        new_sections = [
            {"section_id": "new_1", "content_dependency": []},
            {"section_id": "new_2", "content_dependency": ["existing"]},
        ]
        
        lock_manager.merge_sections(new_sections)
        
        # 验证新章节被添加
        assert "new_1" in lock_manager._section_statuses
        assert "new_2" in lock_manager._section_statuses
        
        # 验证无依赖章节被解锁
        status_new1 = lock_manager.get_status("new_1")
        assert status_new1.state == SectionState.PENDING
        
        # 验证有依赖章节被锁定
        status_new2 = lock_manager.get_status("new_2")
        assert status_new2.content_locked is True
    
    def test_get_execution_progress_comprehensive(self):
        """测试获取完整执行进度"""
        from src.core.content_lock import ContentLockManager, SectionState
        
        # 创建执行计划
        sections = [make_section(f"s{i}", "analysis", f"章节{i}") for i in range(1, 6)]
        task_structure = make_task_structure(sections)
        plan = make_execution_plan(task_structure)
        
        lock_manager = ContentLockManager(plan)
        
        # 标记一些章节为不同状态
        lock_manager.mark_running("s1")
        lock_manager.mark_completed("s1", quality_score=0.9)
        lock_manager.mark_running("s2")
        # 注意：mark_failed 有重试机制，需要多次失败才会变成 FAILED
        # 第一次失败会保持 PENDING 状态等待重试
        lock_manager.mark_failed("s3", "测试失败")  # 第一次失败，会重试
        
        # 获取进度
        progress = lock_manager.get_execution_progress()
        
        # 验证统计
        assert progress["total"] == 5
        assert progress["completed"] == 1
        assert progress["running"] == 1
        # s3 第一次失败后是 PENDING 状态（等待重试），不是 FAILED
        assert progress["pending"] >= 1  # s3 在重试队列中
        assert "skipped" in progress
        
        # 验证章节分组
        assert "s1" in progress["sections_by_state"]["completed"]
        assert "s2" in progress["sections_by_state"]["running"]
        
        # 验证依赖图存在
        assert "dependency_graph" in progress
        
        # 验证预估时间存在
        assert "estimated_remaining_time" in progress
        assert "average_section_duration" in progress


class TestResearchOrchestratorReplan:
    """测试 ResearchOrchestrator.replan() 方法"""
    
    @pytest.mark.asyncio
    async def test_replan_task_not_found(self):
        """测试 replan 任务不存在"""
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        
        orchestrator = ResearchOrchestrator(use_intelligent_routing=False)
        
        result = await orchestrator.replan(
            task_id="nonexistent_task",
            new_order=["section_1", "section_2"],
        )
        
        assert result["status"] == "failed"
        assert "error" in result
    
    @pytest.mark.asyncio
    async def test_replan_empty_new_order(self):
        """测试 replan 空顺序"""
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        
        orchestrator = ResearchOrchestrator(use_intelligent_routing=False)
        
        result = await orchestrator.replan(
            task_id="test_task",
            new_order=[],
        )
        
        assert result["status"] == "failed"
        assert "error" in result
    
    @pytest.mark.asyncio
    async def test_replan_invalid_task_id(self):
        """测试 replan 无效任务ID"""
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        
        orchestrator = ResearchOrchestrator(use_intelligent_routing=False)
        
        result = await orchestrator.replan(
            task_id="",  # 空任务ID
            new_order=["section_1"],
        )
        
        assert result["status"] == "failed"
        assert "error" in result


class TestResearchOrchestratorReanalyze:
    """测试 ResearchOrchestrator.reanalyze() 方法"""
    
    @pytest.mark.asyncio
    async def test_reanalyze_task_not_found(self):
        """测试 reanalyze 任务不存在"""
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        
        orchestrator = ResearchOrchestrator(use_intelligent_routing=False)
        
        result = await orchestrator.reanalyze(
            task_id="nonexistent_task",
            updated_requirement={"topic": "新主题"},
        )
        
        assert result["status"] == "failed"
        assert "error" in result
    
    @pytest.mark.asyncio
    async def test_reanalyze_invalid_requirement(self):
        """测试 reanalyze 无效需求"""
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        
        orchestrator = ResearchOrchestrator(use_intelligent_routing=False)
        
        # 空需求
        result = await orchestrator.reanalyze(
            task_id="test_task",
            updated_requirement={},
        )
        
        assert result["status"] == "failed"
        
        # 非字典需求
        result2 = await orchestrator.reanalyze(
            task_id="test_task",
            updated_requirement="not a dict",
        )
        
        assert result2["status"] == "failed"
    
    @pytest.mark.asyncio
    async def test_reanalyze_intelligent_routing_not_enabled(self):
        """测试 reanalyze 智能路由未启用"""
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        from src.core.storage.research_result_store import ResearchResultStore, ResearchStatus
        
        orchestrator = ResearchOrchestrator(use_intelligent_routing=False)
        
        # 创建模拟的任务结果
        with patch.object(ResearchResultStore, 'load_result') as mock_load:
            mock_load.return_value = {
                "task_id": "test_task",
                "completed_agents": [],
                "sections": [],
            }
            
            result = await orchestrator.reanalyze(
                task_id="test_task",
                updated_requirement={"topic": "新主题"},
            )
            
            # 智能路由未启用时应该返回错误
            assert result["status"] == "failed"
            assert "Intelligent routing not enabled" in result.get("error", "")


class TestExecutionEngineContentLock:
    """测试 ExecutionEngine content_lock 支持"""
    
    @pytest.mark.asyncio
    async def test_execute_with_scheduler_content_lock_none(self):
        """测试 content_lock 为 None 时正常执行"""
        from src.core.orchestrator.execution.engine import ExecutionEngine, ExecutionConfig
        
        # 创建模拟的 message_bus 和 shared_memory
        message_bus = MagicMock()
        shared_memory = MagicMock()
        
        # 创建引擎
        config = ExecutionConfig()
        engine = ExecutionEngine(
            config=config,
            message_bus=message_bus,
            shared_memory=shared_memory,
        )
        
        # 验证引擎创建成功
        assert engine is not None
        assert engine.message_bus is message_bus
        assert engine.shared_memory is shared_memory


class TestIntegrationFlow:
    """集成流程测试"""
    
    def test_content_lock_manager_full_lifecycle(self):
        """测试 ContentLockManager 完整生命周期"""
        from src.core.content_lock import ContentLockManager, SectionState
        
        # 1. 创建执行计划（带依赖规则）
        sections = [
            make_section("data_collect", "collection", "数据收集"),
            make_section("analysis", "analysis", "分析"),
            make_section("summary", "synthesis", "摘要"),
        ]
        task_structure = make_task_structure(sections)
        
        # 添加依赖规则：analysis 依赖 data_collect，summary 依赖 analysis
        plan = make_execution_plan_with_deps(
            task_structure,
            dependencies={
                "analysis": ["data_collect"],
                "summary": ["analysis"],
            }
        )
        
        # 2. 初始化锁管理器
        lock_manager = ContentLockManager(plan)
        
        # 3. 检查初始状态
        progress = lock_manager.get_progress()
        assert progress["total"] == 3
        
        # 4. 执行第一个章节
        can_exec, reason = lock_manager.can_execute("data_collect")
        assert can_exec is True
        
        lock_manager.mark_running("data_collect")
        unlocked = lock_manager.mark_completed("data_collect", quality_score=0.9)
        
        # 5. 验证解锁
        assert "analysis" in unlocked
        
        # 6. 执行第二个章节
        can_exec, _ = lock_manager.can_execute("analysis")
        assert can_exec is True
        
        lock_manager.mark_running("analysis")
        unlocked = lock_manager.mark_completed("analysis", quality_score=0.85)
        
        # 7. 验证最终解锁
        assert "summary" in unlocked
        
        # 8. 获取最终进度
        progress = lock_manager.get_execution_progress()
        assert progress["completed"] == 2
        assert progress["progress_percent"] > 0
    
    def test_update_dependencies_preserves_completed(self):
        """测试 update_dependencies 保留已完成章节状态"""
        from src.core.content_lock import ContentLockManager, SectionState
        
        # 创建计划
        sections = [
            make_section("s1", "analysis", "章节1"),
            make_section("s2", "analysis", "章节2"),
        ]
        task_structure = make_task_structure(sections)
        plan = make_execution_plan(task_structure)
        
        lock_manager = ContentLockManager(plan)
        
        # 标记 s1 为完成
        lock_manager.mark_running("s1")
        lock_manager.mark_completed("s1", quality_score=0.9)
        
        # 更新依赖顺序
        lock_manager.update_dependencies(["s1", "s2"])
        
        # 验证 s1 仍为完成状态
        status_s1 = lock_manager.get_status("s1")
        assert status_s1.state == SectionState.COMPLETED
    
    def test_merge_sections_does_not_duplicate(self):
        """测试 merge_sections 不重复添加已存在的章节"""
        from src.core.content_lock import ContentLockManager
        
        # 创建计划
        section = make_section("existing", "analysis", "已存在章节")
        task_structure = make_task_structure([section])
        plan = make_execution_plan(task_structure)
        
        lock_manager = ContentLockManager(plan)
        
        # 尝试合并已存在的章节
        lock_manager.merge_sections([
            {"section_id": "existing", "content_dependency": []},
            {"section_id": "new", "content_dependency": []},
        ])
        
        # 验证只有一个新章节被添加
        assert len(lock_manager._section_statuses) == 2
        assert "existing" in lock_manager._section_statuses
        assert "new" in lock_manager._section_statuses


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
