"""
Distribution Alignment Engine

Resamples generated persona sets to match target distributions across key
demographic dimensions. Uses a two-stage algorithm:
1. Importance Sampling -- compute weights
2. Stratified Sampling -- ensure per-stratum representativeness

Data source: engine/data/regions/{region}.json (multi-region file-based storage)
"""

import logging
import random
from collections import defaultdict
from typing import Dict, Any, List, Optional, Tuple, Callable

from .persona_models import PersonaV2, PersonaType
from .data import RegionData, list_regions, load_region

logger = logging.getLogger(__name__)


class DistributionAligner:
    """Persona distribution alignment engine (multi-region support)"""

    # City tier classification rules (estimated by permanent resident
    # population, China-only)
    _CHINA_CITY_TIERS: Dict[str, str] = {
        "Beijing": "Tier-1", "Shanghai": "Tier-1", "Guangzhou": "Tier-1", "Shenzhen": "Tier-1",
        "Chengdu": "New-Tier-1", "Hangzhou": "New-Tier-1", "Chongqing": "New-Tier-1", "Wuhan": "New-Tier-1",
        "Xi'an": "New-Tier-1", "Nanjing": "New-Tier-1", "Changsha": "New-Tier-1", "Suzhou": "New-Tier-1",
        "Tianjin": "New-Tier-1", "Zhengzhou": "New-Tier-1", "Dongguan": "New-Tier-1", "Qingdao": "New-Tier-1",
        "Hefei": "New-Tier-1", "Foshan": "New-Tier-1",
        "Shaoxing": "Tier-2", "Jiaxing": "Tier-2", "Changzhou": "Tier-2", "Wenzhou": "Tier-2",
        "Nanchang": "Tier-2", "Kunming": "Tier-2", "Dalian": "Tier-2", "Xiamen": "Tier-2",
        "Jinan": "Tier-2", "Fuzhou": "Tier-2", "Nanning": "Tier-2", "Guiyang": "Tier-2",
        "Taiyuan": "Tier-2", "Shenyang": "Tier-2", "Harbin": "Tier-2", "Changchun": "Tier-2",
        "Shijiazhuang": "Tier-2",
        "Baoding": "Tier-3", "Linyi": "Tier-3", "Luoyang": "Tier-3", "Zunyi": "Tier-3",
        "Jingzhou": "Tier-3", "Mianyang": "Tier-3", "Ganzhou": "Tier-3", "Wuhu": "Tier-3",
        "Yueyang": "Tier-3", "Qujing": "Tier-3",
        "Hong Kong": "Tier-1",
    }

    def __init__(
        self,
        region: str = "china",
        custom_classifier: Optional[Dict[str, str]] = None,
    ):
        """
        Args:
            region: Region identifier (china / us / eu / global)
            custom_classifier: Custom city classifier {city_name: tier_label}
        """
        self._region = region
        self._target_distributions: Dict[str, Dict] = {}
        self._city_classifier = custom_classifier or self._CHINA_CITY_TIERS
        self._load_region_data()

    def _load_region_data(self):
        """Load region data from file."""
        rd = RegionData(self._region)
        self._target_distributions = rd.all_dimensions()
        logger.info(
            f"Alignment engine loaded region: {self._region} "
            f"({rd.meta.get('name_en', self._region)}), "
            f"dimensions: {list(self._target_distributions.keys())}"
        )

    def set_region(self, region: str):
        """Switch target region."""
        self._region = region
        self._load_region_data()

    @classmethod
    def list_available_regions(cls) -> Dict[str, str]:
        """List all available regions."""
        return list_regions()

    def set_target(self, dimension: str, distribution: Dict) -> None:
        """Set target distribution for a specific dimension."""
        self._target_distributions[dimension] = distribution

    # ------------------------------------------------------------------ #
    # Main entry
    # ------------------------------------------------------------------ #
    def align(
        self,
        personas: List[PersonaV2],
        dimensions: Optional[List[str]] = None,
        target_size: Optional[int] = None,
    ) -> List[PersonaV2]:
        """
        Align persona set distribution.

        Args:
            personas: Original persona list
            dimensions: Dimensions to align (default: ["age", "gender", "city_tier"])
            target_size: Target sample size (None = keep original count)

        Returns:
            Aligned persona list
        """
        if not personas:
            return []

        if dimensions is None:
            dimensions = ["age", "gender", "city_tier"]

        target_size = target_size or len(personas)

        # Compute weights
        weights = self._compute_weights(personas, dimensions)

        # Weighted stratified sampling
        aligned = self._stratified_sample(personas, weights, target_size, dimensions)

        logger.info(
            f"Distribution alignment: {len(personas)}->{len(aligned)}, "
            f"dimensions={dimensions}"
        )

        return aligned

    # ------------------------------------------------------------------ #
    # Weight computation
    # ------------------------------------------------------------------ #
    def _compute_weights(
        self,
        personas: List[PersonaV2],
        dimensions: List[str],
    ) -> List[float]:
        """Compute composite weight for each persona."""
        weights = []

        for p in personas:
            prob = 1.0
            for dim in dimensions:
                target = self._target_distributions.get(dim)
                if not target:
                    continue
                group = self._classify(p, dim)
                expected = target.get(group, 0)
                if expected > 0:
                    prob *= expected
            weights.append(prob)

        # Normalize
        total = sum(weights)
        if total > 0:
            weights = [w / total for w in weights]

        return weights

    def _classify(self, persona: PersonaV2, dimension: str) -> str:
        """Classify a persona into a distribution group."""
        # Age -- infer group boundaries from target distribution keys
        if dimension == "age":
            age = persona.age
            best_key = "other"
            best_dist = 999
            for key in self._target_distributions.get("age", {}):
                parts = key.split("_")
                if len(parts) >= 2:
                    try:
                        lo, hi = int(parts[0]), int(parts[1])
                        if lo <= age <= hi:
                            return key
                        dist = min(abs(age - lo), abs(age - hi))
                        if dist < best_dist:
                            best_dist = dist
                            best_key = key
                    except ValueError:
                        continue
            return best_key

        if dimension == "gender":
            return persona.gender if persona.gender in self._target_distributions.get("gender", {}) else "other"

        if dimension == "city_tier":
            return self._city_classifier.get(
                persona.city,
                list(self._target_distributions.get("city_tier", {}).keys())[-1]
            )

        if dimension == "education":
            return (
                persona.education
                if persona.education in self._target_distributions.get("education", {})
                else list(self._target_distributions.get("education", {}).keys())[0]
            )

        if dimension == "income":
            return (
                persona.income
                if persona.income in self._target_distributions.get("income", {})
                else list(self._target_distributions.get("income", {}).keys())[0]
            )

        return "other"

    # ------------------------------------------------------------------ #
    # Stratified sampling
    # ------------------------------------------------------------------ #
    def _stratified_sample(
        self,
        personas: List[PersonaV2],
        weights: List[float],
        target_size: int,
        dimensions: List[str],
    ) -> List[PersonaV2]:
        """Stratified weighted sampling."""
        if not personas:
            return []

        main_dim = dimensions[0] if dimensions else "age"
        strata: Dict[str, List[Tuple[PersonaV2, float]]] = defaultdict(list)

        for p, w in zip(personas, weights):
            group = self._classify(p, main_dim)
            strata[group].append((p, w))

        result: List[PersonaV2] = []
        target_dist = self._target_distributions.get(main_dim, {})

        for group, items in strata.items():
            # Get expected proportion from target distribution
            expected_pct = target_dist.get(group, 0.0)
            group_target = max(1, int(target_size * expected_pct))

            if len(items) <= group_target:
                result.extend(p for p, _ in items)
            else:
                # Take top N by weight descending
                items.sort(key=lambda x: x[1], reverse=True)
                result.extend(p for p, _ in items[:group_target])

        # If result is short, randomly fill from original list
        if len(result) < target_size:
            needed = target_size - len(result)
            pool = [p for p in personas if p not in result]
            result.extend(random.sample(pool, min(needed, len(pool))))

        return result[:target_size]

    # ------------------------------------------------------------------ #
    # Distribution report
    # ------------------------------------------------------------------ #
    def get_distribution_report(
        self, personas: List[PersonaV2]
    ) -> Dict[str, Any]:
        """Generate a distribution report for a persona set."""
        if not personas:
            return {}

        report = {}
        for dim in ("age", "gender", "city_tier", "education"):
            counter: Dict[str, int] = defaultdict(int)
            for p in personas:
                counter[self._classify(p, dim)] += 1
            total = len(personas)
            report[dim] = {
                k: {"count": v, "pct": round(v / total * 100, 1)}
                for k, v in sorted(counter.items())
            }

        return report
