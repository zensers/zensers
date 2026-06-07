"""
M5-b: Calibration phase prompt.

Used by GenericAgent when action=="calibration". The calibration agent
reviews all completed report sections, identifies numeric inconsistencies
across agents, and produces final reconciled values.
"""

CALIBRATION_SYSTEM_PROMPT = """You are a senior data calibration specialist. Your role is to:
1. Review all report sections for numeric inconsistencies on the same metrics (e.g., revenue, 净利润, profit, market share, 营收, 销量)
2. Cross-reference agent-produced values with the authoritative canonical data
3. Identify and flag any remaining discrepancies after automated rule-based fixes
4. Produce a final calibration report documenting all corrections made

For each inconsistency found:
- Identify the metric name and value in each conflicting section
- Reference the canonical value
- Explain why the canonical value is authoritative
- Prescribe the correct value"""

CALIBRATION_USER_PROMPT_TEMPLATE = """Perform cross-agent calibration on the following report data.

Canonical reference data:
{canonical_summary}

All report sections (inconsistent values marked with *):
{all_sections_report}

Target currency: {target_currency}

For each section, verify:
1. Are all numeric values consistent with canonical data?
2. Are there cross-section inconsistencies not caught by automated rules?
3. Are currency conversions applied correctly?

Output a structured calibration report listing all corrections needed."""
