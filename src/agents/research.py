"""ResearchAgent - Base class for research agents.

Provides foundational functionality for research agents such as market analysis, competitive analysis, etc.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from collections import defaultdict

from src.core.agents.base import BaseAgent, AgentState


class Finding:
    """Research finding data class."""
    
    def __init__(
        self,
        finding_type: str,
        value: Any,
        confidence: float = 0.5,
        source: Optional[str] = None,
        source_tier: int = 3,
        cross_verified: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Initialize finding.
        
        Args:
            finding_type: Finding type
            value: Finding value
            confidence: Confidence (0-1)
            source: Source
            source_tier: Source tier (1-3, 1 highest)
            cross_verified: Whether cross-verified
            metadata: Metadata
        """
        self.finding_type = finding_type
        self.value = value
        self.confidence = confidence
        self.source = source
        self.source_tier = source_tier
        self.cross_verified = cross_verified
        self.metadata = metadata or {}
        self.created_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.finding_type,
            "value": self.value,
            "confidence": self.confidence,
            "source": self.source,
            "source_tier": self.source_tier,
            "cross_verified": self.cross_verified,
            "metadata": self.metadata,
            "created_at": self.created_at
        }


class CrossValidator:
    """Cross validation engine for research findings."""
    
    def __init__(self):
        self._validation_rules: Dict[str, List[Dict]] = defaultdict(list)
    
    def add_rule(
        self,
        finding_type: str,
        validation_fn: callable,
        description: str = ""
    ):
        """Add a validation rule.
        
        Args:
            finding_type: Type of finding to validate
            validation_fn: Validation function
            description: Rule description
        """
        self._validation_rules[finding_type].append({
            "fn": validation_fn,
            "description": description,
        })
    
    def validate(
        self,
        finding: Finding,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Validate a finding against applicable rules.
        
        Args:
            finding: Finding to validate
            context: Validation context
            
        Returns:
            Validation result
        """
        rules = self._validation_rules.get(finding.finding_type, [])
        if not rules:
            return {"passed": True, "checks": []}
        
        results = []
        all_passed = True
        
        for rule in rules:
            try:
                passed = rule["fn"](finding, context)
                results.append({
                    "rule": rule["description"],
                    "passed": passed,
                })
                if not passed:
                    all_passed = False
            except Exception as e:
                results.append({
                    "rule": rule["description"],
                    "passed": False,
                    "error": str(e),
                })
                all_passed = False
        
        return {
            "passed": all_passed,
            "checks": results,
        }


class ResearchAgent(BaseAgent):
    """Base class for research agents.
    
    Provides core research capabilities including data collection,
    cross-validation, and finding management.
    """
    
    def __init__(
        self,
        agent_id: str,
        storage_path: Optional[str] = None,
        name: str = "Research Agent",
    ):
        super().__init__(agent_id, storage_path=storage_path)
        self._name = name
        self._findings: List[Finding] = []
        self._validator = CrossValidator()
        self._setup_default_rules()
    
    def _setup_default_rules(self):
        """Setup default validation rules."""
        self._validator.add_rule(
            "market_size",
            lambda f, c: f.value > 0,
            "Market size must be positive",
        )
        self._validator.add_rule(
            "growth_rate",
            lambda f, c: -1 <= f.value <= 100,
            "Growth rate must be between -100% and 100%",
        )
    
    @property
    def name(self) -> str:
        """Get agent name."""
        return self._name
    
    def add_finding(
        self,
        finding_type: str,
        value: Any,
        confidence: float = 0.5,
        source: Optional[str] = None,
        source_tier: int = 3,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Finding:
        """Add a research finding.
        
        Args:
            finding_type: Finding type
            value: Finding value
            confidence: Confidence level
            source: Data source
            source_tier: Source tier
            metadata: Additional metadata
            
        Returns:
            Created finding
        """
        finding = Finding(
            finding_type=finding_type,
            value=value,
            confidence=confidence,
            source=source,
            source_tier=source_tier,
            metadata=metadata,
        )
        self._findings.append(finding)
        return finding
    
    def get_findings(
        self,
        finding_type: Optional[str] = None
    ) -> List[Finding]:
        """Get findings, optionally filtered by type."""
        if finding_type:
            return [f for f in self._findings if f.finding_type == finding_type]
        return self._findings.copy()
    
    def validate_findings(
        self,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Validate all findings.
        
        Args:
            context: Validation context
            
        Returns:
            Validation results summary
        """
        results = {}
        all_passed = True
        
        for finding in self._findings:
            result = self._validator.validate(finding, context)
            key = f"{finding.finding_type}_{id(finding)}"
            results[key] = result
            if not result["passed"]:
                all_passed = False
        
        return {
            "passed": all_passed,
            "total": len(self._findings),
            "passed_count": sum(1 for r in results.values() if r["passed"]),
            "details": results,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize agent state to dictionary."""
        return {
            "agent_id": self.agent_id,
            "name": self._name,
            "findings": [f.to_dict() for f in self._findings],
            "findings_count": len(self._findings),
        }
    
    def reset(self) -> None:
        """Reset agent state."""
        super().reset()
        self._findings.clear()