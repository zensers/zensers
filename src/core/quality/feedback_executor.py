# -*- coding: utf-8 -*-
"""
质量反馈执行器 [DEPRECATED]
==========================

.. deprecated::
    本模块为死代码，全项目0调用者。S2重试反馈已由engine.py:1412-1427实现。
    两者注入位置不同(_context vs task_dict)、格式不一致，若同时启用会产生冲突。
    请勿使用本模块，将在v10.0移除。

    替代方案: engine.py S2重试循环 (quality_feedback注入到agent._context)
    参见: 03_Agent架构诊断.md 10.1节

原设计功能：
1. 执行任务并检查质量
2. 不通过时重试（最多3次）
3. 重试失败后选择最佳结果

设计原则：
1. 行业研究必须高质量
2. 重试3次后，有数据按最佳得分输出，无数据才降级
3. 记录每次尝试的分数和结果
"""

import logging
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Callable, Tuple, Optional
from enum import Enum

from .checkers import BaseQualityChecker as QualityCheckerBase, QualityResult

logger = logging.getLogger(__name__)


class FeedbackActionType(Enum):
    """反馈动作类型"""
    PASS = "pass"                  # 通过，继续下一阶段
    RETRY = "retry"                # 重试当前阶段
    BEST_EFFORT = "best_effort"    # 使用最佳结果输出
    DEGRADE = "degrade"            # 降级处理


@dataclass
class AttemptRecord:
    """每次尝试的记录"""
    attempt_id: int                      # 尝试序号
    score: float                         # 质量分数
    data: Dict[str, Any]                 # 数据
    result: Optional[QualityResult] = None  # 检查结果
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（包含完整信息）"""
        return {
            "attempt_id": self.attempt_id,
            "score": self.score,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "data_keys": list(self.data.keys()) if self.data else [],
            "data_success": self.data.get("success") if self.data else None,
            "result_passed": self.result.passed if self.result else None,
            "result_issues": self.result.issues if self.result else [],
        }


@dataclass
class FeedbackAction:
    """反馈动作"""
    type: FeedbackActionType             # 动作类型
    stage: str                           # 目标阶段
    attempt_id: int = 0                  # 尝试序号
    supplemental_queries: List[str] = field(default_factory=list)  # 补充查询
    note: str = ""                       # 备注
    best_score: float = 0.0              # 最佳分数
    data: Optional[Dict[str, Any]] = None  # 数据


class QualityFeedbackExecutor:
    """
    质量反馈执行器
    
    执行任务并进行质量检查，支持重试和最佳结果选择。
    
    Attributes:
        max_retries: 最大重试次数
        attempts: 各阶段的尝试记录
        min_data_volume: 最小数据量阈值（低于此值视为无数据）
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        min_data_volume: int = 3,
    ):
        """
        初始化执行器
        
        Args:
            max_retries: 最大重试次数
            min_data_volume: 最小数据量阈值
        """
        warnings.warn(
            "QualityFeedbackExecutor is deprecated and unused. "
            "Use engine.py S2 retry loop (quality_feedback injection) instead. "
            "See engine.py:1412-1427.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.max_retries = max_retries
        self.min_data_volume = min_data_volume
        self.attempts: Dict[str, List[AttemptRecord]] = {}
    
    async def execute_with_retry(
        self,
        stage: str,
        execute_func: Callable,
        checker: QualityCheckerBase,
        context: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], QualityResult]:
        """
        执行并支持重试
        
        Args:
            stage: 阶段名称 (data_collection/analysis/report)
            execute_func: 执行函数，接受context参数，返回数据字典
            checker: 质量检查器
            context: 执行上下文
            
        Returns:
            (数据, 检查结果) 元组
        """
        # 初始化尝试记录
        if stage not in self.attempts:
            self.attempts[stage] = []
        
        attempts = []
        best_result = None
        best_data = None
        
        # 初始执行 + 重试
        for attempt_id in range(self.max_retries + 1):
            logger.info(f"[{stage}] 开始第 {attempt_id + 1} 次执行")
            
            try:
                # 执行任务
                data = await execute_func(context)
                
                # 检查质量
                result = checker.check(data, context)
                
                # 记录尝试
                record = AttemptRecord(
                    attempt_id=attempt_id,
                    score=result.score,
                    data=data,
                    result=result,
                )
                attempts.append(record)
                self.attempts[stage].append(record)
                
                # 更新最佳结果
                if best_result is None or result.score > best_result.score:
                    best_result = result
                    best_data = data
                
                # 通过则返回
                if result.passed:
                    logger.info(
                        f"[{stage}] 质量检查通过: "
                        f"score={result.score:.1f}, attempt={attempt_id + 1}"
                    )
                    return data, result
                
                # 不通过，准备重试
                if attempt_id < self.max_retries:
                    logger.warning(
                        f"[{stage}] 质量检查未通过: "
                        f"score={result.score:.1f}, threshold={result.threshold}, "
                        f"准备重试 ({attempt_id + 2}/{self.max_retries + 1})"
                    )
                    # 更新上下文，触发补充
                    context = self._prepare_retry(stage, context, result, attempt_id)
                
            except Exception as e:
                logger.error(f"[{stage}] 执行失败: {e}")
                # 记录失败的尝试
                attempts.append(AttemptRecord(
                    attempt_id=attempt_id,
                    score=0,
                    data={},
                ))
        
        # 重试3次后仍无法达标
        best_score = best_result.score if best_result else 0
        logger.warning(
            f"[{stage}] 重试{self.max_retries}次后仍无法达标，"
            f"最佳分数: {best_score:.1f}"
        )
        
        # 判断是否有有效数据
        if self._has_valid_data(best_data):
            # 有数据 → 按最佳得分输出
            if best_data is not None:
                best_data["quality_note"] = {
                    "message": f"质量分数{best_result.score:.1f}低于阈值{best_result.threshold}",
                    "attempts": len(attempts),
                    "best_score": best_result.score,
                    "passed": False,
                    "stage": stage,
                }
            
            logger.info(f"[{stage}] 使用最佳结果输出: score={best_result.score:.1f}")
            return best_data, best_result
        else:
            # 无数据 → 降级
            degraded_data = {
                "degraded": True,
                "reason": "数据不足",
                "stage": stage,
                "attempts": len(attempts),
            }
            
            logger.warning(f"[{stage}] 数据不足，降级处理")
            return degraded_data, best_result or QualityResult(
                checker_type=checker.get_checker_type(),
                score=0,
                threshold=checker.threshold,
                passed=False,
                issues=["数据不足，无法进行质量检查"],
            )
    
    def _prepare_retry(
        self,
        stage: str,
        context: Dict[str, Any],
        result: QualityResult,
        attempt_id: int,
    ) -> Dict[str, Any]:
        """
        准备重试
        
        根据阶段和失败原因，更新上下文以触发补充数据收集或重新分析。
        
        Args:
            stage: 阶段名称
            context: 当前上下文
            result: 检查结果
            attempt_id: 当前尝试序号
            
        Returns:
            更新后的上下文
        """
        context = context.copy()  # 避免修改原始上下文
        
        if stage == "data_collection":
            original_query = context.get("query", context.get("topic", ""))
            issues = result.issues if result and hasattr(result, 'issues') and result.issues else []
            supplemental = []
            
            # L-FIX-2: issue-driven precise search
            if any('data_volume' in str(i) or '数据量' in str(i) for i in issues):
                supplemental.append(f"{original_query} 数据 统计")
            if any('consistency' in str(i) or '矛盾' in str(i) or '冲突' in str(i) for i in issues):
                supplemental.append(f"{original_query} 年报 官方")
            if any('depth' in str(i) or '深度' in str(i) for i in issues):
                supplemental.append(f"{original_query} 原因 分析 驱动因素")
            if any('counter_evidence' in str(i) or 'risk_disclosure' in str(i) or '反证' in str(i) or '风险提示' in str(i) for i in issues):
                supplemental.append(f"{original_query} 风险 挑战")
            if not supplemental:
                supplemental = [f"{original_query} 数据", f"{original_query} 统计"]
            
            context["supplemental_queries"] = supplemental
            context["retry_attempt"] = attempt_id + 1
            
            logger.info(f"[{stage}] 补充查询: {supplemental}")
            
        elif stage == "analysis":
            # 分析阶段：调整分析策略
            context["analysis_depth"] = "deep"
            context["require_evidence"] = True
            context["retry_attempt"] = attempt_id + 1
            
            logger.info(f"[{stage}] 深化分析策略")
            
        elif stage == "report":
            # 报告阶段：重新生成
            context["regenerate"] = True
            context["focus_areas"] = result.issues if result.issues else []
            context["retry_attempt"] = attempt_id + 1
            
            logger.info(f"[{stage}] 重新生成报告，关注问题: {result.issues}")
        
        return context
    
    def _has_valid_data(self, data: Optional[Dict[str, Any]]) -> bool:
        """
        判断是否有有效数据
        
        Args:
            data: 数据字典
            
        Returns:
            是否有有效数据
        """
        if not data:
            return False
        
        if data.get("degraded"):
            return False
        
        # 检查数据量
        quality_metadata = data.get("quality_metadata", {})
        data_volume = quality_metadata.get("data_volume", 0)
        
        if data_volume >= self.min_data_volume:
            return True
        
        # 检查是否有实际内容
        if data.get("results") or data.get("sections") or data.get("insights"):
            return True
        
        return False
    
    def get_attempts(self, stage: str) -> List[AttemptRecord]:
        """
        获取指定阶段的尝试记录
        
        Args:
            stage: 阶段名称
            
        Returns:
            尝试记录列表
        """
        return self.attempts.get(stage, [])
    
    def get_best_attempt(self, stage: str) -> Optional[AttemptRecord]:
        """
        获取指定阶段的最佳尝试
        
        Args:
            stage: 阶段名称
            
        Returns:
            最佳尝试记录
        """
        attempts = self.get_attempts(stage)
        if not attempts:
            return None
        
        return max(attempts, key=lambda a: a.score)
    
    def get_summary(self) -> Dict[str, Any]:
        """
        获取执行摘要
        
        Returns:
            执行摘要字典
        """
        summary = {
            "total_attempts": sum(len(a) for a in self.attempts.values()),
            "stages": {},
        }
        
        for stage, attempts in self.attempts.items():
            if attempts:
                scores = [a.score for a in attempts]
                summary["stages"][stage] = {
                    "attempts": len(attempts),
                    "best_score": max(scores),
                    "avg_score": sum(scores) / len(scores),
                    "passed": any(a.result and a.result.passed for a in attempts),
                }
        
        return summary
    
    def reset(self):
        """重置尝试记录"""
        self.attempts = {}
