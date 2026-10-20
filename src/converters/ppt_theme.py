# -*- coding: utf-8 -*-
"""PPT theme loader.

Theme files live in ``config/ppt_themes/<name>.json`` (or ``$PPT_THEME_DIR``
relative paths).  The loader returns a dict with ``colors`` and ``fonts``
maps and falls back to :data:`DEFAULT_THEME` when a file is missing or
invalid, so a broken theme file can never break a conversion.
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

DEFAULT_THEME: Dict = {
    "colors": {
        "navy": "1A2744",
        "navy_dark": "0F1A2E",
        "navy_light": "2C3E50",
        "gold": "C9A227",
        "gold_light": "D4AF37",
        "white": "FFFFFF",
        "off_white": "F5F5F5",
        "text_dark": "333333",
        "text_mid": "666666",
        "text_light": "999999",
    },
    "fonts": {
        "default": "Microsoft YaHei",
    },
}

_theme_cache: Dict[str, Dict] = {}


def _resolve_theme_path(name: str):
    env_dir = os.environ.get("PPT_THEME_DIR")
    if env_dir:
        candidate = Path(env_dir) / f"{name}.json"
        if candidate.is_file():
            return candidate
    base = Path(__file__).resolve().parents[2]
    candidate = base / "config" / "ppt_themes" / f"{name}.json"
    if candidate.is_file():
        return candidate
    return None


def load_theme(name: str = "default") -> Dict:
    """Load a theme by name, falling back to DEFAULT_THEME."""
    if name in _theme_cache:
        return _theme_cache[name]

    theme: Dict = {"colors": dict(DEFAULT_THEME["colors"]), "fonts": dict(DEFAULT_THEME["fonts"])}
    path = _resolve_theme_path(name)
    if path is None:
        if name != "default":
            logger.warning(f"PPT theme '{name}' not found, using defaults")
    else:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            colors = data.get("colors") or {}
            fonts = data.get("fonts") or {}
            for key, value in colors.items():
                if isinstance(value, str) and len(value) in (3, 6):
                    theme["colors"][key] = value.lstrip("#")
                else:
                    logger.warning(f"Theme '{name}': invalid color '{key}={value}', keeping default")
            for key, value in fonts.items():
                if isinstance(value, str) and value.strip():
                    theme["fonts"][key] = value.strip()
        except (OSError, json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to load PPT theme '{name}' from {path}: {e}, using defaults")

    _theme_cache[name] = theme
    return theme


def clear_theme_cache() -> None:
    _theme_cache.clear()


__all__ = ["DEFAULT_THEME", "load_theme", "clear_theme_cache"]
