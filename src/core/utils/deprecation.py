# -*- coding: utf-8 -*-
"""
废弃装饰器

用于标记即将废弃的方法，提醒用户迁移到新接口。

使用方式：
    from src.core.utils import deprecated
    
    class MyClass:
        @deprecated(replacement="new_method()", version="2.0")
        def old_method(self):
            '''[DEPRECATED] 使用 new_method() 替代'''
            return self.new_method()
        
        def new_method(self):
            return "new implementation"

当调用 old_method() 时，会输出警告：
    DeprecationWarning: old_method is deprecated, use new_method() instead, 
                       will be removed in version 2.0
"""

__all__ = ["deprecated"]

import warnings
from functools import wraps
from typing import Optional, Callable, TypeVar, Any

# 类型变量，用于保持装饰器的类型提示
F = TypeVar('F', bound=Callable[..., Any])


def deprecated(
    replacement: Optional[str] = None,
    version: Optional[str] = None,
    message: Optional[str] = None
) -> Callable[[F], F]:
    """
    标记方法为废弃的装饰器
    
    当被装饰的方法被调用时，会发出 DeprecationWarning 警告。
    
    Args:
        replacement: 替代方法名或使用说明
            例如: "add()" 或 "list() with filters"
        version: 计划移除的版本号
            例如: "2.0"
        message: 自定义警告消息（可选，会覆盖默认格式）
    
    Returns:
        装饰器函数
    
    Examples:
        # 基本用法
        @deprecated()
        def old_method(self):
            pass
        
        # 指定替代方法
        @deprecated(replacement="new_method()")
        def old_method(self):
            return self.new_method()
        
        # 指定移除版本
        @deprecated(replacement="new_method()", version="2.0")
        def old_method(self):
            return self.new_method()
        
        # 自定义消息
        @deprecated(message="This method will be removed, use OtherClass.method instead")
        def old_method(self):
            pass
    
    Warning:
        警告示例输出：
        >>> obj.old_method()
        DeprecationWarning: old_method is deprecated, use new_method() instead, 
                           will be removed in version 2.0
    """
    def decorator(func: F) -> F:
        # 构建警告消息
        if message is not None:
            # 使用自定义消息
            warning_msg = message
        else:
            # 构建默认消息
            warning_msg = f"{func.__name__} is deprecated"
            if replacement:
                warning_msg += f", use {replacement} instead"
            if version:
                warning_msg += f", will be removed in version {version}"
        
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # 发出废弃警告
            warnings.warn(
                warning_msg,
                DeprecationWarning,
                stacklevel=2  # 指向调用者，而非装饰器
            )
            # 执行原函数
            return func(*args, **kwargs)
        
        # 添加废弃标记属性
        wrapper._is_deprecated = True  # type: ignore
        wrapper._deprecated_replacement = replacement  # type: ignore
        wrapper._deprecated_version = version  # type: ignore
        
        return wrapper  # type: ignore
    
    return decorator


def is_deprecated(func: Callable) -> bool:
    """
    检查函数是否被标记为废弃
    
    Args:
        func: 要检查的函数
        
    Returns:
        是否被 @deprecated 装饰
    """
    return getattr(func, '_is_deprecated', False)


def get_deprecation_info(func: Callable) -> dict:
    """
    获取函数的废弃信息
    
    Args:
        func: 要检查的函数
        
    Returns:
        包含 replacement 和 version 的字典
    """
    return {
        "is_deprecated": is_deprecated(func),
        "replacement": getattr(func, '_deprecated_replacement', None),
        "version": getattr(func, '_deprecated_version', None),
    }
