"""
Cross-tabulation Analyzer

Analyzes relationships between two questions.
Supports: choice × choice, choice × Likert scale.
Includes chi-square test of independence.
"""

from collections import defaultdict, Counter
from typing import Dict, Any, List, Optional, Tuple

from ..models import Survey, SurveyResponse, Question, QuestionType
from .stats_tests import chi_square as _chi_square_test


class CrossTabAnalyzer:
    """Cross-tabulation analyzer with chi-square test."""

    def analyze(
        self,
        survey: Survey,
        responses: List[SurveyResponse],
        row_question_id: str,
        col_question_id: str,
    ) -> Dict[str, Any]:
        """
        Perform cross-tabulation analysis with chi-square test.

        Args:
            survey: Survey object
            responses: List of survey responses
            row_question_id: Row question ID
            col_question_id: Column question ID

        Returns:
            {
                "row_question": "Question text",
                "col_question": "Question text",
                "table": { ... },
                "totals": { ... },
                "chi_square": float | None,  # chi-square test result
            }
        """
        row_q = survey.get_question(row_question_id)
        col_q = survey.get_question(col_question_id)
        if not row_q or not col_q:
            raise ValueError(
                f"Question not found: row={row_question_id}, col={col_question_id}"
            )

        # Build cross-tabulation table
        table: Dict[str, Counter] = defaultdict(Counter)
        row_totals: Counter = Counter()
        col_totals: Counter = Counter()
        grand_total = 0

        for r in responses:
            row_ans = r.get_answer(row_question_id)
            col_ans = r.get_answer(col_question_id)
            if not row_ans or not col_ans:
                continue

            row_val = str(row_ans.answer_value)
            col_val = str(col_ans.answer_value)
            table[row_val][col_val] += 1
            row_totals[row_val] += 1
            col_totals[col_val] += 1
            grand_total += 1

        # Calculate percentages
        pct_table = {}
        for row_label, col_counter in table.items():
            row_total = row_totals[row_label]
            pct_table[row_label] = {
                col: {
                    "count": count,
                    "row_pct": round(count / row_total * 100, 1) if row_total else 0,
                    "col_pct": round(count / col_totals[col] * 100, 1) if col_totals[col] else 0,
                    "total_pct": round(count / grand_total * 100, 1) if grand_total else 0,
                }
                for col, count in col_counter.items()
            }

        # Chi-square test of independence
        chi_sq_result = None
        if grand_total > 0 and len(table) > 1 and len(col_totals) > 1:
            # Build observed matrix from the raw count table
            row_labels = sorted(table.keys())
            col_labels = sorted(col_totals.keys())
            observed = [[table[r][c] for c in col_labels] for r in row_labels]
            try:
                chi_sq_result = _chi_square_test(observed)
            except Exception:
                pass

        return {
            "row_question": row_q.text,
            "col_question": col_q.text,
            "row_question_id": row_question_id,
            "col_question_id": col_question_id,
            "table": pct_table,
            "totals": {
                "rows": dict(row_totals),
                "cols": dict(col_totals),
                "grand_total": grand_total,
            },
            "chi_square": chi_sq_result,
        }

    def auto_discover(
        self,
        survey: Survey,
        responses: List[SurveyResponse],
        max_pairs: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Auto-discover interesting cross-tabulation pairs.

        Selection criteria:
        - Single Choice / Likert / Yes-No questions only
        - Skips open-ended questions
        """
        # Filter candidate questions
        candidates = [
            q for q in survey.questions
            if q.question_type in (
                QuestionType.SINGLE_CHOICE,
                QuestionType.LIKERT,
                QuestionType.SCALE,
                QuestionType.YES_NO,
            )
        ]

        if len(candidates) < 2:
            return []

        # Generate up to max_pairs cross-tabs
        results = []
        pairs_generated = 0
        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                if pairs_generated >= max_pairs:
                    return results
                try:
                    result = self.analyze(
                        survey, responses,
                        candidates[i].question_id,
                        candidates[j].question_id,
                    )
                    results.append(result)
                    pairs_generated += 1
                except Exception:
                    continue

        return results
