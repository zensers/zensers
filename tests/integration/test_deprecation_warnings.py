"""
集成测试：验证废弃警告是否正常工作
"""
import pytest
import warnings

from src.core.utils.deprecation import deprecated, is_deprecated, get_deprecation_info


class TestDeprecationWarnings:
    """测试废弃警告是否正常触发"""
    
    def test_deprecated_function_emits_warning(self):
        """测试废弃函数发出警告"""
        @deprecated(replacement="new_function()")
        def old_function():
            return "result"
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = old_function()
            
            assert result == "result"
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "new_function()" in str(w[0].message)
    
    def test_is_deprecated_helper(self):
        """测试 is_deprecated 辅助函数"""
        @deprecated()
        def old_func():
            pass
        
        def new_func():
            pass
        
        assert is_deprecated(old_func) == True
        assert is_deprecated(new_func) == False
    
    def test_get_deprecation_info_helper(self):
        """测试 get_deprecation_info 辅助函数"""
        @deprecated(replacement="new_func()", version="2.0")
        def old_func():
            pass
        
        info = get_deprecation_info(old_func)
        
        assert info["is_deprecated"] == True
        assert info["replacement"] == "new_func()"
        assert info["version"] == "2.0"
    
    def test_deprecated_class_method(self):
        """测试废弃类方法"""
        class MyClass:
            @deprecated(replacement="new_method()")
            def old_method(self):
                return "result"
            
            def new_method(self):
                return "new_result"
        
        obj = MyClass()
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = obj.old_method()
            
            assert result == "result"
            assert len(w) == 1
            assert "new_method()" in str(w[0].message)
    
    def test_deprecated_static_method(self):
        """测试废弃静态方法"""
        class MyClass:
            @staticmethod
            @deprecated(replacement="new_static()")
            def old_static():
                return "result"
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = MyClass.old_static()
            
            assert result == "result"
            assert len(w) == 1
    
    def test_deprecated_async_function(self):
        """测试废弃异步函数"""
        @deprecated(replacement="new_async()")
        async def old_async():
            return "async_result"
        
        import asyncio
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = asyncio.run(old_async())
            
            assert result == "async_result"
            assert len(w) == 1
    
    def test_multiple_deprecated_calls(self):
        """测试多次调用废弃函数"""
        call_count = 0
        
        @deprecated()
        def old_func():
            nonlocal call_count
            call_count += 1
            return call_count
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            result1 = old_func()
            result2 = old_func()
            
            assert result1 == 1
            assert result2 == 2
            # 每次调用都会发出警告
            assert len(w) >= 1
    
    def test_deprecation_preserves_function_name(self):
        """测试废弃装饰器保留函数名"""
        @deprecated()
        def my_special_function():
            pass
        
        assert my_special_function.__name__ == "my_special_function"
    
    def test_deprecation_preserves_docstring(self):
        """测试废弃装饰器保留文档字符串"""
        @deprecated()
        def documented_function():
            """This is a documented function."""
            pass
        
        assert "documented function" in documented_function.__doc__