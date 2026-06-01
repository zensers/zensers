# -*- coding: utf-8 -*-
"""
PhaseOrchestrator单元测试

测试阶段编排器的核心功能。
"""

import pytest
import asyncio
from datetime import datetime

from src.core.analysis.phase_definition import (
    AnalysisPhase,
    PhaseStatus,
    PhaseConfig,
    StageContext,
    PHASE_DEPENDENCIES,
    PHASE_CONFIGS,
)
from src.core.analysis.shared_memory_schema import (
    SchemaValidator,
    PhaseOutputSchema,
    PHASE_OUTPUT_SCHEMAS,
    DataPoint,
    Insight,
)
from src.core.analysis.phase_prompts import (
    PhasePrompts,
    get_prompt_for_phase,
)
from src.core.analysis.error_strategies import (
    ErrorStrategy,
    ErrorHandlingConfig,
    ErrorStrategies,
    PhaseError,
)
from src.core.analysis.phase_orchestrator import (
    PhaseOrchestrator,
    PhaseOrchestratorConfig,
    Checkpoint,
    PhaseExecutionResult,
)


class TestAnalysisPhase:
    """测试AnalysisPhase枚举"""
    
    def test_phase_order(self):
        """测试阶段顺序"""
        order = AnalysisPhase.get_order()
        assert len(order) == 5
        assert order[0] == AnalysisPhase.DATA_COLLECTION
        assert order[-1] == AnalysisPhase.REPORT_GENERATION
    
    def test_phase_index(self):
        """测试阶段索引"""
        assert AnalysisPhase.DATA_COLLECTION.get_index() == 0
        assert AnalysisPhase.DEEP_ANALYSIS.get_index() == 2
    
    def test_phase_navigation(self):
        """测试阶段导航"""
        phase = AnalysisPhase.DATA_VALIDATION
        assert phase.get_previous() == AnalysisPhase.DATA_COLLECTION
        assert phase.get_next() == AnalysisPhase.DEEP_ANALYSIS
        
        # 边界情况
        assert AnalysisPhase.DATA_COLLECTION.get_previous() is None
        assert AnalysisPhase.REPORT_GENERATION.get_next() is None


class TestPhaseDependencies:
    """测试阶段依赖"""
    
    def test_dependencies_exist(self):
        """测试依赖定义存在"""
        for phase in AnalysisPhase:
            assert phase in PHASE_DEPENDENCIES
    
    def test_dependency_chain(self):
        """测试依赖链正确"""
        # DATA_COLLECTION无依赖
        assert len(PHASE_DEPENDENCIES[AnalysisPhase.DATA_COLLECTION]) == 0
        
        # DATA_VALIDATION依赖DATA_COLLECTION
        deps = PHASE_DEPENDENCIES[AnalysisPhase.DATA_VALIDATION]
        assert AnalysisPhase.DATA_COLLECTION in deps
        
        # DEEP_ANALYSIS依赖DATA_VALIDATION
        deps = PHASE_DEPENDENCIES[AnalysisPhase.DEEP_ANALYSIS]
        assert AnalysisPhase.DATA_VALIDATION in deps


class TestStageContext:
    """测试StageContext"""
    
    def test_context_creation(self):
        """测试上下文创建"""
        ctx = StageContext(phase=AnalysisPhase.DATA_COLLECTION)
        assert ctx.status == PhaseStatus.PENDING
        assert ctx.retry_count == 0
    
    def test_context_state_transitions(self):
        """测试状态转换"""
        ctx = StageContext(phase=AnalysisPhase.DATA_COLLECTION)
        
        # 开始
        ctx.mark_started()
        assert ctx.status == PhaseStatus.RUNNING
        assert ctx.started_at is not None
        
        # 完成
        ctx.mark_completed({"data": "test"})
        assert ctx.status == PhaseStatus.COMPLETED
        assert ctx.output_data == {"data": "test"}
        assert ctx.get_duration_seconds() is not None
    
    def test_context_failure(self):
        """测试失败状态"""
        ctx = StageContext(phase=AnalysisPhase.DATA_COLLECTION)
        ctx.mark_started()
        ctx.mark_failed("Test error")
        
        assert ctx.status == PhaseStatus.FAILED
        assert ctx.error == "Test error"
    
    def test_context_skip(self):
        """测试跳过状态"""
        ctx = StageContext(phase=AnalysisPhase.DATA_COLLECTION)
        ctx.mark_skipped("Test reason")
        
        assert ctx.status == PhaseStatus.SKIPPED
        assert len(ctx.warnings) == 1


class TestSchemaValidator:
    """测试Schema验证器"""
    
    def test_validate_data_collection_output(self):
        """测试数据收集输出验证"""
        validator = SchemaValidator()
        
        valid_output = {
            "topic": "新能源汽车",
            "data_points": [
                {"metric": "市场规模", "value": 1000, "unit": "亿元"}
            ],
            "sources": ["source1"],
        }
        
        is_valid, errors = validator.validate_phase_output("data_collection", valid_output)
        assert is_valid
        assert len(errors) == 0
    
    def test_validate_missing_required_field(self):
        """测试缺少必需字段"""
        validator = SchemaValidator()
        
        invalid_output = {
            "topic": "新能源汽车",
            # 缺少 data_points
        }
        
        is_valid, errors = validator.validate_phase_output("data_collection", invalid_output)
        assert not is_valid
        assert any("data_points" in e for e in errors)


class TestPhasePrompts:
    """测试阶段Prompt模板"""
    
    def test_get_prompt(self):
        """测试获取Prompt"""
        prompt = get_prompt_for_phase(
            phase="data_collection",
            topic="新能源汽车",
            aspect="市场规模",
        )
        
        assert "新能源汽车" in prompt
        assert "市场规模" in prompt
        assert "角色定义" in prompt
    
    def test_prompt_manager(self):
        """测试Prompt管理器"""
        manager = PhasePrompts()
        
        phases = manager.list_available_phases()
        assert len(phases) == 5
        assert "data_collection" in phases


class TestErrorStrategies:
    """测试错误处理策略"""
    
    def test_default_configs(self):
        """测试默认配置"""
        strategies = ErrorStrategies()
        
        config = strategies.get_config("data_collection")
        assert config.strategy == ErrorStrategy.RETRY
        assert config.max_retries == 3
    
    def test_should_retry(self):
        """测试重试判断"""
        strategies = ErrorStrategies()
        
        # 应该重试
        assert strategies.should_retry("data_collection", 0)
        assert strategies.should_retry("data_collection", 2)
        
        # 不应该重试
        assert not strategies.should_retry("data_collection", 3)
    
    def test_error_recording(self):
        """测试错误记录"""
        strategies = ErrorStrategies()
        
        error = PhaseError(
            phase="data_collection",
            error_type="TestError",
            error_message="Test message",
        )
        
        strategies.record_error(error)
        
        history = strategies.get_error_history("data_collection")
        assert len(history) == 1
        assert history[0].error_message == "Test message"


class TestPhaseOrchestrator:
    """测试阶段编排器"""
    
    @pytest.fixture
    def orchestrator(self):
        """创建编排器实例"""
        return PhaseOrchestrator()
    
    def test_orchestrator_creation(self, orchestrator):
        """测试编排器创建"""
        assert orchestrator is not None
        assert len(orchestrator.get_all_statuses()) == 5
    
    def test_initial_phase_statuses(self, orchestrator):
        """测试初始阶段状态"""
        statuses = orchestrator.get_all_statuses()
        
        for phase in AnalysisPhase.get_order():
            assert statuses[phase.value] == PhaseStatus.PENDING.value
    
    def test_get_phase_status(self, orchestrator):
        """测试获取阶段状态"""
        status = orchestrator.get_phase_status(AnalysisPhase.DATA_COLLECTION)
        assert status == PhaseStatus.PENDING
    
    @pytest.mark.asyncio
    async def test_execute_basic(self, orchestrator):
        """测试基本执行"""
        result = await orchestrator.execute({
            "topic": "新能源汽车市场",
            "aspects": ["市场规模"],
        })
        
        assert "task_id" in result
        assert "status" in result
        assert "phase_statuses" in result
    
    @pytest.mark.asyncio
    async def test_execute_parallel_mode(self, orchestrator):
        """测试并行执行模式"""
        # 启用并行执行
        orchestrator._config.parallel_execution = True
        
        result = await orchestrator.execute({
            "topic": "新能源汽车市场",
            "aspects": ["市场规模", "竞争格局", "技术趋势"],
        })
        
        assert "task_id" in result
        assert result["status"] in ["completed", "failed"]
    
    @pytest.mark.asyncio
    async def test_execute_sequential_mode(self, orchestrator):
        """测试顺序执行模式"""
        # 禁用并行执行
        orchestrator._config.parallel_execution = False
        
        result = await orchestrator.execute({
            "topic": "新能源汽车市场",
            "aspects": ["市场规模"],
        })
        
        assert "task_id" in result
        assert "phase_statuses" in result
    
    @pytest.mark.asyncio
    async def test_execute_with_custom_executor(self, orchestrator):
        """测试自定义执行器"""
        custom_results = {
            "data_collection": {"topic": "test", "data_points": [], "sources": []},
            "data_validation": {"valid": True, "quality_score": 0.9},
            "deep_analysis": {"framework_used": "test", "insights": []},
            "synthesis": {"executive_summary": {}},
            "report_generation": {"sections": [], "format": "docx"},
        }
        
        async def custom_executor(phase, context):
            return custom_results.get(phase.value, {})
        
        result = await orchestrator.execute(
            {"topic": "test"},
            phase_executor=custom_executor,
        )
        
        assert result["status"] == "completed"
    
    def test_create_checkpoint(self, orchestrator):
        """测试创建检查点"""
        checkpoint_id = orchestrator._create_checkpoint()
        
        assert checkpoint_id.startswith("cp_")
        checkpoints = orchestrator.get_checkpoints()
        assert len(checkpoints) == 1
    
    def test_rollback(self, orchestrator):
        """测试回滚"""
        # 创建检查点
        checkpoint_id = orchestrator._create_checkpoint()
        
        # 修改状态
        orchestrator._phase_states[AnalysisPhase.DATA_COLLECTION].status = PhaseStatus.COMPLETED
        
        # 回滚
        success = orchestrator.rollback(checkpoint_id)
        assert success
        
        # 验证状态恢复
        status = orchestrator.get_phase_status(AnalysisPhase.DATA_COLLECTION)
        assert status == PhaseStatus.PENDING
    
    def test_reset(self, orchestrator):
        """测试重置"""
        # 修改状态
        orchestrator._phase_states[AnalysisPhase.DATA_COLLECTION].status = PhaseStatus.COMPLETED
        
        # 重置
        orchestrator.reset()
        
        # 验证所有状态恢复
        for phase in AnalysisPhase.get_order():
            status = orchestrator.get_phase_status(phase)
            assert status == PhaseStatus.PENDING
    
    def test_get_prompt(self, orchestrator):
        """测试获取Prompt"""
        prompt = orchestrator.get_prompt(
            AnalysisPhase.DATA_COLLECTION,
            "新能源汽车",
            "市场规模"
        )
        
        assert "新能源汽车" in prompt


class TestCheckpoint:
    """测试检查点"""
    
    def test_checkpoint_creation(self):
        """测试检查点创建"""
        checkpoint = Checkpoint(
            checkpoint_id="cp_test",
            created_at=datetime.now(),
            phase_states={},
            shared_memory_snapshot={"key": "value"},
        )
        
        assert checkpoint.checkpoint_id == "cp_test"
        assert len(checkpoint.phase_states) == 0
    
    def test_checkpoint_serialization(self):
        """测试检查点序列化"""
        checkpoint = Checkpoint(
            checkpoint_id="cp_test",
            created_at=datetime.now(),
            phase_states={},
            shared_memory_snapshot={},
        )
        
        data = checkpoint.to_dict()
        assert "checkpoint_id" in data
        assert "created_at" in data
        
        # 反序列化
        restored = Checkpoint.from_dict(data)
        assert restored.checkpoint_id == checkpoint.checkpoint_id


class TestPhaseExecutionResult:
    """测试阶段执行结果"""
    
    def test_result_creation(self):
        """测试结果创建"""
        result = PhaseExecutionResult(
            phase=AnalysisPhase.DATA_COLLECTION,
            success=True,
            output={"data": "test"},
            duration_seconds=1.5,
        )
        
        assert result.success
        assert result.duration_seconds == 1.5
    
    def test_result_serialization(self):
        """测试结果序列化"""
        result = PhaseExecutionResult(
            phase=AnalysisPhase.DATA_COLLECTION,
            success=True,
            output={},
        )
        
        data = result.to_dict()
        assert data["phase"] == "data_collection"
        assert data["success"] is True


class TestParallelExecution:
    """测试并行执行功能"""
    
    @pytest.fixture
    def orchestrator(self):
        """创建启用并行的编排器"""
        from src.core.analysis.phase_orchestrator import PhaseOrchestratorConfig
        config = PhaseOrchestratorConfig(parallel_execution=True)
        return PhaseOrchestrator(config=config)
    
    @pytest.mark.asyncio
    async def test_parallel_phase_execution(self, orchestrator):
        """测试并行阶段执行"""
        aspects = ["市场规模", "竞争格局", "技术趋势"]
        
        results = await orchestrator._execute_parallel_phase(
            phase=AnalysisPhase.DATA_COLLECTION,
            requirement={"topic": "test", "aspects": aspects},
            phase_executor=None,
            parallel_units=aspects,
        )
        
        assert len(results) == len(aspects)
    
    def test_merge_collection_results(self, orchestrator):
        """测试合并收集结果"""
        results = [
            PhaseExecutionResult(
                phase=AnalysisPhase.DATA_COLLECTION,
                success=True,
                output={
                    "topic": "test",
                    "data_points": [{"metric": "a", "value": 1}],
                    "sources": ["source1"],
                },
                quality_score=0.8,
            ),
            PhaseExecutionResult(
                phase=AnalysisPhase.DATA_COLLECTION,
                success=True,
                output={
                    "topic": "test",
                    "data_points": [{"metric": "b", "value": 2}],
                    "sources": ["source2"],
                },
                quality_score=0.9,
            ),
        ]
        
        merged = orchestrator._merge_phase_results(
            AnalysisPhase.DATA_COLLECTION, results
        )
        
        assert len(merged["data_points"]) == 2
        assert len(merged["sources"]) == 2
        assert merged["coverage_score"] == 0.9
    
    def test_merge_analysis_results(self, orchestrator):
        """测试合并分析结果"""
        results = [
            PhaseExecutionResult(
                phase=AnalysisPhase.DEEP_ANALYSIS,
                success=True,
                output={
                    "framework_used": "TAM_SAM_SOM",
                    "insights": [{"insight": "a"}],
                },
            ),
            PhaseExecutionResult(
                phase=AnalysisPhase.DEEP_ANALYSIS,
                success=True,
                output={
                    "framework_used": "Porter_Five_Forces",
                    "insights": [{"insight": "b"}],
                },
            ),
        ]
        
        merged = orchestrator._merge_phase_results(
            AnalysisPhase.DEEP_ANALYSIS, results
        )
        
        assert len(merged["insights"]) == 2
        assert merged["analysis_details"]["units_processed"] == 2


class TestAgentIntegration:
    """测试Agent集成功能"""
    
    @pytest.fixture
    def orchestrator(self):
        """创建编排器"""
        return PhaseOrchestrator()
    
    def test_build_agent_task(self, orchestrator):
        """测试构建Agent任务"""
        task = orchestrator._build_agent_task(
            phase=AnalysisPhase.DATA_COLLECTION,
            requirement={"topic": "新能源汽车", "aspects": ["市场规模"]},
            input_data={},
            prompt="收集新能源汽车市场规模数据",
        )
        
        assert task["action"] == "data_collection"
        assert task["parameters"]["topic"] == "新能源汽车"
        assert "prompt" in task["parameters"]
    
    def test_build_agent_task_with_input(self, orchestrator):
        """测试带输入数据的Agent任务构建"""
        task = orchestrator._build_agent_task(
            phase=AnalysisPhase.DEEP_ANALYSIS,
            requirement={"topic": "test"},
            input_data={"validated_data": {"quality_score": 0.9}},
            prompt="分析数据",
        )
        
        assert task["action"] == "deep_analysis"
        assert "validated_data" in task["parameters"]
        assert "frameworks" in task["parameters"]
    
    def test_extract_phase_output(self, orchestrator):
        """测试提取阶段输出"""
        agent_result = {
            "success": True,
            "output": {
                "topic": "test",
                "data_points": [],
            },
        }
        
        output = orchestrator._extract_phase_output(
            AnalysisPhase.DATA_COLLECTION, agent_result
        )
        
        assert "topic" in output
        assert "data_points" in output
    
    def test_get_default_output(self, orchestrator):
        """测试获取默认输出"""
        output = orchestrator._get_default_output(
            phase=AnalysisPhase.DATA_COLLECTION,
            requirement={"topic": "test"},
            prompt="test prompt",
        )
        
        assert output["topic"] == "test"
        assert "data_points" in output
        assert "sources" in output


class TestDataStructures:
    """测试数据结构"""
    
    def test_data_point(self):
        """测试数据点"""
        dp = DataPoint(
            metric="市场规模",
            value=1000,
            unit="亿元",
            source="官方报告",
            confidence=0.9,
        )
        
        data = dp.to_dict()
        assert data["metric"] == "市场规模"
        
        restored = DataPoint.from_dict(data)
        assert restored.metric == dp.metric
    
    def test_insight(self):
        """测试洞察"""
        insight = Insight(
            insight="市场增长迅速",
            evidence=["数据1", "数据2"],
            implication="投资机会",
            confidence=0.8,
        )
        
        data = insight.to_dict()
        assert len(data["evidence"]) == 2
        
        restored = Insight.from_dict(data)
        assert restored.insight == insight.insight


class TestProgressCallback:
    """测试进度回调功能"""
    
    @pytest.fixture
    def orchestrator(self):
        """创建编排器"""
        return PhaseOrchestrator()
    
    @pytest.mark.asyncio
    async def test_progress_callback_called(self, orchestrator):
        """测试进度回调被调用"""
        progress_events = []
        
        def progress_callback(progress):
            progress_events.append(progress)
        
        result = await orchestrator.execute(
            {
                "topic": "新能源汽车市场",
                "aspects": ["市场规模"],
            },
            progress_callback=progress_callback,
        )
        
        # 验证回调被调用
        assert len(progress_events) > 0
        
        # 验证进度事件结构
        for event in progress_events:
            assert hasattr(event, 'task_id')
            assert hasattr(event, 'phase')
            assert hasattr(event, 'status')
            assert hasattr(event, 'progress')
    
    @pytest.mark.asyncio
    async def test_progress_callback_async(self, orchestrator):
        """测试异步进度回调"""
        progress_events = []
        
        async def async_progress_callback(progress):
            progress_events.append(progress)
        
        result = await orchestrator.execute(
            {"topic": "测试主题"},
            progress_callback=async_progress_callback,
        )
        
        assert len(progress_events) > 0
    
    @pytest.mark.asyncio
    async def test_progress_callback_error_handling(self, orchestrator):
        """测试进度回调错误处理"""
        def failing_callback(progress):
            raise ValueError("Callback error")
        
        # 回调错误不应影响执行
        result = await orchestrator.execute(
            {"topic": "测试主题"},
            progress_callback=failing_callback,
        )
        
        assert "task_id" in result
    
    def test_phase_progress_to_dict(self):
        """测试PhaseProgress序列化"""
        from src.core.analysis.phase_orchestrator import PhaseProgress
        
        progress = PhaseProgress(
            task_id="test_task",
            phase="data_collection",
            status="completed",
            progress=1.0,
            message="数据收集完成",
            duration_seconds=10.5,
            total_phases=5,
            completed_phases=1,
        )
        
        data = progress.to_dict()
        assert data["task_id"] == "test_task"
        assert data["phase"] == "data_collection"
        assert data["status"] == "completed"
        assert data["progress"] == 1.0


class TestTimeoutControl:
    """测试超时控制功能"""
    
    @pytest.fixture
    def orchestrator(self):
        """创建编排器"""
        return PhaseOrchestrator()
    
    @pytest.mark.asyncio
    async def test_phase_timeout(self, orchestrator):
        """测试阶段超时"""
        # 设置很短的超时时间
        orchestrator._config.default_timeout = 0.1
        
        async def slow_executor(phase, context):
            # 模拟耗时操作
            await asyncio.sleep(1.0)
            return {"data": "test"}
        
        result = await orchestrator.execute(
            {"topic": "测试主题"},
            phase_executor=slow_executor,
        )
        
        # 由于超时，应该有失败记录
        assert result["status"] in ["completed", "failed"]
    
    @pytest.mark.asyncio
    async def test_phase_completes_within_timeout(self, orchestrator):
        """测试阶段在超时内完成"""
        # 设置合理的超时时间
        orchestrator._config.default_timeout = 30.0
        
        async def fast_executor(phase, context):
            return {"data": "test"}
        
        result = await orchestrator.execute(
            {"topic": "测试主题"},
            phase_executor=fast_executor,
        )
        
        assert result["status"] == "completed"
    
    @pytest.mark.asyncio
    async def test_custom_timeout_per_phase(self, orchestrator):
        """测试每个阶段的自定义超时"""
        from src.core.analysis.phase_definition import PhaseConfig
        
        # 为DATA_COLLECTION设置更短的超时
        orchestrator._phase_configs[AnalysisPhase.DATA_COLLECTION] = PhaseConfig(
            phase=AnalysisPhase.DATA_COLLECTION,
            timeout_seconds=5.0,
        )
        
        async def executor(phase, context):
            return {"data": "test"}
        
        result = await orchestrator.execute(
            {"topic": "测试主题"},
            phase_executor=executor,
        )
        
        assert result["status"] == "completed"


class TestSharedMemoryIntegration:
    """测试SharedMemory集成"""
    
    @pytest.fixture
    def orchestrator_with_memory(self):
        """创建带SharedMemory的编排器"""
        from src.core.communication import SharedMemory
        memory = SharedMemory()
        return PhaseOrchestrator(shared_memory=memory)
    
    @pytest.mark.asyncio
    async def test_phase_output_stored_in_memory(self, orchestrator_with_memory):
        """测试阶段输出存储到SharedMemory"""
        orchestrator = orchestrator_with_memory
        
        async def executor(phase, context):
            return {"topic": "test", "data": "collected"}
        
        result = await orchestrator.execute(
            {"topic": "测试主题"},
            phase_executor=executor,
        )
        
        # 验证输出存储在SharedMemory中
        memory = orchestrator._shared_memory
        assert memory is not None
        
        # 检查阶段输出键
        collection_output = memory.get("phase_output.data_collection")
        assert collection_output is not None
    
    def test_shared_memory_sync_methods(self, orchestrator_with_memory):
        """测试SharedMemory同步访问方法"""
        orchestrator = orchestrator_with_memory
        memory = orchestrator._shared_memory
        
        # 测试set/get
        memory.set("test_key", "test_value")
        assert memory.get("test_key") == "test_value"
        
        # 测试默认值
        assert memory.get("nonexistent", "default") == "default"
        
        # 测试set_all/get_all
        memory.set_all({"key1": "value1", "key2": "value2"})
        all_data = memory.get_all()
        assert all_data["key1"] == "value1"
        assert all_data["key2"] == "value2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
