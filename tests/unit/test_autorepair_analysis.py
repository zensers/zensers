"""
auto-repair 系统深度分析

设计目的：质量检查不通过时自动修复 issues，最多重试 3 次
实际表现：每次重试分数递减（40→20→15），3 次后仍然失败

问题清单：
1. 大多数 issue 没有 section 字段 → adjustments 列表为空
2. adjustments 为空时 continue 但依然消耗重试次数
3. html_content 每轮重新读取追加 → 分数越查越低
4. 两处相同代码（research + _research_with_routing）
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path


# 模拟 orchestrator.py:1027-1094 的 auto-repair 逻辑
def simulate_autorepair_loop(issues_list, max_retries=3):
    """
    模拟 auto-repair 循环，追踪每次重试的行为
    
    Returns: {
        "retries_used": int,       # 实际消耗的重试次数
        "repairs_attempted": int,  # 实际执行修复的次数
        "score_sequence": list,    # 每轮分数
    }
    """
    retries_used = 0
    repairs_attempted = 0
    
    for retry in range(max_retries):
        retries_used += 1
        
        # 模拟质量检查
        quality_passed = False
        issues = issues_list[retry] if retry < len(issues_list) else []
        
        if quality_passed:
            break
        
        # auto-repair 逻辑
        if retry < max_retries - 1 and issues:
            adjustments = []
            for issue in issues[:3]:
                issue_type = issue.get("type", "general")
                if issue.get("auto_fixable") is False:
                    continue
                if issue_type == "format":
                    continue
                section = issue.get("section")
                if not section:
                    section = None  # 实际代码中这里就是 None，不会从 message 提取
                if section:
                    adjustments.append({"section": section})
            
            if not adjustments:
                # BUG: 空 adjustments 也消耗 retry
                continue
            
            # 模拟修复执行
            repairs_attempted += 1
    
    return {
        "retries_used": retries_used,
        "repairs_attempted": repairs_attempted,
    }


class TestAutoRepairAnalysis:
    """auto-repair 系统问题分析"""

    def test_empty_adjustments_still_consume_retries(self):
        """
        问题 1：adjustments 为空时 continue 但重试次数照扣
        
        实际日志：score=40 → 20 → 15，3 次用完全部失败
        期望：如果无法修复，应立即退出而不是空转 3 次
        """
        # 模拟真实场景：issues 都没有 section 字段
        issues_rounds = [
            [{"type": "completeness", "severity": "high",
              "message": "word count insufficient"}],  # 没有 section
            [{"type": "accuracy", "severity": "medium",
              "message": "number repeated"}],           # 没有 section
            [{"type": "format", "severity": "low",
              "message": "missing heading"}],           # 没有 section
        ]
        
        result = simulate_autorepair_loop(issues_rounds, max_retries=3)
        
        assert result["retries_used"] == 3, \
            "3 次重试全部消耗"
        assert result["repairs_attempted"] == 0, \
            "但 0 次实际修复！这就是 BUG：空转 3 次"

    def test_issues_without_section_cannot_be_fixed(self):
        """
        问题 2：大多数 issue 类型缺少 section 字段，无法进入修复流程
        
        检查各类 issue 的典型结构
        """
        typical_issues = [
            # completeness issues
            {"type": "completeness", "severity": "high",
             "message": "word count insufficient"},      # ❌ 无 section
            {"type": "completeness", "severity": "medium",
             "message": "Missing required section: Executive Summary",
             "section": "Executive Summary"},             # ✅ 有 section
            
            # accuracy issues
            {"type": "accuracy", "severity": "high",
             "message": "Suspected placeholder repetition"},  # ❌ 无 section
            {"type": "accuracy", "severity": "medium",
             "message": "数值 '40.85' 出现 5 次"},            # ❌ 无 section
            
            # format issues
            {"type": "format", "severity": "low",
             "message": "missing heading",
             "auto_fixable": False},                        # ⏭ 被跳过
        ]
        
        fixable = 0
        for issue in typical_issues:
            if issue.get("auto_fixable") is False:
                continue
            if issue.get("type") == "format":
                continue
            section = issue.get("section")
            if section:
                fixable += 1
        
        assert fixable == 1, \
            f"只有 1/5 的 issue 可修复（只有 'Missing required section' 有 section 字段）"

    def test_html_content_accumulation_degrades_score(self):
        """
        问题 3：html_content 反复追加导致分数递减
        
        每次重试重新读取 HTML 文件，追加到 content 中
        → 更多文本 → 更多数值模式匹配 → 更多"幻觉"告警 → 分数更低
        """
        # 模拟 quality_check_agent 的 html_content 合并逻辑
        check_input_round1 = {
            "report": {"content": "核心内容500字", "sections": []},
            "html_content": "",  # 首次没有
        }
        check_input_round2 = {
            "report": {"content": "核心内容500字\nHTML模板内容3000字包含大量数字"},  # 追加后更多
            "html_content": "HTML模板内容3000字包含大量数字",
        }
        
        # 第二轮因为 content 更长，会触发更多 pattern 匹配
        len_round1 = len(check_input_round1["report"]["content"])
        len_round2 = len(check_input_round2["report"]["content"])
        
        assert len_round2 > len_round1, \
            "每轮 content 越来越长 → 触发更多检测"
        assert "HTML模板" in check_input_round2["report"]["content"], \
            "html_content 被合并到 report.content 中"

    def test_auto_repair_no_empty_retries(self):
        """
        修复验证：auto-repair 不再有空转重试
        
        关键改动：
        1. `if not adjustments: break` 而非 `continue` → 空 adjustments 立即退出
        2. 最多 1 次重试（range(2)）而非 3 次
        3. 修复后 regenerate 新 HTML，而非 append 到旧 content
        """
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        import inspect
        
        source = inspect.getsource(ResearchOrchestrator)
        
        # 原 BUG 标志：max_quality_retries 应已消失
        assert "max_quality_retries" not in source, \
            "max_quality_retries 已移除"
        
        # 新实现：空 adjustments 时 break 而非 continue
        assert "No auto-fixable issues, stopping" in source, \
            "空 adjustments 时停止重试"

    def test_no_feedback_loop_between_repairs(self):
        """
        问题 5：修复后没有反馈循环
        
        adjust_content 修改文档 → 下一轮检查同一个文档
        但检查的 input 包含 aggregated.to_dict()（未更新）
        → 检查的仍然是旧数据，不是修改后的文档内容
        """
        # 模拟修复后检查仍然使用旧数据
        aggregated = {"sections": [{"title": "A", "content": "旧内容"}]}
        
        # 假设修复了新内容
        new_content = "新内容"
        
        # 但检查时用的是 aggregated（未更新）
        check_input = {"report": aggregated, "html_content": ""}
        
        assert check_input["report"]["sections"][0]["content"] == "旧内容", \
            "检查的仍然是旧 aggregated 数据，不是修复后的新内容"
        assert check_input["report"]["sections"][0]["content"] != new_content, \
            "修复被应用于 HTML 文档而非 structured data"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=long"])
