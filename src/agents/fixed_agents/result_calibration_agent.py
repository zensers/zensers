"""
Result Calibration Agent
========================

Used to calibrate AI simulated survey results to make them closer to real-world distribution.

Calibration methods:
1. Weighting: Assign calibration weights to each response
2. Ratio Adjustment: Directly adjust distribution ratios
3. Stratification: Redistribute by demographic strata
4. Raking: Iterative method for multi-dimensional calibration
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum
import math

from src.core.agents.base import BaseAgent
from .base_fixed_agent import FixedAgent


class CalibrationMethod(Enum):
    """Calibration method"""
    WEIGHTING = "weighting"              # Weighting method
    RATIO_ADJUSTMENT = "ratio_adjustment"  # Ratio adjustment
    STRATIFICATION = "stratification"    # Stratification method
    RAKING = "raking"                    # Iterative proportional adjustment


@dataclass
class CalibrationConfig:
    """Calibration configuration"""
    method: CalibrationMethod = CalibrationMethod.WEIGHTING
    target_distribution: Dict[str, Dict[str, float]] = field(default_factory=dict)
    confidence_level: float = 0.95
    min_sample_size: int = 30
    apply_quality_weights: bool = True
    max_weight_ratio: float = 5.0  # Max weight ratio to prevent extreme weights
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "method": self.method.value,
            "target_distribution": self.target_distribution,
            "confidence_level": self.confidence_level,
            "min_sample_size": self.min_sample_size,
            "apply_quality_weights": self.apply_quality_weights,
            "max_weight_ratio": self.max_weight_ratio,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CalibrationConfig":
        """Create from dictionary"""
        return cls(
            method=CalibrationMethod(data.get("method", "weighting")),
            target_distribution=data.get("target_distribution", {}),
            confidence_level=data.get("confidence_level", 0.95),
            min_sample_size=data.get("min_sample_size", 30),
            apply_quality_weights=data.get("apply_quality_weights", True),
            max_weight_ratio=data.get("max_weight_ratio", 5.0),
        )


@dataclass
class CalibrationReport:
    """Calibration report"""
    original_count: int
    calibrated_count: int
    calibration_weights: Dict[str, float]  # response_id -> weight
    distribution_changes: Dict[str, Dict[str, float]]  # dimension -> {before, after}
    confidence_intervals: Dict[str, Dict[str, float]]  # question_id -> {lower, upper}
    recommendations: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "original_count": self.original_count,
            "calibrated_count": self.calibrated_count,
            "calibrated_weights": self.calibration_weights,
            "distribution_changes": self.distribution_changes,
            "confidence_intervals": self.confidence_intervals,
            "recommendations": self.recommendations,
        }


class ResultCalibrationAgent(FixedAgent):
    """Result Calibration Agent
    
    Used to calibrate AI simulated survey results to make their distribution closer to real-world.
    
    Main features:
    1. Calculate difference between current and target distribution
    2. Assign calibration weights to each response
    3. Calculate confidence intervals
    4. Generate calibration report and recommendations
    
    Attributes:
        capabilities: Agent capability list
    """
    
    capabilities = [
        "Distribution calibration",
        "Weight calculation",
        "Confidence interval calculation",
        "Calibration report generation",
        "Multi-dimensional calibration",
    ]
    
    version = "1.0.0"
    
    def __init__(
        self,
        agent_id: str = "calibration_agent",
        name: str = "Result Calibration Agent",
        description: str = "Calibrate AI simulated survey results",
        config: Optional[CalibrationConfig] = None,
        **kwargs
    ):
        """Initialize Calibration Agent
        
        Args:
            agent_id: Agent unique identifier
            name: Agent name
            description: Agent description
            config: Calibration configuration
        """
        super().__init__(agent_id, name=name, description=description, **kwargs)
        self.config = config or CalibrationConfig()
    
    async def execute(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute calibration task (async)
        
        Args:
            task_input: Contains the following fields:
                - responses: SurveyResponse list
                - survey: Survey object
                - target_distribution: Target distribution
                - calibration_dimension: Calibration dimension (e.g., "age")
                
        Returns:
            Calibration results, containing:
                - success: Whether successful
                - calibrated_responses: Calibrated responses
                - calibration_report: Calibration report
        """
        # Publish start event
        await self.publish_event("calibration_started", {})
        
        # Extract input
        responses = task_input.get("responses", [])
        survey = task_input.get("survey")
        target_distribution = task_input.get("target_distribution", {})
        calibration_dimension = task_input.get("calibration_dimension", "age")
        
        # Check for empty input
        if not responses:
            return {
                "success": False,
                "error": "Response list is empty",
                "agent_id": self.agent_id,
                "agent_name": self.name,
            }
        
        # Calculate current distribution
        current_distribution = self._calculate_distribution(responses, calibration_dimension)
        
        # Calculate calibration weights
        weights = self._calculate_weights(current_distribution, target_distribution.get(calibration_dimension, {}))
        
        # Apply weights to each response
        calibration_weights = {}
        for response in responses:
            dimension_value = response.demographics.get(calibration_dimension, "unknown")
            base_weight = weights.get(dimension_value, 1.0)
            
            # Consider quality score
            if self.config.apply_quality_weights and hasattr(response, "quality_score"):
                quality_weight = response.quality_score
                final_weight = base_weight * quality_weight
            else:
                final_weight = base_weight
            
            # Limit weight range
            final_weight = max(0.1, min(self.config.max_weight_ratio, final_weight))
            calibration_weights[response.response_id] = final_weight
        
        # Apply weights
        calibrated_responses = self._apply_weights(responses, calibration_weights)
        
        # Calculate calibrated distribution
        calibrated_distribution = self._calculate_weighted_distribution(
            calibrated_responses, calibration_dimension, calibration_weights
        )
        
        # Calculate distribution changes
        distribution_changes = {
            calibration_dimension: {
                "before": current_distribution,
                "after": calibrated_distribution,
                "target": target_distribution.get(calibration_dimension, {}),
            }
        }
        
        # Calculate confidence intervals
        confidence_intervals = {}
        if survey:
            for question in survey.questions:
                distribution = self._calculate_answer_distribution(responses, survey, question.question_id)
                if distribution:
                    # Use max proportion to calculate confidence interval
                    max_proportion = max(distribution.values()) if distribution else 0.5
                    ci = self._calculate_confidence_interval(
                        max_proportion,
                        len(responses),
                        self.config.confidence_level
                    )
                    confidence_intervals[question.question_id] = ci
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            len(responses),
            self._calculate_distribution_shift(current_distribution, target_distribution.get(calibration_dimension, {})),
            sum(calibration_weights.values()) / len(calibration_weights) if calibration_weights else 1.0
        )
        
        # Create report
        report = CalibrationReport(
            original_count=len(responses),
            calibrated_count=len(calibrated_responses),
            calibration_weights=calibration_weights,
            distribution_changes=distribution_changes,
            confidence_intervals=confidence_intervals,
            recommendations=recommendations,
        )
        
        # Write to shared state
        await self.write_shared_state(f"agent.{self.agent_id}.last_calibration", {
            "original_count": len(responses),
            "calibrated_count": len(calibrated_responses),
        })
        
        # Publish completion event
        await self.publish_event("calibration_completed", {"calibrated_count": len(calibrated_responses)})
        
        return {
            "success": True,
            "calibrated_responses": calibrated_responses,
            "calibration_report": report.to_dict(),
            "agent_id": self.agent_id,
            "agent_name": self.name,
            "agent_version": self.version,
        }
    
    def validate_input(self, task_input: Dict[str, Any]) -> tuple[bool, str]:
        """Validate input parameters
        
        Args:
            task_input: Input parameters to validate
            
        Returns:
            (is_valid, error_message)
        """
        if not isinstance(task_input, dict):
            return False, "Input must be a dictionary type"
        
        if "responses" not in task_input:
            return False, "Missing responses field"
        
        responses = task_input.get("responses")
        if not isinstance(responses, list):
            return False, "responses must be a list"
        
        return True, ""
    
    def _calculate_distribution(
        self,
        responses: List[Any],
        dimension: str
    ) -> Dict[str, float]:
        """Calculate dimension distribution
        
        Args:
            responses: Response list
            dimension: Dimension name
            
        Returns:
            Distribution dictionary {dimension_value: proportion}
        """
        if not responses:
            return {}
        
        counts: Dict[str, int] = {}
        
        for response in responses:
            demographics = response.demographics or {}
            value = demographics.get(dimension, "unknown")
            counts[value] = counts.get(value, 0) + 1
        
        total = sum(counts.values())
        distribution = {k: v / total for k, v in counts.items()}
        
        return distribution
    
    def _calculate_weighted_distribution(
        self,
        responses: List[Any],
        dimension: str,
        weights: Dict[str, float]
    ) -> Dict[str, float]:
        """Calculate weighted distribution
        
        Args:
            responses: Response list
            dimension: Dimension name
            weights: Weight dictionary
            
        Returns:
            Weighted distribution dictionary
        """
        if not responses:
            return {}
        
        weighted_counts: Dict[str, float] = {}
        
        for response in responses:
            demographics = response.demographics or {}
            value = demographics.get(dimension, "unknown")
            weight = weights.get(response.response_id, 1.0)
            weighted_counts[value] = weighted_counts.get(value, 0) + weight
        
        total_weight = sum(weighted_counts.values())
        if total_weight == 0:
            return {}
        
        distribution = {k: v / total_weight for k, v in weighted_counts.items()}
        
        return distribution
    
    def _calculate_answer_distribution(
        self,
        responses: List[Any],
        survey: Any,
        question_id: str
    ) -> Dict[str, float]:
        """Calculate answer distribution
        
        Args:
            responses: Response list
            survey: Survey
            question_id: Question ID
            
        Returns:
            Answer distribution dictionary
        """
        if not responses:
            return {}
        
        counts: Dict[str, int] = {}
        
        for response in responses:
            answer = response.answers.get(question_id)
            if answer:
                value = answer.answer_value
                counts[value] = counts.get(value, 0) + 1
        
        total = sum(counts.values())
        if total == 0:
            return {}
        
        distribution = {k: v / total for k, v in counts.items()}
        
        return distribution
    
    def _calculate_weights(
        self,
        current_distribution: Dict[str, float],
        target_distribution: Dict[str, float]
    ) -> Dict[str, float]:
        """Calculate calibration weights
        
        Args:
            current_distribution: Current distribution
            target_distribution: Target distribution
            
        Returns:
            Weight dictionary {dimension_value: weight}
        """
        weights = {}
        
        for key, current_prop in current_distribution.items():
            target_prop = target_distribution.get(key, current_prop)
            
            if current_prop > 0:
                weight = target_prop / current_prop
            else:
                weight = 1.0
            
            # Limit weight range
            weight = max(0.1, min(self.config.max_weight_ratio, weight))
            weights[key] = weight
        
        return weights
    
    def _apply_weights(
        self,
        responses: List[Any],
        weights: Dict[str, float]
    ) -> List[Any]:
        """Apply weights to responses
        
        Args:
            responses: Response list
            weights: Weight dictionary
            
        Returns:
            Weighted response list
        """
        calibrated = []
        
        for response in responses:
            weight = weights.get(response.response_id, 1.0)
            
            # Create new response copy (with weight)
            # Note: Here we modify metadata to store weight
            if hasattr(response, "metadata"):
                response.metadata["calibration_weight"] = weight
            else:
                # If no metadata attribute, use quality_score
                response.quality_score = weight
            
            calibrated.append(response)
        
        return calibrated
    
    def _calculate_confidence_interval(
        self,
        proportion: float,
        sample_size: int,
        confidence_level: float = 0.95
    ) -> Dict[str, float]:
        """Calculate confidence interval
        
        Args:
            proportion: Sample proportion
            sample_size: Sample size
            confidence_level: Confidence level
            
        Returns:
            Confidence interval dictionary {lower, upper}
        """
        if sample_size <= 0:
            return {"lower": 0.0, "upper": 1.0}
        
        # Standard error
        se = math.sqrt(proportion * (1 - proportion) / sample_size)
        
        # Z-value (1.96 for 95% confidence level)
        z_values = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}
        z = z_values.get(confidence_level, 1.96)
        
        # Confidence interval
        lower = max(0.0, proportion - z * se)
        upper = min(1.0, proportion + z * se)
        
        return {"lower": lower, "upper": upper}
    
    def _calculate_distribution_shift(
        self,
        current: Dict[str, float],
        target: Dict[str, float]
    ) -> float:
        """Calculate distribution shift degree
        
        Args:
            current: Current distribution
            target: Target distribution
            
        Returns:
            Shift degree (0-1)
        """
        if not current or not target:
            return 0.0
        
        # Calculate difference for each dimension
        total_diff = 0.0
        common_keys = set(current.keys()) & set(target.keys())
        
        for key in common_keys:
            diff = abs(current.get(key, 0) - target.get(key, 0))
            total_diff += diff
        
        # Average difference
        shift = total_diff / max(len(common_keys), 1)
        
        return shift
    
    def _generate_recommendations(
        self,
        sample_size: int,
        distribution_shift: float,
        avg_weight: float
    ) -> List[str]:
        """Generate calibration recommendations
        
        Args:
            sample_size: Sample size
            distribution_shift: Distribution shift degree
            avg_weight: Average weight
            
        Returns:
            List of recommendations
        """
        recommendations = []
        
        # Sample size recommendation
        if sample_size < self.config.min_sample_size:
            recommendations.append(f"Sample size ({sample_size}) is below recommended minimum ({self.config.min_sample_size}), suggest increasing sample")
        
        # Distribution shift recommendation
        if distribution_shift > 0.3:
            recommendations.append("Current distribution differs significantly from target, interpret calibrated results with caution")
        elif distribution_shift > 0.1:
            recommendations.append("Distribution has some difference, calibration can improve representativeness")
        
        # Weight recommendation
        if avg_weight > 2.0 or avg_weight < 0.5:
            recommendations.append("Calibration weights deviate significantly, some groups may have insufficient samples")
        
        # Default recommendation
        if not recommendations:
            recommendations.append("Calibrated results are reasonable and can be used for analysis")
        
        return recommendations
