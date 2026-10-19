"""
数据管理模块

提供数据存储和链路追踪功能。
"""
from .data_lineage_manager import DataLineageManager, DataRecord

__all__ = [
    "DataLineageManager",
    "DataRecord",
]