"""
CanonicalDataRegistry — authoritative data dictionary for the entire report (S-FIX-1)

All agents must reference this registry for core metrics instead of extracting
from raw search results independently.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
# NOTE: ConflictRecord/ConflictResolution imported lazily in register()
# to break circular import: generic_agent → canonical_registry → result_aggregator → orchestrator → factory → generic_agent


@dataclass
class CanonicalDataEntry:
    """A single canonical data point with caliber information."""
    metric: str
    value: float
    unit: str = ""
    currency: str = ""  # CNY / HKD / USD / EUR / GBP / JPY
    caliber: str = ""
    year: str = ""
    source: str = ""
    confidence: float = 0.5
    # Scope fields are part of the identity of a metric.  They are optional
    # for backwards compatibility with older callers, but must be preserved
    # whenever the extractor/evidence layer provides them.
    period: str = ""
    geographic_scope: str = ""
    population: str = ""
    statistical_object: str = ""
    source_url: str = ""
    evidence_id: str = ""
    provenance_id: str = ""
    alternative_values: List[Dict] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)


def _entry_key(entry: CanonicalDataEntry) -> str:
    """Registry key: metric + year + currency + caliber (accounting standard).
    Ensures values using different currencies or accounting standards do not falsely conflict.
    e.g. 净利润_2025_CNY_A股口径 ≠ 净利润_2025_HKD_港股口径 ≠ 净利润_2025_CNY_港股口径
    """
    parts = [entry.metric, str(entry.year)]
    if entry.currency:
        parts.append(entry.currency)
    if entry.caliber:
        parts.append(entry.caliber.replace("口径", "").strip()[:10])
    # Keep the historical key stable when no scope identity is available.
    # This avoids breaking existing callers while preventing scoped values
    # from being merged when those fields are present.
    scope = {
        "period": entry.period,
        "geo": entry.geographic_scope,
        "population": entry.population or entry.statistical_object,
        "unit": entry.unit,
        "evidence": entry.evidence_id,
        "provenance": entry.provenance_id,
        # ``source`` is the authority used to resolve conflicts, not an
        # identity dimension.  Keep same-metric values from different source
        # records in the same conflict bucket unless a canonical URL/evidence
        # identity is explicitly available.
    }
    # Evidence/provenance IDs are stable identities. A source URL is evidence
    # provenance, not metric identity: different URLs must still enter the
    # same conflict bucket when metric scope is otherwise identical.
    for label, value in scope.items():
        value = str(value or "").strip()
        if value:
            # Keys are persisted in JSON and used for lookup only; replacing
            # separators keeps the scope suffix unambiguous and readable.
            safe_value = value.replace("|", "/").replace("_", "-")
            parts.append(f"{label}={safe_value}")
    return "_".join(parts)


_CURRENCY_CODES = frozenset({"CNY", "HKD", "USD", "EUR", "GBP", "JPY"})


def parse_entry_key(key: str) -> dict:
    parts = key.split("_")
    result = {
        "metric": "", "year": "", "currency": "", "caliber": "",
        "period": "", "geographic_scope": "", "population": "",
        "statistical_object": "", "unit": "",
        "evidence_id": "", "provenance_id": "", "source_url": "",
    }

    # Scope values are appended as label=value segments by _entry_key().
    # Parse them first, then parse the historical metric/year suffix.
    base_parts = []
    for part in parts:
        if "=" in part:
            label, value = part.split("=", 1)
            field = {
                "geo": "geographic_scope",
                "source": "source_url",
                "evidence": "evidence_id",
                "provenance": "provenance_id",
            }.get(label, label)
            if field in result:
                result[field] = value
                continue
        base_parts.append(part)
    parts = base_parts

    if not parts:
        return result

    cur_idx = -1
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] in _CURRENCY_CODES:
            cur_idx = i
            break

    if cur_idx >= 0:
        result["currency"] = parts[cur_idx]
        if cur_idx + 1 < len(parts):
            result["caliber"] = "_".join(parts[cur_idx + 1:])
        if cur_idx >= 1 and parts[cur_idx - 1].isdigit():
            result["year"] = parts[cur_idx - 1]
            result["metric"] = "_".join(parts[:cur_idx - 1])
        else:
            result["metric"] = "_".join(parts[:cur_idx])
    else:
        yr_idx = -1
        for i in range(len(parts) - 1, -1, -1):
            if parts[i].isdigit():
                yr_idx = i
                break
        if yr_idx >= 0:
            result["year"] = parts[yr_idx]
            result["metric"] = "_".join(parts[:yr_idx])
        else:
            result["metric"] = key

    return result


class CanonicalDataRegistry:
    """
    Report-wide authoritative data dictionary.
    
    All agents read from this registry; conflicts are resolved by
    source authority via CaliberDecisionEngine.
    """
    
    def __init__(self):
        self._data: Dict[str, CanonicalDataEntry] = {}
        self._conflicts: list = []
        self._lock = asyncio.Lock()
    
    async def register(self, entry: CanonicalDataEntry) -> "Optional[ConflictRecord]":
        """Register a data point. Conflicts resolved by source authority (高权威值优先).
        Returns ConflictRecord with resolution details if conflict occurred.
        Key includes currency to distinguish e.g. CNY326 vs HKD520.
        """
        # Lazy import to break circular chain: generic_agent→canonical_registry→result_aggregator→...
        from src.core.orchestrator.aggregation.result_aggregator import ConflictRecord, ConflictResolution
        
        conflict = None
        async with self._lock:
            key = _entry_key(entry)
            existing = self._data.get(key)
            if existing and existing.source != entry.source:
                diff = abs(existing.value - entry.value) / max(abs(entry.value), 0.01)
                if diff > 0.05:
                    # Use CaliberDecisionEngine to pick the authoritative value
                    from src.core.data.caliber_decision import CaliberDecisionEngine
                    decider = CaliberDecisionEngine()
                    decision = decider.decide(key, [
                        {"value": existing.value, "source": existing.source,
                         "caliber": existing.caliber, "confidence": existing.confidence},
                        {"value": entry.value, "source": entry.source,
                         "caliber": entry.caliber, "confidence": entry.confidence},
                    ])
                    winner, loser = (entry, existing) if decision["value"] == entry.value else (existing, entry)
                    
                    conflict = ConflictRecord(
                        key=key,
                        values=[existing.value, entry.value],
                        sources=[existing.source, entry.source],
                        resolution=ConflictResolution.AUTO,
                        resolved_value=decision["value"],
                    )
                    self._conflicts.append(conflict)
                    winner.alternative_values.append({"value": loser.value, "source": loser.source})
                    self._data[key] = winner
                    return conflict
            self._data[key] = entry
        return conflict
    
    async def get(
        self,
        metric: str,
        year: str = "",
        currency: str = "",
        caliber: str = "",
        period: str = "",
        geographic_scope: str = "",
        population: str = "",
        statistical_object: str = "",
        unit: str = "",
        source_url: str = "",
        evidence_id: str = "",
        provenance_id: str = "",
    ) -> Optional[CanonicalDataEntry]:
        """Get the authoritative value for a metric. Specify currency/caliber for multi-market data.
        Key construction matches _entry_key(): metric_year_currency_caliber.
        """
        parts = [metric]
        if year:
            parts.append(str(year))
        if currency:
            parts.append(currency)
        if caliber:
            parts.append(caliber.replace("口径", "").strip()[:10])
        scope = {
            "period": period,
            "geo": geographic_scope,
            "population": population or statistical_object,
            "unit": unit,
            "evidence": evidence_id,
            "provenance": provenance_id,
        }
        for label, value in scope.items():
            value = str(value or "").strip()
            if value:
                parts.append(f"{label}={value.replace('|', '/').replace('_', '-')}")
        key = "_".join(parts)
        async with self._lock:
            return self._data.get(key)
    
    def get_all(self) -> Dict[str, CanonicalDataEntry]:
        """Get all registered entries."""
        return dict(self._data)
    
    def get_conflicts(self) -> "List[ConflictRecord]":
        """Get all conflict records."""
        from src.core.orchestrator.aggregation.result_aggregator import ConflictRecord
        return list(self._conflicts)

    def validate_section(self, section_content: str, section_data_points: List[Dict]) -> List[str]:
        """Validate a section's data points against registered canonical values."""
        import re
        errors = []
        
        for dp in section_data_points:
            metric = dp.get("metric", "")
            value = dp.get("value", "")
            unit = dp.get("unit", "")
            dp_year = dp.get("year", "")
            dp_caliber = dp.get("caliber", "") or ""
            
            if not metric or not value:
                continue
            
            try:
                val = float(re.sub(r'[^\d.\-]', '', str(value)))
            except (ValueError, TypeError):
                continue
            
            for key, entry in self._data.items():
                if dp_year and entry.year and str(dp_year) != str(entry.year):
                    continue
                if dp_caliber and entry.caliber and dp_caliber != (entry.caliber or ""):
                    continue
                
                if entry.metric.lower() in metric.lower() or metric.lower() in entry.metric.lower():
                    diff = abs(entry.value - val) / max(abs(entry.value), 0.01)
                    if diff > 0.05:
                        errors.append(
                            f"数据冲突: '{metric}={val}{unit}' 与规范数据 '{entry.metric}={entry.value}{entry.unit}' "
                            f"不一致（差异{diff*100:.1f}%），请核实口径是否一致"
                        )
        
        for key, entry in self._data.items():
            patterns = [
                rf'{entry.metric}[：:]\s*(\d+[\.\d]*)\s*{re.escape(entry.unit) if entry.unit else ""}',
            ]
            for pattern in patterns:
                for match in re.finditer(pattern, section_content):
                    window = section_content[max(0, match.start()-20):match.end()+20]
                    years_in_window = re.findall(r'(20\d{2})', window)
                    if entry.year and years_in_window and str(entry.year) not in years_in_window:
                        continue
                    
                    all_calibers = set()
                    for _k, _e in self._data.items():
                        if _e.caliber:
                            all_calibers.add(_e.caliber)
                    text_caliber = [ci for ci in all_calibers if ci in window]
                    entry_caliber = [ci for ci in all_calibers if ci in (entry.caliber or "")]
                    if text_caliber and entry_caliber and set(text_caliber) != set(entry_caliber):
                        continue
                    
                    try:
                        text_val = float(match.group(1))
                        diff = abs(entry.value - text_val) / max(abs(entry.value), 0.01)
                        if diff > 0.05:
                            errors.append(
                                f"文本数据冲突: 找到 '{entry.metric}={text_val}{entry.unit}' "
                                f"但规范值为 '{entry.value}{entry.unit}'（差异{diff*100:.1f}%），请核实口径是否一致"
                            )
                    except (ValueError, IndexError):
                        continue
        
        return errors
