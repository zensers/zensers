"""Demographic Data Warehouse - Multi-Region File-Based Storage."""
import json, logging, os
from typing import Dict, Any

logger = logging.getLogger(__name__)
_REGIONS_DIR = os.path.join(os.path.dirname(__file__), "regions")
_cache = {}
_REGION_ALIASES = {
    "us": "usa",
    "united_states": "usa",
    "uk": "gbr",
    "united_kingdom": "gbr",
}


def _region_path(region):
    return os.path.join(_REGIONS_DIR, f"{region}.json")


def list_regions():
    regions = {}
    if not os.path.isdir(_REGIONS_DIR):
        return regions
    for fname in sorted(os.listdir(_REGIONS_DIR)):
        if fname.endswith(".json"):
            rid = fname[:-5]
            try:
                with open(os.path.join(_REGIONS_DIR, fname), encoding="utf-8") as f:
                    meta = json.load(f).get("meta", {})
                regions[rid] = meta.get("name_en", rid)
            except Exception:
                regions[rid] = rid
    return regions


def load_region(region):
    region = str(region or "").strip().lower()
    region = _REGION_ALIASES.get(region, region)
    if region in _cache:
        return _cache[region]
    if region == "eu":
        # EU is a supported aggregate selector.  Build it from the available
        # country datasets instead of silently using one representative state.
        source_regions = ["deu", "fra", "gbr"]
        source_data = [load_region(rid) for rid in source_regions]
        dimensions = {
            dimension
            for data in source_data
            for dimension, values in data.items()
            if dimension != "meta" and isinstance(values, dict)
        }
        aggregate = {"meta": {
            "region": "eu",
            "name_en": "European Union aggregate",
            "source_url": "https://population.un.org/wpp/",
            "sources": {"countries": source_regions},
            "data_notes": "Simple equal-weight aggregate of the available EU country datasets.",
        }}
        for dimension in dimensions:
            keys = {
                key
                for data in source_data
                for key, value in data.get(dimension, {}).items()
                if isinstance(value, (int, float))
            }
            values = {
                key: sum(data.get(dimension, {}).get(key, 0.0) for data in source_data) / len(source_data)
                for key in keys
            }
            total = sum(values.values())
            aggregate[dimension] = {key: value / total for key, value in values.items()} if total else values
        _cache[region] = aggregate
        return aggregate
    path = _region_path(region)
    if not os.path.exists(path):
        avail = list_regions()
        raise FileNotFoundError(
            f"Region data not found: {region}. Available: {list(avail.keys())}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    _cache[region] = data
    logger.info(f"Loaded region: {region} ({data.get('meta', {}).get('name_en', region)})")
    return data


def reload_all():
    _cache.clear()


def validate_region_data(region):
    warnings = []
    try:
        data = load_region(region)
        meta = data.get("meta", {})
        if not meta.get("source_url"):
            warnings.append(f"Missing source_url for {region}")
        for dim in ("age", "gender", "education"):
            dist = data.get(dim, {})
            total = sum(dist.values())
            if abs(total - 1.0) > 0.05:
                warnings.append(f"Distribution sum abnormal: {region}/{dim} = {total:.3f}")
        if meta.get("data_notes", "").startswith("estimate"):
            warnings.append(f"Data precision: {region} contains estimates")
    except Exception as e:
        warnings.append(f"Load failed: {region}: {e}")
    return warnings


class RegionData:
    def __init__(self, region="china"):
        self._data = load_region(region)

    @property
    def age(self):
        return self._data["age"]

    @property
    def gender(self):
        return self._data["gender"]

    @property
    def education(self):
        return self._data.get("education", {})

    @property
    def income(self):
        return self._data.get("income", {})

    @property
    def city_tier(self):
        return self._data.get("city_tier", {})

    @property
    def meta(self):
        return self._data.get("meta", {})

    def get_distribution(self, dimension):
        return self._data.get(dimension, {})

    def all_dimensions(self):
        return {k: v for k, v in self._data.items() if k != "meta"}


_default = RegionData("china")
AGE_DISTRIBUTION = _default.age
GENDER_DISTRIBUTION = _default.gender
EDUCATION_DISTRIBUTION = _default.education
INCOME_DISTRIBUTION = _default.income
CITY_TIER_DISTRIBUTION = _default.city_tier

_builtin_warnings = validate_region_data("china")
if _builtin_warnings:
    for w in _builtin_warnings:
        logger.warning(f"Built-in data warning: {w}")
