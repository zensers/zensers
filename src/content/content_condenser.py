# -*- coding: utf-8 -*-
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_NUM_UNIT_RE = re.compile(
    r'(?<!第)([\d.]+)\s*(万亿|亿|万|[BMK]|家|倍|个|辆|台|颗|款|项|人|名|次|期|支|条|元|美元|USD|CNY|EUR)',
    re.I,
)
_PCT_RE = re.compile(r'(\d+\.?\d*)\s*%')
_TREND_UP_RE = re.compile(r'(增长|上升|提升|增加|上涨|grew|increased|up|rose|surged)', re.I)
_TREND_DOWN_RE = re.compile(r'(下降|减少|下滑|降低|跌|declined|decreased|down|fell|dropped)', re.I)
_YEAR_RE = re.compile(r'(20\d{2})\s*[年]')

# Split on Chinese punctuation/newlines and on whitespace following English
# sentence punctuation.  The previous expression did not split English
# paragraphs at all, so a long revised section was condensed into one bullet
# and its trailing facts were silently discarded.
_SENTENCE_SPLIT_RE = re.compile(r'[。！？；\n]+|(?<=[.!?])\s+')
_BULLET_PREFIX_RE = re.compile(r'^[\-\*•▪▸►]\s*')
_NUMBERED_PREFIX_RE = re.compile(r'^\d+[\.、）)]\s*')


class ContentCondenser:

    def __init__(
        self,
        max_bullet_chars: int = 40,
        max_bullets_per_slide: int = 5,
        max_slide_text_chars: int = 300,
    ):
        self.max_bullet_chars = max_bullet_chars
        self.max_bullets_per_slide = max_bullets_per_slide
        self.max_slide_text_chars = max_slide_text_chars

    def extract_bullets(self, content: str) -> List[str]:
        if not content or not content.strip():
            return []

        stripped = content.strip()

        existing_bullets = self._parse_existing_bullets(stripped)
        if existing_bullets:
            return existing_bullets[:self.max_bullets_per_slide]

        sentences = _SENTENCE_SPLIT_RE.split(stripped)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return [stripped[:self.max_bullet_chars * 2]]

        if len(sentences) == 1:
            bullet = self._condense_sentence(sentences[0])
            return [bullet] if bullet else []

        bullets = []
        for sent in sentences:
            if len(bullets) >= self.max_bullets_per_slide:
                break
            bullet = self._condense_sentence(sent)
            if bullet:
                bullets.append(bullet)

        return bullets

    def _parse_existing_bullets(self, content: str) -> List[str]:
        lines = content.split('\n')
        bullets = []
        for line in lines:
            line_stripped = line.strip()
            m = _BULLET_PREFIX_RE.match(line_stripped)
            if m:
                bullets.append(line_stripped[m.end():])
                continue
            m2 = _NUMBERED_PREFIX_RE.match(line_stripped)
            if m2:
                bullets.append(line_stripped[m2.end():])
        return bullets

    def _condense_sentence(self, sentence: str) -> Optional[str]:
        sentence = sentence.strip()
        if not sentence:
            return None

        num_match = _NUM_UNIT_RE.search(sentence)
        pct_match = _PCT_RE.search(sentence)
        year_match = _YEAR_RE.search(sentence)

        data_parts = []
        if year_match:
            data_parts.append(year_match.group(0))
        if num_match:
            data_parts.append(self._numeric_token(sentence, num_match))
        if pct_match:
            data_parts.append(pct_match.group(0))

        prefix = sentence
        for part in data_parts:
            prefix = prefix.replace(part, '', 1)
        prefix = re.sub(r'[，,、：:；;]?\s*$', '', prefix).strip()
        prefix = re.sub(r'^[，,、：:；;]\s*', '', prefix).strip()

        if not prefix and data_parts:
            return " ".join(data_parts)

        if not prefix:
            return sentence[:self.max_bullet_chars * 2]

        if data_parts:
            # Keep the numeric evidence first-class.  Truncating the whole
            # string from the right used to remove the very number the bullet
            # was meant to surface.
            data_text = " ".join(data_parts)
            prefix_budget = self.max_bullet_chars - len(data_text) - 1
            if prefix_budget <= 0:
                return data_text[:self.max_bullet_chars]
            if len(prefix) > prefix_budget:
                prefix = prefix[:max(1, prefix_budget - 1)] + "…"
            result = f"{prefix} {data_text}"
        else:
            result = prefix
            # This is a slide-writing limit, not a paragraph-writing limit.
            if len(result) > self.max_bullet_chars:
                result = result[:self.max_bullet_chars - 1] + "…"

        return result

    @staticmethod
    def _numeric_token(sentence: str, match) -> str:
        """Keep currency suffixes attached to the numeric evidence."""
        token = match.group(0)
        tail = sentence[match.end():]
        for suffix in ("人民币", "美元", "元"):
            if tail.startswith(suffix):
                return token + suffix
        return token

    def extract_all_bullets(self, content: str) -> List[str]:
        """Return every source point without silently dropping later facts.

        ``extract_bullets`` remains capped for callers that need a single-page
        preview.  The PPT page planner uses this method and performs the
        pagination explicitly.  Unlike the preview path, this method keeps
        the complete sentence: truncating a sentence here can remove a later
        metric or named entity before pagination has a chance to place it on
        another slide.
        """
        if not content or not content.strip():
            return []
        stripped = content.strip()
        existing = self._parse_existing_bullets(stripped)
        if existing:
            return [item.strip() for item in existing if item.strip()]
        sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(stripped) if s.strip()]
        return sentences

    def extract_kpis(self, content: str) -> List[Dict[str, Any]]:
        if not content or not content.strip():
            return []

        kpis = []
        sentences = _SENTENCE_SPLIT_RE.split(content)

        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue

            num_matches = list(_NUM_UNIT_RE.finditer(sent))
            pct_matches = list(_PCT_RE.finditer(sent))

            if not num_matches and not pct_matches:
                continue

            for i, num_match in enumerate(num_matches):
                kpi: Dict[str, Any] = {}
                kpi["number"] = self._numeric_token(sent, num_match).strip()

                associated_pct = None
                for pct_match in pct_matches:
                    if abs(pct_match.start() - num_match.start()) < 20:
                        associated_pct = pct_match.group(0).strip()
                        break

                kpi["trend"] = associated_pct

                if _TREND_UP_RE.search(sent):
                    kpi["trend_direction"] = "up"
                elif _TREND_DOWN_RE.search(sent):
                    kpi["trend_direction"] = "down"
                else:
                    kpi["trend_direction"] = None

                num_pos = num_match.start()
                if num_pos > 0:
                    prefix = sent[:num_pos].strip()
                    words = re.split(r'[，,、：:；;\s]+', prefix)
                    meaningful = [w for w in words if len(w) > 1 and w not in ("的", "了", "在", "是", "和")]
                    if len(meaningful) >= 2:
                        kpi["label"] = meaningful[-2] + meaningful[-1]
                    elif meaningful:
                        kpi["label"] = meaningful[-1]
                    else:
                        kpi["label"] = ""
                    year_m = _YEAR_RE.search(prefix)
                    if year_m and year_m.group(0) not in kpi["label"]:
                        kpi["label"] = year_m.group(0) + kpi["label"]
                    if len(kpi["label"]) > 20:
                        kpi["label"] = kpi["label"][:20]
                else:
                    kpi["label"] = ""

                kpi["original_text"] = sent
                kpis.append(kpi)

            for pct_match in pct_matches:
                already = any(
                    k.get("trend") == pct_match.group(0).strip()
                    for k in kpis
                    if k.get("original_text") == sent
                )
                if already:
                    continue
                if not any(n.start() <= pct_match.start() <= n.end() + 20 for n in num_matches):
                    kpi_solo: Dict[str, Any] = {
                        "number": pct_match.group(0).strip(),
                        "trend": None,
                        "trend_direction": "up" if _TREND_UP_RE.search(sent) else ("down" if _TREND_DOWN_RE.search(sent) else None),
                        "label": "",
                        "original_text": sent,
                    }
                    kpis.append(kpi_solo)

        return kpis

    def suggest_charts(self, content: str) -> List[Dict[str, Any]]:
        if not content or not content.strip():
            return []

        suggestions: List[Dict[str, Any]] = []

        if self._has_ranking_pattern(content):
            suggestions.append({
                "chart_type": "bar",
                "title": "市场份额对比",
                "reason": "检测到排名/对比数据",
            })

        if self._has_time_series_pattern(content):
            suggestions.append({
                "chart_type": "line",
                "title": "趋势变化",
                "reason": "检测到时间序列数据",
            })

        if self._has_composition_pattern(content):
            suggestions.append({
                "chart_type": "pie",
                "title": "构成分析",
                "reason": "检测到占比/构成数据",
            })

        return suggestions

    def _has_ranking_pattern(self, content: str) -> bool:
        ranking_keywords = ["榜首", "稳居", "领先", "排名", "第一", "Top", "市场份额", "占比"]
        count = sum(1 for kw in ranking_keywords if kw in content)
        num_matches = _NUM_UNIT_RE.findall(content)
        return count >= 1 and len(num_matches) >= 2

    def _has_time_series_pattern(self, content: str) -> bool:
        years = _YEAR_RE.findall(content)
        if len(years) >= 2:
            return True
        trend_words = ["增长", "上升", "下降", "CAGR", "同比", "环比"]
        return sum(1 for w in trend_words if w in content) >= 2 and len(_NUM_UNIT_RE.findall(content)) >= 2

    def _has_composition_pattern(self, content: str) -> bool:
        composition_keywords = ["占比", "构成", "份额", "比例", "分布"]
        pct_matches = _PCT_RE.findall(content)
        return any(kw in content for kw in composition_keywords) and len(pct_matches) >= 2

    def condense(
        self,
        content: str,
        title: str = "",
        table_data: Optional[List[List[str]]] = None,
    ) -> Dict[str, Any]:
        items = self.extract_bullets(content)
        all_items = self.extract_all_bullets(content)
        kpi_data = self.extract_kpis(content)
        chart_suggestions = self.suggest_charts(content)

        if table_data and len(table_data) >= 2:
            chart_suggestions.append({
                "chart_type": "bar",
                "title": title or "数据对比",
                "reason": "检测到表格数据",
            })

        return {
            "items": items,
            "all_items": all_items,
            "kpi_data": kpi_data,
            "chart_suggestions": chart_suggestions,
        }
