import json
import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

_frameworks: List[Dict] = []
_frameworks_loaded: bool = False


def load_frameworks():
    global _frameworks_loaded
    frameworks_dir = Path(__file__).parent / "frameworks"
    for f in frameworks_dir.glob("*.json"):
        try:
            with open(f, encoding="utf-8") as fh:
                _frameworks.append(json.load(fh))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Skipping bad framework file {f}: {e}")
    _frameworks.sort(key=lambda x: x.get("priority", 99))
    _frameworks_loaded = True


def _ensure_loaded():
    if not _frameworks_loaded:
        load_frameworks()


def match_for_aspect(aspect: str) -> List[Dict]:
    _ensure_loaded()
    matched = [f for f in _frameworks if aspect in f.get("aspects", [])]
    return matched


def get_aspect_map() -> Dict[str, List[str]]:
    _ensure_loaded()
    mapping = {}
    for fw in _frameworks:
        for aspect in fw.get("aspects", []):
            mapping.setdefault(aspect, []).append(fw["id"])
    return mapping
