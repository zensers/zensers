# -*- coding: utf-8 -*-
"""
文档调整处理器
============

提供文档调整功能：
1. 全局调整（GLOBAL）
2. 章节调整（SECTION）
3. 元素调整（ELEMENT）
4. 调整历史记录

调整范围：
- GLOBAL: 全局样式、字体、间距等
- SECTION: 单章节内容、标题、排序
- ELEMENT: 表格、图表等具体元素
"""

import copy
import json
import logging
import os
import re
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 常量定义
VALID_ADJUSTMENT_TYPES = ['global', 'section', 'element']
TASK_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')


@dataclass
class AdjustmentResult:
    """调整结果"""
    success: bool
    adjustment_id: Optional[str] = None
    adjusted_content: Optional[Dict[str, Any]] = None
    adjustment_type: Optional[str] = None
    target: Optional[str] = None
    changes: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    error_code: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "adjustment_id": self.adjustment_id,
            "adjusted_content": self.adjusted_content,
            "adjustment_type": self.adjustment_type,
            "target": self.target,
            "changes": self.changes,
            "error": self.error,
            "error_code": self.error_code
        }


@dataclass
class AdjustmentRecord:
    """调整记录"""
    adjustment_id: str
    task_id: str
    adjustment_type: str
    target: Optional[str]
    adjustment: Dict[str, Any]
    applied_at: datetime
    changes: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "adjustment_id": self.adjustment_id,
            "task_id": self.task_id,
            "adjustment_type": self.adjustment_type,
            "target": self.target,
            "adjustment": self.adjustment,
            "applied_at": self.applied_at.isoformat(),
            "changes": self.changes
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AdjustmentRecord":
        """从字典创建"""
        return cls(
            adjustment_id=data.get("adjustment_id", ""),
            task_id=data.get("task_id", ""),
            adjustment_type=data.get("adjustment_type", ""),
            target=data.get("target"),
            adjustment=data.get("adjustment", {}),
            applied_at=datetime.fromisoformat(data.get("applied_at", datetime.now().isoformat())),
            changes=data.get("changes", [])
        )


class AdjustmentHandler:
    """
    文档调整处理器
    
    处理文档的各种调整操作。
    
    使用示例：
        handler = AdjustmentHandler()
        
        # 全局调整
        result = handler.apply_adjustment(
            document_content={"title": "报告", "sections": []},
            adjustment_type="global",
            adjustment={"style": {"font": "Arial"}}
        )
        
        # 章节调整
        result = handler.apply_adjustment(
            document_content=document,
            adjustment_type="section",
            target="section_1",
            adjustment={"title": "新标题"}
        )
    """
    
    def __init__(self, history_dir: Optional[str] = None):
        """
        初始化调整处理器
        
        Args:
            history_dir: 调整历史存储目录
        """
        self.history_dir = Path(history_dir) if history_dir else None
        
        if self.history_dir and not self.history_dir.exists():
            self.history_dir.mkdir(parents=True, exist_ok=True)
    
    def _is_valid_adjustment_type(self, adjustment_type: str) -> bool:
        """验证调整类型"""
        return adjustment_type in VALID_ADJUSTMENT_TYPES
    
    def _is_valid_task_id(self, task_id: str) -> bool:
        """验证task_id"""
        return bool(TASK_ID_PATTERN.match(task_id))
    
    def _generate_adjustment_id(self) -> str:
        """生成调整ID"""
        return f"adj_{uuid.uuid4().hex[:8]}"
    
    def apply_adjustment(
        self,
        document_content: Dict[str, Any],
        adjustment_type: str,
        adjustment: Dict[str, Any],
        target: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> AdjustmentResult:
        """
        应用调整
        
        Args:
            document_content: 文档内容
            adjustment_type: 调整类型
            adjustment: 调整参数
            target: 目标（章节ID/元素ID）
            task_id: 任务ID（用于记录历史）
            
        Returns:
            AdjustmentResult 调整结果
        """
        # 验证调整类型
        if not self._is_valid_adjustment_type(adjustment_type):
            logger.warning(f"Invalid adjustment type: {adjustment_type}")
            return AdjustmentResult(
                success=False,
                error=f"Invalid adjustment type: {adjustment_type}",
                error_code="INVALID_TYPE"
            )
        
        # section/element 类型需要 target
        if adjustment_type in ['section', 'element'] and not target:
            logger.warning(f"Adjustment type '{adjustment_type}' requires target")
            return AdjustmentResult(
                success=False,
                error=f"Adjustment type '{adjustment_type}' requires a target",
                error_code="MISSING_TARGET"
            )
        
        # 验证输入
        if not isinstance(document_content, dict):
            return AdjustmentResult(
                success=False,
                error="document_content must be a dict",
                error_code="INVALID_INPUT"
            )
        
        if not isinstance(adjustment, dict):
            return AdjustmentResult(
                success=False,
                error="adjustment must be a dict",
                error_code="INVALID_ADJUSTMENT"
            )
        
        try:
            # 深拷贝避免修改原数据
            adjusted = copy.deepcopy(document_content)
            changes = []
            adjustment_id = self._generate_adjustment_id()
            
            # 根据类型应用调整
            if adjustment_type == "global":
                adjusted, changes = self._apply_global_adjustment(adjusted, adjustment)
            elif adjustment_type == "section" and target:
                adjusted, changes = self._apply_section_adjustment(adjusted, target, adjustment)
            elif adjustment_type == "element" and target:
                adjusted, changes = self._apply_element_adjustment(adjusted, target, adjustment)
            
            # 记录历史
            if task_id and self.history_dir and self._is_valid_task_id(task_id):
                self._record_adjustment(
                    task_id=task_id,
                    adjustment_id=adjustment_id,
                    adjustment_type=adjustment_type,
                    target=target,
                    adjustment=adjustment,
                    changes=changes
                )
            
            logger.info(f"Applied {adjustment_type} adjustment: {adjustment_id}")
            
            return AdjustmentResult(
                success=True,
                adjustment_id=adjustment_id,
                adjusted_content=adjusted,
                adjustment_type=adjustment_type,
                target=target,
                changes=changes
            )
            
        except Exception as e:
            logger.error(f"Adjustment failed: {e}")
            return AdjustmentResult(
                success=False,
                error=str(e),
                error_code="ADJUSTMENT_ERROR"
            )
    
    def _apply_global_adjustment(
        self,
        content: Dict[str, Any],
        adjustment: Dict[str, Any]
    ) -> tuple:
        """应用全局调整"""
        changes = []
        
        for key, value in adjustment.items():
            if key in content:
                old_value = content[key]
                content[key] = value
                changes.append({
                    "type": "update",
                    "key": key,
                    "old_value": old_value,
                    "new_value": value
                })
            else:
                content[key] = value
                changes.append({
                    "type": "add",
                    "key": key,
                    "new_value": value
                })
        
        return content, changes
    
    def _apply_section_adjustment(
        self,
        content: Dict[str, Any],
        target: str,
        adjustment: Dict[str, Any]
    ) -> tuple:
        """应用章节调整"""
        changes = []
        sections = content.get("sections", [])
        
        for i, section in enumerate(sections):
            if isinstance(section, dict) and section.get("id") == target:
                for key, value in adjustment.items():
                    if key in section:
                        old_value = section[key]
                        section[key] = value
                        changes.append({
                            "type": "section_update",
                            "section_id": target,
                            "key": key,
                            "old_value": old_value,
                            "new_value": value
                        })
                    else:
                        section[key] = value
                        changes.append({
                            "type": "section_add",
                            "section_id": target,
                            "key": key,
                            "new_value": value
                        })
                break
        
        return content, changes
    
    def _apply_element_adjustment(
        self,
        content: Dict[str, Any],
        target: str,
        adjustment: Dict[str, Any]
    ) -> tuple:
        """应用元素调整"""
        changes = []
        
        # 递归搜索目标元素
        def find_and_update(data: Any, target_id: str, adj: Dict[str, Any]) -> List[Dict[str, Any]]:
            found_changes = []
            
            if isinstance(data, dict):
                if data.get("id") == target_id:
                    for key, value in adj.items():
                        if key in data:
                            old_value = data[key]
                            data[key] = value
                            found_changes.append({
                                "type": "element_update",
                                "element_id": target_id,
                                "key": key,
                                "old_value": old_value,
                                "new_value": value
                            })
                        else:
                            data[key] = value
                            found_changes.append({
                                "type": "element_add",
                                "element_id": target_id,
                                "key": key,
                                "new_value": value
                            })
                
                for key, value in data.items():
                    if isinstance(value, (dict, list)):
                        found_changes.extend(find_and_update(value, target_id, adj))
            
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, (dict, list)):
                        found_changes.extend(find_and_update(item, target_id, adj))
            
            return found_changes
        
        changes = find_and_update(content, target, adjustment)
        
        return content, changes
    
    def _record_adjustment(
        self,
        task_id: str,
        adjustment_id: str,
        adjustment_type: str,
        target: Optional[str],
        adjustment: Dict[str, Any],
        changes: List[Dict[str, Any]]
    ) -> None:
        """记录调整历史"""
        if not self.history_dir:
            return
        
        record = AdjustmentRecord(
            adjustment_id=adjustment_id,
            task_id=task_id,
            adjustment_type=adjustment_type,
            target=target,
            adjustment=adjustment,
            applied_at=datetime.now(),
            changes=changes
        )
        
        # 加载历史
        history_file = self.history_dir / task_id / "adjustments.json"
        history_file.parent.mkdir(parents=True, exist_ok=True)
        
        records = []
        if history_file.exists():
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    records = [AdjustmentRecord.from_dict(r) for r in data.get("adjustments", [])]
            except (json.JSONDecodeError, IOError):
                pass
        
        records.append(record)
        
        # 保存
        try:
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "task_id": task_id,
                    "adjustments": [r.to_dict() for r in records]
                }, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.warning(f"Failed to save adjustment history: {e}")
    
    def get_adjustment_history(self, task_id: str) -> List[AdjustmentRecord]:
        """获取调整历史"""
        if not self.history_dir:
            return []
        
        history_file = self.history_dir / task_id / "adjustments.json"
        
        if history_file.exists():
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return [AdjustmentRecord.from_dict(r) for r in data.get("adjustments", [])]
            except (json.JSONDecodeError, IOError):
                return []
        
        return []


# 导出
__all__ = ["AdjustmentHandler", "AdjustmentResult", "AdjustmentRecord"]