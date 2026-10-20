# -*- coding: utf-8 -*-
"""PPT theme loader.

Theme files live in ``config/ppt_themes/<name>.json`` (or ``$PPT_THEME_DIR``
relative paths).  The loader returns a dict with ``colors`` and ``fonts``
maps and falls back to :data:`DEFAULT_THEME` when a file is missing or
invalid, so a broken theme file can never break a conversion.
"""

import copy
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_HEX_COLOR_RE = re.compile(r"^[0-9a-fA-F]{6}$|^[0-9a-fA-F]{3}$")

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


def _resolve_theme_path(name: str) -> Optional[Path]:
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
            colors = data.get("colors")
            fonts = data.get("fonts")
            if isinstance(colors, dict):
                for key, value in colors.items():
                    cleaned = value.lstrip("#") if isinstance(value, str) else ""
                    if _HEX_COLOR_RE.match(cleaned):
                        theme["colors"][key] = cleaned
                    else:
                        logger.warning(f"Theme '{name}': invalid color '{key}={value}', keeping default")
            elif colors:
                logger.warning(f"Theme '{name}': 'colors' is not an object, keeping defaults")
            if isinstance(fonts, dict):
                for key, value in fonts.items():
                    if isinstance(value, str) and value.strip():
                        theme["fonts"][key] = value.strip()
            elif fonts:
                logger.warning(f"Theme '{name}': 'fonts' is not an object, keeping defaults")
        except (OSError, json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to load PPT theme '{name}' from {path}: {e}, using defaults")

    _theme_cache[name] = theme
    return copy.deepcopy(theme)


def clear_theme_cache() -> None:
    _theme_cache.clear()


__all__ = ["DEFAULT_THEME", "load_theme", "clear_theme_cache"]
