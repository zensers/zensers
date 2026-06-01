# -*- coding: utf-8 -*-
"""
Phase 8 性能测试
===============

测试各组件的响应时间和性能基准。

验收标准：
- 预览生成 < 5s
- 章节定位 < 1s
- 单次修订 < 30s
"""

import os
import time
from pathlib import Path

import pytest

from src.core.adjustment import (
    RevisionHandler,
    RevisionRequest,
    SectionLocator,
    ContentApplier,
    RevisionManager,
)
from src.core.workflow import (
    PreviewRevisionWorkflow,
    FeedbackRequest,
)


class TestPerformanceBenchmarks:
    """性能基准测试"""
    
    @pytest.fixture
    def large_report(self, tmp_path):
        """创建大型测试报告（模拟真实场景）"""
        sections = []
        
        # 生成50个章节
        for i in range(1, 51):
            sections.append(f"""
## 第{i}章 章节标题{i}

这是第{i}章的内容。包含一些测试数据和分析。

### {i}.1 子章节

子章节内容，包含更多细节和数据。

### {i}.2 分析

本节分析了相关数据，得出以下结论：
- 要点1
- 要点2
- 要点3

### {i}.3 总结

本章总结了关键发现。
""")
        
        content = f"""# 大型研究报告

## 摘要

本报告包含50个章节，用于测试性能。

{''.join(sections)}

## 结论

报告结束。
"""
        file_path = tmp_path / "large_report.md"
        file_path.write_text(content, encoding='utf-8')
        return str(file_path)
    
    @pytest.fixture
    def handler(self, tmp_path):
        """创建处理器"""
        storage = tmp_path / "revisions"
        storage.mkdir(exist_ok=True)
        revision_manager = RevisionManager(storage_path=str(storage))
        return RevisionHandler(revision_manager=revision_manager)
    
    @pytest.fixture
    def locator(self):
        """创建定位器"""
        return SectionLocator()
    
    def test_section_location_performance(self, locator, large_report):
        """测试章节定位性能（目标 < 1s）"""
        # 预热
        locator.locate(large_report, section_title="第1章")
        
        # 测试定位时间
        start_time = time.time()
        
        for _ in range(10):
            location = locator.locate(large_report, section_title="第25章")
            assert location is not None
        
        elapsed = time.time() - start_time
        avg_time = elapsed / 10
        
        print(f"\n章节定位平均时间: {avg_time*1000:.2f}ms")
        assert avg_time < 1.0, f"章节定位应该 < 1s，实际: {avg_time:.2f}s"
    
    def test_list_sections_performance(self, locator, large_report):
        """测试列出章节性能"""
        start_time = time.time()
        
        sections = locator.list_sections(large_report)
        
        elapsed = time.time() - start_time
        
        print(f"\n列出 {len(sections)} 个章节耗时: {elapsed*1000:.2f}ms")
        assert elapsed < 1.0, f"列出章节应该 < 1s"
    
    def test_keyword_search_performance(self, locator, large_report):
        """测试关键词搜索性能"""
        start_time = time.time()
        
        for _ in range(5):
            location = locator.locate(
                large_report,
                keywords=["分析", "结论"]
            )
        
        elapsed = time.time() - start_time
        avg_time = elapsed / 5
        
        print(f"\n关键词搜索平均时间: {avg_time*1000:.2f}ms")
        assert avg_time < 1.0, f"关键词搜索应该 < 1s"
    
    def test_revision_performance(self, handler, large_report):
        """测试修订性能（目标 < 30s）"""
        start_time = time.time()
        
        request = RevisionRequest(
            task_id="perf_task",
            revision_type="section",
            section_title="第10章",
            user_feedback="性能测试",
            target_content="## 第10章 更新内容\n\n这是更新后的内容。\n",
        )
        
        result = handler.handle_revision(large_report, request)
        
        elapsed = time.time() - start_time
        
        print(f"\n单次修订耗时: {elapsed*1000:.2f}ms")
        assert result.success
        assert elapsed < 30.0, f"单次修订应该 < 30s，实际: {elapsed:.2f}s"
    
    def test_cache_effectiveness(self, locator, large_report):
        """测试缓存效果"""
        # 第一次访问（无缓存）
        start_time = time.time()
        locator.locate(large_report, section_title="第30章")
        first_time = time.time() - start_time
        
        # 第二次访问（有缓存）
        start_time = time.time()
        locator.locate(large_report, section_title="第30章")
        second_time = time.time() - start_time
        
        print(f"\n首次访问: {first_time*1000:.2f}ms, 缓存访问: {second_time*1000:.2f}ms")
        print(f"缓存加速比: {first_time/second_time:.2f}x")
        
        # 缓存应该更快
        assert second_time <= first_time * 1.5  # 允许一些波动
    
    def test_workflow_performance(self, handler, large_report):
        """测试工作流性能"""
        workflow = PreviewRevisionWorkflow(revision_handler=handler)
        
        start_time = time.time()
        
        # 启动工作流
        state = workflow.start(
            task_id="workflow_perf",
            document_path=large_report,
        )
        
        # 执行3轮修订
        for i in range(3):
            feedback = FeedbackRequest(
                accepted=False,
                revision_type="minor",
                user_feedback=f"修订 {i+1}",
            )
            state = workflow.submit_feedback(state.loop_id, feedback)
        
        # 确认
        feedback = FeedbackRequest(accepted=True)
        state = workflow.submit_feedback(state.loop_id, feedback)
        
        elapsed = time.time() - start_time
        
        print(f"\n完整工作流（3轮修订）耗时: {elapsed:.2f}s")
        assert state.status.value == "completed"
        assert elapsed < 60.0, f"完整工作流应该 < 60s"


class TestConcurrencyPerformance:
    """并发性能测试"""
    
    @pytest.fixture
    def sample_report(self, tmp_path):
        """创建示例报告"""
        content = "# 测试报告\n\n" + "\n".join([f"## 章节{i}\n\n内容{i}\n" for i in range(20)])
        file_path = tmp_path / "report.md"
        file_path.write_text(content, encoding='utf-8')
        return str(file_path)
    
    @pytest.fixture
    def handler(self, tmp_path):
        """创建处理器"""
        storage = tmp_path / "revisions"
        storage.mkdir(exist_ok=True)
        revision_manager = RevisionManager(storage_path=str(storage))
        return RevisionHandler(revision_manager=revision_manager)
    
    def test_concurrent_revision_count(self, handler, sample_report):
        """测试并发修订计数（线程安全）"""
        import threading
        
        results = []
        errors = []
        
        def do_revision(task_id):
            try:
                for i in range(5):
                    request = RevisionRequest(
                        task_id=task_id,
                        revision_type="minor",
                        user_feedback=f"修订 {i}",
                    )
                    result = handler.handle_revision(sample_report, request)
                    results.append((task_id, result.success))
            except Exception as e:
                errors.append(str(e))
        
        # 启动多个线程
        threads = []
        for i in range(3):
            t = threading.Thread(target=do_revision, args=(f"concurrent_task_{i}",))
            threads.append(t)
            t.start()
        
        # 等待完成
        for t in threads:
            t.join()
        
        # 验证
        assert len(errors) == 0, f"并发错误: {errors}"
        
        # 每个任务应该有5次成功修订
        for i in range(3):
            count = handler.get_revision_count(f"concurrent_task_{i}")
            assert count == 5, f"任务 {i} 应该有5次修订，实际: {count}"


class TestMemoryPerformance:
    """内存性能测试"""
    
    def test_large_document_handling(self, tmp_path):
        """测试大文档处理"""
        # 创建大文档（约1MB）
        content = "# 大型文档\n\n"
        for i in range(10000):
            content += f"段落{i}: 这是第{i}个段落的内容，包含一些测试数据。\n\n"
        
        file_path = tmp_path / "large.md"
        file_path.write_text(content, encoding='utf-8')
        
        locator = SectionLocator()
        
        start_time = time.time()
        sections = locator.list_sections(str(file_path))
        elapsed = time.time() - start_time
        
        print(f"\n处理 {len(content)/1024:.1f}KB 文档耗时: {elapsed:.2f}s")
        assert elapsed < 5.0, f"大文档处理应该 < 5s"
    
    def test_cache_memory_usage(self, tmp_path):
        """测试缓存内存使用"""
        import sys
        
        locator = SectionLocator(cache_enabled=True)
        
        # 创建多个文档
        files = []
        for i in range(10):
            content = f"# 文档{i}\n\n" + "\n".join([f"## 章节{j}\n\n内容{j}\n" for j in range(10)])
            file_path = tmp_path / f"doc{i}.md"
            file_path.write_text(content, encoding='utf-8')
            files.append(str(file_path))
        
        # 解析所有文档
        for f in files:
            locator.list_sections(f)
        
        # 检查缓存大小
        cache_size = len(locator._index_cache)
        print(f"\n缓存了 {cache_size} 个文档索引")
        
        # 清除缓存
        locator.clear_cache()
        assert len(locator._index_cache) == 0


class TestBenchmarkSummary:
    """性能基准总结"""
    
    def test_performance_summary(self, tmp_path):
        """输出性能基准总结"""
        # 创建测试文档
        content = "# 性能测试报告\n\n"
        for i in range(30):
            content += f"## 章节{i}\n\n这是第{i}章的内容。\n\n"
        
        file_path = tmp_path / "perf_test.md"
        file_path.write_text(content, encoding='utf-8')
        
        storage = tmp_path / "revisions"
        storage.mkdir(exist_ok=True)
        
        locator = SectionLocator()
        handler = RevisionHandler(
            revision_manager=RevisionManager(storage_path=str(storage))
        )
        
        results = {}
        
        # 章节定位
        start = time.time()
        locator.locate(str(file_path), section_title="章节15")
        results["章节定位"] = (time.time() - start) * 1000
        
        # 列出章节
        start = time.time()
        locator.list_sections(str(file_path))
        results["列出章节"] = (time.time() - start) * 1000
        
        # 修订
        request = RevisionRequest(
            task_id="summary_task",
            revision_type="section",
            section_title="章节10",
            user_feedback="测试",
            target_content="## 章节10\n\n新内容\n",
        )
        start = time.time()
        handler.handle_revision(str(file_path), request)
        results["单次修订"] = (time.time() - start) * 1000
        
        # 输出结果
        print("\n" + "=" * 50)
        print("Phase 8 性能基准测试结果")
        print("=" * 50)
        
        thresholds = {
            "章节定位": 1000,  # < 1s
            "列出章节": 1000,  # < 1s
            "单次修订": 30000,  # < 30s
        }
        
        all_passed = True
        for name, time_ms in results.items():
            threshold = thresholds.get(name, float('inf'))
            status = "✅ PASS" if time_ms < threshold else "❌ FAIL"
            print(f"{name}: {time_ms:.2f}ms (阈值: {threshold}ms) {status}")
            if time_ms >= threshold:
                all_passed = False
        
        print("=" * 50)
        
        assert all_passed, "部分性能指标未达标"
