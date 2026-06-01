"""
Survey System Data Models

Defines core data structures for surveys, questions, responses, etc.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime


class QuestionType(Enum):
    """Question type"""
    SINGLE_CHOICE = "single_choice"      # Single choice
    MULTIPLE_CHOICE = "multiple_choice"  # Multiple choice
    LIKERT = "likert"                    # Likert scale
    OPEN_ENDED = "open_ended"           # Open-ended
    YES_NO = "yes_no"                   # Yes/No
    RANKING = "ranking"                 # Ranking
    MATRIX = "matrix"                   # Matrix
    SCALE = "scale"                     # Scale rating
    DROPDOWN = "dropdown"               # Dropdown
    DATE_TIME = "date_time"             # Date/Time
    FILE_UPLOAD = "file_upload"         # File upload


class SurveyStatus(Enum):
    """Survey status"""
    DRAFT = "draft"                      # Draft
    PENDING = "pending"                  # Pending distribution
    ACTIVE = "active"                    # Collecting
    PAUSED = "paused"                    # Paused
    
    # ===== New statuses (Phase 9: Survey System Integration) =====
    WAITING = "waiting"                  # Sent to third-party, awaiting feedback
    TIMEOUT = "timeout"                  # Timed out
    
    COMPLETED = "completed"              # Completed
    FAILED = "failed"                    # Failed
    CANCELLED = "cancelled"              # Cancelled


@dataclass
class QuestionOption:
    """Option"""
    option_id: str
    text: str
    value: Optional[Any] = None         # Option value (for analysis)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "option_id": self.option_id,
            "text": self.text,
            "value": self.value,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QuestionOption":
        return cls(
            option_id=data["option_id"],
            text=data["text"],
            value=data.get("value"),
        )


@dataclass
class Question:
    """Question"""
    question_id: str
    text: str
    question_type: QuestionType
    options: Optional[List[QuestionOption]] = None
    required: bool = True
    description: Optional[str] = None
    validation_rules: Dict[str, Any] = field(default_factory=dict)
    skip_logic: Optional[Dict[str, Any]] = None  # Skip logic
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "question_id": self.question_id,
            "text": self.text,
            "question_type": self.question_type.value,
            "options": [opt.to_dict() for opt in self.options] if self.options else None,
            "required": self.required,
            "description": self.description,
            "validation_rules": self.validation_rules,
            "skip_logic": self.skip_logic,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Question":
        return cls(
            question_id=data["question_id"],
            text=data["text"],
            question_type=QuestionType(data["question_type"]),
            options=[QuestionOption.from_dict(opt) for opt in data["options"]] if data.get("options") else None,
            required=data.get("required", True),
            description=data.get("description"),
            validation_rules=data.get("validation_rules", {}),
            skip_logic=data.get("skip_logic"),
        )


@dataclass
class Survey:
    """Survey"""
    survey_id: str
    title: str
    questions: List[Question]
    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_question(self, question_id: str) -> Optional[Question]:
        """Get question by ID"""
        for q in self.questions:
            if q.question_id == question_id:
                return q
        return None

    def get_visible_questions(self, answers: Optional[Dict[str, "Answer"]] = None) -> List[Question]:
        """Return questions that should be visible given existing answers (respects skip_logic)."""
        if not answers:
            return list(self.questions)
        visible = []
        for q in self.questions:
            skip = q.skip_logic
            if skip:
                depends_on = skip.get("depends_on", "")
                condition = skip.get("condition", "equals")
                value = skip.get("value")
                effect = skip.get("effect", "show")
                if depends_on not in answers:
                    visible.append(q)
                    continue
                prev = str(answers[depends_on].answer_value)
                met = False
                if condition == "equals":
                    met = prev == str(value)
                elif condition == "not_equals":
                    met = prev != str(value)
                elif condition == "in":
                    met = prev in [str(v) for v in (value or [])]
                elif condition == "greater_than":
                    try: met = float(prev) > float(value)
                    except: met = False
                elif condition == "less_than":
                    try: met = float(prev) < float(value)
                    except: met = False
                skipped = met if effect == "hide" else not met
                if not skipped:
                    visible.append(q)
            else:
                visible.append(q)
        return visible
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "survey_id": self.survey_id,
            "title": self.title,
            "description": self.description,
            "questions": [q.to_dict() for q in self.questions],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Survey":
        return cls(
            survey_id=data["survey_id"],
            title=data["title"],
            description=data.get("description", ""),
            questions=[Question.from_dict(q) for q in data["questions"]],
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(),
            metadata=data.get("metadata", {}),
        )


@dataclass
class QuotaConfig:
    """Quota configuration"""
    dimensions: Dict[str, Dict[str, int]]
    target_count: int = 0
    
    def __post_init__(self):
        if not self.target_count:
            # Calculate total target
            first_dim = next(iter(self.dimensions.values()), {})
            self.target_count = sum(first_dim.values())
    
    def validate(self) -> bool:
        """Validate quota configuration"""
        for dimension, values in self.dimensions.items():
            total = sum(values.values())
            if self.target_count > 0 and abs(total - self.target_count) > self.target_count * 0.1:
                return False
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimensions": self.dimensions,
            "target_count": self.target_count,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QuotaConfig":
        return cls(
            dimensions=data["dimensions"],
            target_count=data.get("target_count", 0),
        )


@dataclass
class DistributionConfig:
    """Distribution configuration"""
    target_count: int                    # Target sample count
    quota: Optional[QuotaConfig] = None  # Quota control
    incentive: Optional[float] = None    # Incentive amount
    deadline: Optional[datetime] = None  # Deadline
    channels: List[str] = field(default_factory=list)  # Distribution channels
    sampling_spec: Optional[Dict[str, Any]] = None  # Sampling spec for AI simulation
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_count": self.target_count,
            "quota": self.quota.to_dict() if self.quota else None,
            "incentive": self.incentive,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "channels": self.channels,
            "sampling_spec": self.sampling_spec,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DistributionConfig":
        return cls(
            target_count=data["target_count"],
            quota=QuotaConfig.from_dict(data["quota"]) if data.get("quota") else None,
            incentive=data.get("incentive"),
            deadline=datetime.fromisoformat(data["deadline"]) if data.get("deadline") else None,
            channels=data.get("channels", []),
            sampling_spec=data.get("sampling_spec"),
        )


@dataclass
class Answer:
    """Single answer"""
    question_id: str
    answer_value: Any                    # Answer value
    answer_text: Optional[str] = None   # Open-ended text
    answered_at: datetime = field(default_factory=datetime.now)
    duration_seconds: Optional[int] = None  # Response duration
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "question_id": self.question_id,
            "answer_value": self.answer_value,
            "answer_text": self.answer_text,
            "answered_at": self.answered_at.isoformat(),
            "duration_seconds": self.duration_seconds,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Answer":
        return cls(
            question_id=data["question_id"],
            answer_value=data["answer_value"],
            answer_text=data.get("answer_text"),
            answered_at=datetime.fromisoformat(data["answered_at"]) if data.get("answered_at") else datetime.now(),
            duration_seconds=data.get("duration_seconds"),
        )


@dataclass
class SurveyResponse:
    """Survey response"""
    response_id: str
    survey_id: str
    answers: Dict[str, Answer] = field(default_factory=dict)  # question_id -> Answer
    respondent_id: Optional[str] = None  # Respondent ID (anonymous, nullable)
    completed_at: datetime = field(default_factory=datetime.now)
    
    # Data quality metrics
    duration_seconds: int = 0            # Total duration
    quality_score: float = 1.0           # Quality score
    is_valid: bool = True                # Is valid
    
    # Demographics (if collected)
    demographics: Optional[Dict[str, Any]] = None
    
    # Source info
    source_ip: Optional[str] = None
    source_ua: Optional[str] = None
    
    def get_answer(self, question_id: str) -> Optional[Answer]:
        """Get answer for a question"""
        return self.answers.get(question_id)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "response_id": self.response_id,
            "survey_id": self.survey_id,
            "respondent_id": self.respondent_id,
            "answers": {qid: ans.to_dict() for qid, ans in self.answers.items()},
            "completed_at": self.completed_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "quality_score": self.quality_score,
            "is_valid": self.is_valid,
            "demographics": self.demographics,
            "source_ip": self.source_ip,
            "source_ua": self.source_ua,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SurveyResponse":
        return cls(
            response_id=data["response_id"],
            survey_id=data["survey_id"],
            respondent_id=data.get("respondent_id"),
            answers={qid: Answer.from_dict(ans) for qid, ans in data.get("answers", {}).items()},
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else datetime.now(),
            duration_seconds=data.get("duration_seconds", 0),
            quality_score=data.get("quality_score", 1.0),
            is_valid=data.get("is_valid", True),
            demographics=data.get("demographics"),
            source_ip=data.get("source_ip"),
            source_ua=data.get("source_ua"),
        )


@dataclass
class SurveyTask:
    """
    Survey task
    
    Phase 9 extension: supports long-term waiting (1 month+) and master system integration
    """
    task_id: str
    survey_id: str
    backend_type: str                    # Backend type
    status: SurveyStatus
    config: DistributionConfig           # Configuration
    target_count: int                    # Target sample count
    
    # External system ID
    external_id: Optional[str] = None    # Third-party platform survey ID
    
    # Progress
    collected_count: int = 0
    valid_count: int = 0
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Share link
    share_url: Optional[str] = None
    
    # Error message
    error_message: Optional[str] = None
    
    # Results (optional, not stored for large data)
    responses: List[SurveyResponse] = field(default_factory=list)
    
    # ===== Phase 9 New: Master System Association =====
    parent_task_id: Optional[str] = None    # Associated master research task ID
    parent_phase: Optional[str] = None      # Phase (e.g. DATA_COLLECTION)
    
    # ===== Phase 9 New: Long-term Waiting Support =====
    expected_completion_date: Optional[datetime] = None
    timeout_days: int = 30                   # Timeout days (default 30)
    timeout_action: str = "notify"           # Timeout action: notify/cancel/continue
    
    # ===== Phase 9 New: Recovery and Callbacks =====
    callback_topic: Optional[str] = None     # Topic to publish on completion via MessageBus
    checkpoint_id: Optional[str] = None      # Associated checkpoint ID
    result_storage_path: Optional[str] = None # Result file path (for large data)
    
    # ===== Phase 9 New: Polling Configuration =====
    polling_enabled: bool = False            # Enable polling (when webhook not supported)
    polling_interval_hours: int = 24         # Polling interval (hours)
    last_polling_at: Optional[datetime] = None
    next_polling_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "survey_id": self.survey_id,
            "backend_type": self.backend_type,
            "status": self.status.value,
            "external_id": self.external_id,
            "config": self.config.to_dict(),
            "target_count": self.target_count,
            "collected_count": self.collected_count,
            "valid_count": self.valid_count,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "share_url": self.share_url,
            "error_message": self.error_message,
            # Phase 9 new fields
            "parent_task_id": self.parent_task_id,
            "parent_phase": self.parent_phase,
            "expected_completion_date": self.expected_completion_date.isoformat() if self.expected_completion_date else None,
            "timeout_days": self.timeout_days,
            "timeout_action": self.timeout_action,
            "callback_topic": self.callback_topic,
            "checkpoint_id": self.checkpoint_id,
            "result_storage_path": self.result_storage_path,
            "polling_enabled": self.polling_enabled,
            "polling_interval_hours": self.polling_interval_hours,
            "last_polling_at": self.last_polling_at.isoformat() if self.last_polling_at else None,
            "next_polling_at": self.next_polling_at.isoformat() if self.next_polling_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SurveyTask":
        return cls(
            task_id=data["task_id"],
            survey_id=data["survey_id"],
            backend_type=data["backend_type"],
            status=SurveyStatus(data["status"]),
            external_id=data.get("external_id"),
            config=DistributionConfig.from_dict(data["config"]),
            target_count=data["target_count"],
            collected_count=data.get("collected_count", 0),
            valid_count=data.get("valid_count", 0),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            share_url=data.get("share_url"),
            error_message=data.get("error_message"),
            # Phase 9 new fields
            parent_task_id=data.get("parent_task_id"),
            parent_phase=data.get("parent_phase"),
            expected_completion_date=datetime.fromisoformat(data["expected_completion_date"]) if data.get("expected_completion_date") else None,
            timeout_days=data.get("timeout_days", 30),
            timeout_action=data.get("timeout_action", "notify"),
            callback_topic=data.get("callback_topic"),
            checkpoint_id=data.get("checkpoint_id"),
            result_storage_path=data.get("result_storage_path"),
            polling_enabled=data.get("polling_enabled", False),
            polling_interval_hours=data.get("polling_interval_hours", 24),
            last_polling_at=datetime.fromisoformat(data["last_polling_at"]) if data.get("last_polling_at") else None,
            next_polling_at=datetime.fromisoformat(data["next_polling_at"]) if data.get("next_polling_at") else None,
        )
    
    def is_waiting(self) -> bool:
        """Check if waiting for response"""
        return self.status == SurveyStatus.WAITING
    
    def is_timeout(self) -> bool:
        """Check if task has timed out"""
        if not self.expected_completion_date:
            return False
        return datetime.now() > self.expected_completion_date
    
    def calculate_next_polling_time(self) -> datetime:
        """Calculate next polling time"""
        from datetime import timedelta
        return datetime.now() + timedelta(hours=self.polling_interval_hours)
