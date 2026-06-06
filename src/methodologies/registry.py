import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_frameworks: List[Dict] = []
_frameworks_loaded: bool = False

_rubrics: List[Dict] = []
_rubrics_loaded: bool = False

_exemplars: List[Dict] = []
_exemplars_loaded: bool = False

_data_standards: Dict[str, List[Dict]] = {}
_data_standards_loaded: bool = False

_MKB_BASE = Path(__file__).parents[2] / "data" / "knowledge" / "methodology"

_MKB_FRAMEWORKS_DIRS = [
    Path(__file__).parent / "frameworks",
    _MKB_BASE / "frameworks",
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


def load_rubrics():
    global _rubrics_loaded
    rubric_dir = _MKB_BASE / "rubrics"
    if not rubric_dir.exists():
        _rubrics_loaded = True
        return
    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML not installed, skipping rubrics loading")
        _rubrics_loaded = True
        return
    for f in sorted(rubric_dir.glob("*.yaml")):
        try:
            with open(f, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if data and isinstance(data, dict):
                _rubrics.append(data)
        except Exception as e:
            logger.warning(f"Skipping bad rubric file {f}: {e}")
    _rubrics_loaded = True


def load_exemplars():
    global _exemplars_loaded
    exemplar_dir = _MKB_BASE / "exemplars"
    if not exemplar_dir.exists():
        _exemplars_loaded = True
        return
    for subdir in sorted(exemplar_dir.iterdir()):
        if not subdir.is_dir():
            continue
        for f in sorted(subdir.glob("*.json")):
            try:
                with open(f, encoding="utf-8") as fh:
                    data = json.load(fh)
                if data and isinstance(data, dict):
                    _exemplars.append(data)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Skipping bad exemplar file {f}: {e}")
    _exemplars_loaded = True


def load_data_standards():
    global _data_standards_loaded
    ds_dir = _MKB_BASE / "data_standards"
    if not ds_dir.exists():
        _data_standards_loaded = True
        return
    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML not installed, skipping data_standards loading")
        _data_standards_loaded = True
        return
    for f in sorted(ds_dir.glob("*.yaml")):
        try:
            with open(f, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if not data or not isinstance(data, dict):
                continue
            category = f.stem
            for key in ("standards", "multiples"):
                items = data.get(key)
                if items and isinstance(items, list):
                    _data_standards.setdefault(category, []).extend(items)
            benchmarks = data.get("benchmarks")
            if benchmarks and isinstance(benchmarks, list):
                for grp in benchmarks:
                    if isinstance(grp, dict) and "metrics" in grp:
                        for m in grp.get("metrics", []):
                            m.setdefault("industry", grp.get("industry", ""))
                            _data_standards.setdefault(category, []).append(m)
        except Exception as e:
            logger.warning(f"Skipping bad data_standards file {f}: {e}")
    _data_standards_loaded = True


def _ensure_loaded():
    if not _frameworks_loaded:
        load_frameworks()


def _ensure_rubrics():
    if not _rubrics_loaded:
        load_rubrics()


def _ensure_exemplars():
    if not _exemplars_loaded:
        load_exemplars()


def _ensure_data_standards():
    if not _data_standards_loaded:
        load_data_standards()


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


def get_rubric(section_type: str) -> Optional[Dict]:
    _ensure_rubrics()
    for r in _rubrics:
        if r.get("section_type") == section_type:
            return r
    for r in _rubrics:
        if r.get("section_type") == "generic":
            return r
    return None


def get_exemplars(section_type: str, limit: int = 2) -> List[Dict]:
    _ensure_exemplars()
    matched = [e for e in _exemplars if e.get("section_type") == section_type]
    if not matched:
        matched = [e for e in _exemplars if e.get("section_type") == "generic"]
    return matched[:limit]


def get_data_standards(category: Optional[str] = None) -> Dict[str, List[Dict]]:
    _ensure_data_standards()
    if category:
        return {category: _data_standards.get(category, [])}
    return dict(_data_standards)
