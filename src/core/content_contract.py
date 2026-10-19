# src/core/content_contract.py
# -*- coding: utf-8 -*-
"""I1 内容契约：确定性内容健全检查（零 LLM 依赖）。

设计依据：docs/design/2026-10-17-system-invariants-rectification-design.md §I1。
所有进入交付物的文本必须通过 check_content；一行式结论用 check_finding_line。
检查分级：issues=fail 级（任何一条即不通过）；warnings=warn 级（Phase 1 记录
不阻塞，阴性语料通过后可升级为 fail——升级方式是把条目从 warnings 移入 issues）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# ---- C1 元思考模式库（硬/软两级；硬=开头命中即 fail，软=仅计入占比） ----
_META_HARD_OPEN = (
    "the task is to", "let me", "i need to", "i'll ", "we need to", "wait,",
    "hmm", "okay,", "looking at", "let's", "i should", "to summarize",
    "好的，我", "让我", "我需要", "现在的任务是", "我来",
)
_META_SOFT = (
    "首先，", "其次，", "然后", "接下来", "总之", "综上",
    "first,", "second,", "next,", "finally,", "in summary", "basically",
    "所以", "因此",
)
_META_SENTENCE_VOCAB = (
    "撰写摘要", "遵守结构", "不能引入新事实", "核心结论段", "这算重复",
    "不超过1000字", "不超过1000字以内", "不超1000字",
    "i will write", "i'm going to", "let me analyze", "let me look",
)

# E1 迁移补充：chapter_writer 旧版开头嗅探把"首先，/等等，/first,"也视为元思考
# 开场（正常话语标记仅出现在开头时才误伤，委托层保持旧行为不变——
# test_writer_output_sanity 锁定这两个标记）。check_content 的 C1 硬检测
# 仍只用 _META_HARD_OPEN（不含正常话语标记，见设计 §I1）。
_META_OPEN_LEGACY_EXTRAS = ("first,", "首先，", "等等，")
_META_OPEN_ALL = _META_HARD_OPEN + _META_OPEN_LEGACY_EXTRAS

# ---- C5 合同残留标记 ----
_RESIDUE_MARKERS = (
    "<<<", "REPORT_CHAPTER", "【DP|", "```json", '{"content"', '{"status"',
)

# ---- C6 占位符（复用 quality_check_agent 的模式集语义） ----
_PLACEHOLDER_RE = re.compile(
    r"未生成可验证内容|本章节数据不足|待补充|内容待完善|insufficient data|placeholder"
)
# 定性章节限定为设计 §I1 所列（政策环境/风险因素/结论类）；
# 不含"趋势/前景"——量化章节标题（如"市场规模与增长趋势"）不得误判为定性。
_QUALITATIVE_RE = re.compile(r"政策|风险|结论|展望|建议")

_URL_RE = re.compile(r"https?://\S+")
_TABLE_LINE_RE = re.compile(r"^\s*\|.*\|\s*$", re.M)
_CODE_FENCE_RE = re.compile(r"```.*?```", re.S)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_ALPHA_CJK_RE = re.compile(r"[A-Za-z\u4e00-\u9fff]")
_SENT_SPLIT_RE = re.compile(r"[。！？.!?]\s*")
_GRAM_SPLIT_RE = re.compile(r"[\s，。！？、；：“”‘’（）\[\]{}【】|<>\-—…·,.:;!?()]+")

_MIN_LENGTH_DEFAULT = {"chapter": 200, "summary": 80, "finding": 8}


@dataclass
class ContentIssue:
    code: str          # C1..C6
    severity: str      # "fail" | "warn"
    detail: str

    def __str__(self):
        return f"[{self.code}:{self.severity}] {self.detail}"


@dataclass
class ContentVerdict:
    passed: bool
    issues: List[ContentIssue] = field(default_factory=list)
    warnings: List[ContentIssue] = field(default_factory=list)
    text_len: int = 0

    @property
    def fail_codes(self) -> List[str]:
        return sorted({i.code for i in self.issues})


def _strip_noise(text: str) -> str:
    """C2/C4 的分母净化：剔除 URL、markdown 表格行、代码块。"""
    text = _CODE_FENCE_RE.sub(" ", text)
    text = _URL_RE.sub(" ", text)
    text = _TABLE_LINE_RE.sub(" ", text)
    return text


def _meta_sentence_ratio(text: str) -> float:
    sentences = [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip()]
    if not sentences:
        return 0.0
    meta = sum(
        1 for s in sentences
        if any(v in s for v in _META_SENTENCE_VOCAB)
        or any(s.lower().startswith(p) for p in _META_HARD_OPEN)
    )
    return meta / len(sentences)


def _repetition_ratio(text: str) -> float:
    norm = _GRAM_SPLIT_RE.sub("", _strip_noise(text))
    if len(norm) < 200:
        return 0.0
    grams = [norm[i:i + 4] for i in range(len(norm) - 3)]
    grams = [g for g in grams if not g.isdigit() and len(set(g)) > 1]
    if not grams:
        return 0.0
    unique = len(set(grams))
    return 1.0 - unique / len(grams)


def check_content(
    text: str,
    *,
    kind: str = "chapter",
    min_length: Optional[int] = None,
    data_points_count: Optional[int] = None,
    section_name: str = "",
    language: str = "zh",
) -> "ContentVerdict":
    """确定性内容健全检查。kind ∈ chapter|summary|finding。

    language 为报告语言（"zh"/"en"，来源 i18n.get_language，经
    current_report_language() 读取）：仅影响 C2 的行为分支——zh 维持
    中文报告阈值；非 zh 反转为轻量对称检查（中文泄漏仅 warn，Phase 1
    永不 fail）。C1/C3/C4/C5/C6 与语言无关。
    """
    issues: List[ContentIssue] = []
    warnings: List[ContentIssue] = []
    raw = text or ""
    stripped = raw.strip()
    min_len = min_length if min_length is not None else _MIN_LENGTH_DEFAULT.get(kind, 8)

    def _add(code: str, severity: str, detail: str):
        (issues if severity == "fail" else warnings).append(
            ContentIssue(code, severity, detail))

    # C6 占位符 + 长度
    if stripped and _PLACEHOLDER_RE.search(stripped[:200]):
        _add("C6", "fail", "content matches known placeholder patterns")
    if len(stripped) < min_len:
        _add("C6", "fail", f"content too short: {len(stripped)} < {min_len}")

    # C5 合同残留
    for marker in _RESIDUE_MARKERS:
        if marker in raw:
            _add("C5", "fail", f"contract residue marker: {marker!r}")

    body = _strip_noise(stripped)
    if kind == "chapter" and body:
        head = re.sub(r"^[\s#*\-\|>+`]+", "", body[:400]).lower()
        # C1 硬标记：开头命中即 fail（正常话语标记不在硬表中）
        if any(head.startswith(p) for p in _META_HARD_OPEN):
            _add("C1", "fail", "text opens with meta-reasoning marker")
        # C1 软占比：Phase 1 为 warn
        ratio = _meta_sentence_ratio(body)
        if ratio > 0.15:
            _add("C1", "warn", f"meta sentence ratio {ratio:.0%} (Phase1 warn)")
        # C2 语言纯度（单块逻辑，按报告语言选择行为分支）：
        # zh（默认）：CJK 占比 <40% 且长度>500 为 fail；短正文（≤500）降为 warn。
        # 非 zh（如 en）：对称轻检——CJK 占比 >60% 仅 warn（中文泄漏进外文
        # 报告），Phase 1 永不 fail。
        cjk = len(_CJK_RE.findall(body))
        alnum = len(_ALPHA_CJK_RE.findall(body))
        if alnum:
            cjk_ratio = cjk / alnum
            if language == "zh":
                if cjk_ratio < 0.40:
                    if len(stripped) > 500:
                        _add("C2", "fail", f"CJK ratio {cjk_ratio:.0%} < 40%")
                    else:
                        _add("C2", "warn", f"CJK ratio {cjk_ratio:.0%} < 40% (short body)")
            elif cjk_ratio > 0.60:
                _add("C2", "warn",
                     f"CJK ratio {cjk_ratio:.0%} > 60% (Chinese leakage into non-zh report)")
        # C3 数据点密度
        if data_points_count is not None and len(stripped) > 500:
            if data_points_count == 0:
                if _QUALITATIVE_RE.search(section_name or ""):
                    _add("C3", "warn", "qualitative chapter with zero data points")
                else:
                    _add("C3", "fail", "non-qualitative chapter with zero data points")
            elif len(stripped) / 1000 > data_points_count:
                _add("C3", "warn",
                     f"data point density low: {data_points_count} dp / {len(stripped)//1000}k chars")
        # C4 重复率（Phase 1 warn）
        rep = _repetition_ratio(body)
        if rep > 0.30:
            _add("C4", "warn", f"4-gram repetition {rep:.0%} (Phase1 warn)")

    return ContentVerdict(
        passed=not issues, issues=issues, warnings=warnings, text_len=len(stripped))


def current_report_language() -> str:
    """Best-effort pipeline language from the i18n global (single writer: i18n.set_language)."""
    try:
        from src.core.i18n import get_language
        return str(get_language().value)
    except Exception:
        return "zh"


def content_opens_meta(text: str) -> bool:
    """C1 开头硬检测（chapter_writer 迁移委托）：文本是否以元思考/修复独白开场。

    与 check_content 的 C1 硬检测同源，另含旧版 chapter_writer 嗅探集
    （"首先，"等开头话语标记），保证迁移前后行为一致（超集兼容）。
    """
    head = re.sub(r"^[\s#*\-\|>+`]+", "", (text or "")[:400]).lower()
    if not head:
        return False
    return any(head.startswith(p) for p in _META_OPEN_ALL)


def check_finding_line(line: str) -> bool:
    """一行式结论/发现检查：元思考行返回 False（调用方丢弃该行）。"""
    text = (line or "").strip()
    if len(text) < 8:
        return False
    lowered = re.sub(r"^[\s\-*#\d.、]+", "", text).lower()
    if any(lowered.startswith(p) for p in _META_HARD_OPEN):
        return False
    if any(v in text for v in _META_SENTENCE_VOCAB):
        return False
    if any(m in text for m in _RESIDUE_MARKERS):
        return False
    return True
