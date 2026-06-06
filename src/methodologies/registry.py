import json
import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

_frameworks: List[Dict] = []
_frameworks_loaded: bool = False

# Additional framework directories searched after the built-in path
_MKB_FRAMEWORKS_DIRS = [
    Path(__file__).parent / "frameworks",
    Path(__file__).parents[3] / "data" / "knowledge" / "methodology" / "frameworks",
]


def load_frameworks():
    global _frameworks_loaded
    seen_ids = set()
    for fw_dir in _MKB_FRAMEWORKS_DIRS:
        if not fw_dir.exists():
            continue
        for f in sorted(fw_dir.glob("*.json")):
            try:
                with open(f, encoding="utf-8") as fh:
                    data = json.load(fh)
                fw_id = data.get("id")
                if fw_id and fw_id in seen_ids:
                    continue
                if fw_id:
                    seen_ids.add(fw_id)
                _frameworks.append(data)
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
