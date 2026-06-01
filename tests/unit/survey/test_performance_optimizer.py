"""
Week 4 Day 3: 性能优化测试
========================

TDD测试用例，用于PerformanceOptimizer。

测试覆盖:
1. 批量处理性能
2. 并发控制
3. 内存使用优化
4. 缓存策略
5. 性能基准测试
"""

import pytest
import asyncio
import time
from typing import Dict, Any, List
from datetime import datetime

from src.survey.models import (
    Survey, Question, QuestionOption, QuestionType,
    SurveyResponse, Answer
)
from src.survey.services.performance_optimizer import (
    PerformanceOptimizer,
    BatchProcessor,
    CacheStrategy,
    PerformanceReport
)


class TestPerformanceReport:
    """性能报告测试"""
    
    def test_report_creation(self):
        """测试性能报告创建"""
        report = PerformanceReport(
            operation="batch_simulate",
            total_time=5.0,
            item_count=100,
            avg_time_per_item=0.05,
            throughput=20.0,
            memory_usage_mb=50.5,
            recommendations=["建议增加并发数"]
        )
        
        assert report.operation == "batch_simulate"
        assert report.total_time == 5.0
        assert report.throughput == 20.0
    
    def test_report_to_dict(self):
        """测试报告转换为字典"""
        report = PerformanceReport(
            operation="test_op",
            total_time=1.0,
            item_count=10,
            avg_time_per_item=0.1,
            throughput=10.0,
            memory_usage_mb=20.0,
            recommendations=[]
        )
        
        result = report.to_dict()
        
        assert result["operation"] == "test_op"
        assert result["throughput"] == 10.0


class TestBatchProcessor:
    """批量处理器测试"""
    
    def test_processor_initialization(self):
        """测试处理器初始化"""
        processor = BatchProcessor(batch_size=50)
        
        assert processor.batch_size == 50
        assert processor.max_concurrent == 10
    
    def test_processor_with_config(self):
        """测试带配置的处理器初始化"""
        processor = BatchProcessor(
            batch_size=100,
            max_concurrent=20,
            timeout_seconds=60
        )
        
        assert processor.batch_size == 100
        assert processor.max_concurrent == 20
        assert processor.timeout_seconds == 60
    
    @pytest.mark.asyncio
    async def test_process_batch(self):
        """测试批量处理"""
        processor = BatchProcessor(batch_size=10)
        
        async def process_item(item: int) -> int:
            await asyncio.sleep(0.01)
            return item * 2
        
        items = list(range(10))
        results = await processor.process_batch(items, process_item)
        
        assert len(results) == 10
        assert results == [i * 2 for i in range(10)]
    
    @pytest.mark.asyncio
    async def test_process_large_batch(self):
        """测试大批量处理"""
        processor = BatchProcessor(batch_size=20, max_concurrent=5)
        
        async def process_item(item: int) -> int:
            return item + 1
        
        items = list(range(100))
        results = await processor.process_batch(items, process_item)
        
        assert len(results) == 100
        assert results == [i + 1 for i in range(100)]
    
    @pytest.mark.asyncio
    async def test_process_with_error_handling(self):
        """测试错误处理"""
        processor = BatchProcessor()
        
        async def process_item(item: int) -> int:
            if item == 5:
                raise ValueError("Test error")
            return item
        
        items = list(range(10))
        results = await processor.process_batch(
            items, process_item, continue_on_error=True
        )
        
        # 应该有9个成功结果
        successful = [r for r in results if r is not None]
        assert len(successful) == 9


class TestCacheStrategy:
    """缓存策略测试"""
    
    def test_cache_initialization(self):
        """测试缓存初始化"""
        cache = CacheStrategy(max_size=100)
        
        assert cache.max_size == 100
        assert len(cache._cache) == 0
    
    def test_cache_set_get(self):
        """测试缓存存取"""
        cache = CacheStrategy()
        
        cache.set("key1", "value1")
        result = cache.get("key1")
        
        assert result == "value1"
    
    def test_cache_miss(self):
        """测试缓存未命中"""
        cache = CacheStrategy()
        
        result = cache.get("nonexistent")
        
        assert result is None
    
    def test_cache_eviction(self):
        """测试缓存淘汰"""
        cache = CacheStrategy(max_size=3)
        
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.set("key4", "value4")  # 应该淘汰最旧的
        
        assert cache.get("key1") is None  # 被淘汰
        assert cache.get("key4") == "value4"  # 新添加的
    
    def test_cache_clear(self):
        """测试缓存清空"""
        cache = CacheStrategy()
        
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        
        assert len(cache._cache) == 0
    
    def test_cache_stats(self):
        """测试缓存统计"""
        cache = CacheStrategy()
        
        cache.set("key1", "value1")
        cache.get("key1")  # hit
        cache.get("key2")  # miss
        
        stats = cache.get_stats()
        
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5


class TestPerformanceOptimizer:
    """性能优化器测试"""
    
    def test_optimizer_initialization(self):
        """测试优化器初始化"""
        optimizer = PerformanceOptimizer()
        
        assert optimizer.default_batch_size == 100
        assert optimizer.default_max_concurrent == 10
    
    def test_optimizer_with_config(self):
        """测试带配置的优化器"""
        optimizer = PerformanceOptimizer(
            default_batch_size=50,
            default_max_concurrent=5
        )
        
        assert optimizer.default_batch_size == 50
    
    @pytest.mark.asyncio
    async def test_optimize_simulation(self):
        """测试模拟性能优化"""
        survey = self._create_test_survey()
        
        from src.survey.services.persona_factory import PersonaFactory
        from src.survey.services.simulation_engine import SimulationEngine
        
        factory = PersonaFactory()
        personas = factory.generate_population("一线白领", 50)
        
        optimizer = PerformanceOptimizer()
        
        # 执行优化后的模拟
        result = await optimizer.optimize_simulation(
            personas, survey, max_concurrent=10
        )
        
        assert "responses" in result
        assert "performance_report" in result
        assert len(result["responses"]) == 50
    
    @pytest.mark.asyncio
    async def test_benchmark_performance(self):
        """测试性能基准"""
        optimizer = PerformanceOptimizer()
        
        async def test_operation():
            await asyncio.sleep(0.01)
            return "done"
        
        report = await optimizer.benchmark(
            test_operation,
            iterations=10
        )
        
        assert report.total_time > 0
        assert report.item_count == 10
        assert report.throughput > 0
    
    def test_estimate_memory_usage(self):
        """测试内存使用估算"""
        optimizer = PerformanceOptimizer()
        
        # 估算1000个回答的内存使用
        memory_mb = optimizer.estimate_memory_usage(response_count=1000)
        
        assert memory_mb > 0
        assert isinstance(memory_mb, float)
    
    def test_recommend_batch_size(self):
        """测试批量大小推荐"""
        optimizer = PerformanceOptimizer()
        
        # 小样本
        batch_size = optimizer.recommend_batch_size(total_items=50)
        assert batch_size <= 50
        
        # 大样本
        batch_size = optimizer.recommend_batch_size(total_items=10000)
        assert batch_size >= 100
    
    def test_recommend_concurrency(self):
        """测试并发数推荐"""
        optimizer = PerformanceOptimizer()
        
        # 根据CPU核心数推荐
        concurrency = optimizer.recommend_concurrency()
        
        assert concurrency >= 1
        assert concurrency <= 50  # 合理上限
    
    @pytest.mark.asyncio
    async def test_process_with_progress(self):
        """测试带进度的处理"""
        optimizer = PerformanceOptimizer()
        
        progress_updates = []
        
        def progress_callback(progress: float):
            progress_updates.append(progress)
        
        async def process_item(item: int) -> int:
            await asyncio.sleep(0.01)
            return item
        
        items = list(range(20))
        results = await optimizer.process_with_progress(
            items, process_item, progress_callback
        )
        
        assert len(results) == 20
        assert len(progress_updates) > 0
        assert progress_updates[-1] == 1.0  # 最后进度应该是100%
    
    # Helper methods
    
    def _create_test_survey(self) -> Survey:
        """创建测试问卷"""
        return Survey(
            survey_id="perf_test_survey",
            title="性能测试问卷",
            questions=[
                Question(
                    question_id="q1",
                    text="问题1",
                    question_type=QuestionType.SINGLE_CHOICE,
                    options=[
                        QuestionOption("opt1", "选项1"),
                        QuestionOption("opt2", "选项2"),
                    ],
                    required=True
                ),
            ]
        )


class TestPerformanceIntegration:
    """性能集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_pipeline_performance(self):
        """测试完整管道性能"""
        from src.survey.services.persona_factory import PersonaFactory
        from src.survey.services.simulation_engine import SimulationEngine
        from src.survey.services.response_quality_validator import ResponseQualityValidator
        from src.agents.fixed_agents.result_calibration_agent import ResultCalibrationAgent
        from src.survey.services.performance_optimizer import PerformanceOptimizer
        
        # 创建问卷
        survey = Survey(
            survey_id="perf_integration",
            title="性能集成测试",
            questions=[
                Question(
                    question_id="q1",
                    text="满意度",
                    question_type=QuestionType.SINGLE_CHOICE,
                    options=[
                        QuestionOption("opt1", "满意"),
                        QuestionOption("opt2", "不满意"),
                    ],
                    required=True
                ),
            ]
        )
        
        optimizer = PerformanceOptimizer()
        
        # 生成画像
        factory = PersonaFactory()
        personas = factory.generate_population("一线白领", 30)
        
        # 优化模拟
        sim_result = await optimizer.optimize_simulation(personas, survey)
        responses = sim_result["responses"]
        
        # 确保每个response都有demographics
        for i, response in enumerate(responses):
            if response.demographics is None:
                response.demographics = {"age": personas[i].age}
        
        # 质量校验
        validator = ResponseQualityValidator()
        reports = validator.validate_batch(responses, survey)
        
        # 结果校准
        calibration_agent = ResultCalibrationAgent()
        calibration_result = calibration_agent.execute({
            "responses": responses,
            "survey": survey,
            "target_distribution": {"age": {"18-30": 0.5, "31-50": 0.5}},
            "calibration_dimension": "age"
        })
        
        assert len(responses) == 30
        assert len(reports) == 30
        assert calibration_result["success"] is True
    
    @pytest.mark.asyncio
    async def test_large_scale_performance(self):
        """测试大规模性能"""
        from src.survey.services.persona_factory import PersonaFactory
        from src.survey.services.simulation_engine import SimulationEngine
        from src.survey.services.performance_optimizer import PerformanceOptimizer
        
        survey = Survey(
            survey_id="large_scale_test",
            title="大规模测试",
            questions=[
                Question(
                    question_id=f"q{i}",
                    text=f"问题{i}",
                    question_type=QuestionType.SINGLE_CHOICE,
                    options=[
                        QuestionOption("opt1", "选项1"),
                        QuestionOption("opt2", "选项2"),
                    ],
                    required=True
                )
                for i in range(5)
            ]
        )
        
        factory = PersonaFactory()
        personas = factory.generate_population("一线白领", 100)
        
        optimizer = PerformanceOptimizer()
        
        start_time = time.time()
        result = await optimizer.optimize_simulation(personas, survey)
        elapsed_time = time.time() - start_time
        
        # 性能要求：100人×5题应该在30秒内完成
        assert len(result["responses"]) == 100
        assert elapsed_time < 30, f"性能测试失败：{elapsed_time:.2f}秒"
        assert result["performance_report"].throughput > 3  # 至少3个/秒