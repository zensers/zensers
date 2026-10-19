"""
CaliberDecisionEngine — automatic conflict resolution by source authority (G4-FIX-1)

When the same metric has multiple candidate values in CanonicalDataRegistry,
this engine selects the authoritative one based on source priority.

Priority chain: audit/annual > official announcement > analyst > news > forecast
"""

from typing import Dict, List


class CaliberDecisionEngine:
    """Resolve data conflicts by source authority scoring."""

    SOURCE_PRIORITY = {
        "年报": 100, "annual": 100, "10-K": 100, "10-Q": 100,
        "审计": 100, "audit": 100, "财报": 100, "financial statement": 100,
        "公告": 90, "招股": 90, "prospectus": 90, "官方": 85, "official": 85,
        "Bloomberg": 80, "Reuters": 80, "彭博": 80, "路透": 80,
        "研报": 70, "券商": 70, "research": 70, "brokerage": 70,
        "行业协会": 60, "乘联会": 60, "industry": 60,
        "新闻": 50, "报道": 50, "news": 50,
        "预测": 30, "预计": 30, "forecast": 30, "estimate": 30,
    }
    CALIBER_PRIORITY = {
        "审计口径": 100, "A股口径": 90, "港股口径": 80,
        "合并口径": 80, "GAAP口径": 75, "IFRS口径": 75,
        "含少数股东权益": 70, "不含少数股东权益": 70,
    }

    def decide(self, metric: str, candidates: List[Dict]) -> Dict:
        """Score candidates and return the winner with rejection reasons."""
        if not candidates:
            return {"metric": metric, "value": None, "decision_score": 0,
                    "rejected": []}
        scored = []
        for c in candidates:
            ss = self._source_score(c.get("source", ""))
            cs = self._caliber_score(c.get("caliber", ""))
            conf = c.get("confidence", 0.5)
            scored.append((ss * 0.5 + cs * 0.3 + conf * 20, c))
        scored.sort(key=lambda x: -x[0])
        best = scored[0][1]
        return {
            "metric": metric,
            "value": best["value"],
            "unit": best.get("unit", ""),
            "caliber": best.get("caliber", ""),
            "source": best.get("source", ""),
            "decision_score": scored[0][0],
            "rejected": [
                {"value": r["value"], "source": r.get("source", ""),
                 "reason": f"score={s:.1f} < winner={scored[0][0]:.1f}"}
                for s, r in scored[1:]
            ],
        }

    def _source_score(self, source: str) -> float:
        src_l = source.lower()
        best, best_len = 10, 0
        for kw, score in self.SOURCE_PRIORITY.items():
            kw_l = kw.lower()
            if kw_l in src_l and len(kw_l) > best_len:
                best, best_len = score, len(kw_l)
        return best

    def _caliber_score(self, caliber: str) -> float:
        cal_l = caliber.lower()
        best, best_len = 50, 0
        for kw, score in self.CALIBER_PRIORITY.items():
            kw_l = kw.lower()
            if kw_l and kw_l in cal_l and len(kw_l) > best_len:
                best, best_len = score, len(kw_l)
        return best
