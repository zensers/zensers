# -*- coding: utf-8 -*-
"""
TokenBudgetManager - Token 预算管理器

实现 CONTEXT_COMPRESSION.md 第4节的 Token 预算管理功能：
- 预算计算
- 状态监控
- 自动压缩触发
- 分层预算分配
"""

__all__ = ["TokenBudgetManager"]

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class WarningInfo:
    """预警信息"""
    level: str  # yellow, orange, red
    message: str
    threshold: float
    current: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CompressionResult:
    """压缩结果"""
    compressed: bool
    layer: str
    before: int
    after: int
    duration_ms: float = 0.0


class TokenBudgetManager:
    """
    Token 预算管理器
    
    职责：
    - 计算和追踪各层 Token 使用量
    - 监控预算状态，发出预警
    - 触发自动压缩
    
    设计规范：
    - 总预算：200,000 tokens
    - 黄色预警：75% (150,000)
    - 橙色预警：85% (170,000)
    - 红色预警：95% (190,000)
    
    各层预算限制：
    - Layer 0 (系统基座): 5-15KB
    - Layer 1 (核心记忆): < 10KB
    - Layer 2 (工作上下文): 动态，上限 50KB
    - Layer 3 (知识检索): ~10KB
    - Conversation (对话历史): ~40KB
    """
    
    # 默认预算限制
    TOTAL_BUDGET = 200_000
    WARNING_YELLOW = 150_000  # 75%
    WARNING_ORANGE = 170_000  # 85%
    WARNING_RED = 190_000     # 95%
    
    # 各层限制（tokens）
    LAYER_LIMITS = {
        "layer0": {"min": 5 * 1024, "max": 15 * 1024},
        "layer1": {"min": 0, "max": 10 * 1024},
        "layer2": {"min": 0, "max": 50 * 1024},
        "layer3": {"min": 0, "max": 15 * 1024},
        "conversation": {"min": 0, "max": 100 * 1024}  # 可压缩空间大
    }
    
    def __init__(
        self,
        total_budget: int = TOTAL_BUDGET,
        yellow_threshold: float = 0.75,
        orange_threshold: float = 0.85,
        red_threshold: float = 0.95,
        auto_compress_threshold: float = 0.95
    ):
        """
        初始化 Token 预算管理器
        
        Args:
            total_budget: 总预算（tokens）
            yellow_threshold: 黄色预警阈值（百分比）
            orange_threshold: 橙色预警阈值（百分比）
            red_threshold: 红色预警阈值（百分比）
            auto_compress_threshold: 自动压缩阈值（百分比）
        """
        # 验证阈值
        if not (0 < yellow_threshold < orange_threshold < red_threshold <= 1.0):
            raise ValueError("Thresholds must be: 0 < yellow < orange < red <= 1.0")
        
        self.total_budget = total_budget
        self.yellow_threshold = yellow_threshold
        self.orange_threshold = orange_threshold
        self.red_threshold = red_threshold
        self.auto_compress_threshold = auto_compress_threshold
        
        # 当前使用量
        self.current_usage: Dict[str, int] = {
            "layer0": 0,
            "layer1": 0,
            "layer2": 0,
            "layer3": 0,
            "conversation": 0
        }
        
        # 使用历史
        self._usage_history: List[Dict[str, Any]] = []
        self._max_history = 100
        
        # 压缩策略
        self._compression_strategies: Dict[str, Any] = {}
        
        # 回调
        self._warning_callbacks: List[Callable] = []
        self._compression_callbacks: List[Callable] = []
        self._notification_handlers: List[Callable] = []
        
        # 通知冷却
        self._notification_cooldown = 1.0  # 秒
        self._last_notification_time: Optional[datetime] = None
        
        # 压缩指标
        self._compression_metrics = {
            "total_compressions": 0,
            "total_tokens_saved": 0,
            "compression_history": []
        }
        
        logger.debug(f"TokenBudgetManager initialized with total_budget={total_budget}")
    
    # ========== 预算计算 ==========
    
    def get_total_usage(self) -> int:
        """获取总使用量"""
        return sum(self.current_usage.values())
    
    def get_layer_usage(self, layer: str) -> int:
        """获取指定层使用量"""
        if layer not in self.current_usage:
            raise KeyError(f"Unknown layer: {layer}")
        return self.current_usage[layer]
    
    def set_layer_usage(self, layer: str, usage: int) -> None:
        """设置指定层使用量"""
        if layer not in self.current_usage:
            raise KeyError(f"Unknown layer: {layer}")
        if usage < 0:
            raise ValueError(f"Usage cannot be negative: {usage}")
        self.current_usage[layer] = usage
    
    def get_usage_percentage(self) -> float:
        """获取使用百分比"""
        return self.get_total_usage() / self.total_budget
    
    def get_remaining_budget(self) -> int:
        """获取剩余预算"""
        return self.total_budget - self.get_total_usage()
    
    def get_remaining_percentage(self) -> float:
        """获取剩余百分比"""
        return 1.0 - self.get_usage_percentage()
    
    # ========== 状态检查 ==========
    
    def check_budget(self) -> Dict[str, Any]:
        """检查预算状态"""
        percentage = self.get_usage_percentage()
        
        if percentage >= self.red_threshold:
            return {
                "status": "critical",
                "action": "force_compress",
                "percentage": percentage,
                "total_usage": self.get_total_usage()
            }
        elif percentage >= self.orange_threshold:
            return {
                "status": "warning",
                "action": "suggest_compress",
                "percentage": percentage,
                "total_usage": self.get_total_usage()
            }
        elif percentage >= self.yellow_threshold:
            return {
                "status": "caution",
                "action": "monitor",
                "percentage": percentage,
                "total_usage": self.get_total_usage()
            }
        else:
            return {
                "status": "ok",
                "action": "continue",
                "percentage": percentage,
                "total_usage": self.get_total_usage()
            }
    
    def check_warnings(self) -> List[Dict[str, Any]]:
        """检查预警"""
        warnings = []
        percentage = self.get_usage_percentage()
        
        if percentage >= self.red_threshold:
            warnings.append({
                "level": "red",
                "message": f"预算使用率 {percentage*100:.1f}% 已达紧急水平",
                "threshold": self.red_threshold,
                "current": percentage
            })
        elif percentage >= self.orange_threshold:
            warnings.append({
                "level": "orange",
                "message": f"预算使用率 {percentage*100:.1f}% 已达警告水平",
                "threshold": self.orange_threshold,
                "current": percentage
            })
        elif percentage >= self.yellow_threshold:
            warnings.append({
                "level": "yellow",
                "message": f"预算使用率 {percentage*100:.1f}% 已达注意水平",
                "threshold": self.yellow_threshold,
                "current": percentage
            })
        
        return warnings
    
    # ========== 预算分配 ==========
    
    def suggest_allocation(self) -> Dict[str, int]:
        """建议预算分配"""
        # 基于设计规范的默认分配
        return {
            "layer0": 10 * 1024,      # 10KB
            "layer1": 8 * 1024,       # 8KB
            "layer2": 20 * 1024,      # 20KB
            "layer3": 10 * 1024,      # 10KB
            "conversation": 40 * 1024  # 40KB
        }
    
    def get_layer_limits(self) -> Dict[str, Dict[str, int]]:
        """获取各层限制"""
        return self.LAYER_LIMITS.copy()
    
    def validate_layer_usage(self, layer: str, usage: int) -> bool:
        """验证层使用量是否在限制内"""
        if layer not in self.LAYER_LIMITS:
            return False
        
        limits = self.LAYER_LIMITS[layer]
        return limits["min"] <= usage <= limits["max"]
    
    # ========== 监控 ==========
    
    def get_current_state(self) -> Dict[str, Any]:
        """获取当前状态"""
        return {
            "total_usage": self.get_total_usage(),
            "percentage": self.get_usage_percentage(),
            "status": self.check_budget()["status"],
            "timestamp": datetime.now().isoformat(),
            "layer_breakdown": self.current_usage.copy()
        }
    
    def record_usage_snapshot(self) -> None:
        """记录使用快照"""
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "total_usage": self.get_total_usage(),
            "layer_usage": self.current_usage.copy()
        }
        
        self._usage_history.append(snapshot)
        
        # 限制历史长度
        if len(self._usage_history) > self._max_history:
            self._usage_history = self._usage_history[-self._max_history:]
    
    def get_usage_history(self, max_records: int = 100) -> List[Dict[str, Any]]:
        """获取使用历史"""
        return self._usage_history[-max_records:]
    
    def get_usage_summary(self) -> Dict[str, Any]:
        """获取使用摘要"""
        return {
            "total": self.get_total_usage(),
            "percentage": self.get_usage_percentage(),
            "by_layer": self.current_usage.copy()
        }
    
    def generate_report(self) -> Dict[str, Any]:
        """生成预算报告"""
        return {
            "timestamp": datetime.now().isoformat(),
            "total_usage": self.get_total_usage(),
            "remaining": self.get_remaining_budget(),
            "percentage": self.get_usage_percentage(),
            "status": self.check_budget(),
            "layer_breakdown": self.current_usage.copy()
        }
    
    def generate_monitoring_report(self) -> Dict[str, Any]:
        """生成监控报告"""
        warnings = self.check_warnings()
        status = self.check_budget()
        
        recommendations = []
        if status["status"] in ["warning", "critical"]:
            recommendations.append("建议执行压缩操作以释放预算空间")
        if self.current_usage.get("conversation", 0) > 50 * 1024:
            recommendations.append("对话历史较大，建议优先压缩")
        
        return {
            "current_state": self.get_current_state(),
            "warnings": warnings,
            "recommendations": recommendations,
            "generated_at": datetime.now().isoformat()
        }
    
    # ========== Token 估算 ==========
    
    def estimate_tokens(self, text: str) -> int:
        """
        估算文本的 Token 数量
        
        简单估算：平均 4 字符 = 1 token
        中文可能 1-2 字符 = 1 token
        """
        if not text:
            return 0
        
        # 简单估算
        char_count = len(text)
        
        # 检测是否主要是中文
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        chinese_ratio = chinese_chars / char_count if char_count > 0 else 0
        
        if chinese_ratio > 0.5:
            # 主要是中文，估算 1.5 字符/token
            return int(char_count / 1.5)
        else:
            # 主要是英文，估算 4 字符/token
            return int(char_count / 4)
    
    def update_from_context(self, context: Dict[str, Any]) -> None:
        """从上下文更新预算"""
        # 估算各部分的 token 数
        if "system_prompt" in context:
            self.current_usage["layer0"] = self.estimate_tokens(context["system_prompt"])
        
        if "core_memory" in context:
            self.current_usage["layer1"] = self.estimate_tokens(context["core_memory"])
        
        if "working_context" in context:
            self.current_usage["layer2"] = self.estimate_tokens(context["working_context"])
        
        if "knowledge_results" in context:
            combined = " ".join(str(r) for r in context["knowledge_results"])
            self.current_usage["layer3"] = self.estimate_tokens(combined)
        
        if "conversation" in context:
            combined = " ".join(str(m) for m in context["conversation"])
            self.current_usage["conversation"] = self.estimate_tokens(combined)
    
    # ========== 自动压缩 ==========
    
    def should_auto_compress(self) -> bool:
        """判断是否应该自动压缩"""
        return self.get_usage_percentage() >= self.auto_compress_threshold
    
    def get_compression_priority(self) -> str:
        """获取压缩优先级最高的层"""
        # 优先压缩使用量最大的可压缩层
        compressible_layers = ["conversation", "layer2"]
        
        max_usage = 0
        priority_layer = "conversation"
        
        for layer in compressible_layers:
            usage = self.current_usage.get(layer, 0)
            if usage > max_usage:
                max_usage = usage
                priority_layer = layer
        
        return priority_layer
    
    def set_compression_strategy(self, layer: str, strategy: Any) -> None:
        """设置压缩策略"""
        self._compression_strategies[layer] = strategy
    
    def get_compression_strategy(self, layer: str) -> Optional[Any]:
        """获取压缩策略"""
        return self._compression_strategies.get(layer)
    
    async def execute_auto_compress(self) -> Dict[str, Any]:
        """执行自动压缩"""
        layer = self.get_compression_priority()
        strategy = self.get_compression_strategy(layer)
        
        if strategy is None:
            return {
                "compressed": False,
                "layer": layer,
                "before": self.current_usage[layer],
                "after": self.current_usage[layer],
                "reason": "No compression strategy available"
            }
        
        before = self.current_usage[layer]
        
        # 调用压缩策略
        import asyncio
        start_time = datetime.now()
        
        after = await strategy.compress(before)
        
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        # 更新使用量
        self.current_usage[layer] = after
        
        # 记录压缩指标
        self._compression_metrics["total_compressions"] += 1
        self._compression_metrics["total_tokens_saved"] += (before - after)
        
        result = {
            "compressed": True,
            "layer": layer,
            "before": before,
            "after": after,
            "duration_ms": duration_ms
        }
        
        # 通知回调
        self.notify_compression(result)
        
        return result
    
    async def compress_all_critical(self) -> Dict[str, Any]:
        """压缩所有需要压缩的层"""
        compressed_layers = []
        
        for layer in ["conversation", "layer2"]:
            if self.current_usage[layer] > 30 * 1024:  # 大于 30KB 才压缩
                strategy = self.get_compression_strategy(layer)
                if strategy:
                    before = self.current_usage[layer]
                    after = await strategy.compress(before)
                    self.current_usage[layer] = after
                    compressed_layers.append({
                        "layer": layer,
                        "before": before,
                        "after": after
                    })
        
        return {
            "layers_compressed": len(compressed_layers),
            "details": compressed_layers
        }
    
    async def auto_compress_if_needed(self) -> Dict[str, Any]:
        """如果需要则自动压缩"""
        if not self.should_auto_compress():
            return {"compressed": False, "reason": "Below threshold"}
        
        return await self.execute_auto_compress()
    
    async def compress_until_safe(self) -> None:
        """持续压缩直到安全"""
        max_iterations = 5
        iteration = 0
        
        while self.get_usage_percentage() >= self.orange_threshold and iteration < max_iterations:
            await self.execute_auto_compress()
            iteration += 1
    
    def validate_compression_result(self, before: int, after: int, min_reduction: float = 0.0) -> bool:
        """验证压缩结果"""
        if after >= before:
            return False
        
        if min_reduction > 0:
            reduction = (before - after) / before
            if reduction < min_reduction:
                return False
        
        return True
    
    def record_compression(self, layer: str, before: int, after: int, duration_ms: float = 0) -> None:
        """记录压缩"""
        self._compression_metrics["total_compressions"] += 1
        self._compression_metrics["total_tokens_saved"] += (before - after)
        self._compression_metrics["compression_history"].append({
            "layer": layer,
            "before": before,
            "after": after,
            "duration_ms": duration_ms,
            "timestamp": datetime.now().isoformat()
        })
    
    def get_compression_metrics(self) -> Dict[str, Any]:
        """获取压缩指标"""
        return self._compression_metrics.copy()
    
    # ========== 回调注册 ==========
    
    def register_warning_callback(self, callback: Callable) -> None:
        """注册预警回调"""
        self._warning_callbacks.append(callback)
    
    def register_compression_callback(self, callback: Callable) -> None:
        """注册压缩回调"""
        self._compression_callbacks.append(callback)
    
    def register_notification_handler(self, handler: Callable) -> None:
        """注册通知处理器"""
        self._notification_handlers.append(handler)
    
    def set_notification_cooldown(self, seconds: float) -> None:
        """设置通知冷却时间"""
        self._notification_cooldown = seconds
    
    def check_and_notify(self) -> None:
        """检查并发送通知"""
        warnings = self.check_warnings()
        
        if not warnings:
            return
        
        # 检查冷却
        now = datetime.now()
        if self._last_notification_time:
            elapsed = (now - self._last_notification_time).total_seconds()
            if elapsed < self._notification_cooldown:
                return
        
        self._last_notification_time = now
        
        # 发送通知
        for warning in warnings:
            for handler in self._notification_handlers:
                try:
                    handler(warning)
                except Exception as e:
                    logger.warning(f"Notification handler error: {e}")
    
    def notify_compression(self, result: Dict[str, Any]) -> None:
        """通知压缩结果"""
        for callback in self._compression_callbacks:
            try:
                callback(result)
            except Exception as e:
                logger.warning(f"Compression callback error: {e}")
    
    # ========== 阈值配置 ==========
    
    def get_thresholds(self) -> Dict[str, float]:
        """获取阈值配置"""
        return {
            "yellow": self.yellow_threshold,
            "orange": self.orange_threshold,
            "red": self.red_threshold
        }