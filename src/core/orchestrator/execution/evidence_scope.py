"""Compatibility import for the chapter evidence scope.

The implementation lives in ``src.core.evidence_scope`` so importing an agent
does not initialize the eager orchestrator package and create a cycle.
"""

from src.core.evidence_scope import EvidenceScope

__all__ = ["EvidenceScope"]
