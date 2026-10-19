"""
SurveyAnalysisAgent - Survey Analysis Agent

Analyzes and statistically processes survey results, generating insight reports.

Features:
1. Response data statistical analysis
2. Cross-tabulation analysis
3. Text sentiment analysis
4. Data visualization suggestions
5. Report generation
6. Chart generation (P0-2 fix)

Input:
{
    "responses": List[Dict],      # Response data
    "questions": List[Dict],      # Question list
    "analysis_type": str,         # Analysis type
    "report_format": str,         # Report format
    "generate_charts": bool,      # Whether to generate charts (default True)
    "chart_output_dir": str,      # Chart output directory (optional)
}

Output:
{
    "success": bool,
    "statistics": Dict,           # Statistical results
    "insights": List[Dict],       # Insight findings
    "report": str,                # Analysis report
    "charts": List[Dict],         # Chart information (P0-2 addition)
}
"""
from typing import Any, Dict, List, Optional
from collections import Counter
import asyncio
import logging
from pathlib import Path

from src.agents.fixed_agents.base_fixed_agent import FixedAgent

logger = logging.getLogger(__name__)


class SurveyAnalysisAgent(FixedAgent):
    """Survey Analysis Agent.
    
    Responsible for analyzing survey results and generating statistical reports and insights.
    """
    
    agent_type = "survey_analysis"
    version = "1.0.0"
    capabilities = [
        "Response statistical analysis",
        "Cross-tabulation analysis",
        "Text sentiment analysis",
        "Data visualization",
        "Report generation",
    ]
    
    def __init__(
        self,
        agent_id: str,
        name: str = "Survey Analysis Agent",
        description: str = "Analyze survey results and generate statistical reports",
        storage_path: Optional[str] = None,
        chart_generator: Optional[Any] = None,
    ):
        """Initialize Survey Analysis Agent."""
        super().__init__(agent_id, name=name, description=description, storage_path=storage_path)
        self._chart_generator = chart_generator
        self._charts_output_dir: Optional[Path] = None
    
    def validate_input(self, task_input: Dict[str, Any]) -> tuple[bool, str]:
        """Validate input parameters."""
        valid, error = super().validate_input(task_input)
        if not valid:
            return valid, error
        
        if "responses" not in task_input:
            return False, "Missing required 'responses' field"
        
        if "questions" not in task_input:
            return False, "Missing required 'questions' field"
        
        return True, ""
    
    async def execute(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute survey analysis (async).
        
        Args:
            task_input: {
                "responses": List[Dict],      # Response data
                "questions": List[Dict],      # Question list
                "analysis_type": str,         # Analysis type
                "report_format": str,         # Report format
                "generate_charts": bool,      # Whether to generate charts (default True)
                "chart_output_dir": str,      # Chart output directory (optional)
            }
            
        Returns:
            Analysis results
        """
        responses = task_input["responses"]
        questions = task_input["questions"]
        analysis_type = task_input.get("analysis_type", "basic")
        report_format = task_input.get("report_format", "markdown")
        generate_charts = task_input.get("generate_charts", True)
        chart_output_dir = task_input.get("chart_output_dir")
        
        # Publish start event
        await self.publish_event("analysis_started", {"response_count": len(responses)})
        
        # Statistical analysis
        statistics = await self._calculate_statistics_async(responses, questions)
        
        # Cross-tabulation analysis (if requested)
        cross_analysis = None
        if analysis_type in ["cross", "full"]:
            cross_analysis = self._cross_analysis(responses, questions)
        
        # Generate insights
        insights = self._generate_insights(statistics, cross_analysis)
        
        # P0-2 fix: Generate charts
        charts = []
        if generate_charts:
            charts = await self._generate_charts(statistics, questions, chart_output_dir)
        
        # Generate report
        report = self._generate_report(statistics, insights, cross_analysis, report_format)
        
        # Write to shared state
        await self.write_shared_state(f"agent.{self.agent_id}.last_analysis", {
            "response_count": len(responses),
            "insight_count": len(insights),
            "chart_count": len(charts),
        })
        
        # Publish completion event
        await self.publish_event("analysis_completed", {
            "insight_count": len(insights),
            "chart_count": len(charts),
        })
        
        return {
            "success": True,
            "statistics": statistics,
            "insights": insights,
            "cross_analysis": cross_analysis,
            "charts": charts,  # P0-2 addition: chart information
            "report": report,
            # Add key_findings field for upstream use
            "key_findings": [i.get("description", "") for i in insights if i.get("type") == "finding"],
        }
    
    async def _calculate_statistics_async(
        self, 
        responses: List[Dict], 
        questions: List[Dict]
    ) -> Dict[str, Any]:
        """Asynchronously calculate statistics."""
        # Statistical calculation logic
        return self._calculate_statistics(responses, questions)
    
    def _execute_sync(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute survey analysis synchronously."""
        responses = task_input["responses"]
        questions = task_input["questions"]
        analysis_type = task_input.get("analysis_type", "statistics")
        report_format = task_input.get("report_format", "markdown")
        
        # 1. Basic statistics
        statistics = self._calculate_statistics(responses, questions)
        
        # 2. Cross-tabulation analysis (optional)
        cross_analysis = None
        if analysis_type in ["cross", "full"]:
            cross_analysis = self._cross_analysis(responses, questions)
        
        # 3. Generate insights
        insights = self._generate_insights(statistics, cross_analysis)
        
        # 4. Generate report
        report = None
        if analysis_type in ["report", "full"]:
            report = self._generate_report(
                statistics, insights, cross_analysis, report_format
            )
        
        return {
            "success": True,
            "statistics": statistics,
            "cross_analysis": cross_analysis,
            "insights": insights,
            "report": report,
        }
    
    async def execute_async(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute survey analysis asynchronously."""
        responses = task_input["responses"]
        questions = task_input["questions"]
        analysis_type = task_input.get("analysis_type", "statistics")
        report_format = task_input.get("report_format", "markdown")
        
        # 1. Basic statistics
        statistics = self._calculate_statistics(responses, questions)
        
        # 2. Cross-tabulation analysis (optional)
        cross_analysis = None
        if analysis_type in ["cross", "full"]:
            cross_analysis = self._cross_analysis(responses, questions)
        
        # 3. Generate insights
        insights = self._generate_insights(statistics, cross_analysis)
        
        # 4. Generate report
        report = None
        if analysis_type in ["report", "full"]:
            report = self._generate_report(
                statistics, insights, cross_analysis, report_format
            )
        
        return {
            "success": True,
            "statistics": statistics,
            "cross_analysis": cross_analysis,
            "insights": insights,
            "report": report,
        }
    
    def _calculate_statistics(
        self,
        responses: List[Dict],
        questions: List[Dict]
    ) -> Dict[str, Any]:
        """Calculate basic statistics."""
        statistics = {
            "total_responses": len(responses),
            "questions": {},
        }
        
        for q in questions:
            # Support both field name formats
            q_id = q.get("question_id") or q.get("id")
            q_type = q.get("question_type") or q.get("type", "unknown")
            q_text = q.get("text", "")
            
            # Collect all answers for this question
            answers = []
            for r in responses:
                answer = r.get("answers", {}).get(q_id, {})
                if answer:
                    # Support direct value or dict format
                    if isinstance(answer, dict):
                        answers.append(answer.get("answer_value"))
                    else:
                        answers.append(answer)
            
            q_stats = {
                "text": q_text,
                "type": q_type,
                "answer_count": len(answers),
                "response_rate": len(answers) / len(responses) if responses else 0,
            }
            
            # Calculate statistics based on question type
            if q_type in ["single_choice", "multiple_choice"]:
                q_stats["distribution"] = dict(Counter(answers))
                q_stats["top_answer"] = Counter(answers).most_common(1)[0] if answers else None
            
            elif q_type in ["scale", "likert"]:
                numeric_answers = [a for a in answers if isinstance(a, (int, float))]
                if numeric_answers:
                    import math
                    n = len(numeric_answers)
                    mean = sum(numeric_answers) / n
                    q_stats["mean"] = mean
                    q_stats["min"] = min(numeric_answers)
                    q_stats["max"] = max(numeric_answers)
                    q_stats["median"] = sorted(numeric_answers)[n // 2]
                    
                    # P1-2 fix: Add advanced statistical metrics
                    # Standard deviation
                    variance = sum((x - mean) ** 2 for x in numeric_answers) / n
                    std_dev = math.sqrt(variance)
                    q_stats["std_dev"] = round(std_dev, 2)
                    q_stats["variance"] = round(variance, 2)
                    
                    # 95% confidence interval
                    if n > 1:
                        # Use t-distribution (small samples)
                        # For large samples (n>30), t-value approaches 1.96
                        t_value = 1.96 if n > 30 else self._get_t_value(n - 1, 0.05)
                        margin_error = t_value * (std_dev / math.sqrt(n))
                        q_stats["confidence_interval_95"] = {
                            "lower": round(mean - margin_error, 2),
                            "upper": round(mean + margin_error, 2),
                            "margin_error": round(margin_error, 2),
                        }
                    
                    # Quartiles
                    sorted_answers = sorted(numeric_answers)
                    q_stats["q1"] = sorted_answers[n // 4] if n >= 4 else sorted_answers[0]
                    q_stats["q3"] = sorted_answers[3 * n // 4] if n >= 4 else sorted_answers[-1]
                    q_stats["iqr"] = q_stats["q3"] - q_stats["q1"]  # Interquartile range
            
            elif q_type == "open_ended":
                q_stats["text_count"] = len([a for a in answers if a])
                q_stats["avg_length"] = sum(len(str(a)) for a in answers) / len(answers) if answers else 0
            
            statistics["questions"][q_id] = q_stats
        
        return statistics
    
    def _get_t_value(self, df: int, alpha: float = 0.05) -> float:
        """
        P1-2 fix: Get t-distribution critical value (approximation)
        
        For 95% confidence interval (two-tailed), alpha=0.05
        
        Args:
            df: Degrees of freedom (n-1)
            alpha: Significance level
            
        Returns:
            t critical value
        """
        # Common t-values (95% confidence interval, two-tailed)
        t_table = {
            1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
            6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
            11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
            16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
            21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
            26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
        }
        
        if df in t_table:
            return t_table[df]
        elif df > 30:
            # Large sample approximates normal distribution
            return 1.96
        else:
            # Linear interpolation
            return 2.0 + (30 - df) * 0.01  # Simplified approximation
    
    def _cross_analysis(
        self,
        responses: List[Dict],
        questions: List[Dict]
    ) -> Dict[str, Any]:
        """Cross-tabulation analysis."""
        cross_analysis = {}
        
        # Get choice questions
        choice_questions = [
            q for q in questions 
            if (q.get("question_type") or q.get("type")) in ["single_choice", "multiple_choice"]
        ]
        
        # Pairwise cross-tabulation
        for i, q1 in enumerate(choice_questions):
            for q2 in choice_questions[i+1:]:
                q1_id = q1.get("question_id") or q1.get("id")
                q2_id = q2.get("question_id") or q2.get("id")
                
                key = f"{q1_id}_x_{q2_id}"
                cross_analysis[key] = self._calculate_cross_tab(
                    responses, q1_id, q2_id
                )
        
        return cross_analysis
    
    def _calculate_cross_tab(
        self,
        responses: List[Dict],
        q1_id: str,
        q2_id: str
    ) -> Dict[str, Any]:
        """Calculate cross-tabulation table."""
        cross_tab = {}
        
        # Collect paired data for correlation analysis
        pairs = []
        
        for r in responses:
            answers = r.get("answers", {})
            # Support direct value or dict format
            a1 = answers.get(q1_id, {})
            a2 = answers.get(q2_id, {})
            
            if isinstance(a1, dict):
                a1 = a1.get("answer_value")
            if isinstance(a2, dict):
                a2 = a2.get("answer_value")
            
            if a1 is not None and a2 is not None:
                key = f"{a1}|{a2}"
                cross_tab[key] = cross_tab.get(key, 0) + 1
                pairs.append((a1, a2))
        
        result = {
            "cross_table": cross_tab,
            "total": sum(cross_tab.values()),
        }
        
        # P1-3 fix: Add correlation analysis
        if len(pairs) >= 5:  # Need at least 5 pairs for correlation
            try:
                # Check if numeric data
                numeric_pairs = [(a, b) for a, b in pairs if isinstance(a, (int, float)) and isinstance(b, (int, float))]
                
                if len(numeric_pairs) >= 5:
                    # Calculate Pearson correlation coefficient
                    correlation = self._calculate_pearson_correlation(numeric_pairs)
                    result["correlation"] = correlation
                    
                    # Interpret correlation strength
                    abs_r = abs(correlation.get("r", 0))
                    if abs_r >= 0.7:
                        strength = "Strong correlation"
                    elif abs_r >= 0.4:
                        strength = "Moderate correlation"
                    elif abs_r >= 0.2:
                        strength = "Weak correlation"
                    else:
                        strength = "Almost no correlation"
                    result["correlation"]["strength"] = strength
                else:
                    # For categorical variables, calculate chi-square test
                    chi_square = self._calculate_chi_square(cross_tab, pairs)
                    if chi_square:
                        result["chi_square"] = chi_square
                        
            except Exception as e:
                logger.warning(f"Correlation analysis failed: {e}")
        
        return result
    
    def _calculate_pearson_correlation(
        self, numeric_pairs: List[tuple]
    ) -> Dict[str, Any]:
        """
        Calculate Pearson correlation using consolidated stats_tests.pearson_r.

        Args:
            numeric_pairs: List of (x, y) numeric pairs (lists)

        Returns:
            Dict with r, r_squared, n, p_value, significant
        """
        from src.survey.analysis.stats_tests import pearson_r

        if not numeric_pairs:
            return {"r": 0, "r_squared": 0, "n": 0, "p_value": 1.0, "significant": False}

        x_vals = [pair[0] for pair in numeric_pairs]
        y_vals = [pair[1] for pair in numeric_pairs]

        result = pearson_r(x_vals, y_vals)
        return result

    def _calculate_chi_square(
        self, cross_tab: Dict[str, Dict[str, int]], pairs: List[tuple]
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate chi-square test using consolidated stats_tests.chi_square.
        """
        from src.survey.analysis.stats_tests import chi_square

        if not cross_tab or not pairs:
            return None

        # Build observed matrix
        row_categories = list(cross_tab.keys())
        col_categories = list(pairs[0].keys()) if pairs and isinstance(pairs[0], dict) else []
        if not col_categories:
            return None

        observed = []
        for row_cat in row_categories:
            row_data = cross_tab.get(row_cat, {})
            observed.append([row_data.get(col_cat, 0) for col_cat in col_categories])

        if len(observed) < 2 or len(observed[0]) < 2:
            return None

        result = chi_square(observed)
        return {
            "chi_square": result["chi2_stat"],
            "df": result["df"],
            "p_value": result["p_value"],
            "significant": result["significant"],
        }
    
    def _calculate_chi_square(
        self, 
        cross_tab: Dict[str, int],
        pairs: List[tuple]
    ) -> Optional[Dict[str, Any]]:
        """
        P1-3 fix: Calculate chi-square test
        
        Args:
            cross_tab: Cross-tabulation table
            pairs: Raw data pairs
            
        Returns:
            Chi-square statistic and p-value
        """
        import math
        
        # Get unique values
        unique_a = list(set(p[0] for p in pairs))
        unique_b = list(set(p[1] for p in pairs))
        
        n_rows = len(unique_a)
        n_cols = len(unique_b)
        
        if n_rows < 2 or n_cols < 2:
            return None
        
        # Calculate expected frequencies
        row_totals = {}
        col_totals = {}
        total = len(pairs)
        
        for a, b in pairs:
            row_totals[a] = row_totals.get(a, 0) + 1
            col_totals[b] = col_totals.get(b, 0) + 1
        
        # Calculate chi-square statistic
        chi_sq = 0
        for a in unique_a:
            for b in unique_b:
                observed = cross_tab.get(f"{a}|{b}", 0)
                expected = (row_totals[a] * col_totals[b]) / total if total > 0 else 0
                if expected > 0:
                    chi_sq += (observed - expected) ** 2 / expected
        
        # Degrees of freedom
        df = (n_rows - 1) * (n_cols - 1)
        
        # Simplified p-value estimation (for df=1, chi_sq>3.84 means p<0.05)
        # This is a simplified version; actual implementation should use scipy.stats.chi2.sf
        p_value_estimate = 0.05 if chi_sq > 3.84 else 0.5  # Simplified estimate
        
        return {
            "chi_square": round(chi_sq, 4),
            "degrees_of_freedom": df,
            "p_value_estimate": p_value_estimate,
            "significant_at_005": chi_sq > 3.84,  # Critical value for df=1
        }
    
    def _generate_insights(
        self,
        statistics: Dict[str, Any],
        cross_analysis: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Generate insights."""
        insights = []
        
        # Generate insights based on statistics
        total = statistics.get("total_responses", 0)
        
        if total > 0:
            insights.append({
                "type": "overview",
                "title": "Response Overview",
                "description": f"Collected {total} valid responses",
            })
        
        # Analyze each question
        for q_id, q_stats in statistics.get("questions", {}).items():
            # Response rate insight
            response_rate = q_stats.get("response_rate", 0)
            if response_rate < 0.8:
                insights.append({
                    "type": "warning",
                    "title": f"Question {q_id} has low response rate",
                    "description": f"Response rate is {response_rate:.1%}, may need to optimize question phrasing",
                })
            
            # Distribution insight
            distribution = q_stats.get("distribution", {})
            if distribution:
                values = list(distribution.values())
                if values:
                    max_ratio = max(values) / sum(values) if sum(values) > 0 else 0
                    if max_ratio > 0.7:
                        top_answer = q_stats.get("top_answer")
                        if top_answer:
                            insights.append({
                                "type": "finding",
                                "title": f"Question {q_id} answers are concentrated",
                                "description": f"{max_ratio:.1%} of respondents chose '{top_answer[0]}'",
                            })
            
            # Rating insight
            if "mean" in q_stats:
                mean = q_stats["mean"]
                if mean >= 4:
                    insights.append({
                        "type": "positive",
                        "title": f"Question {q_id} has high rating",
                        "description": f"Average rating {mean:.2f}, overall good performance",
                    })
                elif mean <= 2:
                    insights.append({
                        "type": "negative",
                        "title": f"Question {q_id} has low rating",
                        "description": f"Average rating {mean:.2f}, needs attention",
                    })
        
        return insights
    
    def _generate_report(
        self,
        statistics: Dict[str, Any],
        insights: List[Dict[str, Any]],
        cross_analysis: Optional[Dict[str, Any]],
        report_format: str
    ) -> str:
        """Generate analysis report."""
        if report_format == "markdown":
            return self._generate_markdown_report(statistics, insights, cross_analysis)
        elif report_format == "json":
            import json
            return json.dumps({
                "statistics": statistics,
                "insights": insights,
                "cross_analysis": cross_analysis,
            }, ensure_ascii=False, indent=2)
        else:
            return self._generate_text_report(statistics, insights)
    
    def _generate_markdown_report(
        self,
        statistics: Dict[str, Any],
        insights: List[Dict[str, Any]],
        cross_analysis: Optional[Dict[str, Any]]
    ) -> str:
        """Generate Markdown format report."""
        lines = [
            "# Survey Analysis Report",
            "",
            f"**Total Responses**: {statistics.get('total_responses', 0)}",
            "",
            "## Key Findings",
            "",
        ]
        
        for insight in insights:
            lines.append(f"### {insight.get('title', 'Unknown')}")
            lines.append(f"- Type: {insight.get('type', 'unknown')}")
            lines.append(f"- {insight.get('description', '')}")
            lines.append("")
        
        lines.extend([
            "## Question Statistics",
            "",
        ])
        
        for q_id, q_stats in statistics.get("questions", {}).items():
            lines.append(f"### Question: {q_stats.get('text', q_id)}")
            lines.append(f"- Type: {q_stats.get('type', 'unknown')}")
            lines.append(f"- Response Rate: {q_stats.get('response_rate', 0):.1%}")
            
            if "distribution" in q_stats:
                lines.append("- Distribution:")
                for answer, count in q_stats["distribution"].items():
                    lines.append(f"  - {answer}: {count}")
            
            if "mean" in q_stats:
                lines.append(f"- Mean: {q_stats['mean']:.2f}")
                lines.append(f"- Median: {q_stats.get('median', 'N/A')}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def _generate_text_report(
        self,
        statistics: Dict[str, Any],
        insights: List[Dict[str, Any]]
    ) -> str:
        """Generate plain text report."""
        lines = [
            f"Survey Analysis Report",
            f"=" * 40,
            f"Total Responses: {statistics.get('total_responses', 0)}",
            "",
            "Key Findings:",
        ]
        
        for i, insight in enumerate(insights, 1):
            lines.append(f"{i}. {insight.get('title', '')}: {insight.get('description', '')}")
        
        return "\n".join(lines)
    
    # ==================== P0-2 fix: Chart generation integration ====================
    
    async def _generate_charts(
        self,
        statistics: Dict[str, Any],
        questions: List[Dict],
        output_dir: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate charts based on statistical data
        
        Args:
            statistics: Statistical results
            questions: Question list
            output_dir: Chart output directory
            
        Returns:
            List of chart information, each containing:
            - chart_type: Chart type
            - title: Chart title
            - path: Chart file path
            - question_id: Associated question ID
        """
        charts = []
        
        try:
            # Lazy import ChartGenerator
            if self._chart_generator is None:
                from src.services.chart_generator import ChartGenerator, ChartConfig, ChartType
                chart_output_dir = output_dir or str(Path(self.storage_path or "output") / "charts")
                self._chart_generator = ChartGenerator(output_dir=chart_output_dir)
            else:
                ChartConfig = type(self._chart_generator).__module__
                from src.services.chart_generator import ChartConfig, ChartType
            
            # Generate distribution chart for each choice question
            for q_id, q_stats in statistics.get("questions", {}).items():
                q_type = q_stats.get("type", "")
                distribution = q_stats.get("distribution", {})
                q_text = q_stats.get("text", f"Question {q_id}")
                
                if not distribution:
                    continue
                
                # Generate bar chart for choice questions
                if q_type in ["single_choice", "multiple_choice"]:
                    try:
                        from src.services.chart_generator import ChartConfig, ChartType
                        
                        categories = list(distribution.keys())
                        values = list(distribution.values())
                        total = sum(values)
                        percentages = [v / total * 100 if total > 0 else 0 for v in values]
                        
                        config = ChartConfig(
                            chart_type=ChartType.BAR,
                            title=q_text[:50],  # Limit title length
                            data={
                                "categories": categories,
                                "values": percentages,
                            },
                            ylabel="Percentage (%)",
                        )
                        
                        result = self._chart_generator.generate(config)
                        
                        if result.success and result.image_path:
                            charts.append({
                                "chart_type": "bar",
                                "title": q_text,
                                "path": result.image_path,
                                "question_id": q_id,
                            })
                            logger.info(f"Generated bar chart for question {q_id}: {result.image_path}")
                    except Exception as e:
                        logger.warning(f"Failed to generate chart for question {q_id}: {e}")
                
                # Generate distribution chart for rating questions
                elif q_type in ["scale", "likert"]:
                    try:
                        from src.services.chart_generator import ChartConfig, ChartType
                        
                        if "mean" in q_stats:
                            # Generate rating statistics (can be used for later visualization)
                            charts.append({
                                "chart_type": "stat",
                                "title": q_text,
                                "data": {
                                    "mean": q_stats.get("mean"),
                                    "median": q_stats.get("median"),
                                    "min": q_stats.get("min"),
                                    "max": q_stats.get("max"),
                                },
                                "question_id": q_id,
                            })
                    except Exception as e:
                        logger.warning(f"Failed to generate stat for question {q_id}: {e}")
            
            logger.info(f"Generated {len(charts)} charts for survey analysis")
            
        except ImportError as e:
            logger.warning(f"ChartGenerator not available: {e}")
        except Exception as e:
            logger.error(f"Chart generation failed: {e}", exc_info=True)
        
        return charts
