"""
Word Cloud Generator

Performs word segmentation and frequency analysis on open-ended responses,
generates word cloud images.

Dependencies: jieba (segmentation) + wordcloud (generation)
Both are optional dependencies - falls back to frequency table output if missing.
"""

import logging
import os
import re
from collections import Counter
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Stop words
_STOP_WORDS = {
    "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "对",
    "而", "但", "把", "被", "让", "给", "用", "做", "为", "能", "所",
    "可以", "还", "从", "与", "以", "及", "或", "之", "比", "等", "多",
    "来", "出", "过", "只", "如", "如果", "因为", "所以", "虽然", "但是",
    "可能", "什么", "怎么", "哪种", "有些", "这个", "那个", "哪些",
    "比较", "已经", "一种", "不是", "就是", "还是", "或者", "没有",
}

# Check for optional dependencies
try:
    import jieba
    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False
    logger.info("jieba not installed, word cloud will only output frequency table (pip install jieba)")

try:
    from wordcloud import WordCloud
    HAS_WORDCLOUD = True
except ImportError:
    HAS_WORDCLOUD = False
    logger.info("wordcloud not installed, word cloud will only output frequency table (pip install wordcloud)")


class WordCloudGenerator:
    """Word cloud generator."""

    def __init__(self, font_path: Optional[str] = None):
        self.font_path = font_path or self._find_chinese_font()

    @staticmethod
    def _find_chinese_font() -> Optional[str]:
        """Find a Chinese font on the system."""
        candidates = [
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/simsun.ttc",
            "/System/Library/Fonts/PingFang.ttc",  # macOS
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",  # Linux
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return None

    def generate(
        self,
        texts: List[str],
        output_path: Optional[str] = None,
        top_n: int = 100,
        min_word_length: int = 2,
    ) -> Dict[str, Any]:
        """
        Generate word cloud and frequency statistics.

        Args:
            texts: List of open-ended text responses
            output_path: Word cloud image output path (optional)
            top_n: Number of top frequent words to keep
            min_word_length: Minimum word length

        Returns:
            {
                "frequencies": [{"word": "...", "count": N}, ...],
                "total_words": int,
                "unique_words": int,
                "image_path": str | None,
            }
        """
        if not texts:
            return {
                "frequencies": [],
                "total_words": 0,
                "unique_words": 0,
                "image_path": None,
            }

        # Segment texts
        words = self._segment_texts(texts, min_word_length)

        # Count frequencies
        counter = Counter(words)
        total = sum(counter.values())
        top = counter.most_common(top_n)

        frequencies = [
            {"word": word, "count": count, "percentage": round(count / total * 100, 2)}
            for word, count in top
        ]

        result: Dict[str, Any] = {
            "frequencies": frequencies,
            "total_words": total,
            "unique_words": len(counter),
        }

        # Generate image if requested
        if output_path and HAS_JIEBA and HAS_WORDCLOUD:
            try:
                image_path = self._render_wordcloud(dict(top), output_path)
                result["image_path"] = image_path
            except Exception as e:
                logger.warning(f"Word cloud image generation failed: {e}")

        return result

    def _segment_texts(self, texts: List[str], min_len: int) -> List[str]:
        """Segment texts into words."""
        words: List[str] = []

        if HAS_JIEBA:
            for text in texts:
                # Clean text (keep Chinese characters and alphanumeric)
                clean = re.sub(r"[^\u4e00-\u9fff\w]", " ", text)
                tokens = jieba.lcut(clean)
                words.extend(
                    w for w in tokens
                    if len(w) >= min_len and w not in _STOP_WORDS
                )
        else:
            # Fallback: simple bigram extraction
            for text in texts:
                clean = re.sub(r"[^\u4e00-\u9fff]", "", text)
                for i in range(len(clean) - 1):
                    bigram = clean[i:i + 2]
                    if bigram not in _STOP_WORDS:
                        words.append(bigram)

        return words

    def _render_wordcloud(
        self, frequencies: Dict[str, int], output_path: str
    ) -> str:
        """Render word cloud image."""
        wc = WordCloud(
            font_path=self.font_path,
            width=800,
            height=600,
            background_color="white",
            max_words=100,
            max_font_size=80,
            random_state=42,
        )
        wc.generate_from_frequencies(frequencies)
        wc.to_file(output_path)
        logger.info(f"Word cloud saved: {output_path}")
        return output_path
