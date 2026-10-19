"""Evidence Strength Labeler — transparent quality labeling for data points."""

from typing import Any, Dict


TIER_STRONG = {"tier1_authority", "tier2_professional"}
TIER_MODERATE = {"tier3_reputable"}
TIER_WEAK = {"tier4_general", "tier5_low_quality"}


class EvidenceStrengthLabeler:
    def label(self, data_point: Dict[str, Any]) -> Dict[str, Any]:
        """为 data_point 打 evidence_strength 标签。"""
        cred = str(data_point.get("credibility") or "").lower()
        period = str(data_point.get("period") or "").strip()
        geo = str(data_point.get("geographic_scope") or "").strip()
        unit = str(data_point.get("unit") or "").strip()
        source = str(data_point.get("source") or "").strip()

        score = 0
        reasons = []

        if cred in TIER_STRONG:
            score += 3
            reasons.append("high_credibility")
        elif cred in TIER_MODERATE:
            score += 2
            reasons.append("moderate_credibility")
        else:
            score += 1
            reasons.append("low_credibility")

        if period:
            score += 1
            reasons.append("has_period")
        else:
            reasons.append("missing_period")

        if geo:
            score += 1
            reasons.append("has_geographic_scope")
        else:
            reasons.append("missing_geographic_scope")

        if unit:
            score += 1
            reasons.append("has_unit")

        if source:
            score += 1
            reasons.append("has_source")

        if score >= 6:
            strength = "strong"
        elif score >= 4:
            strength = "moderate"
        else:
            strength = "weak"

        return {
            "evidence_strength": strength,
            "strength_score": score,
            "strength_reasons": reasons,
        }
