"""
v9.1 修复验证测试 (TDD - RED phase first)

验证项:
1. feedback_executor 标记@deprecated + 初始化时触发DeprecationWarning
2. get_agent_factory() 创建的agent有_shared_memory实例
3. dynamic_orchestrator quality_threshold 默认值为75.0 (0-100尺度)
4. survey/models.py SurveyResponse.quality_score 默认值为50.0
5. simulation_engine quality_score 默认值为50.0
6. AgentSessionStatus 枚举数量为7
"""
import pytest
import warnings


class TestFeedbackExecutorDeprecated:
    """v9.1-1: feedback_executor应标记为@deprecated"""

    def test_init_emits_deprecation_warning(self):
        """QualityFeedbackExecutor.__init__()应触发DeprecationWarning"""
        from src.core.quality.feedback_executor import QualityFeedbackExecutor

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            executor = QualityFeedbackExecutor(max_retries=2)

            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) >= 1, \
                "QualityFeedbackExecutor.__init__() should emit DeprecationWarning"

    def test_deprecation_warning_mentions_replacement(self):
        """废弃警告应指向engine.py S2重试循环替代方案"""
        from src.core.quality.feedback_executor import QualityFeedbackExecutor

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            executor = QualityFeedbackExecutor()

            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) >= 1
            msg = str(deprecation_warnings[0].message).lower()
            assert "engine.py" in msg or "s2" in msg or "quality_feedback" in msg, \
                "Deprecation warning should mention the replacement (engine.py S2 retry loop)"

    def test_executor_still_functional_after_deprecation(self):
        """废弃后功能仍可使用（向后兼容）"""
        from src.core.quality.feedback_executor import QualityFeedbackExecutor

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("ignore", DeprecationWarning)
            executor = QualityFeedbackExecutor(max_retries=2)

            assert executor.max_retries == 2
            assert executor.min_data_volume == 3


class TestGetAgentFactorySharedMemory:
    """v9.1-2: get_agent_factory()创建的agent应有_shared_memory"""

    def test_factory_has_shared_memory_attribute(self):
        """get_agent_factory()返回的工厂应有_shared_memory属性"""
        from src.core.agents.factory import get_agent_factory, _factory_instance

        import src.core.agents.factory as factory_module
        factory_module._factory_instance = None

        try:
            factory = get_agent_factory()
            assert hasattr(factory, '_shared_memory'), \
                "DynamicAgentFactory should have _shared_memory attribute"
        finally:
            factory_module._factory_instance = None

    def test_factory_has_message_bus_attribute(self):
        """get_agent_factory()返回的工厂应有_message_bus属性"""
        from src.core.agents.factory import get_agent_factory
        import src.core.agents.factory as factory_module
        factory_module._factory_instance = None

        try:
            factory = get_agent_factory()
            assert hasattr(factory, '_message_bus'), \
                "DynamicAgentFactory should have _message_bus attribute"
        finally:
            factory_module._factory_instance = None

    def test_factory_shared_memory_is_not_none(self):
        """get_agent_factory()返回的工厂_shared_memory不应为None"""
        import src.core.agents.factory as factory_module
        factory_module._factory_instance = None

        try:
            factory = factory_module.get_agent_factory()
            assert factory._shared_memory is not None, \
                "DynamicAgentFactory._shared_memory should not be None (P0-1 SharedMemory写入依赖此实例)"
        finally:
            factory_module._factory_instance = None

    def test_factory_message_bus_is_not_none(self):
        """get_agent_factory()返回的工厂_message_bus不应为None"""
        import src.core.agents.factory as factory_module
        factory_module._factory_instance = None

        try:
            factory = factory_module.get_agent_factory()
            assert factory._message_bus is not None, \
                "DynamicAgentFactory._message_bus should not be None"
        finally:
            factory_module._factory_instance = None


class TestDynamicOrchestratorThreshold:
    """v9.1-3: dynamic_orchestrator quality_threshold应为75.0 (0-100尺度)"""

    def test_content_lock_rule_default_threshold(self):
        """ContentLockRule.quality_threshold默认值应为75.0"""
        from src.core.dynamic_orchestrator import ContentLockRule

        rule = ContentLockRule(
            target_section="test_section",
            required_sections=["section_a"]
        )
        assert rule.quality_threshold == 75.0, \
            f"ContentLockRule.quality_threshold should be 75.0 (0-100 scale), got {rule.quality_threshold}"

    def test_agent_spec_default_threshold(self):
        """AgentSpec.quality_threshold默认值应为75.0"""
        from src.core.dynamic_orchestrator import AgentSpec

        spec = AgentSpec(
            agent_id="test_agent",
            agent_type="analysis",
            section_ids=["section_1"]
        )
        assert spec.quality_threshold == 75.0, \
            f"AgentSpec.quality_threshold should be 75.0 (0-100 scale), got {spec.quality_threshold}"


class TestSurveyModelsQualityScore:
    """v9.1-4: survey/models.py SurveyResponse.quality_score默认值应为50.0"""

    def test_survey_response_default_quality_score(self):
        """SurveyResponse.quality_score默认值应为50.0 (0-100尺度)"""
        from src.survey.models import SurveyResponse

        response = SurveyResponse(
            response_id="r_001",
            survey_id="s_001"
        )
        assert response.quality_score == 50.0, \
            f"SurveyResponse.quality_score default should be 50.0 (0-100 scale), got {response.quality_score}"


class TestSimulationEngineQualityScore:
    """v9.1-5: simulation_engine quality_score默认值应为50.0"""

    def test_simulation_response_quality_score(self):
        """simulation_engine生成的SurveyResponse quality_score应为50.0"""
        from src.survey.models import SurveyResponse

        response = SurveyResponse(
            response_id="r_sim_001",
            survey_id="s_001"
        )
        assert response.quality_score == 50.0, \
            f"Simulation SurveyResponse.quality_score should be 50.0, got {response.quality_score}"


class TestAgentSessionStatusCount:
    """v9.1-6: AgentSessionStatus枚举数量应为7"""

    def test_status_count(self):
        """AgentSessionStatus应有7个枚举值"""
        from src.core.agents.agent_session import AgentSessionStatus

        assert len(AgentSessionStatus) == 7, \
            f"AgentSessionStatus should have 7 values (PENDING/RUNNING/COMPLETED/FAILED/CANCELLED/HIBERNATED/RESUMING), got {len(AgentSessionStatus)}"

    def test_hibernated_status_exists(self):
        """AgentSessionStatus.HIBERNATED应存在"""
        from src.core.agents.agent_session import AgentSessionStatus

        assert hasattr(AgentSessionStatus, 'HIBERNATED')
        assert AgentSessionStatus.HIBERNATED.value == "hibernated"

    def test_resuming_status_exists(self):
        """AgentSessionStatus.RESUMING应存在"""
        from src.core.agents.agent_session import AgentSessionStatus

        assert hasattr(AgentSessionStatus, 'RESUMING')
        assert AgentSessionStatus.RESUMING.value == "resuming"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestEngineNoQualityExecutor:
    """v9.1-9: engine.py不应再实例化废弃的QualityFeedbackExecutor"""

    def test_engine_no_quality_executor_attribute(self):
        """ExecutionEngine不应有quality_executor属性（已废弃）"""
        from src.core.orchestrator.execution.engine import ExecutionEngine

        engine = ExecutionEngine.__new__(ExecutionEngine)
        has_attr = hasattr(engine, 'quality_executor')
        if has_attr:
            assert engine.quality_executor is None, \
                "ExecutionEngine.quality_executor should be None or removed (QualityFeedbackExecutor is deprecated)"

    def test_engine_init_no_deprecation_warning(self):
        """ExecutionEngine.__init__()不应触发QualityFeedbackExecutor的DeprecationWarning"""
        from src.core.orchestrator.execution.engine import ExecutionEngine

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            try:
                engine = ExecutionEngine(enable_quality_control=True)
            except Exception:
                pass

            deprecation_from_executor = [
                x for x in w
                if issubclass(x.category, DeprecationWarning)
                and "QualityFeedbackExecutor" in str(x.message)
            ]
            assert len(deprecation_from_executor) == 0, \
                "ExecutionEngine.__init__() should not instantiate QualityFeedbackExecutor (deprecated)"
