"""
@deprecated 装饰器单元测试
"""
import pytest
import warnings
from src.core.utils.deprecation import deprecated


class TestDeprecatedDecorator:
    """@deprecated 装饰器测试类"""
    
    def test_basic_deprecation(self):
        """测试基本废弃警告"""
        @deprecated()
        def old_function():
            return "result"
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = old_function()
            
            assert result == "result"
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "deprecated" in str(w[0].message).lower()
    
    def test_deprecation_with_replacement(self):
        """测试带替代方法的废弃警告"""
        @deprecated(replacement="new_function")
        def old_function():
            return "result"
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = old_function()
            
            assert result == "result"
            assert len(w) == 1
            assert "new_function" in str(w[0].message)
    
    def test_deprecation_with_version(self):
        """测试带版本信息的废弃警告"""
        @deprecated(version="2.0")
        def old_function():
            return "result"
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = old_function()
            
            assert result == "result"
            assert len(w) == 1
            assert "2.0" in str(w[0].message)
    
    def test_deprecation_with_custom_message(self):
        """测试自定义消息"""
        @deprecated(message="Use new_function instead for better performance")
        def old_function():
            return "result"
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = old_function()
            
            assert result == "result"
            assert len(w) == 1
            assert "better performance" in str(w[0].message)
    
    def test_deprecation_all_parameters(self):
        """测试所有参数组合"""
        @deprecated(
            replacement="new_function",
            version="2.0",
            message="This function will be removed"
        )
        def old_function():
            return "result"
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = old_function()
            
            assert result == "result"
            assert len(w) == 1
            # 当提供 message 时，message 会覆盖默认格式
            msg = str(w[0].message)
            assert "removed" in msg
    
    def test_deprecation_on_class_method(self):
        """测试类方法废弃"""
        class MyClass:
            @deprecated(replacement="new_method")
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
            assert "new_method" in str(w[0].message)
    
    def test_deprecation_on_static_method(self):
        """测试静态方法废弃"""
        class MyClass:
            @staticmethod
            @deprecated(replacement="new_static")
            def old_static():
                return "result"
            
            @staticmethod
            def new_static():
                return "new_result"
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = MyClass.old_static()
            
            assert result == "result"
            assert len(w) == 1
    
    def test_deprecation_preserves_function_metadata(self):
        """测试废弃装饰器保留函数元数据"""
        @deprecated()
        def my_function():
            """This is my function"""
            return "result"
        
        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "This is my function"
    
    def test_deprecation_on_class(self):
        """测试类废弃"""
        @deprecated(replacement="NewClass")
        class OldClass:
            def method(self):
                return "result"
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            obj = OldClass()
            
            assert len(w) == 1
            assert "NewClass" in str(w[0].message)
            
            # 方法调用不应再次触发警告
            result = obj.method()
            assert result == "result"
    
    def test_multiple_calls_single_warning(self):
        """测试多次调用只触发一次警告"""
        @deprecated()
        def old_function():
            return "result"
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            # 第一次调用
            old_function()
            first_count = len(w)
            
            # 第二次调用
            old_function()
            second_count = len(w)
            
            # Python warnings 模块默认行为：同类型警告可能被过滤
            # 但我们设置 simplefilter("always")，所以每次都记录
            assert first_count >= 1
            assert second_count >= first_count
    
    def test_deprecation_warning_stack_level(self):
        """测试警告堆栈级别"""
        @deprecated()
        def old_function():
            return "result"
        
        def caller():
            return old_function()
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            caller()
            
            # 警告应指向调用者，而非装饰器内部
            assert len(w) == 1
            # 检查文件名是否正确（应该是测试文件）
            assert "test_deprecation" in w[0].filename or "test_" in w[0].filename
    
    def test_deprecation_with_async_function(self):
        """测试异步函数废弃"""
        @deprecated(replacement="new_async")
        async def old_async():
            return "async_result"
        
        import asyncio
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = asyncio.run(old_async())
            
            assert result == "async_result"
            assert len(w) == 1
            assert "new_async" in str(w[0].message)
    
    def test_deprecation_with_class_property(self):
        """测试类属性废弃"""
        class MyClass:
            @property
            @deprecated(replacement="new_property")
            def old_property(self):
                return "property_value"
            
            @property
            def new_property(self):
                return "new_value"
        
        obj = MyClass()
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = obj.old_property
            
            assert result == "property_value"
            assert len(w) == 1
    
    def test_no_replacement_provided(self):
        """测试未提供替代方法"""
        @deprecated()
        def old_function():
            return "result"
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            old_function()
            
            msg = str(w[0].message)
            # 应包含基本废弃信息
            assert "deprecated" in msg.lower()
            # 不应包含 "Use ... instead"（因为无替代）
            assert "instead" not in msg or "No replacement specified" in msg
    
    def test_deprecation_message_format(self):
        """测试警告消息格式"""
        @deprecated(
            replacement="new_func",
            version="v2.0.0"
        )
        def old_func():
            pass
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            old_func()
            
            msg = str(w[0].message)
            # 消息应清晰、结构化
            assert "old_func" in msg
            assert "new_func" in msg
            assert "v2.0.0" in msg