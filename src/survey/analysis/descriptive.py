"""
Descriptive Statistics Analyzer

Analyzes Survey Response data including frequency distributions,
central tendency, and dispersion measures.
"""

import statistics
from collections import Counter, defaultdict
from typing import Dict, Any, List, Optional, Tuple

from ..models import Survey, SurveyResponse, Question, QuestionType


class DescriptiveAnalyzer:
    """Descriptive statistics analyzer for survey responses."""

    def analyze(
        self,
        survey: Survey,
        responses: List[SurveyResponse],
    ) -> Dict[str, Any]:
        """
        Analyze survey responses.

        Args:
            survey: Survey object
            responses: List of survey responses

        Returns:
            {
                "total_responses": int,
                "valid_responses": int,
                "per_question": {
                    "q_1": {
                        "question_text": "...",
                        "question_type": "single_choice",
                        "total": int,
                        "skipped": int,
                        "stats": { ... }
                    }
                },
                "overall": {
                    "completion_rate": float,
                    "avg_duration_seconds": float,
                }
            }
        """
        valid = [r for r in responses if r.is_valid]
        result: Dict[str, Any] = {
            "total_responses": len(responses),
            "valid_responses": len(valid),
            "per_question": {},
            "overall": self._overall_stats(responses, valid),
        }

        for question in survey.questions:
            result["per_question"][question.question_id] = self._analyze_question(
                question, responses, valid
            )

        return result

    def _overall_stats(
        self, all_responses: List[SurveyResponse], valid: List[SurveyResponse]
    ) -> Dict[str, Any]:
        """Calculate overall statistics."""
        completion = len(valid) / len(all_responses) if all_responses else 0.0
        durations = [r.duration_seconds for r in valid if r.duration_seconds > 0]
        return {
            "completion_rate": round(completion, 4),
            "avg_duration_seconds": round(statistics.mean(durations), 1) if durations else 0,
            "median_duration_seconds": round(statistics.median(durations), 1) if durations else 0,
        }

    def _analyze_question(
        self,
        question: Question,
        all_responses: List[SurveyResponse],
        valid: List[SurveyResponse],
    ) -> Dict[str, Any]:
        """Analyze a single question."""
        base = {
            "question_text": question.text,
            "question_type": question.question_type.value,
            "total": len(all_responses),
            "skipped": len(all_responses) - len(valid),
        }

        handler = self._get_handler(question.question_type)
        if handler:
            base["stats"] = handler(question, valid)
        return base

    def _get_handler(self, qtype: QuestionType):
        """Get the appropriate handler for a question type."""
        handlers = {
            QuestionType.SINGLE_CHOICE: self._analyze_single_choice,
            QuestionType.MULTIPLE_CHOICE: self._analyze_multiple_choice,
            QuestionType.LIKERT: self._analyze_scale,
            QuestionType.SCALE: self._analyze_scale,
            QuestionType.YES_NO: self._analyze_single_choice,
            QuestionType.OPEN_ENDED: self._analyze_open_ended,
            QuestionType.RANKING: self._analyze_ranking,
            QuestionType.DROPDOWN: self._analyze_single_choice,
            QuestionType.MATRIX: self._analyze_matrix,
        }
        return handlers.get(qtype)

    # ------------------------------------------------------------------ #
    # Question type handlers
    # ------------------------------------------------------------------ #
    def _analyze_single_choice(
        self, question: Question, responses: List[SurveyResponse]
    ) -> Dict[str, Any]:
        """Analyze single choice question."""
        counter: Counter[str] = Counter()
        for r in responses:
            ans = r.get_answer(question.question_id)
            if ans:
                counter[str(ans.answer_value)] += 1

        total = sum(counter.values()) or 1
        distribution = {
            opt.text: {
                "count": counter.get(opt.text, 0),
                "percentage": round(counter.get(opt.text, 0) / total * 100, 1),
            }
            for opt in (question.options or [])
        }

        # Sort by count descending
        sorted_items = sorted(
            distribution.items(),
            key=lambda x: x[1]["count"],
            reverse=True
        )

        return {
            "distribution": dict(sorted_items),
            "total_answers": sum(counter.values()),
            "most_selected": sorted_items[0][0] if sorted_items else None,
            "most_selected_pct": sorted_items[0][1]["percentage"] if sorted_items else 0,
        }

    def _analyze_multiple_choice(
        self, question: Question, responses: List[SurveyResponse]
    ) -> Dict[str, Any]:
        """Analyze multiple choice question."""
        counter: Counter[str] = Counter()
        for r in responses:
            ans = r.get_answer(question.question_id)
            if ans and ans.answer_value:
                for val in str(ans.answer_value).split(","):
                    counter[val.strip()] += 1

        total = sum(counter.values()) or 1
        distribution = {
            opt.text: {
                "count": counter.get(opt.text, 0),
                "percentage": round(counter.get(opt.text, 0) / total * 100, 1),
            }
            for opt in (question.options or [])
        }

        return {
            "distribution": distribution,
            "total_selections": sum(counter.values()),
            "avg_selections_per_respondent": round(
                sum(counter.values()) / len(responses), 2
            ) if responses else 0,
        }

    def _analyze_scale(
        self, question: Question, responses: List[SurveyResponse]
    ) -> Dict[str, Any]:
        """Analyze scale/Likert question."""
        values: List[float] = []
        for r in responses:
            ans = r.get_answer(question.question_id)
            if ans:
                try:
                    values.append(float(ans.answer_value))
                except (ValueError, TypeError):
                    pass

        if not values:
            return {"mean": 0, "median": 0, "std": 0, "distribution": {}}

        counter = Counter(values)
        dist = {
            str(k): {
                "count": v,
                "percentage": round(v / len(values) * 100, 1)
            }
            for k, v in sorted(counter.items())
        }

        return {
            "mean": round(statistics.mean(values), 2),
            "median": round(statistics.median(values), 2),
            "std": round(statistics.stdev(values), 2) if len(values) > 1 else 0,
            "min": min(values),
            "max": max(values),
            "distribution": dist,
            "total_answers": len(values),
        }

    def _analyze_open_ended(
        self, question: Question, responses: List[SurveyResponse]
    ) -> Dict[str, Any]:
        """Analyze open-ended question."""
        texts: List[str] = []
        for r in responses:
            ans = r.get_answer(question.question_id)
            if ans and ans.answer_value:
                texts.append(str(ans.answer_value))

        word_counts = [len(t) for t in texts]
        return {
            "total_answers": len(texts),
            "avg_length": round(statistics.mean(word_counts), 1) if word_counts else 0,
            "min_length": min(word_counts) if word_counts else 0,
            "max_length": max(word_counts) if word_counts else 0,
            # Sample texts (first 5)
            "sample_texts": texts[:5],
        }

    def _analyze_ranking(
        self, question: Question, responses: List[SurveyResponse]
    ) -> Dict[str, Any]:
        """Analyze ranking question."""
        position_counts: Dict[str, Counter] = defaultdict(Counter)
        for r in responses:
            ans = r.get_answer(question.question_id)
            if ans and ans.answer_value:
                items = str(ans.answer_value).split(",")
                for pos, item in enumerate(items, 1):
                    position_counts[f"rank_{pos}"][item.strip()] += 1

        total = len(responses)
        result = {}
        for rank, counter in sorted(position_counts.items()):
            result[rank] = {
                item: {
                    "count": c,
                    "percentage": round(c / total * 100, 1),
                }
                for item, c in counter.most_common()
            }
        return {"ranking": result, "total_rankings": total}

    def _analyze_matrix(
        self, question: Question, responses: List[SurveyResponse]
    ) -> Dict[str, Any]:
        """Analyze matrix question."""
        rows: Dict[str, Counter] = defaultdict(Counter)
        for r in responses:
            ans = r.get_answer(question.question_id)
            if ans and isinstance(ans.answer_value, dict):
                for row_id, value in ans.answer_value.items():
                    rows[row_id][str(value)] += 1

        total = len(responses)
        result = {}
        for row_id, counter in rows.items():
            result[row_id] = {
                str(k): {"count": v, "percentage": round(v / total * 100, 1)}
                for k, v in counter.most_common()
            }
        return {"matrix": result}
