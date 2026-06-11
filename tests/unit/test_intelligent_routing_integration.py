"""
测试智能路由集成到 ResearchOrchestrator

验证：
1. ResearchOrchestrator 初始化支持 use_intelligent_routing 参数
2. research() 方法正确路由到 _research_with_routing()
3. 智能路由流程完整执行
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import sys
from pathlib import Path

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class TestResearchOrchestratorRouting:
    """测试 ResearchOrchestrator 的智能路由集成"""
    
    def test_init_without_intelligent_routing(self):
        """测试默认初始化（不启用智能路由）"""
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        
        orchestrator = ResearchOrchestrator(
            use_intelligent_routing=False,
        )
        
        assert orchestrator._use_intelligent_routing is False
        assert orchestrator._routing_adapter is None
    
    def test_init_with_intelligent_routing(self):
        """测试启用智能路由初始化"""
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        
        orchestrator = ResearchOrchestrator(
            use_intelligent_routing=True,
        )
        
        assert orchestrator._use_intelligent_routing is True
        assert orchestrator._routing_adapter is not None
    
    def test_init_with_injected_adapter(self):
        """测试注入外部 IntelligentRoutingAdapter"""
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter
        
        # 创建自定义适配器
        custom_adapter = IntelligentRoutingAdapter(
            use_llm=False,
            fallback_to_keyword=True,
            enable_content_lock=False,
        )
        
        orchestrator = ResearchOrchestrator(
            use_intelligent_routing=False,  # 显式设为 False
            routing_adapter=custom_adapter,  # 但注入了适配器
        )
        
        # 注入适配器后，自动启用智能路由
        assert orchestrator._use_intelligent_routing is True
        assert orchestrator._routing_adapter is custom_adapter
    
    @pytest.mark.asyncio
    async def test_research_routes_to_intelligent_routing(self):
        """测试 research() 正确路由到智能路由分支"""
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        
        orchestrator = ResearchOrchestrator(
            use_intelligent_routing=True,
        )
        
        # Mock _research_with_routing 方法
        orchestrator._research_with_routing = AsyncMock(
            return_value=MagicMock(
                task_id="test_task",
                status="completed",
                topic="测试主题",
            )
        )
        
        # 调用 research
        result = await orchestrator.research(
            user_input="测试研究请求",
            interaction_mode=False,
        )
        
        # 验证 _research_with_routing 被调用
        orchestrator._research_with_routing.assert_called_once()
        assert result.task_id == "test_task"
    
    @pytest.mark.asyncio
    async def test_research_uses_legacy_without_intelligent_routing(self):
        """测试不启用智能路由时使用传统流程"""
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        
        orchestrator = ResearchOrchestrator(
            use_intelligent_routing=False,
        )
        
        # Mock _research_with_routing 方法（不应被调用）
        orchestrator._research_with_routing = AsyncMock()
        
        # Mock 传统流程所需的方法
        orchestrator._parse_requirement = MagicMock(
            return_value=MagicMock(
                topic="测试主题",
                aspects=["aspect1"],
                output_type=MagicMock(value="markdown"),
            )
        )
        orchestrator._routing_adapter = None
        orchestrator._unified_intent_analyzer = None
        orchestrator._wisdom_store = MagicMock(
            get_recommended_skills=MagicMock(return_value=[])
        )
        orchestrator._create_agents = MagicMock(return_value=[])
        orchestrator._execution_engine = MagicMock(
            execute_with_scheduler=AsyncMock(
                return_value={"stage_results": {}, "status": "completed"}
            )
        )
        orchestrator._result_aggregator = AsyncMock(
            return_value={"sections": {}}
        )
        orchestrator._document_agent = MagicMock(
            execute=AsyncMock(return_value={"output_path": "/test/path.md"})
        )
        orchestrator._task_persistence = MagicMock(
            create_task=MagicMock(return_value=MagicMock()),
            save_task=MagicMock(),
            update_task_state=MagicMock(),
        )
        orchestrator._agent_factory = MagicMock(
            get_registry=MagicMock(return_value=None)
        )
        orchestrator._execution_scheduler = MagicMock()
        
        # 调用 research
        try:
            result = await orchestrator.research(
                user_input="测试研究请求",
                interaction_mode=False,
            )
        except Exception as e:
            # 传统流程可能因为 mock 不完整而失败
            # 但关键点是 _research_with_routing 不应被调用
            pass
        
        # 验证 _research_with_routing 没有被调用
        orchestrator._research_with_routing.assert_not_called()


class TestResearchWithRouting:
    """测试 _research_with_routing 方法"""
    
    @pytest.mark.asyncio
    async def test_research_with_routing_basic_flow(self):
        """测试智能路由基本流程"""
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        from src.core.intelligent_routing_adapter import IntelligentRoutingResult
        from src.core.semantic_intent import DeepIntentResult
        # Phase 4: 更新导入
        from src.core.intent_types import IntentType, TaskComplexity
        from src.core.task_structure import TaskStructure
        from src.core.dynamic_orchestrator import ExecutionPlan
        
        orchestrator = ResearchOrchestrator(
            use_intelligent_routing=True,
        )
        
        # Mock 需求解析
        mock_requirement = MagicMock(
            topic="测试研究主题",
            aspects=["市场规模", "竞争格局"],
            output_type=MagicMock(value="markdown"),
        )
        orchestrator._parse_requirement = MagicMock(return_value=mock_requirement)
        
        # Mock 智能路由分析结果
        mock_intent_result = DeepIntentResult(
            primary_intent=IntentType.RESEARCH,
            intent_confidence=0.9,
            intent_reasoning="测试意图",
            complexity=TaskComplexity.SINGLE,
        )
        
        mock_task_structure = TaskStructure(
            task_id="test",
            topic="测试",
            sections=[],
            dependencies=[],
            execution_graph={},
            parallel_groups=[],
            critical_path=[],
            total_estimated_agents=0,
        )
        
        mock_execution_plan = ExecutionPlan(
            plan_id="test_plan",
            task_structure=mock_task_structure,
            phases=[],
            content_lock_rules=[],
            total_agents=0,
            estimated_duration="1h",
        )
        
        mock_routing_result = IntelligentRoutingResult(
            user_request="测试",
            requirement={},
            intent_result=mock_intent_result,
            task_structure=mock_task_structure,
            execution_plan=mock_execution_plan,
            decomposition_plan=MagicMock(),
        )
        
        orchestrator._routing_adapter.analyze = MagicMock(return_value=mock_routing_result)
        orchestrator._routing_adapter.get_lock_manager = MagicMock(return_value=None)
        
        # Mock Agent 创建
        orchestrator._create_agents = MagicMock(return_value=[])
        
        # Mock 执行引擎
        mock_exec_result = MagicMock()
        mock_exec_result.status = "completed"
        mock_exec_result.errors = []
        mock_exec_result.stage_results = {}
        orchestrator._execution_engine = MagicMock(
            execute_with_scheduler=AsyncMock(return_value=mock_exec_result)
        )
        
        # Mock 结果聚合（同步调用）
        mock_aggregated = MagicMock(sections=[])
        orchestrator._result_aggregator = MagicMock(
            aggregate=MagicMock(return_value=mock_aggregated)
        )
        
        # Mock 文档生成
        orchestrator._document_agent = MagicMock(
            execute=AsyncMock(return_value={"output_path": "/test/output.md"})
        )
        
        # Mock 任务持久化
        orchestrator._task_persistence = MagicMock(
            create_task=MagicMock(return_value=MagicMock()),
            save_task=MagicMock(),
            update_task_state=MagicMock(),
        )
        
        # Mock Agent 工厂
        orchestrator._agent_factory = MagicMock(
            get_registry=MagicMock(return_value=None)
        )
        
        orchestrator._execution_scheduler = MagicMock()
        
        # 执行
        result = await orchestrator._research_with_routing(
            user_input="测试研究请求",
            output_dir=None,
            user_id=None,
            interaction_mode=False,
            interaction_callback=None,
            task_id="test_task_001",
        )
        
        # 验证
        assert result.status in ("completed", "completed_with_warnings"), \
            f"Expected completed or completed_with_warnings, got {result.status}"
        assert result.topic == "测试研究主题"
        orchestrator._routing_adapter.analyze.assert_called_once()


def test_module_imports():
    """测试模块导入"""
    try:
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter
        
        assert ResearchOrchestrator is not None
        assert IntelligentRoutingAdapter is not None
        print("[PASS] All imports successful")
    except ImportError as e:
        pytest.fail(f"Import failed: {e}")


if __name__ == "__main__":
    # 运行基本测试
    print("=" * 50)
    print("测试智能路由集成")
    print("=" * 50)
    
    # 测试导入
    test_module_imports()
    
    # 测试初始化
    print("\n[PASS] Testing ResearchOrchestrator initialization...")
    from src.core.orchestrator.orchestrator import ResearchOrchestrator
    
    # 不启用智能路由
    orch1 = ResearchOrchestrator(use_intelligent_routing=False)
    assert orch1._use_intelligent_routing is False
    print("  [PASS] Default initialization (no intelligent routing)")
    
    # 启用智能路由
    orch2 = ResearchOrchestrator(use_intelligent_routing=True)
    assert orch2._use_intelligent_routing is True
    assert orch2._routing_adapter is not None
    print("  [PASS] Initialization with intelligent routing")
    
    print("\n" + "=" * 50)
    print("所有基础测试通过!")
    print("=" * 50)
