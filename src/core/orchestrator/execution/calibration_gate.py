"""
M5-a: Enhanced NumericConsistencyGate — content + data_points fixing via MetricExtractor.

Extracted from engine.py for testability. Called by engine's post-execution quality gate.
"""
import re as _re
from copy import deepcopy
from typing import Dict, List, Any


CURRENCY_RATES = {"CNY": 1.0, "HKD": 0.92, "USD": 7.25, "EUR": 7.85, "GBP": 9.15, "JPY": 0.048}
CURRENCY_CODES = frozenset(CURRENCY_RATES.keys())


def _normalize_canonical(canonical_data: dict, target_currency: str = "CNY"):
    """
    Normalize canonical data: convert non-target currencies.
    Returns (normalized_dict, conversion_log).
    """
    from src.core.data.canonical_registry import parse_entry_key

    normalized = {}
    converted = []
    for key, entry in canonical_data.items():
        entry = dict(entry)
        pk = parse_entry_key(key)
        cur = pk.get("currency", "")
        if cur and cur in CURRENCY_CODES and cur != target_currency:
            from_rate = CURRENCY_RATES.get(cur, 1.0)
            to_rate = CURRENCY_RATES.get(target_currency, 1.0)
            old_val = entry.get("value")
            if old_val is not None:
                entry["value"] = round(old_val * from_rate / to_rate, 2)
                converted.append({
                    "metric": pk["metric"],
                    "from_currency": cur,
                    "to_currency": target_currency,
                    "old_value": old_val,
                    "new_value": entry["value"],
                })
        normalized[key] = entry
    return normalized, converted


def fix_content_from_canonical(
    all_results: List[Dict],
    canonical_data: Dict,
    target_currency: str = "CNY",
) -> Dict:
    """
    M5-a: Fix content text and data_points using canonical data.
    
    Args:
        all_results: List of agent result dicts
        canonical_data: Dict of canonical entries (key → {value, unit, ...})
        target_currency: Target currency for conversion
        
    Returns:
        Dict with "all_results" (fixed copy) and "calibration_report"
    """
    from src.core.data.metric_extractor import MetricExtractor
    from src.core.data.canonical_registry import parse_entry_key

    extractor = MetricExtractor()
    en_aliases = getattr(MetricExtractor, 'ENGLISH_ALIASES', {})
    results = deepcopy(all_results)

    normalized_canonical, currency_converted = _normalize_canonical(canonical_data, target_currency)

    auto_fixed = []
    all_metrics_checked = set()

    for r in results:
        if not r.get("success"):
            continue

        content = r.get("content", "")
        if content:
            found = extractor.extract([{"content": content, "url": ""}])
            for fm in found:
                metric_name = fm["metric"]
                text_value = fm["value"]
                text_unit = fm.get("unit", "")
                all_metrics_checked.add(metric_name)

                candidates = []
                for key, entry in normalized_canonical.items():
                    pk = parse_entry_key(key)
                    if pk["metric"] != metric_name:
                        continue
                    canonical_value = entry.get("value")
                    if canonical_value is None:
                        continue
                    diff = abs(text_value - float(canonical_value)) / max(abs(float(canonical_value)), 0.01)
                    if diff > 0.05:
                        candidates.append((diff, canonical_value, entry))

                if not candidates:
                    continue
                candidates.sort(key=lambda x: -x[0])
                best_canonical = candidates[0][1]

                old_str = str(text_value)
                new_str = str(best_canonical)
                if old_str.endswith(".0"):
                    old_pattern = _re.escape(old_str[:-2]) + r'(?:\.0)?'
                else:
                    old_pattern = _re.escape(old_str)

                names = [metric_name] + en_aliases.get(metric_name, [])
                name_part = "(?:" + "|".join(_re.escape(n) for n in names) + ")"
                pattern = (
                    rf'({name_part}'
                    rf'[^\d]*?)'
                    rf'({old_pattern})'
                    rf'(\s*{_re.escape(text_unit)})'
                )

                def _skip_table(m, _n=new_str):
                    last_nl = content.rfind('\n', 0, m.start())
                    if last_nl >= 0 and content[last_nl + 1:].startswith('|'):
                        return m.group(0)
                    return m.group(1) + _n + m.group(3)

                new_content = _re.sub(pattern, _skip_table, content)
                if new_content != content:
                    auto_fixed.append({
                        "metric": metric_name,
                        "old_value": text_value,
                        "new_value": best_canonical,
                        "section": r.get("agent_id", ""),
                    })
                    content = new_content
            r["content"] = content

        for dp in r.get("data_points", []):
            dp_metric = dp.get("metric", "")
            for key, entry in normalized_canonical.items():
                pk = parse_entry_key(key)
                if pk["metric"].lower() != dp_metric.lower():
                    continue
                dp_year = str(dp.get("year", ""))
                dp_caliber = dp.get("caliber", "") or ""
                canon_year = str(pk.get("year", ""))
                canon_caliber = entry.get("caliber", "") or ""
                if canon_year and dp_year and dp_year != canon_year:
                    continue
                if canon_caliber and dp_caliber and dp_caliber != canon_caliber:
                    continue
                canon_val = entry.get("value")
                if canon_val is not None:
                    old_val = dp.get("value")
                    if old_val is not None and str(old_val) != str(canon_val):
                        dp["value"] = canon_val

    calibration_report = {
        "total_metrics_checked": len(all_metrics_checked),
        "auto_fixed": auto_fixed,
        "currency_converted": currency_converted,
        "remaining_conflicts": [],
        "canonical_summary": dict(normalized_canonical),
    }

    return {"all_results": results, "calibration_report": calibration_report}
