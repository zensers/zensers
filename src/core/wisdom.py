# -*- coding: utf-8 -*-
"""
WisdomStore - Tool Layer Experience Storage

Track one of the dual-track learning system, independent from track two (LearningStore).

Responsibilities:
1. Record task execution experience
2. Aggregate best practices
3. Provide recommended Skills
4. Update Category templates

Boundary with LearningStore:
- Wisdom: Focus on "how to do", improve Agent factory capability
- LearningStore: Focus on "what is known", accumulate user knowledge
"""

__all__ = [
    "WisdomStore",
    "WisdomEntry",
    "WisdomAggregation"
]

import json
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from collections import defaultdict
import copy

logger = logging.getLogger(__name__)


@dataclass
class WisdomEntry:
    """
    Wisdom Entry - Task execution experience

    Organized by task_type:task_aspect
    """
    task_type: str
    task_aspect: str
    skills_used: List[str]
    success: bool
    approach: str
    duration_ms: int
    confidence_score: float = 0.5
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "task_type": self.task_type,
            "task_aspect": self.task_aspect,
            "skills_used": self.skills_used,
            "success": self.success,
            "approach": self.approach,
            "duration_ms": self.duration_ms,
            "confidence_score": self.confidence_score,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WisdomEntry":
        """Deserialize from dictionary"""
        return cls(
            task_type=data["task_type"],
            task_aspect=data["task_aspect"],
            skills_used=data["skills_used"],
            success=data["success"],
            approach=data["approach"],
            duration_ms=data["duration_ms"],
            confidence_score=data.get("confidence_score", 0.5),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


@dataclass
class WisdomAggregation:
    """
    Wisdom Aggregation Data

    Aggregated statistics by task_type:task_aspect
    """
    task_type: str
    task_aspect: str
    total_tasks: int = 0
    successful_tasks: int = 0
    success_rate: float = 0.0
    skill_recommendations: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    best_approaches: List[Dict[str, Any]] = field(default_factory=list)
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())

    def update_with_entry(self, entry: WisdomEntry) -> None:
        """Update aggregation data with entry"""
        self.total_tasks += 1
        if entry.success:
            self.successful_tasks += 1
        self.success_rate = self.successful_tasks / self.total_tasks if self.total_tasks > 0 else 0.0
        
        # Update Skill statistics
        for skill in entry.skills_used:
            if skill not in self.skill_recommendations:
                self.skill_recommendations[skill] = {
                    "usage_count": 0,
                    "success_count": 0,
                    "success_rate": 0.0,
                    "total_duration_ms": 0,
                    "avg_duration_ms": 0
                }

            self.skill_recommendations[skill]["usage_count"] += 1
            if entry.success:
                self.skill_recommendations[skill]["success_count"] += 1

            # Update success rate
            stats = self.skill_recommendations[skill]
            stats["success_rate"] = (
                stats["success_count"] / stats["usage_count"]
                if stats["usage_count"] > 0 else 0.0
            )

            # Update duration
            stats["total_duration_ms"] += entry.duration_ms
            stats["avg_duration_ms"] = (
                stats["total_duration_ms"] / stats["usage_count"]
                if stats["usage_count"] > 0 else 0
            )

        # Update best approaches
        approach_found = False
        for ap in self.best_approaches:
            if ap["approach"] == entry.approach:
                ap["count"] += 1
                if entry.success:
                    ap["success_count"] += 1
                ap["confidence"] = ap["success_count"] / ap["count"] if ap["count"] > 0 else 0.0
                approach_found = True
                break

        if not approach_found:
            self.best_approaches.append({
                "approach": entry.approach,
                "count": 1,
                "success_count": 1 if entry.success else 0,
                "confidence": 1.0 if entry.success else 0.0
            })

        # Sort best approaches by success count
        self.best_approaches.sort(key=lambda x: x["success_count"], reverse=True)
        
        self.last_updated = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "task_type": self.task_type,
            "task_aspect": self.task_aspect,
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "success_rate": self.success_rate,
            "skill_recommendations": self.skill_recommendations,
            "best_approaches": self.best_approaches,
            "last_updated": self.last_updated
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WisdomAggregation":
        """Deserialize from dictionary"""
        return cls(
            task_type=data["task_type"],
            task_aspect=data["task_aspect"],
            total_tasks=data.get("total_tasks", 0),
            successful_tasks=data.get("successful_tasks", 0),
            success_rate=data.get("success_rate", 0.0),
            skill_recommendations=data.get("skill_recommendations", {}),
            best_approaches=data.get("best_approaches", []),
            last_updated=data.get("last_updated", datetime.now().isoformat())
        )


class WisdomStore:
    """
    Wisdom Storage - Tool layer experience accumulation

    Track one of the dual-track system, independent from LearningStore (track two)
    """

    def __init__(self, store_path: Path):
        """
        Initialize Wisdom storage

        Args:
            store_path: Storage root directory
        """
        self.store_path = Path(store_path)
        self.store_path.mkdir(parents=True, exist_ok=True)

        # In-memory aggregation data
        self._aggregations: Dict[str, WisdomAggregation] = {}

        # Load existing data
        self._load()

        logger.info(f"WisdomStore initialized at {self.store_path}")

    def _get_key(self, task_type: str, task_aspect: str) -> str:
        """Generate storage key"""
        # Safely handle special characters
        safe_type = task_type.replace(":", "_").replace("/", "_")
        safe_aspect = task_aspect.replace(":", "_").replace("/", "_")
        return f"{safe_type}:{safe_aspect}"

    def _load(self) -> None:
        """Load existing data"""
        index_file = self.store_path / "wisdom_index.json"
        
        if index_file.exists():
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    index_data = json.load(f)
                
                for key, file_path in index_data.get("aggregations", {}).items():
                    full_path = self.store_path / file_path
                    if full_path.exists():
                        with open(full_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            self._aggregations[key] = WisdomAggregation.from_dict(data)
                
                logger.info(f"Loaded {len(self._aggregations)} wisdom aggregations")
            except Exception as e:
                logger.error(f"Failed to load wisdom data: {e}")
    
    def _save(self) -> None:
        """Save data"""
        index_data = {
            "version": "1.0",
            "last_updated": datetime.now().isoformat(),
            "aggregations": {}
        }

        for key, agg in self._aggregations.items():
            # Determine file path
            safe_type = agg.task_type.replace(":", "_").replace("/", "_")
            safe_aspect = agg.task_aspect.replace(":", "_").replace("/", "_")

            dir_path = self.store_path / safe_type
            dir_path.mkdir(exist_ok=True)

            file_name = f"{safe_aspect}.json"
            file_path = dir_path / file_name

            # Save aggregation data
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(agg.to_dict(), f, indent=2, ensure_ascii=False)

            # Update index
            index_data["aggregations"][key] = str(Path(safe_type) / file_name)

        # Save index
        index_file = self.store_path / "wisdom_index.json"
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(index_data, f, indent=2, ensure_ascii=False)

    def record_experience(
        self,
        task_type: str,
        task_aspect: str,
        skills_used: List[str],
        success: bool,
        approach: str,
        duration_ms: int,
        confidence_score: float = 0.5
    ) -> None:
        """
        Record task execution experience

        Args:
            task_type: Task type
            task_aspect: Task aspect
            skills_used: Skills used
            success: Whether successful
            approach: Approach used
            duration_ms: Execution duration (milliseconds)
            confidence_score: Confidence score
        """
        entry = WisdomEntry(
            task_type=task_type,
            task_aspect=task_aspect,
            skills_used=skills_used,
            success=success,
            approach=approach,
            duration_ms=duration_ms,
            confidence_score=confidence_score
        )
        
        key = self._get_key(task_type, task_aspect)

        # Get or create aggregation data
        if key not in self._aggregations:
            self._aggregations[key] = WisdomAggregation(
                task_type=task_type,
                task_aspect=task_aspect
            )

        # Update aggregation data
        self._aggregations[key].update_with_entry(entry)

        # Persist
        self._save()

        logger.debug(f"Recorded experience: {key}, success={success}")

    def get_best_practice(
        self,
        task_type: str,
        task_aspect: str
    ) -> Dict[str, Any]:
        """
        Get best practice

        Args:
            task_type: Task type
            task_aspect: Task aspect

        Returns:
            Best practice data, including:
            - total_tasks: Total task count
            - successful_tasks: Successful task count
            - success_rate: Success rate
            - skill_recommendations: Skill recommendations
            - best_approaches: Best approaches list
        """
        key = self._get_key(task_type, task_aspect)

        if key not in self._aggregations:
            # Return default values
            return {
                "task_type": task_type,
                "task_aspect": task_aspect,
                "total_tasks": 0,
                "successful_tasks": 0,
                "success_rate": 0.0,
                "skill_recommendations": {},
                "best_approaches": [],
                "last_updated": datetime.now().isoformat()
            }

        return self._aggregations[key].to_dict()

    def get_recommended_skills(
        self,
        task_type: str,
        task_aspect: str,
        min_success_rate: float = 0.0,
        min_usage_count: int = 1
    ) -> List[str]:
        """
        Get recommended Skills

        Sorted by Skill usage frequency from successful tasks

        Args:
            task_type: Task type
            task_aspect: Task aspect
            min_success_rate: Minimum success rate threshold
            min_usage_count: Minimum usage count threshold

        Returns:
            Recommended Skills list (sorted by usage frequency)
        """
        best = self.get_best_practice(task_type, task_aspect)

        skill_stats = best.get("skill_recommendations", {})

        # Filter and sort
        filtered_skills = []
        for skill, stats in skill_stats.items():
            if (stats.get("success_rate", 0) >= min_success_rate and
                stats.get("usage_count", 0) >= min_usage_count):
                filtered_skills.append((skill, stats.get("usage_count", 0)))

        # Sort by usage frequency
        filtered_skills.sort(key=lambda x: x[1], reverse=True)

        return [skill for skill, _ in filtered_skills]

    def update_category_template(
        self,
        task_type: str,
        task_aspect: str,
        min_success_rate: float = 0.7,
        min_samples: int = 5
    ) -> Dict[str, Any]:
        """
        Update Category template

        Generate template update suggestions based on accumulated experience

        Args:
            task_type: Task type
            task_aspect: Task aspect
            min_success_rate: Minimum success rate threshold
            min_samples: Minimum sample count

        Returns:
            Template update suggestions
        """
        best = self.get_best_practice(task_type, task_aspect)

        # Return empty suggestion when sample count is insufficient
        if best["total_tasks"] < min_samples:
            return {
                "status": "insufficient_data",
                "total_tasks": best["total_tasks"],
                "required": min_samples
            }

        # Get recommended Skills
        recommended_skills = self.get_recommended_skills(
            task_type, task_aspect,
            min_success_rate=min_success_rate
        )

        # Get best approach
        best_approaches = best.get("best_approaches", [])
        top_approach = best_approaches[0] if best_approaches else None

        return {
            "status": "ready",
            "recommended_category": self._infer_category(task_type, task_aspect),
            "recommended_skills": recommended_skills,
            "recommended_agent_name": f"{task_aspect}Agent",
            "best_approach": top_approach.get("approach") if top_approach else None,
            "confidence": best["success_rate"],
            "sample_count": best["total_tasks"]
        }

    def _infer_category(self, task_type: str, task_aspect: str) -> str:
        """Infer task category"""
        # Simple category inference logic
        type_lower = task_type.lower()
        aspect_lower = task_aspect.lower()

        if "data" in type_lower or "数据" in aspect_lower:
            return "data-collection"
        elif "financial" in type_lower or "财务" in aspect_lower:
            return "financial-analysis"
        elif "report" in type_lower or "报告" in aspect_lower:
            return "report-generation"
        elif "quality" in type_lower or "质量" in aspect_lower:
            return "quality-check"
        else:
            return "market-analysis"

    def get_all_aggregations(self) -> Dict[str, WisdomAggregation]:
        """Get all aggregation data"""
        return copy.deepcopy(self._aggregations)

    def clear(self) -> None:
        """Clear all data"""
        self._aggregations.clear()
        self._save()
        logger.info("WisdomStore cleared")