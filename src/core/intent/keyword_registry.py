# -*- coding: utf-8 -*-
"""
Keyword Registry — single source of truth for all intent keywords.

Reads from config/keyword_mappings.yaml and provides compiled patterns
to RevisionIntentAnalyzer, RevisionIntentMapper, and strategies.

No hardcoded keywords in code — everything comes from YAML.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Any

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path("config/keyword_mappings.yaml")
_instance: Optional["KeywordRegistry"] = None


class KeywordRegistry:
    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path or _CONFIG_PATH
        self._raw: Dict[str, Any] = {}
        self._revision_patterns: Dict[str, List[re.Pattern]] = {}
        self._implicit_zh_patterns: List[re.Pattern] = []
        self._implicit_en_patterns: List[re.Pattern] = []
        self._implicit_fallback_action: str = "modify"
        self._global_feedback_zh: List[str] = []
        self._global_feedback_en: List[re.Pattern] = []
        self._mapper_config: Dict[str, Any] = {}
        self._listed_company_suffixes: List[str] = []
        self._listed_company_names: List[str] = []
        self._load()

    def _load(self) -> None:
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._raw = yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning(f"Keyword config not found: {self._config_path}, using empty defaults")
            return
        except Exception as e:
            logger.warning(f"Failed to load keyword config: {e}")
            return

        self._parse_revision_intents()
        self._parse_implicit_intent()
        self._parse_global_feedback()
        self._parse_revision_mapper()
        self._parse_listed_company()

    def _parse_revision_intents(self) -> None:
        ri = self._raw.get("revision_intents", {})
        for action_type, spec in ri.items():
            patterns = []
            for p in spec.get("patterns", []):
                try:
                    patterns.append(re.compile(p))
                except re.error as e:
                    logger.warning(f"Invalid regex in revision_intents.{action_type}: {p} — {e}")
            self._revision_patterns[action_type] = patterns

    def _parse_implicit_intent(self) -> None:
        ii = self._raw.get("implicit_intent", {})
        self._implicit_fallback_action = ii.get("fallback_action", "modify")
        for p in ii.get("chinese", []):
            try:
                self._implicit_zh_patterns.append(re.compile(p))
            except re.error as e:
                logger.warning(f"Invalid implicit zh pattern: {p} — {e}")
        for p in ii.get("english", []):
            try:
                self._implicit_en_patterns.append(re.compile(p, re.IGNORECASE))
            except re.error as e:
                logger.warning(f"Invalid implicit en pattern: {p} — {e}")

    def _parse_global_feedback(self) -> None:
        gf = self._raw.get("global_feedback", {})
        self._global_feedback_zh = gf.get("chinese", [])
        for p in gf.get("english", []):
            try:
                self._global_feedback_en.append(re.compile(p, re.IGNORECASE))
            except re.error as e:
                logger.warning(f"Invalid global feedback pattern: {p} — {e}")

    def _parse_revision_mapper(self) -> None:
        self._mapper_config = self._raw.get("revision_intent_mapper", {})

    def _parse_listed_company(self) -> None:
        lc = self._raw.get("listed_company_indicators", {})
        self._listed_company_suffixes = lc.get("suffixes", [])
        self._listed_company_names = lc.get("names", [])

    def get_revision_patterns(self) -> Dict[str, List[re.Pattern]]:
        return dict(self._revision_patterns)

    def get_revision_pattern_strings(self) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for action_type, patterns in self._revision_patterns.items():
            result["|".join(p.pattern for p in patterns)] = action_type
        return result

    def get_implicit_pattern_strings(self) -> Dict[str, List[str]]:
        return {
            "chinese": [p.pattern for p in self._implicit_zh_patterns],
            "english": [p.pattern for p in self._implicit_en_patterns],
        }

    def get_global_feedback_pattern_strings(self) -> Dict[str, List[str]]:
        return {
            "chinese": list(self._global_feedback_zh),
            "english": [p.pattern for p in self._global_feedback_en],
        }

    def is_implicit_intent(self, text: str) -> bool:
        for p in self._implicit_zh_patterns:
            if p.search(text):
                return True
        for p in self._implicit_en_patterns:
            if p.search(text):
                return True
        return False

    def is_global_feedback(self, text: str) -> bool:
        for kw in self._global_feedback_zh:
            if kw in text:
                return True
        for p in self._global_feedback_en:
            if p.search(text):
                return True
        return False

    def get_implicit_fallback_action(self) -> str:
        return self._implicit_fallback_action

    def get_mapper_config(self) -> Dict[str, Any]:
        return self._mapper_config

    def is_listed_company_topic(self, topic: str) -> bool:
        if not topic:
            return False
        for suffix in self._listed_company_suffixes:
            if suffix in topic:
                return True
        for name in self._listed_company_names:
            if name in topic:
                return True
        return False


def get_registry(config_path: Optional[Path] = None) -> KeywordRegistry:
    global _instance
    if _instance is None:
        _instance = KeywordRegistry(config_path)
    return _instance


def reload_registry(config_path: Optional[Path] = None) -> KeywordRegistry:
    global _instance
    _instance = KeywordRegistry(config_path)
    return _instance
