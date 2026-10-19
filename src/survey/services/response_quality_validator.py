"""
Response Quality Validator
=============

Used to validate survey response quality, identify various quality issues, and calculate quality scores.

Quality Issue Types:
1. Straight-line: All single-choice answers are the same
2. Speeder: Response time too short
3. Incomplete: Missing required questions
4. Inconsistent: Logical contradictions
5. Nonsense text: Open-ended question responses are meaningless
6. Pattern response: Obvious answer patterns
7. Logic error: Violates survey logic rules
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
import re
import statistics


class QualityIssueType(Enum):
    """Quality Issue Type"""
    STRAIGHT_LINE = "straight_line"
    SPEEDER = "speeder"
    INCOMPLETE = "incomplete"
    INCONSISTENT = "inconsistent"
    NONSENSE_TEXT = "nonsense_text"
    PATTERN_RESPONSE = "pattern_response"
    LOGIC_ERROR = "logic_error"


@dataclass
class QualityIssue:
    """Quality Issue"""
    issue_type: QualityIssueType
    severity: str                         # high, medium, low
    description: str
    affected_questions: List[str]
    confidence: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "issue_type": self.issue_type.value,
            "severity": self.severity,
            "description": self.description,
            "affected_questions": self.affected_questions,
            "confidence": self.confidence,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QualityIssue":
        """Create from dictionary"""
        return cls(
            issue_type=QualityIssueType(data["issue_type"]),
            severity=data["severity"],
            description=data["description"],
            affected_questions=data["affected_questions"],
            confidence=data.get("confidence", 1.0),
        )


@dataclass
class QualityReport:
    """Quality Report"""
    response_id: str
    quality_score: float
    is_valid: bool
    issues: List[QualityIssue] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "response_id": self.response_id,
            "quality_score": self.quality_score,
            "is_valid": self.is_valid,
            "issues": [issue.to_dict() for issue in self.issues],
            "recommendations": self.recommendations,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QualityReport":
        """Create from dictionary"""
        return cls(
            response_id=data["response_id"],
            quality_score=data["quality_score"],
            is_valid=data["is_valid"],
            issues=[QualityIssue.from_dict(i) for i in data.get("issues", [])],
            recommendations=data.get("recommendations", []),
        )


class ResponseQualityValidator:
    """Response Quality Validator

    Validates individual or batch response quality, identifies various quality issues, calculates quality scores.

    Attributes:
        min_duration_seconds: Minimum response time (seconds)
        max_duration_seconds: Maximum response time (seconds)
        straight_line_threshold: Straight-line response threshold (proportion of identical single-choice answers)
        min_quality_score: Minimum quality score threshold
        nonsense_patterns: Nonsense text patterns
    """
    
    # Nonsense text patterns
    NONSENSE_PATTERNS = [
        r'^[a-zA-Z]{5,}$',           # Pure letters
        r'^[0-9]{5,}$',              # Pure digits
        r'^[asdfghjkl]{5,}$',        # Keyboard mashing
        r'^.{1,3}$',                 # Too short
        r'^[\.\,\-\_]+$',            # Pure symbols
        r'(ok|yes|good|right|fine|sure){3,}',  # Repeated words
    ]
    
    # Severity weights
    SEVERITY_WEIGHTS = {
        "high": 0.3,
        "medium": 0.15,
        "low": 0.05,
    }
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize validator

        Args:
            config: Configuration dict, optional parameters:
                - min_duration_seconds: Minimum response time
                - max_duration_seconds: Maximum response time
                - straight_line_threshold: Straight-line response threshold
                - min_quality_score: Minimum quality score
        """
        config = config or {}
        
        self.min_duration_seconds = config.get("min_duration_seconds", 30)
        self.max_duration_seconds = config.get("max_duration_seconds", 1800)
        self.straight_line_threshold = config.get("straight_line_threshold", 0.7)
        self.min_quality_score = config.get("min_quality_score", 0.5)
    
    def validate_response(
        self,
        response: Any,
        survey: Any
    ) -> QualityReport:
        """Validate a single response

        Args:
            response: SurveyResponse object
            survey: Survey object

        Returns:
            QualityReport
        """
        issues: List[QualityIssue] = []
        
        # 1. Detect speeder
        speeder_issue = self._detect_speeder(response)
        if speeder_issue:
            issues.append(speeder_issue)
        
        # 2. Detect incomplete response
        incomplete_issue = self._detect_incomplete(response, survey)
        if incomplete_issue:
            issues.append(incomplete_issue)
        
        # 3. Detect straight-line response
        straight_line_issue = self._detect_straight_line(response, survey)
        if straight_line_issue:
            issues.append(straight_line_issue)
        
        # 4. Detect nonsense text
        nonsense_issue = self._detect_nonsense_text(response, survey)
        if nonsense_issue:
            issues.append(nonsense_issue)
        
        # 5. Detect pattern response
        pattern_issue = self._detect_pattern_response(response, survey)
        if pattern_issue:
            issues.append(pattern_issue)
        
        # Calculate quality score
        quality_score = self._calculate_quality_score(issues)
        
        # Determine validity
        is_valid = quality_score >= self.min_quality_score
        
        # Generate recommendations
        recommendations = self._generate_recommendations(issues)
        
        return QualityReport(
            response_id=response.response_id,
            quality_score=quality_score,
            is_valid=is_valid,
            issues=issues,
            recommendations=recommendations,
        )
    
    def validate_batch(
        self,
        responses: List[Any],
        survey: Any
    ) -> List[QualityReport]:
        """Validate batch responses

        Args:
            responses: List of SurveyResponse objects
            survey: Survey object

        Returns:
            List of QualityReport
        """
        return [
            self.validate_response(response, survey)
            for response in responses
        ]
    
    def filter_valid_responses(
        self,
        responses: List[Any],
        survey: Any
    ) -> Tuple[List[Any], List[Any]]:
        """Filter valid responses

        Args:
            responses: List of SurveyResponse objects
            survey: Survey object

        Returns:
            (valid responses list, invalid responses list)
        """
        reports = self.validate_batch(responses, survey)
        
        valid_responses = []
        invalid_responses = []
        
        for i, report in enumerate(reports):
            if report.is_valid:
                valid_responses.append(responses[i])
            else:
                invalid_responses.append(responses[i])
        
        return valid_responses, invalid_responses
    
    def get_quality_statistics(
        self,
        reports: List[QualityReport]
    ) -> Dict[str, Any]:
        """Get quality statistics

        Args:
            reports: List of QualityReport

        Returns:
            Statistics dictionary
        """
        if not reports:
            return {
                "total_count": 0,
                "valid_count": 0,
                "invalid_count": 0,
                "avg_quality_score": 0.0,
                "issue_distribution": {},
            }
        
        total_count = len(reports)
        valid_count = sum(1 for r in reports if r.is_valid)
        invalid_count = total_count - valid_count
        
        # Calculate average quality score
        quality_scores = [r.quality_score for r in reports]
        avg_quality_score = statistics.mean(quality_scores) if quality_scores else 0.0
        
        # Issue distribution statistics
        issue_distribution: Dict[str, int] = {}
        for report in reports:
            for issue in report.issues:
                issue_type = issue.issue_type.value
                issue_distribution[issue_type] = issue_distribution.get(issue_type, 0) + 1
        
        return {
            "total_count": total_count,
            "valid_count": valid_count,
            "invalid_count": invalid_count,
            "avg_quality_score": avg_quality_score,
            "min_quality_score": min(quality_scores) if quality_scores else 0.0,
            "max_quality_score": max(quality_scores) if quality_scores else 0.0,
            "issue_distribution": issue_distribution,
        }
    
    def _detect_speeder(self, response: Any) -> Optional[QualityIssue]:
        """Detect speeder"""
        duration = response.duration_seconds
        
        if duration < self.min_duration_seconds:
            # Severity grading
            # Below 10 seconds: high severity, below 20 seconds: medium severity, otherwise: low severity
            if duration < 10:
                severity = "high"
            elif duration < 20:
                severity = "medium"
            else:
                severity = "low"
            
            return QualityIssue(
                issue_type=QualityIssueType.SPEEDER,
                severity=severity,
                description=f"Response time too short ({duration}s), below minimum threshold {self.min_duration_seconds}s",
                affected_questions=["all"],
                confidence=0.9,
            )
        
        return None
    
    def _detect_incomplete(
        self,
        response: Any,
        survey: Any
    ) -> Optional[QualityIssue]:
        """Detect incomplete response"""
        # Find all required questions
        required_questions = [
            q.question_id for q in survey.questions
            if q.required
        ]
        
        # Find missing required questions
        missing_questions = [
            qid for qid in required_questions
            if qid not in response.answers
        ]
        
        if missing_questions:
            # Determine severity based on missing count
            missing_ratio = len(missing_questions) / len(required_questions)
            
            if missing_ratio >= 0.5:
                severity = "high"
            elif missing_ratio >= 0.2:
                severity = "medium"
            else:
                severity = "low"
            
            return QualityIssue(
                issue_type=QualityIssueType.INCOMPLETE,
                severity=severity,
                description=f"Missing {len(missing_questions)} required questions",
                affected_questions=missing_questions,
                confidence=1.0,
            )
        
        return None
    
    def _detect_straight_line(
        self,
        response: Any,
        survey: Any
    ) -> Optional[QualityIssue]:
        """Detect straight-line response"""
        # Collect single-choice answers
        from src.survey.models import QuestionType
        
        single_choice_questions = [
            q for q in survey.questions
            if q.question_type == QuestionType.SINGLE_CHOICE
        ]
        
        if len(single_choice_questions) < 3:
            # Too few single-choice questions to determine
            return None
        
        # Collect answer values
        answer_values = []
        for q in single_choice_questions:
            answer = response.answers.get(q.question_id)
            if answer:
                answer_values.append(answer.answer_value)
        
        if not answer_values:
            return None
        
        # Calculate proportion of identical answers
        from collections import Counter
        counter = Counter(answer_values)
        most_common_count = counter.most_common(1)[0][1]
        same_ratio = most_common_count / len(answer_values)
        
        if same_ratio >= self.straight_line_threshold:
            # Determine severity based on proportion
            if same_ratio >= 0.9:
                severity = "high"
            elif same_ratio >= 0.8:
                severity = "medium"
            else:
                severity = "low"
            
            return QualityIssue(
                issue_type=QualityIssueType.STRAIGHT_LINE,
                severity=severity,
                description=f"Single-choice answer identical ratio {same_ratio:.2%}, exceeds threshold {self.straight_line_threshold:.2%}",
                affected_questions=[q.question_id for q in single_choice_questions],
                confidence=same_ratio,
            )
        
        return None
    
    def _detect_nonsense_text(
        self,
        response: Any,
        survey: Any
    ) -> Optional[QualityIssue]:
        """Detect nonsense text"""
        from src.survey.models import QuestionType
        
        # Find open-ended questions
        open_ended_questions = [
            q for q in survey.questions
            if q.question_type == QuestionType.OPEN_ENDED
        ]
        
        nonsense_questions = []
        
        for q in open_ended_questions:
            answer = response.answers.get(q.question_id)
            if answer and answer.answer_value:
                text = str(answer.answer_value)
                
                # Check against nonsense patterns
                for pattern in self.NONSENSE_PATTERNS:
                    if re.match(pattern, text, re.IGNORECASE):
                        nonsense_questions.append(q.question_id)
                        break
        
        if nonsense_questions:
            # Determine severity based on count of nonsense questions
            if len(nonsense_questions) >= len(open_ended_questions):
                severity = "high"
            elif len(nonsense_questions) >= len(open_ended_questions) / 2:
                severity = "medium"
            else:
                severity = "low"
            
            return QualityIssue(
                issue_type=QualityIssueType.NONSENSE_TEXT,
                severity=severity,
                description=f"Open-ended question responses are meaningless",
                affected_questions=nonsense_questions,
                confidence=0.7,
            )
        
        return None
    
    def _detect_pattern_response(
        self,
        response: Any,
        survey: Any
    ) -> Optional[QualityIssue]:
        """Detect pattern response"""
        # Detect sequential patterns (e.g., 1,2,3,4 or 4,3,2,1)
        from src.survey.models import QuestionType
        
        ordered_questions = sorted(
            [q for q in survey.questions if q.question_type == QuestionType.SINGLE_CHOICE],
            key=lambda q: q.question_id
        )
        
        if len(ordered_questions) < 4:
            return None
        
        # Collect answer values
        answer_values = []
        for q in ordered_questions:
            answer = response.answers.get(q.question_id)
            if answer:
                answer_values.append(answer.answer_value)
        
        if len(answer_values) < 4:
            return None
        
        # Detect sequential pattern
        # Check if monotonically increasing or decreasing
        is_increasing = all(
            answer_values[i] <= answer_values[i + 1]
            for i in range(len(answer_values) - 1)
        )
        is_decreasing = all(
            answer_values[i] >= answer_values[i + 1]
            for i in range(len(answer_values) - 1)
        )
        
        if is_increasing or is_decreasing:
            return QualityIssue(
                issue_type=QualityIssueType.PATTERN_RESPONSE,
                severity="medium",
                description="Answers show an obvious sequential pattern",
                affected_questions=[q.question_id for q in ordered_questions],
                confidence=0.6,
            )
        
        return None
    
    def _calculate_quality_score(
        self,
        issues: List[QualityIssue]
    ) -> float:
        """Calculate quality score

        Args:
            issues: List of issues

        Returns:
            Quality score (0-1)
        """
        if not issues:
            return 1.0
        
        # Calculate total penalty
        total_penalty = sum(
            self.SEVERITY_WEIGHTS.get(issue.severity, 0.1)
            for issue in issues
        )
        
        # Ensure score is between 0 and 1
        quality_score = max(0.0, min(1.0, 1.0 - total_penalty))
        
        return quality_score
    
    def _generate_recommendations(
        self,
        issues: List[QualityIssue]
    ) -> List[str]:
        """Generate recommendations

        Args:
            issues: List of issues

        Returns:
            List of recommendations
        """
        if not issues:
            return ["Response quality is good, no review needed"]
        
        recommendations = []
        
        # Group by severity
        high_issues = [i for i in issues if i.severity == "high"]
        medium_issues = [i for i in issues if i.severity == "medium"]
        
        if high_issues:
            recommendations.append("Recommend excluding this response")
        elif medium_issues:
            recommendations.append("Recommend manual review")
        else:
            recommendations.append("Can be kept, but monitor closely")
        
        # Issue-specific recommendations
        for issue in issues:
            if issue.issue_type == QualityIssueType.SPEEDER:
                recommendations.append("Check if response speed is reasonable")
            elif issue.issue_type == QualityIssueType.STRAIGHT_LINE:
                recommendations.append("Check for straight-line responses")
            elif issue.issue_type == QualityIssueType.INCOMPLETE:
                recommendations.append("Fill in missing required questions")
        
        return recommendations
