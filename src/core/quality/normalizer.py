"""
评分归一化工具

提供统一的评分归一化入口，将 0-1 和 0-100 尺度的分数统一为 0-100。
"""

import logging
from typing import Optional, Literal

logger = logging.getLogger(__name__)


def normalize_quality_score(
    score: Optional[float],
    source_scale: Optional[Literal["0-1", "0-100"]] = None,
    default: float = 50.0,
) -> float:
    """
    统一评分归一化入口。

    Args:
        score: 原始分数，None 时返回 default
        source_scale: 显式标注分数尺度
            "0-1"   → 乘以 100（0.5 → 50.0）
            "0-100" → 原值返回
            None    → 自动检测（保留向后兼容）
        default: score 为 None 时的默认值

    Returns:
        归一化后的分数，clamp 到 [0, 100]

    自动检测规则（匹配 engine.py:2544 原始行为）:
        - None → default
        - 0.0 <= score < 1.0 → 乘以 100
        - score >= 1.0 → 原值返回（1.0 本身不被放大）
        - score < 0 → clamp 到 0
        - score > 100 → clamp 到 100
    """
    if score is None:
        return max(0.0, min(100.0, default))

    if source_scale == "0-1":
        normalized = score * 100.0
    elif source_scale == "0-100":
        normalized = score
    else:
        # 自动检测（匹配 engine 原始逻辑：仅 [0, 1.0) 被放大）
        if 0.0 <= score < 1.0:
            normalized = score * 100.0
        else:
            normalized = score

    return max(0.0, min(100.0, normalized))
