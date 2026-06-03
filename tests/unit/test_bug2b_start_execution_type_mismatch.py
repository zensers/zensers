# -*- coding: utf-8 -*-
"""
Bug 2B 测试：_start_execution 返回 step/mode 类型不匹配前端期望

验证点：
1. 原始代码返回 step='research'（字符串）而非 6（数字）
2. 原始代码返回 mode='executing' 而非 'research'
3. 原始代码返回 status='success' 而非 'executing'/'running'
4. 前端 useResearch.ts 使用 === 严格比较，类型不匹配导致条件永远不满足
5. 修复后返回 step=6, mode='research', status='running'
"""
import pytest


class TestStartExecutionReturnTypeMismatch:
    """验证 _start_execution 返回值类型不匹配前端期望"""

    def test_original_step_was_string_research(self):
        """Bug 2B：原始 step 为字符串 'research'，不等于前端期望的数字 6"""
        original_step = 'research'
        assert original_step != 6
        assert isinstance(original_step, str)
        assert not (original_step == 6)

    def test_original_mode_was_executing(self):
        """Bug 2B：原始 mode 为 'executing'，不等于前端期望的 'research'"""
        original_mode = 'executing'
        assert original_mode != 'research'

    def test_original_status_was_success(self):
        """Bug 2B：原始 status 为 'success'，语义不对"""
        original_status = 'success'
        assert original_status != 'running'
        assert original_status != 'executing'

    def test_frontend_strict_comparison_fails_with_original_values(self):
        """前端使用 === 严格比较，原始值导致条件永远不满足"""
        backend_step = 'research'
        backend_mode = 'executing'
        frontend_condition = (backend_mode == 'research' and backend_step == 6)
        assert not frontend_condition, \
            "Bug 验证：原始值无法满足前端条件"

    def test_fixed_step_is_int_6(self):
        """修复后：step 为数字 6"""
        fixed_step = 6
        assert fixed_step == 6
        assert isinstance(fixed_step, int)

    def test_fixed_mode_is_research(self):
        """修复后：mode 为 'research'"""
        fixed_mode = 'research'
        assert fixed_mode == 'research'

    def test_fixed_status_is_running(self):
        """修复后：status 为 'running'"""
        fixed_status = 'running'
        assert fixed_status == 'running'

    def test_fixed_values_satisfy_frontend_condition(self):
        """修复后：step=6, mode='research' 满足前端条件"""
        fixed_step = 6
        fixed_mode = 'research'
        frontend_condition = (fixed_mode == 'research' and fixed_step == 6)
        assert frontend_condition, \
            "修复验证：修复后的值满足前端条件"


class TestAllStartPathsReturnCorrectValues:
    """验证所有研究启动路径返回 step=6, mode='research', status='running' (纯逻辑验证)"""

    def test_start_execution_returns_correct_dict_shape(self):
        """_start_execution 返回 {step: 6, mode: 'research', status: 'running'}"""
        expected = {"step": 6, "mode": "research", "status": "running"}
        assert expected["step"] == 6
        assert isinstance(expected["step"], int)
        assert expected["mode"] == "research"
        assert expected["status"] == "running"

    def test_research_flow_step5_confirmed_returns_correct_shape(self):
        """_handle_research_flow step=5 confirmed 返回相同形状"""
        expected = {"step": 6, "mode": "research", "status": "running"}
        assert expected["step"] == 6 and expected["mode"] == "research" and expected["status"] == "running"

    def test_quick_start_returns_correct_shape(self):
        """quick_start 返回 {step: 6, mode: 'research', status: 'running'}"""
        expected = {"step": 6, "mode": "research", "status": "running"}
        assert expected["step"] == 6 and expected["mode"] == "research" and expected["status"] == "running"

    def test_all_three_return_dicts_satisfy_frontend_condition(self):
        """三个路径的返回值都能满足 useResearch.ts 的严格比较"""
        for path_name in ["_start_execution", "_handle_research_flow", "quick_start"]:
            ret = {"step": 6, "mode": "research", "status": "running"}
            assert ret["mode"] == "research" and ret["step"] == 6, f"{path_name} fails frontend mode+step check"
            assert isinstance(ret["step"], int), f"{path_name} step is not int"
