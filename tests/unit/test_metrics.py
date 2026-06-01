# -*- coding: utf-8 -*-
"""
指标收集模块测试
================

TDD: 测试先行

测试范围:
- Counter - 计数器
- Gauge - 仪表盘
- Histogram - 直方图
- MetricsRegistry - 指标注册表
- SystemMetricsCollector - 系统指标收集器
"""

import pytest
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.core.metrics import (
    Counter,
    Gauge,
    Histogram,
    MetricType,
    MetricsRegistry,
    SystemMetricsCollector,
    get_registry,
    counter as get_counter,
    gauge as get_gauge,
    histogram as get_histogram,
)


class TestCounter:
    """计数器测试"""
    
    def test_counter_init(self):
        """测试计数器初始化"""
        c = Counter("test_counter", "测试计数器")
        assert c.name == "test_counter"
        assert c.description == "测试计数器"
        assert c.get() == 0.0
    
    def test_counter_init_with_labels(self):
        """测试带标签的计数器初始化"""
        c = Counter("test_counter", "描述", labels={"method": "GET", "status": "200"})
        assert c.labels == {"method": "GET", "status": "200"}
    
    def test_counter_increment(self):
        """测试计数器增加"""
        c = Counter("test_counter")
        
        c.increment()
        assert c.get() == 1.0
        
        c.increment()
        assert c.get() == 2.0
    
    def test_counter_increment_by_amount(self):
        """测试按指定量增加"""
        c = Counter("test_counter")
        
        c.increment(5)
        assert c.get() == 5.0
        
        c.increment(3.5)
        assert c.get() == 8.5
    
    def test_counter_increment_negative_raises(self):
        """测试增加负值抛出异常"""
        c = Counter("test_counter")
        
        with pytest.raises(ValueError, match="只能增加"):
            c.increment(-1)
    
    def test_counter_reset(self):
        """测试计数器重置"""
        c = Counter("test_counter")
        c.increment(10)
        assert c.get() == 10.0
        
        c.reset()
        assert c.get() == 0.0
    
    def test_counter_to_dict(self):
        """测试序列化为字典"""
        c = Counter("test_counter", "描述", labels={"key": "value"})
        c.increment(5)
        
        d = c.to_dict()
        
        assert d["name"] == "test_counter"
        assert d["type"] == MetricType.COUNTER.value
        assert d["description"] == "描述"
        assert d["value"] == 5.0
        assert d["labels"] == {"key": "value"}
    
    def test_counter_thread_safety(self):
        """测试计数器线程安全"""
        c = Counter("test_counter")
        num_threads = 10
        increments_per_thread = 100
        
        def increment_counter():
            for _ in range(increments_per_thread):
                c.increment()
        
        threads = [threading.Thread(target=increment_counter) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert c.get() == num_threads * increments_per_thread


class TestGauge:
    """仪表盘测试"""
    
    def test_gauge_init(self):
        """测试仪表盘初始化"""
        g = Gauge("test_gauge", "测试仪表盘")
        assert g.name == "test_gauge"
        assert g.description == "测试仪表盘"
        assert g.get() == 0.0
    
    def test_gauge_set(self):
        """测试设置值"""
        g = Gauge("test_gauge")
        
        g.set(100)
        assert g.get() == 100.0
        
        g.set(50)
        assert g.get() == 50.0
    
    def test_gauge_increment(self):
        """测试增加值"""
        g = Gauge("test_gauge")
        g.set(10)
        
        g.increment()
        assert g.get() == 11.0
        
        g.increment(5)
        assert g.get() == 16.0
    
    def test_gauge_decrement(self):
        """测试减少值"""
        g = Gauge("test_gauge")
        g.set(20)
        
        g.decrement()
        assert g.get() == 19.0
        
        g.decrement(5)
        assert g.get() == 14.0
    
    def test_gauge_can_be_negative(self):
        """测试仪表盘可以为负值"""
        g = Gauge("test_gauge")
        g.set(0)
        g.decrement(10)
        assert g.get() == -10.0
    
    def test_gauge_to_dict(self):
        """测试序列化为字典"""
        g = Gauge("test_gauge", "描述", labels={"env": "prod"})
        g.set(42)
        
        d = g.to_dict()
        
        assert d["name"] == "test_gauge"
        assert d["type"] == MetricType.GAUGE.value
        assert d["value"] == 42.0
        assert d["labels"] == {"env": "prod"}
    
    def test_gauge_thread_safety(self):
        """测试仪表盘线程安全"""
        g = Gauge("test_gauge")
        g.set(0)
        num_threads = 10
        operations_per_thread = 100
        
        def modify_gauge():
            for i in range(operations_per_thread):
                g.increment(1)
                g.decrement(0.5)
        
        threads = [threading.Thread(target=modify_gauge) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # 每个线程: 100 * (1 - 0.5) = 50
        assert g.get() == num_threads * operations_per_thread * 0.5


class TestHistogram:
    """直方图测试"""
    
    def test_histogram_init(self):
        """测试直方图初始化"""
        h = Histogram("test_histogram", "测试直方图")
        assert h.name == "test_histogram"
        assert h.description == "测试直方图"
        assert h.get_count() == 0
        assert h.get_sum() == 0.0
    
    def test_histogram_default_buckets(self):
        """测试默认桶边界"""
        h = Histogram("test_histogram")
        buckets = h.get_buckets()
        
        # 应包含默认桶 + inf
        assert len(buckets) > 0
        assert float('inf') in buckets
    
    def test_histogram_custom_buckets(self):
        """测试自定义桶边界"""
        h = Histogram("test_histogram", buckets=[0.1, 0.5, 1.0])
        buckets = h.get_buckets()
        
        assert 0.1 in buckets
        assert 0.5 in buckets
        assert 1.0 in buckets
        assert float('inf') in buckets
    
    def test_histogram_observe(self):
        """测试记录观测值"""
        h = Histogram("test_histogram")
        
        h.observe(0.3)
        assert h.get_count() == 1
        assert h.get_sum() == 0.3
        
        h.observe(0.7)
        assert h.get_count() == 2
        assert h.get_sum() == 1.0
    
    def test_histogram_buckets_count(self):
        """测试桶计数"""
        h = Histogram("test_histogram", buckets=[0.5, 1.0])
        
        h.observe(0.3)  # <= 0.5
        h.observe(0.6)  # <= 1.0
        h.observe(1.5)  # > 1.0, 在 inf 桶
        
        buckets = h.get_buckets()
        
        assert buckets[0.5] == 1   # 0.3
        assert buckets[1.0] == 2   # 0.3, 0.6
        assert buckets[float('inf')] == 3  # 所有值
    
    def test_histogram_percentile(self):
        """测试百分位数计算"""
        h = Histogram("test_histogram", buckets=[0.1, 0.5, 1.0, 2.0])
        
        # 记录 10 个值: 0.1, 0.2, ..., 1.0
        for i in range(1, 11):
            h.observe(i * 0.1)
        
        # P50 应该在 0.5 桶附近
        p50 = h.get_percentile(50)
        assert p50 >= 0.5
        
        # P90 应该在更大的桶
        p90 = h.get_percentile(90)
        assert p90 >= p50
    
    def test_histogram_percentile_empty(self):
        """测试空直方图的百分位数"""
        h = Histogram("test_histogram")
        
        assert h.get_percentile(50) == 0.0
    
    def test_histogram_percentile_invalid(self):
        """测试无效百分位数"""
        h = Histogram("test_histogram")
        
        with pytest.raises(ValueError, match="0-100"):
            h.get_percentile(-1)
        
        with pytest.raises(ValueError, match="0-100"):
            h.get_percentile(101)
    
    def test_histogram_to_dict(self):
        """测试序列化为字典"""
        h = Histogram("test_histogram", "描述", labels={"service": "api"})
        h.observe(0.5)
        h.observe(1.0)
        
        d = h.to_dict()
        
        assert d["name"] == "test_histogram"
        assert d["type"] == MetricType.HISTOGRAM.value
        assert d["count"] == 2
        assert d["sum"] == 1.5
        assert "buckets" in d
        assert d["labels"] == {"service": "api"}
    
    def test_histogram_thread_safety(self):
        """测试直方图线程安全"""
        h = Histogram("test_histogram", buckets=[0.1, 0.5, 1.0])
        num_threads = 10
        observations_per_thread = 100
        
        def observe_values():
            for i in range(observations_per_thread):
                h.observe(0.5)
        
        threads = [threading.Thread(target=observe_values) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert h.get_count() == num_threads * observations_per_thread
        assert h.get_sum() == num_threads * observations_per_thread * 0.5


class TestMetricsRegistry:
    """指标注册表测试"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前重置注册表"""
        MetricsRegistry._instance = None
    
    def test_registry_init(self):
        """测试注册表初始化"""
        registry = MetricsRegistry()
        
        assert registry.namespace == ""
        assert len(registry._counters) == 0
        assert len(registry._gauges) == 0
        assert len(registry._histograms) == 0
    
    def test_registry_with_namespace(self):
        """测试带命名空间的注册表"""
        registry = MetricsRegistry(namespace="myapp")
        
        assert registry.namespace == "myapp"
    
    def test_registry_singleton(self):
        """测试单例模式"""
        r1 = MetricsRegistry.get_instance()
        r2 = MetricsRegistry.get_instance()
        
        assert r1 is r2
    
    def test_registry_counter(self):
        """测试创建计数器"""
        registry = MetricsRegistry()
        c = registry.counter("requests_total", "总请求数")
        
        assert isinstance(c, Counter)
        assert c.name == "requests_total"
        assert c.description == "总请求数"
    
    def test_registry_counter_same_key(self):
        """测试相同名称返回同一计数器"""
        registry = MetricsRegistry()
        c1 = registry.counter("test_counter")
        c2 = registry.counter("test_counter")
        
        assert c1 is c2
    
    def test_registry_counter_with_labels(self):
        """测试带标签的计数器"""
        registry = MetricsRegistry()
        c1 = registry.counter("http_requests", labels={"method": "GET"})
        c2 = registry.counter("http_requests", labels={"method": "POST"})
        
        # 不同标签应该是不同实例
        assert c1 is not c2
    
    def test_registry_gauge(self):
        """测试创建仪表盘"""
        registry = MetricsRegistry()
        g = registry.gauge("memory_usage", "内存使用")
        
        assert isinstance(g, Gauge)
        assert g.name == "memory_usage"
    
    def test_registry_histogram(self):
        """测试创建直方图"""
        registry = MetricsRegistry()
        h = registry.histogram("latency", "延迟", buckets=[0.1, 0.5, 1.0])
        
        assert isinstance(h, Histogram)
        assert h.name == "latency"
    
    def test_registry_export_all(self):
        """测试导出所有指标"""
        registry = MetricsRegistry()
        
        c = registry.counter("requests", "请求数")
        c.increment(10)
        
        g = registry.gauge("memory", "内存")
        g.set(1024)
        
        h = registry.histogram("latency", "延迟")
        h.observe(0.5)
        
        metrics = registry.export_all()
        
        assert "requests" in metrics
        assert "memory" in metrics
        assert "latency" in metrics
        
        assert metrics["requests"]["value"] == 10.0
        assert metrics["memory"]["value"] == 1024.0
        assert metrics["latency"]["count"] == 1
    
    def test_registry_export_prometheus_counters(self):
        """测试导出 Prometheus 格式 - 计数器"""
        registry = MetricsRegistry()
        c = registry.counter("http_requests", "HTTP 请求数")
        c.increment(100)
        
        prom = registry.export_prometheus()
        
        assert "# HELP http_requests HTTP 请求数" in prom
        assert "# TYPE http_requests counter" in prom
        assert "http_requests 100" in prom
    
    def test_registry_export_prometheus_gauges(self):
        """测试导出 Prometheus 格式 - 仪表盘"""
        registry = MetricsRegistry()
        g = registry.gauge("cpu_usage", "CPU 使用率")
        g.set(75.5)
        
        prom = registry.export_prometheus()
        
        assert "# TYPE cpu_usage gauge" in prom
        assert "cpu_usage 75.5" in prom
    
    def test_registry_export_prometheus_histogram(self):
        """测试导出 Prometheus 格式 - 直方图"""
        registry = MetricsRegistry()
        h = registry.histogram("request_duration", "请求延迟", buckets=[0.1, 0.5, 1.0])
        h.observe(0.3)
        h.observe(0.7)
        
        prom = registry.export_prometheus()
        
        assert "# TYPE request_duration histogram" in prom
        assert "request_duration_bucket" in prom
        assert "request_duration_sum" in prom
        assert "request_duration_count 2" in prom
    
    def test_registry_export_prometheus_with_labels(self):
        """测试带标签的 Prometheus 导出"""
        registry = MetricsRegistry()
        c = registry.counter("http_requests", "HTTP 请求数", labels={"method": "GET"})
        c.increment(50)
        
        prom = registry.export_prometheus()
        
        assert 'method="GET"' in prom
    
    def test_registry_clear(self):
        """测试清除所有指标"""
        registry = MetricsRegistry()
        
        registry.counter("test1")
        registry.gauge("test2")
        registry.histogram("test3")
        
        assert len(registry._counters) == 1
        assert len(registry._gauges) == 1
        assert len(registry._histograms) == 1
        
        registry.clear()
        
        assert len(registry._counters) == 0
        assert len(registry._gauges) == 0
        assert len(registry._histograms) == 0


class TestConvenienceFunctions:
    """便捷函数测试"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """重置注册表"""
        MetricsRegistry._instance = None
    
    def test_get_registry(self):
        """测试获取注册表"""
        registry = get_registry()
        
        assert isinstance(registry, MetricsRegistry)
    
    def test_get_counter(self):
        """测试获取计数器"""
        c = get_counter("test_counter", "测试")
        
        assert isinstance(c, Counter)
        assert c.name == "test_counter"
    
    def test_get_gauge(self):
        """测试获取仪表盘"""
        g = get_gauge("test_gauge", "测试")
        
        assert isinstance(g, Gauge)
        assert g.name == "test_gauge"
    
    def test_get_histogram(self):
        """测试获取直方图"""
        h = get_histogram("test_histogram", "测试")
        
        assert isinstance(h, Histogram)
        assert h.name == "test_histogram"


class TestSystemMetricsCollector:
    """系统指标收集器测试"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """重置注册表"""
        MetricsRegistry._instance = None
    
    def test_collector_init(self):
        """测试收集器初始化"""
        registry = MetricsRegistry()
        collector = SystemMetricsCollector(registry)
        
        assert collector.registry is registry
    
    def test_collector_uses_default_registry(self):
        """测试使用默认注册表"""
        collector = SystemMetricsCollector()
        
        assert collector.registry is get_registry()
    
    def test_collector_creates_system_gauges(self):
        """测试创建系统指标"""
        registry = MetricsRegistry()
        collector = SystemMetricsCollector(registry)
        
        # 验证系统指标已创建
        assert "system_cpu_usage" in registry._gauges
        assert "system_memory_usage" in registry._gauges
        assert "system_memory_percent" in registry._gauges
    
    def test_collector_collect_without_psutil(self, monkeypatch):
        """测试无 psutil 时的收集"""
        registry = MetricsRegistry()
        collector = SystemMetricsCollector(registry)
        
        # 模拟 psutil 不存在
        import sys
        monkeypatch.setitem(sys.modules, 'psutil', None)
        
        # 不应该抛出异常
        collector.collect()


class TestHistogramPercentileAccuracy:
    """直方图百分位数精度测试"""
    
    def test_percentile_p50(self):
        """测试 P50 计算"""
        h = Histogram("test", buckets=[0.1, 0.5, 1.0, 2.0, 5.0])
        
        # 添加 100 个值，均匀分布
        for i in range(1, 101):
            h.observe(i * 0.05)  # 0.05 到 5.0
        
        p50 = h.get_percentile(50)
        p95 = h.get_percentile(95)
        p99 = h.get_percentile(99)
        
        # P95 > P50
        assert p95 >= p50
        # P99 > P95
        assert p99 >= p95
    
    def test_percentile_with_single_value(self):
        """测试单个值时的百分位数"""
        h = Histogram("test", buckets=[0.5, 1.0])
        h.observe(0.3)
        
        # 任何百分位都应返回值所在的桶
        assert h.get_percentile(0) == 0.5
        assert h.get_percentile(50) == 0.5
        assert h.get_percentile(100) == 0.5


class TestThreadSafetyStress:
    """线程安全压力测试"""
    
    def test_counter_high_concurrency(self):
        """测试计数器高并发"""
        c = Counter("stress_test")
        num_operations = 10000
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(c.increment) for _ in range(num_operations)]
            for f in as_completed(futures):
                f.result()
        
        assert c.get() == num_operations
    
    def test_gauge_high_concurrency(self):
        """测试仪表盘高并发"""
        g = Gauge("stress_test")
        num_operations = 5000
        
        def increment():
            g.increment(1)
        
        def decrement():
            g.decrement(1)
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = []
            for _ in range(num_operations):
                futures.append(executor.submit(increment))
                futures.append(executor.submit(decrement))
            
            for f in as_completed(futures):
                f.result()
        
        # 增加和减少相同次数，应该接近 0
        assert abs(g.get()) < 0.001
    
    def test_histogram_high_concurrency(self):
        """测试直方图高并发"""
        h = Histogram("stress_test", buckets=[0.5, 1.0])
        num_operations = 10000
        test_value = 0.3
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(h.observe, test_value) for _ in range(num_operations)]
            for f in as_completed(futures):
                f.result()
        
        assert h.get_count() == num_operations
        assert abs(h.get_sum() - num_operations * test_value) < 0.001


class TestMetricType:
    """指标类型枚举测试"""
    
    def test_metric_type_values(self):
        """测试指标类型值"""
        assert MetricType.COUNTER.value == "counter"
        assert MetricType.GAUGE.value == "gauge"
        assert MetricType.HISTOGRAM.value == "histogram"
        assert MetricType.SUMMARY.value == "summary"
