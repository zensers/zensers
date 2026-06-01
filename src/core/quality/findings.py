"""
SectionFindings - 结构化研究发现协议

核心判断提取 + 关键数据点抽取，作为 Knowledge Handoff 的标准协议。

设计原则：
1. 后处理提取 - 不修改 agent 输出，从最终正文中提取
2. 双通道抽取 - 正则(数值) + LLM(核心判断)，互备
3. 轻量依赖 - 正则通道零外部依赖，LLM 通道为可选增强
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── 数据结构 ─────────────────────────────────────────


@dataclass
class SectionFindings:
    """单章节的结构化研究发现"""
    section_id: str
    core_claims: List[str] = field(default_factory=list)
    key_data_points: List[Dict[str, str]] = field(default_factory=list)
    methodology_note: str = ""

    def to_dict(self) -> Dict:
        return {
            "section_id": self.section_id,
            "core_claims": self.core_claims,
            "key_data_points": self.key_data_points,
            "methodology_note": self.methodology_note,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "SectionFindings":
        return cls(
            section_id=data.get("section_id", ""),
            core_claims=data.get("core_claims", []),
            key_data_points=data.get("key_data_points", []),
            methodology_note=data.get("methodology_note", ""),
        )


# ─── 数值提取 - 正则通道 ─────────────────────────────


# 匹配模式: 数字 + 可选单位
_NUMERIC_PATTERN = re.compile(
    r"(\d+\.?\d*)\s*"
    r"(亿元|亿美元|元/斤|元/公斤|元/吨|元|"
    r"%|百分点|bps|"
    r"万吨|亿羽|亿只|亿|万|吨|公斤|斤|只|羽|枚|"
    r"美元|欧元|日元|英镑|"
    r"月|日|天|小时|分钟)"
)

# 核心判断标记词（正则 fallback 用）
_CLAIM_MARKERS = [
    "核心判断", "核心发现", "核心结论", "关键发现",
    "核心观点", "根本原因", "关键洞察",
    "core judgment", "key finding", "key insight",
    "综上所述", "总体来看", "总体判断",
]


def _find_core_claims_regex(text: str) -> List[str]:
    """正则通道：抽取含有标记词的核心判断句"""
    claims = []
    for marker in _CLAIM_MARKERS:
        for match in re.finditer(re.escape(marker) + r"[：:。\n，,].*?[。\n]", text, re.DOTALL):
            sentence = match.group().strip()
            if sentence and sentence not in claims:
                claims.append(sentence)
            if len(claims) >= 3:
                return claims

    # Fallback: 取前 3 个包含"判断""趋势""结论"的句子
    if not claims:
        fallback_markers = ["判断", "趋势", "结论", "预计", "预测"]
        for line in text.split("\n"):
            line = line.strip()
            if any(m in line for m in fallback_markers) and len(line) > 15:
                claims.append(line[:120])
                if len(claims) >= 3:
                    break
    return claims


def _find_data_points_regex(text: str) -> List[Dict[str, str]]:
    """正则通道：抽取数值型数据点"""
    points = []
    seen = set()
    for match in _NUMERIC_PATTERN.finditer(text):
        value = match.group(1)
        unit = match.group(2)
        # 避免重复：同一数值+单位只取一次
        key = f"{value}_{unit}"
        if key in seen:
            continue
        seen.add(key)

        # 提取上下文（数值前面最多 30 个字符）
        start = max(0, match.start() - 30)
        context = text[start:match.start()].strip()
        # 清理上下文中的标点
        context = context.rstrip("，,。.）)】、")

        points.append({
            "value": value,
            "unit": unit,
            "context": context[-30:] if context else "",
        })
    return points


# ─── 主提取器 ─────────────────────────────────────────


def extract_findings(section_id: str, text: str, use_llm: bool = False) -> SectionFindings:
    """
    从章节正文中提取结构化研究发现

    Args:
        section_id: 章节 ID
        text: 章节正文（纯文本，已去除 HTML 标签）
        use_llm: 是否启用 LLM 辅助通道（默认 False，仅用正则）

    Returns:
        SectionFindings 实例
    """
    if not text or not text.strip():
        return SectionFindings(section_id=section_id)

    # 正则通道：始终执行
    core_claims = _find_core_claims_regex(text)
    key_data_points = _find_data_points_regex(text)

    # LLM 通道：可选，当正则通道未找到核心判断时作为 fallback
    if use_llm and not core_claims:
        try:
            llm_claims = _extract_claims_via_llm(text)
            core_claims = llm_claims or core_claims
        except Exception as e:
            logger.warning(f"LLM 抽取 core_claims 失败: {e}")

    return SectionFindings(
        section_id=section_id,
        core_claims=core_claims[:3],
        key_data_points=key_data_points[:10],
        methodology_note="extracted via regex" if not use_llm else "extracted via regex+llm",
    )


def _extract_claims_via_llm(text: str) -> Optional[List[str]]:
    """LLM 通道：抽取核心判断（需要 llm_skill 可用）"""
    try:
        from src.skills.llm_skill import LLMSkill
    except ImportError:
        logger.warning("LLMSkill not available, skipping LLM extraction")
        return None

    prompt = (
        "从以下研究文本中提取 1-3 条核心判断语句。\n"
        "核心判断是作者做出的关键性结论或预测，而不是事实性陈述。\n"
        "每条判断用一句话概括，不超过 80 字。\n"
        "以 JSON 数组格式输出，例如：[\"判断1\", \"判断2\"]\n\n"
        "文本：\n" + text[:3000]
    )

    skill = LLMSkill()
    result = skill.execute(prompt=prompt)
    if not result.get("success"):
        return None

    content = result.get("content", "")
    import json
    try:
        parsed = json.loads(content)
        if isinstance(parsed, list):
            return [str(c).strip() for c in parsed if c]
    except json.JSONDecodeError:
        pass
    return None
