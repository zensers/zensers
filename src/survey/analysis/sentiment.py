"""
Sentiment Analysis Module (Bilingual: Chinese + English)

Hybrid approach: language-aware tokenization + comprehensive dictionary + LLM fallback.

Flow:
  1. Auto-detect language (Chinese 'zh' or English 'en')
  2. Tokenize: jieba for Chinese, whitespace+punctuation split for English
  3. Look up each token in the bilingual sentiment dictionary
  4. Apply intensifier multipliers and negation reversal
  5. Calculate sentiment score (-1.0 ~ 1.0)
  6. Low-confidence texts (< 0.4) optionally enhanced via LLM
"""

import logging
import re
from collections import Counter
from typing import Dict, Any, List, Optional

from src.core.llm_client import call_llm_sync

from .sentiment_dict import SentimentDict, get_default_dict, detect_language

logger = logging.getLogger(__name__)

# Regex for English word tokenization
_EN_WORD_RE = re.compile(r"[a-zA-Z]+(?:['-][a-zA-Z]+)*")


class SentimentAnalyzer:
    """Bilingual sentiment analyzer: auto-detects Chinese/English.

    Usage:
        sa = SentimentAnalyzer()

        # Chinese
        sa.analyze_text("This product is great, I'm very satisfied")

        # English
        sa.analyze_text("This product is great, I love it")

        # Batch (mixed languages OK)
        sa.analyze_batch(["Good quality", "This is terrible"])
    """

    def __init__(
        self,
        sentiment_dict: Optional[SentimentDict] = None,
    ):
        self._dict = sentiment_dict or get_default_dict()
        self._jieba_initialized = False

    # ------------------------------------------------------------------ #
    # Lazy jieba initialisation
    # ------------------------------------------------------------------ #
    def _ensure_jieba(self):
        if self._jieba_initialized:
            return
        import jieba
        # Register custom words for better compound sentiment matching
        for word in ["better_than_expected", "exceeds_expectations", "beyond_anticipation", "above_average", "surprisingly_good"]:
            jieba.add_word(word)
        self._jieba_initialized = True

    # ------------------------------------------------------------------ #
    # Tokenization
    # ------------------------------------------------------------------ #
    def _tokenize(self, text: str, lang: str) -> List[str]:
        """Tokenize text based on detected language."""
        if lang == "zh":
            return self._tokenize_chinese(text)
        return self._tokenize_english(text)

    @staticmethod
    def _tokenize_english(text: str) -> List[str]:
        """Tokenize English text by words and punctuation."""
        return _EN_WORD_RE.findall(text.lower())

    def _tokenize_chinese(self, text: str) -> List[str]:
        """Tokenize Chinese text with jieba."""
        self._ensure_jieba()
        import jieba
        return list(jieba.cut(text.strip()))

    # ------------------------------------------------------------------ #
    # Core analysis
    # ------------------------------------------------------------------ #
    def analyze_text(
        self,
        text: str,
        lang: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Analyze sentiment of a single text.

        Args:
            text: The text to analyze (Chinese or English)
            lang: Force language ('zh' or 'en'). Auto-detect if None.

        Returns:
            {
                "sentiment": "positive" | "neutral" | "negative",
                "score": float,  # -1.0 ~ 1.0
                "positive_words": List[str],
                "negative_words": List[str],
                "confidence": float,
                "language": "zh" | "en",
            }
        """
        if not text or not text.strip():
            return self._neutral_result(language="en")

        lang = lang or detect_language(text)
        tokens = self._tokenize(text, lang)

        pos_count = 0
        neg_count = 0
        pos_matched: List[str] = []
        neg_matched: List[str] = []
        intensifier = 1.0
        negation_active = False

        for token in tokens:
            if not token.strip():
                continue

            # Check intensifier (before negation)
            intensity = self._dict.get_intensity(token)
            if abs(intensity - 1.0) > 0.01:
                if not negation_active:
                    intensifier = max(intensifier, intensity) if intensity > 1.0 else min(intensifier, intensity)
                continue

            # Check negation (flips sentiment of the next sentiment word)
            if self._dict.is_negation(token):
                negation_active = True
                continue

            # Check positive/negative
            if self._dict.is_positive(token):
                if negation_active:
                    neg_count += 1
                    neg_matched.append(f"~{token}")
                else:
                    pos_count += 1
                    pos_matched.append(token)
                negation_active = False
            elif self._dict.is_negative(token):
                if negation_active:
                    pos_count += 1
                    pos_matched.append(f"~{token}")
                else:
                    neg_count += 1
                    neg_matched.append(token)
                negation_active = False
            else:
                # Token not in dictionary - try sub-word matching for Chinese
                if lang == "zh" and len(token) >= 3:
                    sub_pos, sub_neg = self._subword_match(token, negation_active)
                    if sub_pos > 0 or sub_neg > 0:
                        pos_count += sub_pos
                        neg_count += sub_neg
                    negation_active = False
                # For English, just reset negation if next token isn't a sentiment word
                elif lang == "en":
                    negation_active = False

        # Calculate score
        total = pos_count + neg_count
        if total == 0:
            return self._neutral_result(confidence=0.3, language=lang)

        raw_score = (pos_count - neg_count) / total

        # Apply intensifier
        score = max(-1.0, min(1.0, raw_score * intensifier))

        # Determine sentiment
        if score > 0.2:
            sentiment = "positive"
        elif score < -0.2:
            sentiment = "negative"
        else:
            sentiment = "neutral"

        # Confidence: more matching words = higher confidence
        confidence = min(1.0, 0.3 + total * 0.12)

        return {
            "sentiment": sentiment,
            "score": round(score, 4),
            "positive_words": pos_matched,
            "negative_words": neg_matched,
            "confidence": round(confidence, 4),
            "language": lang,
        }

    def _subword_match(self, token: str, negated: bool = False) -> tuple:
        """Try to match sentiment sub-words within a compound Chinese token."""
        pos = 0
        neg = 0
        t = token

        for length in range(min(len(t), 6), 1, -1):
            if pos > 0 or neg > 0:
                break
            for start in range(len(t) - length + 1):
                sub = t[start:start + length]
                if len(sub) < 2:
                    continue
                if self._dict.is_positive(sub):
                    if negated:
                        neg += 1
                    else:
                        pos += 1
                elif self._dict.is_negative(sub):
                    if negated:
                        pos += 1
                    else:
                        neg += 1

        return pos, neg

    # ------------------------------------------------------------------ #
    # Batch analysis
    # ------------------------------------------------------------------ #
    def analyze_batch(
        self,
        texts: List[str],
        use_llm: bool = False,
        lang: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Batch analyze multiple texts.

        Args:
            texts: List of texts to analyze (mixed languages OK)
            use_llm: Whether to use LLM for low-confidence texts
            lang: Force language for all texts. Auto-detect each if None.

        Returns:
            {
                "overall": {"positive": %, "neutral": %, "negative": %},
                "avg_score": float,
                "total_analyzed": int,
                "per_item": [{...}, ...],
            }
        """
        results = [self.analyze_text(t, lang=lang) for t in texts]

        # Optional: LLM enhancement for low-confidence texts
        if use_llm:
            results = self._llm_enhance(texts, results)

        # Aggregate results
        sentiments = Counter(r["sentiment"] for r in results)
        total = len(results) or 1
        scores = [r["score"] for r in results if r["confidence"] > 0]

        overall = {
            "positive": round(sentiments.get("positive", 0) / total * 100, 1),
            "neutral": round(sentiments.get("neutral", 0) / total * 100, 1),
            "negative": round(sentiments.get("negative", 0) / total * 100, 1),
        }

        return {
            "overall": overall,
            "avg_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
            "total_analyzed": total,
            "per_item": results,
        }

    # ------------------------------------------------------------------ #
    # LLM enhancement
    # ------------------------------------------------------------------ #
    def _llm_enhance(self, texts: List[str], results: List[Dict]) -> List[Dict]:
        """Use LLM to enhance low-confidence results."""
        for i, (text, r) in enumerate(zip(texts, results)):
            if r["confidence"] < 0.4 and len(text) > 20:
                try:
                    llm_result = call_llm_sync(
                        prompt=(
                            f"Please analyze the sentiment of the following text, "
                            f"output only 'positive', 'neutral', or 'negative':\n\n{text[:500]}"
                        ),
                        temperature=0.3,
                        max_tokens=10,
                    )
                    if llm_result.get("success"):
                        content = llm_result.get("content", "").strip().lower()
                        if content in ("positive", "neutral", "negative"):
                            results[i]["sentiment"] = content
                            results[i]["confidence"] = 0.7
                except Exception as e:
                    logger.debug("LLM sentiment enhancement failed: %s", e)

        return results

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _neutral_result(confidence: float = 0.0, language: str = "en") -> Dict[str, Any]:
        return {
            "sentiment": "neutral",
            "score": 0.0,
            "positive_words": [],
            "negative_words": [],
            "confidence": confidence,
            "language": language,
        }

    @property
    def dictionary_stats(self) -> Dict[str, int]:
        """Get dictionary word counts for diagnostics."""
        return self._dict.word_count()
