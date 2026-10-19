"""
Sentiment Dictionary Loader (Bilingual: Chinese + English)

Loads sentiment word lists from data/sentiment/ text files.
Supports lazy loading, hot-reload, and merging with external dictionaries.
Language auto-detection based on character set.

File naming convention:
  positive_zh.txt, negative_zh.txt    - Chinese
  positive_en.txt, negative_en.txt    - English
  intensifiers_{lang}.txt             - Intensifiers per language
  negation_{lang}.txt                 - Negation words per language

File format: one word per line, UTF-8. Lines starting with # are comments.
"""

import logging
import os
import re
from typing import Dict, Set

logger = logging.getLogger(__name__)

# Default path relative to project root
_DEFAULT_DICT_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "sentiment")
)

# Supported languages
_SUPPORTED_LANGS = ("zh", "en")


def detect_language(text: str) -> str:
    """Detect whether text is primarily Chinese or English.

    Heuristic: count CJK characters vs ASCII alphabetic characters.
    Returns 'zh' or 'en'.
    """
    if not text:
        return "en"
    cjk = len(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]", text))
    alpha = len(re.findall(r"[a-zA-Z]", text))
    return "zh" if cjk >= alpha else "en"


class SentimentDict:
    """Bilingual sentiment dictionary loader with lazy loading.

    Loads both Chinese (zh) and English (en) dictionaries.
    All words are merged into unified sets since the character sets
    don't overlap. Language detection is handled by the analyzer.

    Usage:
        sd = SentimentDict()
        sd.is_positive("satisfied") -> True
        sd.is_positive("good") -> True
        sd.is_negative("poor") -> True
        sd.is_negative("bad") -> True
        sd.get_intensity("very") -> 1.5
        sd.is_negation("not") -> True
    """

    def __init__(self, dict_dir: str = _DEFAULT_DICT_DIR):
        self._dict_dir = dict_dir
        self._positive: Set[str] = set()
        self._negative: Set[str] = set()
        self._intensifiers: Dict[str, float] = {}
        self._negation: Set[str] = set()
        self._loaded = False

    # ------------------------------------------------------------------ #
    # Lazy loading
    # ------------------------------------------------------------------ #
    def _ensure_loaded(self):
        if self._loaded:
            return
        self._load_all()
        self._loaded = True

    def _load_all(self):
        """Load all word lists for all languages."""
        for lang in _SUPPORTED_LANGS:
            pos = self._load_set(f"positive_{lang}.txt")
            neg = self._load_set(f"negative_{lang}.txt")
            self._positive.update(pos)
            self._negative.update(neg)

            # Intensifiers: merge (later files overwrite same keys, which is fine)
            intf = self._load_intensifiers(f"intensifiers_{lang}.txt")
            self._intensifiers.update(intf)

            # Negation
            ng = self._load_set(f"negation_{lang}.txt")
            self._negation.update(ng)

            logger.info(
                "  [%s] +%d positive, +%d negative, +%d intensifiers, +%d negation",
                lang, len(pos), len(neg), len(intf), len(ng),
            )

        logger.info(
            "Loaded sentiment dictionary: %d positive, %d negative, "
            "%d intensifiers, %d negation words (total across %d languages)",
            len(self._positive), len(self._negative),
            len(self._intensifiers), len(self._negation),
            len(_SUPPORTED_LANGS),
        )

    def _load_set(self, filename: str) -> Set[str]:
        """Load a word-per-line file into a set, skipping comments/blank lines."""
        path = os.path.join(self._dict_dir, filename)
        if not os.path.exists(path):
            logger.warning("Sentiment dict file not found: %s", path)
            return set()
        words = set()
        with open(path, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip().lower()
                if not stripped or stripped.startswith("#"):
                    continue
                words.add(stripped)
        return words

    def _load_intensifiers(self, filename: str) -> Dict[str, float]:
        """Load intensifiers with intensity multipliers.

        Format:
            # High intensity (x2.0)
            very
            extremely
            ...
            # Low intensity (x0.8)
            slightly
            ...
        """
        path = os.path.join(self._dict_dir, filename)
        if not os.path.exists(path):
            logger.warning("Intensifier file not found: %s", path)
            return {}

        multipliers: Dict[str, float] = {}
        current_mult = 1.0

        with open(path, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip().lower()
                if not stripped:
                    continue
                if stripped.startswith("#"):
                    # Parse intensity level from comment
                    if "high" in stripped.lower():
                        current_mult = 2.0
                    elif "medium-high" in stripped.lower():
                        current_mult = 1.5
                    elif "medium" in stripped.lower():
                        current_mult = 1.2
                    elif "low" in stripped.lower():
                        current_mult = 0.8
                    continue
                multipliers[stripped] = current_mult

        return multipliers

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    @property
    def positive_words(self) -> Set[str]:
        self._ensure_loaded()
        return self._positive

    @property
    def negative_words(self) -> Set[str]:
        self._ensure_loaded()
        return self._negative

    @property
    def intensifiers(self) -> Dict[str, float]:
        self._ensure_loaded()
        return self._intensifiers

    @property
    def negation_words(self) -> Set[str]:
        self._ensure_loaded()
        return self._negation

    def is_positive(self, word: str) -> bool:
        """Check if a word is in the positive dictionary (case-insensitive)."""
        self._ensure_loaded()
        return word.lower() in self._positive

    def is_negative(self, word: str) -> bool:
        """Check if a word is in the negative dictionary (case-insensitive)."""
        self._ensure_loaded()
        return word.lower() in self._negative

    def get_intensity(self, word: str) -> float:
        """Get intensity multiplier for a word (1.0 if not found)."""
        self._ensure_loaded()
        return self._intensifiers.get(word.lower(), 1.0)

    def is_negation(self, word: str) -> bool:
        """Check if a word is a negation word (case-insensitive)."""
        self._ensure_loaded()
        return word.lower() in self._negation

    def reload(self):
        """Force reload from disk (useful for hot-reload)."""
        self._loaded = False
        self._ensure_loaded()

    def word_count(self) -> Dict[str, int]:
        """Get word counts for all categories."""
        self._ensure_loaded()
        return {
            "positive": len(self._positive),
            "negative": len(self._negative),
            "intensifiers": len(self._intensifiers),
            "negation": len(self._negation),
            "total": len(self._positive) + len(self._negative)
                     + len(self._intensifiers) + len(self._negation),
            "languages": list(_SUPPORTED_LANGS),
        }

    def word_count_by_lang(self) -> Dict[str, Dict[str, int]]:
        """Get word counts broken down by language."""
        counts = {}
        for lang in _SUPPORTED_LANGS:
            counts[lang] = {
                "positive": len(self._load_set(f"positive_{lang}.txt")),
                "negative": len(self._load_set(f"negative_{lang}.txt")),
                "intensifiers": len(self._load_intensifiers(f"intensifiers_{lang}.txt")),
                "negation": len(self._load_set(f"negation_{lang}.txt")),
            }
        return counts


# Singleton for global reuse
_default_dict: SentimentDict = None


def get_default_dict() -> SentimentDict:
    """Get the default singleton sentiment dictionary."""
    global _default_dict
    if _default_dict is None:
        _default_dict = SentimentDict()
    return _default_dict
