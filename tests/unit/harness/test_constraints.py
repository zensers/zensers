"""
约束层测试 - TDD模式
测试 SourceWhitelist 和 FactTracer
"""

import pytest
from datetime import datetime
from pathlib import Path
import tempfile
import shutil


class TestSourceWhitelist:
    """测试数据来源白名单"""
    
    @pytest.fixture
    def temp_dir(self):
        """临时目录"""
        path = tempfile.mkdtemp()
        yield path
        shutil.rmtree(path, ignore_errors=True)
    
    @pytest.fixture
    def whitelist(self, temp_dir):
        """创建白名单实例"""
        from src.core.harness.constraints import SourceWhitelist
        return SourceWhitelist(config_path=temp_dir)
    
    def test_init_default_whitelist(self, whitelist):
        """测试默认白名单初始化"""
        # 验证默认可信来源
        assert whitelist.is_trusted("政府官网") is True
        assert whitelist.is_trusted("上市公司财报") is True
        assert whitelist.is_trusted("知名媒体") is True
    
    def test_init_untrusted_sources(self, whitelist):
        """测试默认可疑来源"""
        assert whitelist.is_trusted("匿名论坛") is False
        assert whitelist.is_trusted("未经验证的自媒体") is False
    
    def test_add_trusted_source(self, whitelist):
        """测试添加可信来源"""
        whitelist.add_trusted_source("行业协会", tier="tier1")
        assert whitelist.is_trusted("行业协会") is True
    
    def test_add_untrusted_source(self, whitelist):
        """测试添加不可信来源"""
        whitelist.add_untrusted_source("某小网站")
        assert whitelist.is_trusted("某小网站") is False
    
    def test_get_source_tier(self, whitelist):
        """测试获取来源等级"""
        assert whitelist.get_source_tier("政府官网") == "tier1"
        assert whitelist.get_source_tier("上市公司财报") == "tier1"
        assert whitelist.get_source_tier("知名媒体") == "tier2"
    
    def test_validate_url(self, whitelist):
        """测试验证URL"""
        # 政府域名
        assert whitelist.validate_url("https://www.gov.cn/policy") is True
        # 知名媒体
        assert whitelist.validate_url("https://www.xinhuanet.com/news") is True
        # 可疑域名
        assert whitelist.validate_url("https://unknown-blog.com") is False
    
    def test_save_and_load_config(self, temp_dir):
        """测试保存和加载配置"""
        from src.core.harness.constraints import SourceWhitelist
        
        # 创建并修改
        whitelist1 = SourceWhitelist(config_path=temp_dir)
        whitelist1.add_trusted_source("新来源", tier="tier2")
        whitelist1.save_config()
        
        # 重新加载
        whitelist2 = SourceWhitelist(config_path=temp_dir)
        assert whitelist2.is_trusted("新来源") is True
        assert whitelist2.get_source_tier("新来源") == "tier2"


class TestFactTracer:
    """测试事实溯源器"""
    
    @pytest.fixture
    def temp_dir(self):
        """临时目录"""
        path = tempfile.mkdtemp()
        yield path
        shutil.rmtree(path, ignore_errors=True)
    
    @pytest.fixture
    def tracer(self, temp_dir):
        """创建溯源器实例"""
        from src.core.harness.constraints import FactTracer
        return FactTracer(storage_path=temp_dir)
    
    def test_trace_fact(self, tracer):
        """测试记录事实溯源"""
        tracer.trace_fact(
            fact_id="fact-001",
            fact_statement="2025年中国GDP增长5.2%",
            source="国家统计局",
            source_url="https://www.stats.gov.cn/",
            confidence="high",
            verification_method="官方发布"
        )
        
        # 验证记录存在
        trace = tracer.get_trace("fact-001")
        assert trace is not None
        assert trace["fact_statement"] == "2025年中国GDP增长5.2%"
        assert trace["source"] == "国家统计局"
    
    def test_get_trace_not_found(self, tracer):
        """测试获取不存在的事实"""
        trace = tracer.get_trace("non-existent")
        assert trace is None
    
    def test_get_all_traces(self, tracer):
        """测试获取所有溯源记录"""
        tracer.trace_fact("fact-001", "事实1", "来源1")
        tracer.trace_fact("fact-002", "事实2", "来源2")
        
        traces = tracer.get_all_traces()
        assert len(traces) == 2
    
    def test_verify_fact_exists(self, tracer):
        """测试验证事实是否存在"""
        tracer.trace_fact("fact-001", "测试事实", "测试来源")
        assert tracer.verify_fact("fact-001") is True
        assert tracer.verify_fact("fact-999") is False
    
    def test_update_trace(self, tracer):
        """测试更新溯源记录"""
        tracer.trace_fact("fact-001", "原始事实", "来源A")
        tracer.update_trace("fact-001", confidence="low", notes="需要验证")
        
        trace = tracer.get_trace("fact-001")
        assert trace["confidence"] == "low"
        assert trace["notes"] == "需要验证"
    
    def test_export_report(self, tracer, temp_dir):
        """测试导出溯源报告"""
        tracer.trace_fact(
            "fact-001",
            "2025年新能源汽车销量1000万辆",
            "中汽协",
            confidence="high"
        )
        
        report_path = Path(temp_dir) / "fact_report.json"
        tracer.export_report(str(report_path))
        
        assert report_path.exists()
        import json
        with open(report_path, 'r', encoding='utf-8') as f:
            report = json.load(f)
            assert len(report["traces"]) == 1
    
    def test_trace_without_optional_fields(self, tracer):
        """测试记录最小化事实"""
        tracer.trace_fact(
            fact_id="fact-min",
            fact_statement="简化事实",
            source="简化来源"
        )
        
        trace = tracer.get_trace("fact-min")
        assert trace["fact_statement"] == "简化事实"
        assert trace["confidence"] == "medium"  # 默认值
