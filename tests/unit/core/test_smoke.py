"""
冒烟测试 - 验证测试环境正常
"""
import pytest
import sys


class TestSmoke:
    """冒烟测试类"""
    
    @pytest.mark.smoke
    def test_python_version(self):
        """测试Python版本 >= 3.11"""
        assert sys.version_info >= (3, 11), "Python版本必须 >= 3.11"
    
    @pytest.mark.smoke
    def test_import_pydantic(self):
        """测试可以导入pydantic"""
        import pydantic
        assert pydantic.__version__ >= "2.0.0"
    
    @pytest.mark.smoke
    def test_import_pytest_asyncio(self):
        """测试可以导入pytest-asyncio"""
        import pytest_asyncio
        assert pytest_asyncio is not None
    
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_async_test_works(self):
        """测试异步测试可以正常运行"""
        result = await self.async_helper()
        assert result == "success"
    
    async def async_helper(self):
        """异步辅助方法"""
        return "success"
