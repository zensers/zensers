"""Keyword Deriver — derive search keywords from research topic + aspect."""

import re
from datetime import datetime
from typing import Dict, List


# 口径词典：按行业领域自动匹配
CALIBER_TERMS = {
    "market": ["出货量", "销量", "零售量", "批发量", "激活量", "ASP", "均价", "市场份额"],
    "production": ["产量", "产能", "产能利用率", "开工率"],
    "finance": ["营收", "利润", "毛利率", "净利率", "估值"],
    "policy": ["补贴", "法规", "标准", "规划", "通知"],
    "technology": ["专利", "研发投入", "技术路线", "专利数量"],
}

# 排除词：跨行业噪音
EXCLUDE_TERMS_DEFAULT = ["猪肉", "新能源汽车", "AI芯片"]


class KeywordDeriver:
    def derive(self, topic: str, aspect: str = "") -> Dict[str, List[str]]:
        """从 topic + aspect 派生搜索关键词组。"""
        core = self._extract_core(topic)
        caliber = self._match_caliber(topic, aspect)
        time_words = self._time_words()
        exclude = self._exclude_words(topic)
        return {
            "core": core,
            "caliber": caliber,
            "time": time_words,
            "exclude": exclude,
        }

    def _extract_core(self, topic: str) -> List[str]:
        t = re.sub(
            r"(深度研究|市场研究|研究报告|分析报告|行业分析|行业研究|发展研究|"
            r"发展分析|前景分析|市场分析|调查报告|调研报告|白皮书|蓝皮书)",
            "", topic,
        )
        t = re.sub(r"^(中国|全球|国内|国外|亚太|欧美)\s*", "", t)
        t = t.strip()
        return [t] if t else []

    def _match_caliber(self, topic: str, aspect: str) -> List[str]:
        combined = (topic + " " + aspect).lower()
        matched = []
        for domain, terms in CALIBER_TERMS.items():
            for term in terms:
                if term.lower() in combined:
                    matched.append(term)
        if not matched:
            matched = CALIBER_TERMS.get("market", [])[:3]
        return matched

    def _time_words(self) -> List[str]:
        now = datetime.now()
        return [str(now.year), str(now.year - 1), f"Q{min((now.month - 1) // 3 + 1, 4)}"]

    def _exclude_words(self, topic: str) -> List[str]:
        excludes = list(EXCLUDE_TERMS_DEFAULT)
        topic_lower = topic.lower()
        for word in EXCLUDE_TERMS_DEFAULT:
            if word in topic_lower:
                excludes.remove(word)
        return excludes
