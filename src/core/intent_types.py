# -*- coding: utf-8 -*-
"""
Intent Type Definitions

Provides core type definitions for intent analysis, shared by traditional routing and intelligent routing.

Type list:
- IntentType: Intent type enumeration
- TaskComplexity: Task complexity enumeration
- RevisionIntentType: Revision intent type enumeration (N5: fine-grained revision classification)
- AgentCreationStrategy: Agent creation strategy data class
- IntentAnalysisResult: Intent analysis result data class

Design principles:
- Type definitions separated from implementation logic
- Traditional routing and intelligent routing share the same types
- Easy to migrate and maintain
"""

__all__ = [
    "IntentType",
    "TaskComplexity",
    "RevisionIntentType",  # N5: 新增修订意图类型
    "AgentCreationStrategy",
    "IntentAnalysisResult",
]

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


class IntentType(Enum):
    """Intent type"""
    RESEARCH = "research"              # Research task (market analysis, data collection)
    IMPLEMENTATION = "implementation"  # Implementation task (code writing, report generation)
    INVESTIGATION = "investigation"    # Investigation task (problem diagnosis, data validation)
    EVALUATION = "evaluation"          # Evaluation task (quality check, comparative analysis)
    FIX = "fix"                        # Fix task (error correction, data cleaning)
    OPEN_ENDED = "open_ended"          # Open-ended task (exploratory research)
    CLARIFICATION = "clarification"    # Clarification task (requires further user input)


class TaskComplexity(Enum):
    """Task complexity"""
    TRIVIAL = "trivial"      # Single file/operation, execute directly
    SINGLE = "single"        # Single Agent can complete
    MULTI = "multi"          # Requires 2-5 Agent collaboration
    COMPLEX = "complex"      # Requires 5+ Agent collaboration, needs detailed planning


class RevisionIntentType(Enum):
    """
    N5 新增: 修订意图类型 - 细粒度分类
    
    用于三级映射架构的 Level 2，将通用意图细化为修订专用操作。
    """
    
    # === 数据级操作 ===
    VERIFY_DATA = "verify_data"           # 核实数据准确性
    UPDATE_DATA = "update_data"           # 更新数据值
    ADD_DATA = "add_data"                 # 补充新数据
    
    # === 文本级操作 ===
    REWRITE_TEXT = "rewrite_text"         # 重写文本表达
    CORRECT_ERROR = "correct_error"       # 修正错误
    IMPROVE_CLARITY = "improve_clarity"   # 提升清晰度
    
    # === 结构级操作 ===
    ADD_SECTION = "add_section"           # 新增章节
    REMOVE_SECTION = "remove_section"     # 删除章节
    
    # === 分析级操作 ===
    COMPARE_SECTIONS = "compare_sections" # 章节对比
    CHECK_CONSISTENCY = "check_consistency"  # 一致性检查


@dataclass
class AgentCreationStrategy:
    """
    Agent Creation Strategy

    Core object output by IntentGate, guides DynamicAgentFactory on how to create Agents
    """
    intent: IntentType
    complexity: TaskComplexity
    recommended_agents: List[str]           # Recommended agent type identifiers
    agent_count_estimate: int               # Estimated agent count
    parallel_execution: bool                # Whether supports parallel execution
    skill_requirements: List[str]           # Required skills
    creation_mode: str                      # "predefined" or "dynamic"
    priority: str                           # Priority high/medium/low
    context_requirements: Dict[str, Any]    # Context needed by agents
    clarification_needed: bool              # Whether user clarification needed
    clarification_questions: Optional[List[str]]  # Clarification questions


@dataclass
class IntentAnalysisResult:
    """Complete intent analysis result"""
    intent: IntentType
    complexity: TaskComplexity
    strategy: AgentCreationStrategy
    confidence: float                       # Classification confidence 0-1
    keywords_matched: List[str]             # Matched keywords
    reasoning: str                          # Classification reasoning explanation
