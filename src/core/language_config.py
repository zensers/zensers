# -*- coding: utf-8 -*-
"""
Language Configuration Module
=============================

Provides language settings management for the Zensers system.
Supports user-level and session-level language preferences.

Usage:
    from src.core.language_config import LanguageConfig, get_language_config
    
    # Get language configuration
    config = get_language_config()
    
    # Set user language preference
    config.set_user_language("user_123", "en")
    
    # Get effective language for a request
    lang = config.get_effective_language(user_id="user_123", request_lang="zh")
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Any
from pathlib import Path
import yaml
import logging

from src.core.i18n import Language, set_language, get_language

logger = logging.getLogger(__name__)


@dataclass
class LanguageConfig:
    """Language configuration manager.
    
    Manages language preferences at multiple levels:
    1. System default (from config/i18n.yaml)
    2. User preference (stored in user profile)
    3. Request parameter (explicit language in request)
    
    Priority: Request > User > System Default
    """
    
    # System default language
    default_language: Language = Language.ZH
    
    # User language preferences cache
    user_preferences: Dict[str, Language] = field(default_factory=dict)
    
    # Supported languages
    supported_languages: list = field(default_factory=lambda: ["zh", "en", "ja", "ko"])
    
    def get_effective_language(
        self,
        user_id: Optional[str] = None,
        request_lang: Optional[str] = None,
        session_lang: Optional[str] = None
    ) -> Language:
        """Get the effective language for a request.
        
        Priority order:
        1. Request parameter (explicit)
        2. Session language
        3. User preference
        4. System default
        
        Args:
            user_id: User identifier
            request_lang: Language specified in request
            session_lang: Language stored in session
            
        Returns:
            Effective Language enum value
        """
        # 1. Request parameter has highest priority
        if request_lang:
            try:
                return Language(request_lang.lower())
            except ValueError:
                logger.warning(f"Invalid request language: {request_lang}")
        
        # 2. Session language
        if session_lang:
            try:
                return Language(session_lang.lower())
            except ValueError:
                logger.warning(f"Invalid session language: {session_lang}")
        
        # 3. User preference
        if user_id and user_id in self.user_preferences:
            return self.user_preferences[user_id]
        
        # 4. System default
        return self.default_language
    
    def set_user_language(self, user_id: str, language: str) -> None:
        """Set user language preference.
        
        Args:
            user_id: User identifier
            language: Language code (zh, en, ja, ko)
        """
        try:
            lang = Language(language.lower())
            self.user_preferences[user_id] = lang
            logger.info(f"Set user {user_id} language to {lang.value}")
        except ValueError:
            logger.warning(f"Invalid language: {language}")
    
    def get_user_language(self, user_id: str) -> Optional[Language]:
        """Get user language preference.
        
        Args:
            user_id: User identifier
            
        Returns:
            User's preferred Language, or None if not set
        """
        return self.user_preferences.get(user_id)
    
    def clear_user_language(self, user_id: str) -> None:
        """Clear user language preference.
        
        Args:
            user_id: User identifier
        """
        if user_id in self.user_preferences:
            del self.user_preferences[user_id]
            logger.info(f"Cleared user {user_id} language preference")
    
    def apply_language(self, language: Language) -> None:
        """Apply language setting to current thread.
        
        Args:
            language: Language to apply
        """
        set_language(language)
    
    def is_supported(self, language: str) -> bool:
        """Check if language is supported.
        
        Args:
            language: Language code
            
        Returns:
            True if supported, False otherwise
        """
        return language.lower() in self.supported_languages
    
    def get_supported_languages(self) -> list:
        """Get list of supported language codes.
        
        Returns:
            List of supported language codes
        """
        return self.supported_languages
    
    def get_language_info(self, language: Language) -> Dict[str, Any]:
        """Get language information.
        
        Args:
            language: Language enum value
            
        Returns:
            Dictionary with language info
        """
        info = {
            "code": language.value,
            "name": {
                Language.ZH: "Chinese (Simplified)",
                Language.EN: "English",
                Language.JA: "Japanese",
                Language.KO: "Korean",
            }.get(language, "Unknown"),
            "native_name": {
                Language.ZH: "中文",
                Language.EN: "English",
                Language.JA: "日本語",
                Language.KO: "한국어",
            }.get(language, "Unknown"),
        }
        return info


# Global language configuration instance
_language_config: Optional[LanguageConfig] = None


def get_language_config() -> LanguageConfig:
    """Get the global language configuration instance.
    
    Returns:
        LanguageConfig instance
    """
    global _language_config
    
    if _language_config is None:
        # Load from config file
        config_path = Path(__file__).parent.parent.parent / "config" / "i18n.yaml"
        
        default_lang = Language.ZH
        supported = ["zh", "en", "ja", "ko"]
        
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                
                default_lang_str = config.get("default_language", "zh")
                try:
                    default_lang = Language(default_lang_str)
                except ValueError:
                    pass
                
                supported = config.get("supported_languages", supported)
            except Exception as e:
                logger.warning(f"Failed to load i18n config: {e}")
        
        _language_config = LanguageConfig(
            default_language=default_lang,
            supported_languages=supported
        )
    
    return _language_config


def set_request_language(
    user_id: Optional[str] = None,
    request_lang: Optional[str] = None,
    session_lang: Optional[str] = None
) -> Language:
    """Set the language for current request context.
    
    This function determines the effective language and applies it
    to the current thread.
    
    Args:
        user_id: User identifier
        request_lang: Language specified in request
        session_lang: Language stored in session
        
    Returns:
        Applied Language
    """
    config = get_language_config()
    language = config.get_effective_language(user_id, request_lang, session_lang)
    config.apply_language(language)
    return language


__all__ = [
    "LanguageConfig",
    "get_language_config",
    "set_request_language",
]