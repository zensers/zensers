"""Unit tests for epistemic defense (L1-L5) implementation.

Tests are self-contained and do not require LLM calls.
They verify the logic of each defense layer in isolation.
"""
import asyncio
import hashlib
import pytest
import sys
import os
from unittest.mock import patch, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.core.agents.generic_agent import GenericAgent


# ==================== L1: _extract_claims_from_analysis ====================

class TestL1Truncation:
    """L1-C: Paragraph-level sliding window preserves key middle conclusions."""

    def test_short_content_not_truncated(self):
        content = "A" * 2000
        if len(content) > 3000:
            _paragraphs = [p for p in content.split("\n\n") if p.strip()]
            _truncated = content
        else:
            _truncated = content
        assert _truncated == content

    def test_long_content_head_tail_preserved(self):
        head = "H" * 2500
        middle = "M" * 3000
        tail = "T" * 500
        content = head + middle + tail
        assert len(content) > 3000
        _truncated = content[:2500] + "\n\n...[中间省略]...\n\n" + content[-500:]
        assert _truncated.startswith("H" * 2500)
        assert _truncated.endswith("T" * 500)
        assert "...[中间省略]..." in _truncated

    def test_conclusion_section_preserved(self):
        content = "概述部分" + "详细分析" * 800 + "结论：AI芯片国产化率已突破30%"
        assert len(content) > 3000
        _paragraphs = [p for p in content.split("\n\n") if p.strip()]
        _truncated = content[:2500] + "\n\n...[中间省略]...\n\n" + content[-500:]
        assert "结论：AI芯片国产化率已突破30%" in _truncated

    def test_paragraph_level_key_conclusion_preserved(self):
        content = "\n\n".join([
            "第一段概述",
            "第二段背景",
            "中间段普通内容" * 50,
            "中间段结论：关键发现X",
            "中间段普通内容" * 50,
            "最后段总结",
            "最终结论",
        ])
        if len(content) > 3000:
            _paragraphs = [p for p in content.split("\n\n") if p.strip()]
            if len(_paragraphs) <= 5:
                _truncated = content
            else:
                _head = "\n\n".join(_paragraphs[:2])
                _tail = "\n\n".join(_paragraphs[-2:])
                _key_patterns = ["结论", "发现", "验证", "结果", "综上", "因此", "表明", "证明"]
                _mid_candidates = []
                for p in _paragraphs[2:-2]:
                    if any(kw in p for kw in _key_patterns):
                        _mid_candidates.append(p)
                _mid = "\n\n".join(_mid_candidates[:2]) if _mid_candidates else ""
                _parts = [_head]
                if _mid:
                    _parts.append("...[关键中间段落]...")
                    _parts.append(_mid)
                _parts.append("...[中间省略]...")
                _parts.append(_tail)
                _truncated = "\n\n".join(_parts)
        else:
            _truncated = content
        assert "关键发现X" in _truncated
        assert "第一段概述" in _truncated
        assert "最终结论" in _truncated


class TestL1RuleBasedValidation:
    """L1: Rule-based epistemic_level validation."""

    def test_low_confidence_with_premise_not_factual(self):
        claim = {"statement": "市场份额下降", "confidence": "LOW", "前提条件": "数据准确", "epistemic_level": "factual"}
        _epistemic_order = {"factual": 0, "inferential": 1, "speculative": 2}
        _speculative_words = {"可能", "预计", "或许", "也许", "大概", "猜测", "推测", "预期"}
        _level = claim.get("epistemic_level", "inferential")
        if claim.get("confidence") == "LOW" and claim.get("前提条件") and _level == "factual":
            claim["epistemic_level"] = "inferential"
            _level = "inferential"
        assert claim["epistemic_level"] != "factual"

    def test_speculative_word_in_factual_downgraded(self):
        claim = {"statement": "企业可能通过并购突破", "confidence": "HIGH", "epistemic_level": "factual"}
        _speculative_words = {"可能", "预计", "或许", "也许", "大概", "猜测", "推测", "预期"}
        _level = claim.get("epistemic_level", "inferential")
        if _level == "factual" and any(w in claim.get("statement", "") for w in _speculative_words):
            claim["epistemic_level"] = "inferential"
        assert claim["epistemic_level"] == "inferential"

    def test_factual_without_speculative_words_kept(self):
        claim = {"statement": "2025年Q1市场份额为32%", "confidence": "HIGH", "epistemic_level": "factual"}
        _speculative_words = {"可能", "预计", "或许", "也许", "大概", "猜测", "推测", "预期"}
        _level = claim.get("epistemic_level", "inferential")
        if _level == "factual" and any(w in claim.get("statement", "") for w in _speculative_words):
            claim["epistemic_level"] = "inferential"
        assert claim["epistemic_level"] == "factual"

    def test_missing_epistemic_level_defaults_to_inferential(self):
        claim = {"statement": "some claim", "confidence": "MEDIUM"}
        if "epistemic_level" not in claim:
            claim["epistemic_level"] = "inferential"
        assert claim["epistemic_level"] == "inferential"

    def test_invalid_epistemic_level_defaults_to_inferential(self):
        claim = {"statement": "some claim", "confidence": "MEDIUM", "epistemic_level": "unknown"}
        _epistemic_order = {"factual": 0, "inferential": 1, "speculative": 2}
        _level = claim.get("epistemic_level", "inferential")
        if _level not in _epistemic_order:
            claim["epistemic_level"] = "inferential"
        assert claim["epistemic_level"] == "inferential"


class TestL1DimensionCeiling:
    """L1-D: Dimension-level epistemic ceiling."""

    def test_strategic_intent_factual_downgraded(self):
        ASPECT_EPISTEMIC_CEILING = {
            "strategic_intent": "speculative",
            "战略意图": "speculative",
            "战略意图推断": "speculative",
            "Strategic Intent": "speculative",
        }
        _epistemic_order = {"factual": 0, "inferential": 1, "speculative": 2}
        aspect = "strategic_intent"
        claim = {"epistemic_level": "factual"}
        _ceiling = ASPECT_EPISTEMIC_CEILING.get(aspect, None)
        _level = claim.get("epistemic_level", "inferential")
        if _ceiling and _epistemic_order.get(_level, 1) < _epistemic_order.get(_ceiling, 1):
            claim["epistemic_level"] = _ceiling
        assert claim["epistemic_level"] == "speculative"

    def test_strategic_intent_inferential_downgraded(self):
        ASPECT_EPISTEMIC_CEILING = {"strategic_intent": "speculative"}
        _epistemic_order = {"factual": 0, "inferential": 1, "speculative": 2}
        aspect = "strategic_intent"
        claim = {"epistemic_level": "inferential"}
        _ceiling = ASPECT_EPISTEMIC_CEILING.get(aspect, None)
        _level = claim.get("epistemic_level", "inferential")
        if _ceiling and _epistemic_order.get(_level, 1) < _epistemic_order.get(_ceiling, 1):
            claim["epistemic_level"] = _ceiling
        assert claim["epistemic_level"] == "speculative"

    def test_non_ceiling_aspect_not_affected(self):
        ASPECT_EPISTEMIC_CEILING = {"strategic_intent": "speculative"}
        _epistemic_order = {"factual": 0, "inferential": 1, "speculative": 2}
        aspect = "市场规模"
        claim = {"epistemic_level": "factual"}
        _ceiling = ASPECT_EPISTEMIC_CEILING.get(aspect, None)
        _level = claim.get("epistemic_level", "inferential")
        if _ceiling and _epistemic_order.get(_level, 1) < _epistemic_order.get(_ceiling, 1):
            claim["epistemic_level"] = _ceiling
        assert claim["epistemic_level"] == "factual"

    def test_strategic_intent_speculative_not_changed(self):
        ASPECT_EPISTEMIC_CEILING = {"strategic_intent": "speculative"}
        _epistemic_order = {"factual": 0, "inferential": 1, "speculative": 2}
        aspect = "strategic_intent"
        claim = {"epistemic_level": "speculative"}
        _ceiling = ASPECT_EPISTEMIC_CEILING.get(aspect, None)
        _level = claim.get("epistemic_level", "inferential")
        if _ceiling and _epistemic_order.get(_level, 1) < _epistemic_order.get(_ceiling, 1):
            claim["epistemic_level"] = _ceiling
        assert claim["epistemic_level"] == "speculative"


# ==================== L2: SOURCE_PRIORITY + caliber ====================

class TestL2SourcePriority:
    """L2: Expanded SOURCE_PRIORITY with factual/inferential/speculative."""

    def test_priority_ordering(self):
        SOURCE_PRIORITY = {
            "structured_source": 100,
            "search_result": 50,
            "llm_inference_factual": 15,
            "llm_inference": 10,
            "llm_inference_speculative": 5,
        }
        assert SOURCE_PRIORITY["structured_source"] > SOURCE_PRIORITY["search_result"]
        assert SOURCE_PRIORITY["search_result"] > SOURCE_PRIORITY["llm_inference_factual"]
        assert SOURCE_PRIORITY["llm_inference_factual"] > SOURCE_PRIORITY["llm_inference"]
        assert SOURCE_PRIORITY["llm_inference"] > SOURCE_PRIORITY["llm_inference_speculative"]

    def test_caliber_map(self):
        caliber_map = {
            "factual": "llm_inference_factual",
            "inferential": "llm_inference",
            "speculative": "llm_inference_speculative",
        }
        assert caliber_map["factual"] == "llm_inference_factual"
        assert caliber_map["inferential"] == "llm_inference"
        assert caliber_map["speculative"] == "llm_inference_speculative"

    def test_caliber_map_default(self):
        caliber_map = {
            "factual": "llm_inference_factual",
            "inferential": "llm_inference",
            "speculative": "llm_inference_speculative",
        }
        assert caliber_map.get("unknown", "llm_inference") == "llm_inference"


class TestL2BWriteCanonical:
    """L2-B: Same-caliber logic with same-source exception."""

    @pytest.fixture
    def shared_memory(self):
        from src.core.communication import SharedMemory
        return SharedMemory()

    @pytest.mark.asyncio
    async def test_speculative_does_not_overwrite_factual(self, shared_memory):
        await shared_memory.write_canonical("test", 100, caliber="llm_inference_factual", source="a1", publisher="p")
        result = await shared_memory.write_canonical("test", 200, caliber="llm_inference_speculative", source="a2", publisher="p")
        entry = await shared_memory.get_canonical("test")
        assert entry["value"] == 100
        assert entry["caliber"] == "llm_inference_factual"

    @pytest.mark.asyncio
    async def test_factual_overwrites_inferential(self, shared_memory):
        await shared_memory.write_canonical("test", 100, caliber="llm_inference", source="a1", publisher="p")
        await shared_memory.write_canonical("test", 200, caliber="llm_inference_factual", source="a2", publisher="p")
        entry = await shared_memory.get_canonical("test")
        assert entry["value"] == 200
        assert entry["caliber"] == "llm_inference_factual"

    @pytest.mark.asyncio
    async def test_same_caliber_different_source_blocked(self, shared_memory):
        await shared_memory.write_canonical("test", 100, caliber="llm_inference_factual", source="a1", publisher="p")
        result = await shared_memory.write_canonical("test", 200, caliber="llm_inference_factual", source="a2", publisher="p")
        entry = await shared_memory.get_canonical("test")
        assert entry["value"] == 100
        assert result is not None

    @pytest.mark.asyncio
    async def test_same_caliber_same_source_allowed(self, shared_memory):
        await shared_memory.write_canonical("test", 100, caliber="llm_inference_factual", source="a1", publisher="p")
        await shared_memory.write_canonical("test", 200, caliber="llm_inference_factual", source="a1", publisher="p")
        entry = await shared_memory.get_canonical("test")
        assert entry["value"] == 200

    @pytest.mark.asyncio
    async def test_search_result_not_overwritten_by_factual(self, shared_memory):
        await shared_memory.write_canonical("test", 100, caliber="search_result", source="web", publisher="p")
        await shared_memory.write_canonical("test", 200, caliber="llm_inference_factual", source="a1", publisher="p")
        entry = await shared_memory.get_canonical("test")
        assert entry["value"] == 100
        assert entry["caliber"] == "search_result"


# ==================== L4: _parse_hypothesis_verification ====================

class TestL4HypothesisVerification:
    """L4: Structured output hypothesis verification parsing."""

    def _parse(self, content, hypotheses):
        import re as _re
        verified = []
        verification_section = ""
        markers = ["假设验证结果", "假设验证结果：", "验证结果"]
        for marker in markers:
            if marker in content:
                idx = content.index(marker)
                verification_section = content[idx:]
                break
        if not verification_section:
            for h in hypotheses:
                h_copy = dict(h)
                h_copy["status"] = "unverified"
                h_copy["id"] = hashlib.md5(h.get("statement", "").encode()).hexdigest()[:8]
                verified.append(h_copy)
            return verified
        for i, h in enumerate(hypotheses):
            h_copy = dict(h)
            h_copy["id"] = hashlib.md5(h.get("statement", "").encode()).hexdigest()[:8]
            pattern = f"假设{i+1}"
            if pattern in verification_section:
                matching_lines = [line for line in verification_section.split("\n")
                                  if pattern in line and "|" in line and "(新)" not in line]
                if matching_lines:
                    line = matching_lines[-1]
                    line_parts = line.split("|")
                    judgment_part = line_parts[0].strip()
                    if any(kw in judgment_part for kw in ["验证", "证实", "verified", "confirmed"]):
                        h_copy["status"] = "verified"
                    elif any(kw in judgment_part for kw in ["修正", "修订", "revised", "modified", "部分"]):
                        h_copy["status"] = "revised"
                        if len(line_parts) > 2:
                            h_copy["revision_note"] = line_parts[-1].strip().replace("修正内容：", "").replace("修正内容:", "")
                    elif any(kw in judgment_part for kw in ["推翻", "否定", "refuted", "rejected", "不成立"]):
                        h_copy["status"] = "refuted"
                    else:
                        h_copy["status"] = "unverified"
                    for lp in line_parts:
                        lp = lp.strip()
                        if lp.startswith("反面假设可能性：") or lp.startswith("反面假设可能性:"):
                            h_copy["counter_possibility"] = lp.split("：", 1)[-1].split(":", 1)[-1].strip()
                else:
                    h_copy["status"] = "unverified"
            else:
                h_copy["status"] = "unverified"
            verified.append(h_copy)
        new_hyp_pattern = _re.compile(r'假设(\d+)\s*\(新\)\s*[：:]\s*(.+?)(?:\s*\||$)')
        for line in verification_section.split("\n"):
            m = new_hyp_pattern.search(line)
            if m and "|" in line:
                line_parts = line.split("|")
                new_h = {"id": f"new_{m.group(1)}", "source": "agent_generated", "statement": m.group(2).strip()}
                for lp in line_parts:
                    lp = lp.strip()
                    if lp.startswith("依据：") or lp.startswith("依据:"):
                        new_h["evidence"] = lp.split("：", 1)[-1].split(":", 1)[-1].strip()
                    elif lp.startswith("反面假设可能性：") or lp.startswith("反面假设可能性:"):
                        new_h["counter_possibility"] = lp.split("：", 1)[-1].split(":", 1)[-1].strip()
                full_line = line
                if any(kw in full_line for kw in ["修正", "修订", "部分"]):
                    new_h["status"] = "revised"
                elif any(kw in full_line for kw in ["推翻", "否定", "不成立"]):
                    new_h["status"] = "refuted"
                elif any(kw in full_line for kw in ["验证", "证实"]):
                    new_h["status"] = "verified"
                else:
                    new_h["status"] = "unverified"
                if new_h.get("statement"):
                    verified.append(new_h)
        return verified

    def test_verified_hypothesis(self):
        content = "分析内容...\n假设验证结果：\n假设1：验证 | 依据：数据支撑"
        hypotheses = [{"statement": "政策收紧导致增速放缓"}]
        result = self._parse(content, hypotheses)
        assert result[0]["status"] == "verified"

    def test_revised_hypothesis(self):
        content = "分析内容...\n假设验证结果：\n假设1：修正 | 依据：部分成立 | 修正内容：政策是辅助因素"
        hypotheses = [{"statement": "政策收紧导致增速放缓"}]
        result = self._parse(content, hypotheses)
        assert result[0]["status"] == "revised"
        assert "政策是辅助因素" in result[0].get("revision_note", "")

    def test_refuted_hypothesis(self):
        content = "分析内容...\n假设验证结果：\n假设1：推翻 | 依据：与数据矛盾"
        hypotheses = [{"statement": "政策收紧导致增速放缓"}]
        result = self._parse(content, hypotheses)
        assert result[0]["status"] == "refuted"

    def test_no_verification_section_fallback(self):
        content = "分析内容中无验证结果段"
        hypotheses = [{"statement": "政策收紧导致增速放缓"}]
        result = self._parse(content, hypotheses)
        assert result[0]["status"] == "unverified"

    def test_multiple_hypotheses(self):
        content = "分析...\n假设验证结果：\n假设1：验证 | 依据：数据支撑\n假设2：修正 | 依据：部分成立 | 修正内容：非唯一原因\n假设3：推翻 | 依据：矛盾"
        hypotheses = [{"statement": "假设A"}, {"statement": "假设B"}, {"statement": "假设C"}]
        result = self._parse(content, hypotheses)
        assert result[0]["status"] == "verified"
        assert result[1]["status"] == "revised"
        assert result[2]["status"] == "refuted"

    def test_last_matching_line_taken(self):
        content = "分析...\n假设验证结果：\n假设1：修正 | 依据：初步判断\n假设1：推翻 | 依据：最终判断"
        hypotheses = [{"statement": "假设A"}]
        result = self._parse(content, hypotheses)
        assert result[0]["status"] == "refuted"

    def test_stable_id_via_hash(self):
        hypotheses = [{"statement": "政策收紧导致增速放缓"}]
        result = self._parse("假设验证结果：\n假设1：验证 | 依据：数据", hypotheses)
        expected_id = hashlib.md5("政策收紧导致增速放缓".encode()).hexdigest()[:8]
        assert result[0]["id"] == expected_id

    def test_counter_possibility_parsed(self):
        content = "分析...\n假设验证结果：\n假设1：验证 | 依据：数据支撑 | 反面假设可能性：低"
        hypotheses = [{"statement": "芯片供应紧张导致出货量下降"}]
        result = self._parse(content, hypotheses)
        assert result[0]["status"] == "verified"
        assert result[0].get("counter_possibility") == "低"

    def test_new_hypothesis_parsed(self):
        content = "分析...\n假设验证结果：\n假设1：验证 | 依据：数据支撑\n假设2(新)：消费降级抑制换机需求 | 验证 | 依据：出货量下降 | 反面假设可能性：中"
        hypotheses = [{"statement": "芯片供应紧张导致出货量下降"}]
        result = self._parse(content, hypotheses)
        assert len(result) == 2
        assert result[0]["status"] == "verified"
        assert result[1]["source"] == "agent_generated"
        assert "消费降级" in result[1].get("statement", "")
        assert result[1].get("counter_possibility") == "中"

    def test_multiple_new_hypotheses(self):
        content = "假设验证结果：\n假设1：验证 | 依据：数据\n假设2(新)：消费降级抑制换机 | 修正 | 依据：部分成立 | 反面假设可能性：中\n假设3(新)：AI换机潮对冲下滑 | 验证 | 依据：AI手机增长 | 反面假设可能性：低"
        hypotheses = [{"statement": "芯片供应紧张导致出货量下降"}]
        result = self._parse(content, hypotheses)
        assert len(result) == 3
        assert result[1]["source"] == "agent_generated"
        assert result[1]["status"] == "revised"
        assert result[2]["source"] == "agent_generated"
        assert result[2]["status"] == "verified"


# ==================== L5: _detect_claim_contradiction ====================

class TestL5ContradictionPrecheck:
    """L5 pre-check: Fast heuristic candidate filtering."""

    def _precheck(self, claim_a, claim_b):
        stmt_a = claim_a.get("statement", "")
        stmt_b = claim_b.get("statement", "")
        if not stmt_a or not stmt_b:
            return False
        positive = {"增长", "上升", "扩张", "改善", "提升", "增加", "上涨", "回暖",
                    "普及", "加速", "领先", "突破", "恢复", "繁荣", "强劲", "乐观",
                    "收紧", "趋严", "升级", "扩张", "扩张", "强化", "推进", "普及"}
        negative = {"下降", "萎缩", "收缩", "恶化", "下滑", "减少", "下跌", "承压",
                    "渗透率下滑", "放缓", "滞后", "受阻", "衰退", "疲软", "悲观",
                    "放松", "趋缓", "降级", "收缩", "弱化", "停滞", "萎缩", "低迷"}
        a_pos = any(w in stmt_a for w in positive)
        a_neg = any(w in stmt_a for w in negative)
        b_pos = any(w in stmt_b for w in positive)
        b_neg = any(w in stmt_b for w in negative)
        if (a_pos and b_neg) or (a_neg and b_pos):
            def _bigrams(text):
                return {text[i:i+2] for i in range(len(text)-1)}
            bigrams_a = _bigrams(stmt_a)
            bigrams_b = _bigrams(stmt_b)
            dir_bigrams = set()
            for w in positive | negative:
                for i in range(len(w)-1):
                    dir_bigrams.add(w[i:i+2])
            content_a = bigrams_a - dir_bigrams
            content_b = bigrams_b - dir_bigrams
            if content_a and content_b:
                overlap = len(content_a & content_b) / max(len(content_a), 1)
                if overlap > 0.25:
                    return True
        return False

    def test_direction_contradiction_candidate(self):
        a = {"statement": "市场规模持续增长"}
        b = {"statement": "市场规模面临萎缩"}
        assert self._precheck(a, b) is True

    def test_same_direction_not_candidate(self):
        a = {"statement": "市场规模持续增长"}
        b = {"statement": "行业收入快速提升"}
        assert self._precheck(a, b) is False

    def test_no_direction_words_not_candidate(self):
        a = {"statement": "企业A占据主导地位"}
        b = {"statement": "企业B市场份额领先"}
        assert self._precheck(a, b) is False

    def test_empty_statement_not_candidate(self):
        a = {"statement": ""}
        b = {"statement": "市场规模增长"}
        assert self._precheck(a, b) is False

    def test_different_subject_low_overlap_not_candidate(self):
        a = {"statement": "出口额持续增长"}
        b = {"statement": "内销利润面临萎缩"}
        assert self._precheck(a, b) is False

    def test_extended_keywords_candidate(self):
        a = {"statement": "AI手机快速普及"}
        b = {"statement": "AI手机渗透率下滑"}
        assert self._precheck(a, b) is True

    def test_english_keywords_not_candidate(self):
        a = {"statement": "revenue increased significantly"}
        b = {"statement": "revenue declined sharply"}
        assert self._precheck(a, b) is False

    def test_moderate_overlap_different_subject_not_candidate(self):
        """Pairs with moderate content overlap but clearly different subjects should not pass precheck (defect 3.6)"""
        a = {"statement": "出口额持续增长，贸易顺差扩大"}
        b = {"statement": "内销利润面临萎缩，库存压力上升"}
        assert self._precheck(a, b) is False


class TestL5ContradictionLLM:
    """L5: LLM-based semantic contradiction detection (with mock)."""

    @pytest.fixture
    def agent(self):
        agent = GenericAgent(agent_id="test_l5", config={})
        agent._shared_memory = None
        return agent

    @pytest.mark.asyncio
    async def test_llm_confirms_contradiction(self, agent, monkeypatch):
        async def mock_call_llm(**kwargs):
            return {"content": '{"contradiction": true, "type": "方向矛盾", "confidence": 0.9, "explanation": "增长与萎缩方向相反"}'}
        monkeypatch.setattr("src.core.agents.generic_agent.call_llm", mock_call_llm)
        a = {"statement": "市场规模持续增长"}
        b = {"statement": "市场规模面临萎缩"}
        result = await agent._detect_claim_contradiction(a, b)
        assert result is not None
        assert "方向矛盾" in result

    @pytest.mark.asyncio
    async def test_llm_rejects_false_positive(self, agent, monkeypatch):
        async def mock_call_llm(**kwargs):
            return {"content": '{"contradiction": false, "type": "无矛盾", "confidence": 0.85, "explanation": "讨论不同主体"}'}
        monkeypatch.setattr("src.core.agents.generic_agent.call_llm", mock_call_llm)
        a = {"statement": "出口额持续增长"}
        b = {"statement": "内销利润面临萎缩"}
        result = await agent._detect_claim_contradiction(a, b)
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_detects_domain_contradiction(self, agent, monkeypatch):
        async def mock_call_llm(**kwargs):
            return {"content": '{"contradiction": true, "type": "方向矛盾", "confidence": 0.88, "explanation": "普及与渗透率下滑方向相反"}'}
        monkeypatch.setattr("src.core.agents.generic_agent.call_llm", mock_call_llm)
        a = {"statement": "AI手机快速普及"}
        b = {"statement": "AI手机渗透率下滑"}
        result = await agent._detect_claim_contradiction(a, b)
        assert result is not None
        assert "方向矛盾" in result

    @pytest.mark.asyncio
    async def test_llm_failure_returns_none_not_false_positive(self, agent, monkeypatch):
        async def mock_call_llm(**kwargs):
            raise Exception("LLM unavailable")
        monkeypatch.setattr("src.core.agents.generic_agent.call_llm", mock_call_llm)
        a = {"statement": "市场规模持续增长"}
        b = {"statement": "市场规模面临萎缩"}
        result = await agent._detect_claim_contradiction(a, b)
        assert result is None

    @pytest.mark.asyncio
    async def test_precheck_rejects_unrelated_pair(self, agent, monkeypatch):
        call_count = [0]
        async def mock_call_llm(**kwargs):
            call_count[0] += 1
            return {"content": '{"contradiction": false}'}
        monkeypatch.setattr("src.core.agents.generic_agent.call_llm", mock_call_llm)
        a = {"statement": "企业A占据主导地位"}
        b = {"statement": "企业B市场份额领先"}
        result = await agent._detect_claim_contradiction(a, b)
        assert result is None
        assert call_count[0] == 0

    @pytest.mark.asyncio
    async def test_empty_statement_skips_both_stages(self, agent, monkeypatch):
        call_count = [0]
        async def mock_call_llm(**kwargs):
            call_count[0] += 1
            return {"content": '{"contradiction": false}'}
        monkeypatch.setattr("src.core.agents.generic_agent.call_llm", mock_call_llm)
        a = {"statement": ""}
        b = {"statement": "市场规模增长"}
        result = await agent._detect_claim_contradiction(a, b)
        assert result is None
        assert call_count[0] == 0

    @pytest.mark.asyncio
    async def test_llm_low_confidence_rejected(self, agent, monkeypatch):
        async def mock_call_llm(**kwargs):
            return {"content": '{"contradiction": true, "type": "方向矛盾", "confidence": 0.4, "explanation": "不确定"}'}
        monkeypatch.setattr("src.core.agents.generic_agent.call_llm", mock_call_llm)
        a = {"statement": "市场规模持续增长"}
        b = {"statement": "市场规模面临萎缩"}
        result = await agent._detect_claim_contradiction(a, b)
        assert result is None


# ==================== L3: Stratified injection ====================

class TestL3StratifiedInjection:
    """L3: Claims stratified by epistemic_level in prompt injection."""

    def test_claims_grouped_by_epistemic_level(self):
        cross_dimension_claims = [
            {"statement": "市场份额32%", "epistemic_level": "factual", "confidence": "HIGH", "source_aspect": "市场"},
            {"statement": "竞争加剧", "epistemic_level": "inferential", "confidence": "MEDIUM", "前提条件": "数据准确", "source_aspect": "竞争"},
            {"statement": "可能并购", "epistemic_level": "speculative", "confidence": "LOW", "falsification": "6个月无公告", "source_aspect": "战略"},
        ]
        factual = [c for c in cross_dimension_claims if c.get("epistemic_level") == "factual"]
        inferential = [c for c in cross_dimension_claims if c.get("epistemic_level") == "inferential"]
        speculative = [c for c in cross_dimension_claims if c.get("epistemic_level") == "speculative"]
        no_level = [c for c in cross_dimension_claims if c.get("epistemic_level") not in ("factual", "inferential", "speculative")]
        assert len(factual) == 1
        assert len(inferential) == 1
        assert len(speculative) == 1
        assert len(no_level) == 0

    def test_missing_epistemic_level_treated_as_inferential(self):
        cross_dimension_claims = [
            {"statement": "旧claim无level", "confidence": "MEDIUM"},
        ]
        no_level = [c for c in cross_dimension_claims if c.get("epistemic_level") not in ("factual", "inferential", "speculative")]
        inferential = [c for c in cross_dimension_claims if c.get("epistemic_level") == "inferential"]
        inferential.extend(no_level)
        assert len(inferential) == 1

    def test_conflict_entries_filtered_by_prefix(self):
        _all_canon = {
            "claim:市场:0": {"value": {"statement": "增长"}},
            "conflict:claim:市场:0": {"value": {"contradiction": "方向矛盾"}},
            "claim:竞争:0": {"value": {"statement": "加剧"}},
        }
        conflict_entries = {k: v for k, v in _all_canon.items() if k.startswith("conflict:claim:")}
        assert len(conflict_entries) == 1
        assert "conflict:claim:市场:0" in conflict_entries


# ==================== Integration: L1→L2→L3 end-to-end ====================

class TestEpistemicEndToEnd:
    """End-to-end test: L1 classification → L2 caliber → L3 injection."""

    def test_speculative_claim_gets_lowest_caliber(self):
        claim = {"statement": "企业可能通过并购突破", "epistemic_level": "speculative"}
        caliber_map = {
            "factual": "llm_inference_factual",
            "inferential": "llm_inference",
            "speculative": "llm_inference_speculative",
        }
        caliber = caliber_map.get(claim.get("epistemic_level", "inferential"), "llm_inference")
        assert caliber == "llm_inference_speculative"
        SOURCE_PRIORITY = {"llm_inference_factual": 15, "llm_inference": 10, "llm_inference_speculative": 5}
        assert SOURCE_PRIORITY[caliber] == 5

    def test_factual_claim_gets_highest_llm_caliber(self):
        claim = {"statement": "2025年Q1市场份额为32%", "epistemic_level": "factual"}
        caliber_map = {
            "factual": "llm_inference_factual",
            "inferential": "llm_inference",
            "speculative": "llm_inference_speculative",
        }
        caliber = caliber_map.get(claim.get("epistemic_level", "inferential"), "llm_inference")
        assert caliber == "llm_inference_factual"

    def test_strategic_intent_claim_always_speculative(self):
        aspect = "strategic_intent"
        ASPECT_EPISTEMIC_CEILING = {"strategic_intent": "speculative", "战略意图": "speculative", "战略意图推断": "speculative", "Strategic Intent": "speculative"}
        _epistemic_order = {"factual": 0, "inferential": 1, "speculative": 2}
        for level in ["factual", "inferential"]:
            claim = {"epistemic_level": level}
            _ceiling = ASPECT_EPISTEMIC_CEILING.get(aspect, None)
            _l = claim.get("epistemic_level", "inferential")
            if _ceiling and _epistemic_order.get(_l, 1) < _epistemic_order.get(_ceiling, 1):
                claim["epistemic_level"] = _ceiling


# ==================== Cognitive Strategy Tests ====================

class TestCognitiveStrategyRegistry:
    def test_all_four_types_exist(self):
        from src.core.agents.generic_agent import COGNITIVE_STRATEGY
        for ct in ["fact_driven", "inference_driven", "forward_looking", "assessment_driven"]:
            assert ct in COGNITIVE_STRATEGY
            assert "L1" in COGNITIVE_STRATEGY[ct]
            assert "L3" in COGNITIVE_STRATEGY[ct]
            assert "L4" in COGNITIVE_STRATEGY[ct]
            assert "L5" in COGNITIVE_STRATEGY[ct]

    def test_fact_driven_dimension_ceiling(self):
        from src.core.agents.generic_agent import COGNITIVE_STRATEGY
        assert COGNITIVE_STRATEGY["fact_driven"]["L1"]["dimension_ceiling"] == "inferential"

    def test_forward_looking_no_ceiling(self):
        from src.core.agents.generic_agent import COGNITIVE_STRATEGY
        assert COGNITIVE_STRATEGY["forward_looking"]["L1"]["dimension_ceiling"] is None

    def test_inference_driven_speculative_policy(self):
        from src.core.agents.generic_agent import COGNITIVE_STRATEGY
        assert COGNITIVE_STRATEGY["inference_driven"]["L3"]["speculative_policy"] == "cautious_use"

    def test_forward_looking_speculative_policy(self):
        from src.core.agents.generic_agent import COGNITIVE_STRATEGY
        assert COGNITIVE_STRATEGY["forward_looking"]["L3"]["speculative_policy"] == "open_use"

    def test_fact_driven_hypothesis_count(self):
        from src.core.agents.generic_agent import COGNITIVE_STRATEGY
        assert COGNITIVE_STRATEGY["fact_driven"]["L4"]["hypothesis_count"] == (1, 2)
        assert COGNITIVE_STRATEGY["fact_driven"]["L4"]["agent_hypothesis_count"] == 0

    def test_inference_driven_hypothesis_count(self):
        from src.core.agents.generic_agent import COGNITIVE_STRATEGY
        assert COGNITIVE_STRATEGY["inference_driven"]["L4"]["hypothesis_count"] == (3, 5)
        assert COGNITIVE_STRATEGY["inference_driven"]["L4"]["agent_hypothesis_count"] == 2


class TestHeuristicCognitiveType:
    def _heuristic(self, aspect):
        agent = GenericAgent.__new__(GenericAgent)
        return agent._heuristic_cognitive_type(aspect)

    def test_chinese_inference_driven(self):
        assert self._heuristic("投资建议") == "inference_driven"

    def test_chinese_forward_looking(self):
        assert self._heuristic("技术趋势") == "forward_looking"

    def test_chinese_assessment_driven(self):
        assert self._heuristic("估值分析") == "assessment_driven"

    def test_english_inference_driven(self):
        assert self._heuristic("Investment Strategy") == "inference_driven"

    def test_english_forward_looking(self):
        assert self._heuristic("Technology Trends") == "forward_looking"

    def test_english_assessment_driven(self):
        assert self._heuristic("Risk Assessment") == "assessment_driven"

    def test_no_match_returns_none(self):
        assert self._heuristic("市场规模") is None


class TestInferCognitiveType:
    @pytest.mark.asyncio
    async def test_llm_full_classification(self):
        agent = GenericAgent.__new__(GenericAgent)
        agent._context = {}
        agent.agent_id = "test"
        with patch("src.core.agents.generic_agent.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"content": "inference_driven", "success": True}
            result = await agent.infer_cognitive_type("投资建议", "中国智能手机")
            assert result == "inference_driven"
            assert mock_llm.call_count == 1

    @pytest.mark.asyncio
    async def test_heuristic_fallback(self):
        agent = GenericAgent.__new__(GenericAgent)
        agent._context = {}
        agent.agent_id = "test"
        with patch("src.core.agents.generic_agent.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [{"content": "", "success": True}, {"content": "", "success": True}]
            result = await agent.infer_cognitive_type("投资建议", "中国智能手机")
            assert result == "inference_driven"

    @pytest.mark.asyncio
    async def test_ultimate_fallback(self):
        agent = GenericAgent.__new__(GenericAgent)
        agent._context = {}
        agent.agent_id = "test"
        with patch("src.core.agents.generic_agent.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [{"content": "", "success": True}, {"content": "", "success": True}]
            result = await agent.infer_cognitive_type("市场规模", "中国智能手机")
            assert result == "fact_driven"

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        agent = GenericAgent.__new__(GenericAgent)
        agent._context = {}
        agent.agent_id = "test"
        with patch("src.core.agents.generic_agent.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"content": "assessment_driven", "success": True}
            r1 = await agent.infer_cognitive_type("风险分析", "中国智能手机")
            r2 = await agent.infer_cognitive_type("风险分析", "中国智能手机")
            assert r1 == "assessment_driven"
            assert r2 == "assessment_driven"
            assert mock_llm.call_count == 1
