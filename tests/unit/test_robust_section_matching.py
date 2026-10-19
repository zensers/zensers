"""
验证章节匹配的健壮性设计

问题：当前匹配逻辑依赖原始字符串比较，顿号、下划线、空格、
全角/半角符号等任何差异都导致匹配失败。

目标：匹配逻辑应能处理所有常见变化，而不是逐个修补。
"""
import pytest
import re


# ==================== 改进后的匹配设计 ====================

PUNCTUATION_CHARS = set(
    '、，,；;：:（）()【】[]「」""''！!？?/\\- \t\n\r\u3000'
)


def _normalize_key(key: str) -> str:
    """
    统一规范化：消除所有标点差异
    
    处理范围：
    - 中文标点：顿号、逗号、分号、冒号、括号等
    - 英文标点：逗号、分号、冒号、括号等
    - 空白字符：空格、全角空格
    - 大小写：统一小写
    """
    if not key:
        return ""
    # 1. 统一小写
    key = key.lower()
    # 2. 去除 section_N_ 前缀（用于 engine key）
    key = re.sub(r'^section_\d+_', '', key)
    # 3. 逐个字符替换标点为统一分隔符
    result = []
    for ch in key:
        if ch in PUNCTUATION_CHARS:
            result.append('_')
        else:
            result.append(ch)
    key = ''.join(result)
    # 4. 合并连续分隔符
    key = re.sub(r'_+', '_', key)
    # 5. 去除首尾分隔符
    key = key.strip('_')
    return key


def section_matches_robust(stored_key: str, framework_id: str, framework_name: str = "") -> bool:
    """
    健壮的章节匹配逻辑
    
    1. 先规范化双方
    2. 然后用归一化的值做多层匹配
    3. 匹配失败时记录具体原因
    """
    norm_stored = _normalize_key(stored_key)
    norm_id = _normalize_key(framework_id)
    norm_name = _normalize_key(framework_name) if framework_name else norm_id
    
    reasons = []
    
    # 方法1: 精确匹配（归一化后）
    if norm_stored == norm_id:
        return True
    if norm_stored == norm_name:
        return True
    
    # 方法2: 包含匹配（归一化后）
    if norm_id in norm_stored:
        return True
    if norm_name in norm_stored:
        return True
    if norm_stored in norm_id:
        return True
    if norm_stored in norm_name:
        return True
    
    # 方法3: 逐token匹配（按分隔符拆分）
    stored_tokens = set(norm_stored.split('_'))
    id_tokens = set(norm_id.split('_'))
    name_tokens = set(norm_name.split('_'))
    
    overlap_id = stored_tokens & id_tokens
    overlap_name = stored_tokens & name_tokens
    
    # 如果超过一半的 token 匹配，认为匹配成功
    if len(overlap_id) >= max(len(id_tokens) // 2, 1):
        return True
    if len(overlap_name) >= max(len(name_tokens) // 2, 1):
        return True
    
    return False


class TestRobustSectionMatching:
    """验证改进后的匹配设计"""

    # === 当前修复前的 BUG — 标点符号 ===

    def test_current_bug_punctuation(self):
        """修复前的 BUG：顿号 vs 下划线"""
        # framework 用顿号，engine key 用下划线
        result = section_matches_robust(
            stored_key="section_5_财务健康_风险评估与季度业绩波动",
            framework_id="财务健康、风险评估与季度业绩波动",
            framework_name="财务健康、风险评估与季度业绩波动",
        )
        assert result, "顿号/下划线差异应能匹配"

    # === 未来的变化 — 各种标点 ===

    @pytest.mark.parametrize("punctuation_char", [
        "、",  # 中文顿号
        "，",  # 中文逗号
        ",",   # 英文逗号
        "；",  # 中文分号
        ";",   # 英文分号
        " ",   # 空格
        "　",  # 全角空格
        "-",   # 连字符
    ])
    def test_any_punctuation(self, punctuation_char):
        """任何标点变体都应匹配"""
        # 构造含不同标点的 framework section_id
        framework_id = f"财务健康{punctuation_char}风险评估与季度业绩波动"
        # engine key 用下划线
        engine_key = "section_5_财务健康_风险评估与季度业绩波动"
        
        result = section_matches_robust(engine_key, framework_id)
        assert result, f"标点 '{punctuation_char}' 应能匹配下划线 '{framework_id}'"

    # === 前缀差异 ===

    def test_section_prefix_variation(self):
        """section_N_ 前缀有无都应匹配"""
        # engine 注入时带前缀 section_5_
        result = section_matches_robust(
            stored_key="section_5_财务健康_风险评估与季度业绩波动",
            framework_id="财务健康_风险评估与季度业绩波动",
        )
        assert result, "prefix 差异应能匹配"

    # === 大小写差异 ===

    def test_case_insensitive(self):
        """大小写不敏感"""
        result = section_matches_robust(
            stored_key="Section_5_财务健康_风险评估",
            framework_id="财务健康_风险评估",
        )
        assert result, "大小写差异应能匹配"

    # === 部分匹配（非完美但可用） ===

    def test_partial_token_match(self):
        """部分 token 匹配应通过"""
        # framework：财务健康_风险评估与季度业绩
        # engine：   section_5_财务健康
        # 至少 "财务健康" 匹配
        result = section_matches_robust(
            stored_key="section_5_财务健康",
            framework_id="财务健康_风险评估与季度业绩",
        )
        assert result, "部分 token 匹配应通过"

    # === 完全不相关 → 不应误匹配 ===

    def test_no_false_positive(self):
        """不相关的内容不应误匹配"""
        result = section_matches_robust(
            stored_key="section_0_核心财务指标",
            framework_id="财务预测",
        )
        assert not result, "不相关章节不应误匹配"

    # === 完整 8 章节模拟 ===

    def test_all_8_sections_match(self):
        """全部 8 章节都应匹配成功"""
        framework_ids = [
            "核心财务指标与盈利能力",
            "研发与创新投入",
            "供应链成本效率",
            "销量与市场份额",
            "国际化与出口",
            "财务健康、风险评估与季度业绩波动",
            "行业对标与竞争格局",
            "财务预测",
        ]
        engine_keys = [
            "section_0_核心财务指标与盈利能力",
            "section_1_研发与创新投入",
            "section_2_供应链成本效率",
            "section_3_销量与市场份额",
            "section_4_国际化与出口",
            "section_5_财务健康_风险评估与季度业绩波动",
            "section_6_行业对标与竞争格局",
            "section_7_财务预测",
        ]
        
        for i, ek in enumerate(engine_keys):
            fw_id = framework_ids[i]
            result = section_matches_robust(ek, fw_id)
            assert result, \
                f"section_{i} (framework={fw_id}, engine={ek}) 应匹配"

    # === 规范化函数自身 ===

    def test_normalize_consistency(self):
        """归一化后不同类型的输入应收敛到同一值"""
        variations = [
            "section_5_财务健康、风险评估与季度业绩波动",
            "财务健康,风险评估与季度业绩波动",
            "财务健康 风险评估与季度业绩波动",
            "财务健康_风险评估与季度业绩波动",
            "Section_5_财务健康，风险评估与季度业绩波动",
        ]
        normalized = [_normalize_key(v) for v in variations]
        # 所有变体归一化后应相同
        assert len(set(normalized)) == 1, \
            f"归一化结果不一致: {normalized}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=long"])
