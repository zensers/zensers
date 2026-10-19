"""Pytest collection policy for legacy standalone verification scripts.

These files execute assertions at import time and call ``sys.exit`` because
they are command-line verification scripts, not pytest modules.  Importing
them during collection aborts the entire suite before pytest can report test
results.  They remain runnable directly with Python.
"""

collect_ignore = [
    "test_profitability_bug_fix.py",
    "test_profitability_bug_fix_v2.py",
    # Standalone verification scripts: they execute at import time and are
    # validated explicitly in the audit plan instead of as pytest modules.
    "test_phase3.py",
    "test_quality_scoring.py",
    "test_regions.py",
    "test_e2e.py",
]
