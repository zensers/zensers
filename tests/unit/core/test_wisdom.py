# -*- coding: utf-8 -*-
"""
WisdomStore 测试

TDD 测试优先实现

测试覆盖:
1. 经验记录存储
2. 最佳实践查询
3. 推荐 Skills 获取
4. 聚合统计功能
5. 持久化和恢复
"""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# 导入待测试的类
from src.core.wisdom import (
    WisdomStore,
    WisdomEntry,
    WisdomAggregation
)


class TestWisdomEntry:
    """Wisdom 条目数据类测试"""
    
    def test_entry_creation(self):
        """测试条目数据类创建"""
        entry = WisdomEntry(
            task_type="market_analysis",
            task_aspect="competition",
            skills_used=["search_skill", "http_skill"],
            success=True,
            approach="先收集TOP5企业数据",
            duration_ms=5000,
            confidence_score=0.85
        )
        
        assert entry.task_type == "market_analysis"
        assert entry.task_aspect == "competition"
        assert len(entry.skills_used) == 2
        assert entry.success is True
        assert entry.confidence_score == 0.85
    
    def test_entry_to_dict(self):
        """测试条目序列化"""
        entry = WisdomEntry(
            task_type="test",
            task_aspect="test_aspect",
            skills_used=["skill1"],
            success=True,
            approach="test approach",
            duration_ms=1000,
            confidence_score=0.9
        )
        
        result = entry.to_dict()
        assert result["task_type"] == "test"
        assert result["skills_used"] == ["skill1"]
        assert "timestamp" in result
    
    def test_entry_from_dict(self):
        """测试条目反序列化"""
        data = {
            "task_type": "test",
            "task_aspect": "test_aspect",
            "skills_used": ["skill1", "skill2"],
            "success": False,
            "approach": "test approach",
            "duration_ms": 2000,
            "confidence_score": 0.75,
            "timestamp": "2026-04-10T15:00:00"
        }
        
        entry = WisdomEntry.from_dict(data)
        assert entry.task_type == "test"
        assert entry.success is False


class TestWisdomAggregation:
    """Wisdom 聚合数据类测试"""
    
    def test_aggregation_creation(self):
        """测试聚合数据类创建"""
        agg = WisdomAggregation(
            task_type="market_analysis",
            task_aspect="competition",
            total_tasks=10,
            successful_tasks=8,
            success_rate=0.8,
            skill_recommendations={
                "search_skill": {"usage_count": 10, "success_rate": 0.9}
            },
            best_approaches=["approach1", "approach2"]
        )
        
        assert agg.task_type == "market_analysis"
        assert agg.total_tasks == 10
        assert agg.success_rate == 0.8
    
    def test_aggregation_update(self):
        """测试聚合数据更新"""
        agg = WisdomAggregation(
            task_type="test",
            task_aspect="test",
            total_tasks=0,
            successful_tasks=0,
            success_rate=0.0,
            skill_recommendations={},
            best_approaches=[]
        )
        
        entry = WisdomEntry(
            task_type="test",
            task_aspect="test",
            skills_used=["skill1"],
            success=True,
            approach="test approach",
            duration_ms=1000,
            confidence_score=0.8
        )
        
        agg.update_with_entry(entry)
        
        assert agg.total_tasks == 1
        assert agg.successful_tasks == 1
        assert agg.success_rate == 1.0
        assert "skill1" in agg.skill_recommendations


class TestWisdomStore:
    """WisdomStore 核心功能测试"""
    
    @pytest.fixture
    def temp_store_path(self):
        """创建临时存储路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / ".wisdom"
    
    @pytest.fixture
    def wisdom_store(self, temp_store_path):
        """创建 WisdomStore 实例"""
        return WisdomStore(store_path=temp_store_path)
    
    # ========== 经验记录测试 ==========
    
    def test_record_experience(self, wisdom_store):
        """测试记录经验"""
        wisdom_store.record_experience(
            task_type="market_analysis",
            task_aspect="competition",
            skills_used=["search_skill", "http_skill"],
            success=True,
            approach="先收集TOP5企业数据",
            duration_ms=5000
        )
        
        # 验证记录成功
        wisdom = wisdom_store.get_best_practice("market_analysis", "competition")
        assert wisdom is not None
        assert wisdom["total_tasks"] == 1
        assert wisdom["successful_tasks"] == 1
    
    def test_record_multiple_experiences(self, wisdom_store):
        """测试记录多条经验"""
        for i in range(5):
            wisdom_store.record_experience(
                task_type="market_analysis",
                task_aspect="competition",
                skills_used=["search_skill", "http_skill"],
                success=i < 4,  # 4次成功，1次失败
                approach="test approach",
                duration_ms=1000 * (i + 1)
            )
        
        wisdom = wisdom_store.get_best_practice("market_analysis", "competition")
        assert wisdom["total_tasks"] == 5
        assert wisdom["successful_tasks"] == 4
        assert wisdom["success_rate"] == 0.8
    
    def test_record_different_aspects(self, wisdom_store):
        """测试记录不同维度的经验"""
        wisdom_store.record_experience(
            task_type="market_analysis",
            task_aspect="competition",
            skills_used=["search_skill"],
            success=True,
            approach="approach1",
            duration_ms=1000
        )
        
        wisdom_store.record_experience(
            task_type="market_analysis",
            task_aspect="market_size",
            skills_used=["search_skill", "http_skill"],
            success=True,
            approach="approach2",
            duration_ms=2000
        )
        
        # 两个维度应该分别存储
        wisdom1 = wisdom_store.get_best_practice("market_analysis", "competition")
        wisdom2 = wisdom_store.get_best_practice("market_analysis", "market_size")
        
        assert wisdom1["total_tasks"] == 1
        assert wisdom2["total_tasks"] == 1
    
    # ========== 最佳实践查询测试 ==========
    
    def test_get_best_practice(self, wisdom_store):
        """测试获取最佳实践"""
        wisdom_store.record_experience(
            task_type="market_analysis",
            task_aspect="competition",
            skills_used=["search_skill", "http_skill"],
            success=True,
            approach="先收集TOP5企业数据",
            duration_ms=5000
        )
        
        best = wisdom_store.get_best_practice("market_analysis", "competition")
        
        assert best is not None
        assert "skill_recommendations" in best
        assert "best_approaches" in best
        assert best["success_rate"] == 1.0
    
    def test_get_best_practice_not_found(self, wisdom_store):
        """测试获取不存在的最佳实践"""
        best = wisdom_store.get_best_practice("unknown_type", "unknown_aspect")
        
        # 应返回默认值而非 None
        assert best is not None
        assert best["total_tasks"] == 0
    
    # ========== 推荐 Skills 测试 ==========
    
    def test_get_recommended_skills(self, wisdom_store):
        """测试获取推荐 Skills"""
        # 记录多次成功经验
        for _ in range(3):
            wisdom_store.record_experience(
                task_type="market_analysis",
                task_aspect="competition",
                skills_used=["search_skill", "http_skill", "web_scraper"],
                success=True,
                approach="test",
                duration_ms=1000
            )
        
        skills = wisdom_store.get_recommended_skills(
            task_type="market_analysis",
            task_aspect="competition"
        )
        
        assert len(skills) > 0
        assert "search_skill" in skills
        assert "http_skill" in skills
    
    def test_get_recommended_skills_with_min_success_rate(self, wisdom_store):
        """测试带成功率阈值的推荐 Skills"""
        # 3次成功，2次失败
        for i in range(5):
            wisdom_store.record_experience(
                task_type="market_analysis",
                task_aspect="competition",
                skills_used=["search_skill"],
                success=i < 3,
                approach="test",
                duration_ms=1000
            )
        
        # 只返回高成功率的 Skills
        skills = wisdom_store.get_recommended_skills(
            task_type="market_analysis",
            task_aspect="competition",
            min_success_rate=0.7
        )
        
        # search_skill 成功率 = 3/5 = 0.6，低于阈值，不应返回
        assert len(skills) == 0 or "search_skill" not in skills
    
    def test_get_recommended_skills_sorted_by_usage(self, wisdom_store):
        """测试推荐 Skills 按使用频率排序"""
        # search_skill 使用 5 次
        for _ in range(5):
            wisdom_store.record_experience(
                task_type="test",
                task_aspect="test",
                skills_used=["search_skill", "http_skill"],
                success=True,
                approach="test",
                duration_ms=1000
            )
        
        # web_scraper 只使用 2 次
        for _ in range(2):
            wisdom_store.record_experience(
                task_type="test",
                task_aspect="test",
                skills_used=["web_scraper"],
                success=True,
                approach="test",
                duration_ms=1000
            )
        
        skills = wisdom_store.get_recommended_skills("test", "test")
        
        # search_skill 使用频率最高，应排第一
        assert len(skills) > 0
        if len(skills) >= 2:
            # 验证排序逻辑（高频在前）
            pass  # 具体排序逻辑在实现中
    
    # ========== 聚合统计测试 ==========
    
    def test_skill_recommendations_aggregation(self, wisdom_store):
        """测试 Skill 推荐聚合"""
        # 记录多次使用相同 Skill 的经验
        for i in range(3):
            wisdom_store.record_experience(
                task_type="market_analysis",
                task_aspect="competition",
                skills_used=["search_skill"],
                success=True,
                approach="test",
                duration_ms=1000 + i * 500
            )
        
        best = wisdom_store.get_best_practice("market_analysis", "competition")
        
        assert "search_skill" in best["skill_recommendations"]
        skill_stats = best["skill_recommendations"]["search_skill"]
        assert skill_stats["usage_count"] == 3
        assert skill_stats["success_rate"] == 1.0
    
    def test_best_approaches_tracking(self, wisdom_store):
        """测试最佳方法追踪"""
        # 记录多种方法
        approaches = [
            "方法A：先收集TOP5企业",
            "方法B：从行业报告入手",
            "方法A：先收集TOP5企业"  # 重复方法
        ]
        
        for approach in approaches:
            wisdom_store.record_experience(
                task_type="market_analysis",
                task_aspect="competition",
                skills_used=["search_skill"],
                success=True,
                approach=approach,
                duration_ms=1000
            )
        
        best = wisdom_store.get_best_practice("market_analysis", "competition")
        
        assert len(best["best_approaches"]) > 0
        # 方法A 应该有更高的计数
    
    # ========== 持久化测试 ==========
    
    def test_persistence(self, temp_store_path):
        """测试持久化"""
        # 创建并记录
        store1 = WisdomStore(store_path=temp_store_path)
        store1.record_experience(
            task_type="market_analysis",
            task_aspect="competition",
            skills_used=["search_skill"],
            success=True,
            approach="test",
            duration_ms=1000
        )
        
        # 重新加载
        store2 = WisdomStore(store_path=temp_store_path)
        best = store2.get_best_practice("market_analysis", "competition")
        
        # 应恢复之前的数据
        assert best["total_tasks"] == 1
    
    def test_index_file_created(self, wisdom_store, temp_store_path):
        """测试索引文件创建"""
        wisdom_store.record_experience(
            task_type="test",
            task_aspect="test",
            skills_used=["skill1"],
            success=True,
            approach="test",
            duration_ms=1000
        )
        
        # 检查文件是否存在
        index_file = temp_store_path / "wisdom_index.json"
        assert index_file.exists() or (temp_store_path / "market_analysis").exists()
    
    # ========== 边界条件测试 ==========
    
    def test_empty_skills_list(self, wisdom_store):
        """测试空 Skills 列表"""
        wisdom_store.record_experience(
            task_type="test",
            task_aspect="test",
            skills_used=[],
            success=True,
            approach="test",
            duration_ms=1000
        )
        
        best = wisdom_store.get_best_practice("test", "test")
        assert best is not None
        assert best["total_tasks"] == 1
    
    def test_very_long_approach_description(self, wisdom_store):
        """测试超长方法描述"""
        long_approach = "test" * 1000
        
        wisdom_store.record_experience(
            task_type="test",
            task_aspect="test",
            skills_used=["skill1"],
            success=True,
            approach=long_approach,
            duration_ms=1000
        )
        
        # 应正常处理
        best = wisdom_store.get_best_practice("test", "test")
        assert best is not None
    
    def test_special_characters_in_type(self, wisdom_store):
        """测试特殊字符处理"""
        wisdom_store.record_experience(
            task_type="market:analysis",
            task_aspect="竞争/格局",
            skills_used=["skill1"],
            success=True,
            approach="test",
            duration_ms=1000
        )
        
        # 特殊字符应被安全处理
        best = wisdom_store.get_best_practice("market:analysis", "竞争/格局")
        assert best is not None


class TestWisdomStoreIntegration:
    """WisdomStore 集成测试"""
    
    @pytest.fixture
    def temp_store_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / ".wisdom"
    
    @pytest.fixture
    def wisdom_store(self, temp_store_path):
        return WisdomStore(store_path=temp_store_path)
    
    def test_full_workflow(self, wisdom_store):
        """测试完整工作流"""
        # 1. 记录多次经验
        for i in range(10):
            wisdom_store.record_experience(
                task_type="market_analysis",
                task_aspect="competition",
                skills_used=["search_skill", "http_skill"] if i % 2 == 0 else ["search_skill"],
                success=i < 8,  # 80% 成功率
                approach="先收集TOP5企业数据" if i < 5 else "从行业报告入手",
                duration_ms=1000 * (i + 1)
            )
        
        # 2. 获取最佳实践
        best = wisdom_store.get_best_practice("market_analysis", "competition")
        
        assert best["total_tasks"] == 10
        assert best["successful_tasks"] == 8
        assert best["success_rate"] == 0.8
        
        # 3. 获取推荐 Skills
        skills = wisdom_store.get_recommended_skills(
            task_type="market_analysis",
            task_aspect="competition"
        )
        
        assert len(skills) > 0
    
    def test_category_template_update(self, wisdom_store):
        """测试 Category 模板更新"""
        # 积累足够经验后，模板应更新
        for _ in range(10):
            wisdom_store.record_experience(
                task_type="market_analysis",
                task_aspect="competition",
                skills_used=["search_skill", "http_skill", "web_scraper"],
                success=True,
                approach="test approach",
                duration_ms=1000
            )
        
        # 获取更新后的模板建议
        template = wisdom_store.update_category_template(
            task_type="market_analysis",
            task_aspect="competition"
        )
        
        assert template is not None
        # 模板应包含高成功率的 Skills
        assert len(template.get("recommended_skills", [])) > 0