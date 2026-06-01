# -*- coding: utf-8 -*-
"""
对话状态机

管理对话状态转换和上下文
"""

import json
import logging
from enum import Enum
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

from src.core.dialogue.sub_intent import ReadinessLevel

logger = logging.getLogger(__name__)


class ConversationState(Enum):
    """对话状态"""
    UNDERSTANDING = "understanding"       # 理解用户意图
    CLARIFYING = "clarifying"             # 澄清细节
    FRAMEWORK_CONFIRM = "framework_confirm"  # 确认框架
    EXECUTING = "executing"               # 执行研究
    PAUSED = "paused"                     # 已暂停（可恢复）
    CANCELLED = "cancelled"               # 已取消（终态）
    PREVIEWING = "previewing"             # 预览报告
    COMPLETED = "completed"               # 完成


class InvalidTransitionError(Exception):
    """无效状态转换错误"""
    pass


class ConversationStateMachine:
    """
    对话状态机
    
    管理对话的状态转换、上下文和历史记录
    """
    
    # 定义有效的状态转换
    VALID_TRANSITIONS = {
        ConversationState.UNDERSTANDING: [
            ConversationState.UNDERSTANDING,
            ConversationState.CLARIFYING,
            ConversationState.EXECUTING,
            ConversationState.FRAMEWORK_CONFIRM,
            ConversationState.CANCELLED,
        ],
        ConversationState.CLARIFYING: [
            ConversationState.CLARIFYING,
            ConversationState.FRAMEWORK_CONFIRM,
            ConversationState.CANCELLED,
        ],
        ConversationState.FRAMEWORK_CONFIRM: [
            ConversationState.FRAMEWORK_CONFIRM,
            ConversationState.EXECUTING,
            ConversationState.PREVIEWING,
            ConversationState.CLARIFYING,
            ConversationState.CANCELLED,
        ],
        ConversationState.EXECUTING: [
            ConversationState.EXECUTING,
            ConversationState.PAUSED,       # 暂停
            ConversationState.PREVIEWING,
            ConversationState.COMPLETED,
            ConversationState.CANCELLED,    # P0 fix: allow cancel from executing state
            ConversationState.CLARIFYING,          # 需求补充时回退澄清
            ConversationState.FRAMEWORK_CONFIRM,  # 用户明确要求重新设计框架
        ],
        ConversationState.PAUSED: [
            ConversationState.PAUSED,
            ConversationState.EXECUTING,    # 恢复执行
            ConversationState.FRAMEWORK_CONFIRM,  # 修改需求 → 重新确认框架
            ConversationState.CANCELLED,    # 取消
        ],
        ConversationState.CANCELLED: [
            ConversationState.CANCELLED,    # 终态
        ],
        ConversationState.PREVIEWING: [
            ConversationState.PREVIEWING,
            ConversationState.PAUSED,       # 暂停
            ConversationState.COMPLETED,
            ConversationState.CANCELLED,
        ],
        ConversationState.COMPLETED: [
            ConversationState.COMPLETED,    # 终态
        ],
    }
    
    def __init__(
        self,
        research_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        初始化状态机
        
        Args:
            research_id: 研究ID
            context: 初始上下文
        """
        self.research_id = research_id
        self.current_state = ConversationState.UNDERSTANDING
        self.context = context or {}
        self._history: List[Dict[str, Any]] = []
        
        # 记录初始状态
        self._record_state_change(ConversationState.UNDERSTANDING)
    
    def transition(self, target_state: ConversationState):
        """
        转换状态
        
        Args:
            target_state: 目标状态
        
        Raises:
            InvalidTransitionError: 无效的状态转换
        """
        if not self._is_valid_transition(target_state):
            raise InvalidTransitionError(
                f"Invalid transition from {self.current_state.value} to {target_state.value}"
            )
        
        self.current_state = target_state
        self._record_state_change(target_state)
    
    def _is_valid_transition(self, target_state: ConversationState) -> bool:
        """检查转换是否有效"""
        allowed = self.VALID_TRANSITIONS.get(self.current_state, [])
        return target_state in allowed
    
    def _record_state_change(self, state: ConversationState):
        """记录状态变化"""
        self._history.append({
            "state": state,
            "timestamp": datetime.now().isoformat()
        })
    
    def update_context(self, key: str, value: Any):
        """
        更新上下文
        
        Args:
            key: 键
            value: 值
        """
        self.context[key] = value
    
    def get_context(self, key: str, default: Any = None) -> Any:
        """
        获取上下文值
        
        Args:
            key: 键
            default: 默认值
        
        Returns:
            上下文值
        """
        return self.context.get(key, default)
    
    def get_history(self) -> List[Dict[str, Any]]:
        """获取状态历史"""
        return self._history.copy()
    
    def clear_history(self):
        """清除历史"""
        self._history.clear()
    
    def is_in_state(self, state: ConversationState) -> bool:
        """检查是否在指定状态"""
        return self.current_state == state
    
    def can_transition_to(self, target_state: ConversationState) -> bool:
        """检查是否可以转换到目标状态"""
        return self._is_valid_transition(target_state)
    
    def get_allowed_transitions(self) -> List[ConversationState]:
        """获取允许的转换"""
        return self.VALID_TRANSITIONS.get(self.current_state, []).copy()
    
    def reset(self):
        """重置状态机"""
        self.current_state = ConversationState.UNDERSTANDING
        self.context.clear()
        self._history.clear()
        self._record_state_change(ConversationState.UNDERSTANDING)
    
    def save(self, file_path: str):
        """
        保存状态到文件
        
        Args:
            file_path: 文件路径
        """
        data = {
            "research_id": self.research_id,
            "current_state": self.current_state.value,
            "context": self.context,
            "history": [
                {"state": h["state"].value, "timestamp": h["timestamp"]}
                for h in self._history
            ]
        }
        
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load(cls, file_path: str) -> 'ConversationStateMachine':
        """
        从文件加载状态
        
        Args:
            file_path: 文件路径
        
        Returns:
            状态机实例
        
        Raises:
            FileNotFoundError: 文件不存在
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"State file not found: {file_path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        machine = cls(
            research_id=data.get("research_id"),
            context=data.get("context", {})
        )
        
        # 恢复状态
        machine.current_state = ConversationState(data["current_state"])
        
        # 恢复历史
        machine._history = [
            {
                "state": ConversationState(h["state"]),
                "timestamp": h["timestamp"]
            }
            for h in data.get("history", [])
        ]
        
        return machine
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "research_id": self.research_id,
            "current_state": self.current_state.value,
            "context": self.context,
            "history": [
                {"state": h["state"].value, "timestamp": h["timestamp"]}
                for h in self._history
            ]
        }

    def force_set_state(self, target_state: ConversationState):
        if not isinstance(target_state, ConversationState):
            raise ValueError(f"Invalid state: {target_state}")
        logger.warning(
            f"Force setting state from {self.current_state.value} to {target_state.value}"
        )
        self.current_state = target_state
        self._record_state_change(target_state)

    def suggest_next(self, intent_state) -> Optional[ConversationState]:
        if self.current_state == ConversationState.UNDERSTANDING:
            if intent_state.readiness_level == ReadinessLevel.SUFFICIENT:
                return ConversationState.FRAMEWORK_CONFIRM
            elif intent_state.readiness_level == ReadinessLevel.PARTIAL:
                return ConversationState.CLARIFYING
            return None

        if self.current_state == ConversationState.CLARIFYING:
            if intent_state.readiness_level == ReadinessLevel.SUFFICIENT:
                return ConversationState.FRAMEWORK_CONFIRM
            return None

        if self.current_state == ConversationState.FRAMEWORK_CONFIRM:
            if intent_state.readiness_level in (ReadinessLevel.INSUFFICIENT, ReadinessLevel.PARTIAL):
                return ConversationState.CLARIFYING
            return None

        return None