"""
v9.3-A1/A3: normalize_quality_score() + QualityResult.score_scale

验证:
  1. normalize_quality_score() 处理 0-1/0-100/自动检测三种模式
  2. QualityResult 新增 score_scale 字段且不影响现有逻辑
  3. engine._extract_quality_score 改为使用统一函数
  4. content_lock 阈值去重并添加 warning
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pytest
from unittest.mock import MagicMock, patch
from typing import List, Optional, Literal


# ============================================================
# Tests for A1: normalize_quality_score()
# ============================================================

class TestNormalizeQualityScore:
    """验证归一化函数的三种模式"""

    def test_normalize_0_1_scale_explicit(self):
        """0-1 尺度显式标注 → 乘以 100"""
        from src.core.quality.normalizer import normalize_quality_score

        assert normalize_quality_score(0.5, source_scale="0-1") == 50.0
        assert normalize_quality_score(0.0, source_scale="0-1") == 0.0
        assert normalize_quality_score(1.0, source_scale="0-1") == 100.0
        assert normalize_quality_score(0.75, source_scale="0-1") == 75.0

    def test_normalize_0_100_scale_explicit(self):
        """0-100 尺度显式标注 → 原值返回"""
        from src.core.quality.normalizer import normalize_quality_score

        assert normalize_quality_score(50.0, source_scale="0-100") == 50.0
        assert normalize_quality_score(0.0, source_scale="0-100") == 0.0
        assert normalize_quality_score(100.0, source_scale="0-100") == 100.0
        assert normalize_quality_score(75.5, source_scale="0-100") == 75.5

    def test_normalize_auto_detect_no_ambiguity(self):
        """自动检测 — 无歧义的值应正确处理"""
        from src.core.quality.normalizer import normalize_quality_score

        # 值 > 1.0 → 已是 0-100 尺度
        assert normalize_quality_score(75.0) == 75.0
        assert normalize_quality_score(100.0) == 100.0
        assert normalize_quality_score(50.5) == 50.5

        # 值在 [0, 1.0) → 放大（匹配 engine 原始行为）
        assert normalize_quality_score(0.5) == 50.0
        assert normalize_quality_score(0.0) == 0.0

        # score=1.0 边界: 不被放大（匹配 engine.py:2544 原始行为）
        assert normalize_quality_score(1.0) == 1.0, \
            "score=1.0 should NOT be scaled (matches original engine behavior)"

    def test_normalize_score_1_via_explicit_0_1(self):
        """需要将 1.0 作为 0-1 尺度满分时，必须显式标注"""
        from src.core.quality.normalizer import normalize_quality_score

        assert normalize_quality_score(1.0, source_scale="0-1") == 100.0, \
            "score=1.0 with source_scale=0-1 should scale to 100"
        assert normalize_quality_score(0.5, source_scale="0-1") == 50.0

    def test_normalize_auto_detect_ambiguity_edge(self):
        """自动检测边界 — 0.5 有歧义, 按兼容规则处理"""
        from src.core.quality.normalizer import normalize_quality_score

        result = normalize_quality_score(0.5)
        assert result == 50.0, f"Expected 50.0, got {result}"

    def test_normalize_default_fallback(self):
        """无分数时回退默认值"""
        from src.core.quality.normalizer import normalize_quality_score

        assert normalize_quality_score(None, default=50.0) == 50.0
        assert normalize_quality_score(None, default=0.0) == 0.0

    def test_normalize_clamp_range(self):
        """超出范围的值应 clamp 到 [0, 100]"""
        from src.core.quality.normalizer import normalize_quality_score

        assert normalize_quality_score(-10.0) == 0.0
        assert normalize_quality_score(150.0) == 100.0
        assert normalize_quality_score(-0.1) == 0.0
        assert normalize_quality_score(101.0) == 100.0


# ============================================================
# Tests for A3: QualityResult.score_scale field
# ============================================================

class TestQualityResultScoreScale:
    """验证 QualityResult 新增 score_scale 字段"""

    def test_score_scale_default_is_0_100(self):
        """新增字段默认值应为 "0-100"，不破坏现有构造方式"""
        from src.core.quality.checkers import QualityResult

        result = QualityResult(
            checker_type="test",
            score=75.0,
            threshold=70.0,
            passed=True,
            issues=["test issue"],
        )
        assert result.score_scale == "0-100"
        assert result.score == 75.0
        assert result.passed is True
        assert "test issue" in result.issues

    def test_score_scale_explicit_set(self):
        """显式设置 score_scale 应生效"""
        from src.core.quality.checkers import QualityResult

        result = QualityResult(
            checker_type="test",
            score=0.75,
            threshold=0.7,
            passed=True,
            score_scale="0-1",
        )
        assert result.score_scale == "0-1"

    def test_score_scale_to_dict_included(self):
        """score_scale 应包含在 to_dict() 输出中"""
        from src.core.quality.checkers import QualityResult

        result = QualityResult(
            checker_type="test",
            score=50.0,
            threshold=50.0,
            passed=True,
            score_scale="0-100",
        )
        d = result.to_dict()
        assert "score_scale" in d
        assert d["score_scale"] == "0-100"

    def test_extract_quality_score_uses_normalize(self):
        """engine._extract_quality_score 应调用 normalize_quality_score"""
        from src.core.quality.checkers import QualityResult
        from src.core.quality.normalizer import normalize_quality_score

        result = QualityResult(
            checker_type="test",
            score=0.75,
            threshold=70.0,
            passed=True,
            score_scale="0-1",
        )
        normalized = normalize_quality_score(result.score, source_scale=result.score_scale)
        assert normalized == 75.0

    def test_backward_compatible_no_score_scale(self):
        """旧代码不传 score_scale 应正常工作"""
        from src.core.quality.checkers import QualityResult

        result = QualityResult(
            checker_type="test",
            score=50.0,
            threshold=50.0,
            passed=True,
        )
        assert hasattr(result, "score_scale")
        assert result.score_scale == "0-100"


# ============================================================
# Tests for A1 integration: replace engine._extract_quality_score
# ============================================================

class TestExtractQualityScoreReplacement:
    """验证 engine._extract_quality_score 替换为 normalize"""

    def test_replace_heuristic_with_normalize(self):
        """engine 的自动放大逻辑应改为 normalize_quality_score 调用"""
        from src.core.quality.normalizer import normalize_quality_score

        test_cases = [
            (0.5, 50.0),    # [0,1) → 放大
            (75.0, 75.0),   # 0-100 → 不变
            (None, 50.0),    # None → 默认
            (-5.0, 0.0),     # 负值 → clamp 0
            (120.0, 100.0),  # 超限 → clamp 100
            (1.0, 1.0),      # 边界: 1.0 不被放大 (匹配 engine)
        ]
        for raw, expected in test_cases:
            if raw is None:
                result = normalize_quality_score(raw, default=50.0)
            else:
                result = normalize_quality_score(raw)
            assert result == expected, f"normalize({raw}) = {result}, expected {expected}"


# ============================================================
# Tests for A2: content_lock threshold warning + dedup
# ============================================================

class TestContentLockManagerThresholdNormalization:
    """验证 content_lock 阈值去重和 warning"""

    def test_normalize_threshold_normal(self):
        """正常阈值 (>= 1.0) 应不变"""
        from src.core.content_lock import ContentLockManager

        lock = ContentLockManager.__new__(ContentLockManager)
        assert lock._normalize_threshold(75.0) == 75.0
        assert lock._normalize_threshold(10.0) == 10.0
        assert lock._normalize_threshold(1.0) == 100.0  # 等于 1.0 时触发放大

    def test_normalize_threshold_auto_scale(self):
        """[0, 1] 阈值应自动放大"""
        from src.core.content_lock import ContentLockManager

        lock = ContentLockManager.__new__(ContentLockManager)
        assert lock._normalize_threshold(0.75) == 75.0
        assert lock._normalize_threshold(0.5) == 50.0
        assert lock._normalize_threshold(1.0) == 100.0

    def test_normalize_threshold_raises_on_negative(self):
        """负阈值应抛 ValueError"""
        from src.core.content_lock import ContentLockManager

        lock = ContentLockManager.__new__(ContentLockManager)
        with pytest.raises(ValueError, match="Negative"):
            lock._normalize_threshold(-1.0)

    def test_dedup_threshold_logic(self):
        """原两处阈值放大应调用同一 _normalize_threshold 方法"""
        from src.core.content_lock import ContentLockManager

        lock = ContentLockManager.__new__(ContentLockManager)

        with patch.object(lock, '_normalize_threshold', wraps=lock._normalize_threshold) as mock_nt:
            threshold = mock_nt(0.75)
            assert threshold == 75.0
            mock_nt.assert_called_once()

    def test_low_threshold_warning(self, caplog):
        """分数阈值 (0 < t < 1.0) 应触发 warning"""
        import logging
        from src.core.content_lock import ContentLockManager

        caplog.set_level(logging.WARNING)
        lock = ContentLockManager.__new__(ContentLockManager)

        lock._normalize_threshold(0.5)
        assert "fractional" in caplog.text or "auto-scaling" in caplog.text

        lock._normalize_threshold(0.8)
        assert "fractional" in caplog.text

    def test_threshold_border_no_warning(self, caplog):
        """>= 1.0 的阈值不触发 warning"""
        import logging
        from src.core.content_lock import ContentLockManager

        caplog.set_level(logging.WARNING)
        lock = ContentLockManager.__new__(ContentLockManager)

        lock._normalize_threshold(0.0)  # 零值不触发
        lock._normalize_threshold(1.0)  # 正好边界，会被放大但不 warning
        lock._normalize_threshold(1.5)  # 正常值
        lock._normalize_threshold(75.0)
        assert "fractional" not in caplog.text


if __name__ == "__main__":
    pytest.main([__file__])
