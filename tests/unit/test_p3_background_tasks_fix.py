# -*- coding: utf-8 -*-
"""
P3 Fix: _background_tasks 属性缺失导致 shutdown 清理失败

Bug: main.py shutdown 访问 ResearchAPI._background_tasks 作为类属性，
但它是实例属性，导致 AttributeError: type object 'ResearchAPI' has no attribute '_background_tasks'

修复: 将 _background_tasks 和 _background_task_gen 改为类属性
"""

import pytest


class TestBackgroundTasksClassAttribute:
    """_background_tasks 应为类属性以便 shutdown 访问"""

    def test_background_tasks_is_class_attribute(self):
        """ResearchAPI._background_tasks 应作为类属性存在"""
        from src.api.research_api import ResearchAPI
        assert hasattr(ResearchAPI, "_background_tasks"), \
            "ResearchAPI 应有 _background_tasks 类属性"

    def test_background_task_gen_is_class_attribute(self):
        """ResearchAPI._background_task_gen 应作为类属性存在"""
        from src.api.research_api import ResearchAPI
        assert hasattr(ResearchAPI, "_background_task_gen"), \
            "ResearchAPI 应有 _background_task_gen 类属性"

    def test_shutdown_can_access_class_attributes(self):
        """shutdown 代码应能通过类访问这些属性"""
        from src.api.research_api import ResearchAPI
        try:
            bg_tasks = ResearchAPI._background_tasks
            bg_gen = ResearchAPI._background_task_gen
            assert isinstance(bg_tasks, dict)
            assert isinstance(bg_gen, dict)
        except AttributeError as e:
            pytest.fail(f"shutdown 无法访问类属性: {e}")

    def test_instance_and_class_share_same_dict(self):
        """实例属性和类属性应是同一个字典（共享状态）"""
        from src.api.research_api import ResearchAPI
        api = ResearchAPI()
        assert api._background_tasks is ResearchAPI._background_tasks, \
            "实例和类应共享同一个 _background_tasks 字典"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
