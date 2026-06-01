"""Survey analysis report builder - renders descriptive/sentiment/wordcloud/crosstab/charts into Markdown."""
from datetime import datetime
import os
from typing import Dict, Any, List, Optional
from ..models import Survey, SurveyResponse, QuestionType
from .descriptive import DescriptiveAnalyzer
from .sentiment import SentimentAnalyzer
from .wordcloud import WordCloudGenerator
from .crosstab import CrossTabAnalyzer


class SurveyReportBuilder:
    """Builds a comprehensive Markdown survey analysis report with optional charts."""

    def __init__(self, descriptive=None, sentiment=None, wordcloud=None, crosstab=None):
        self._descriptive = descriptive or DescriptiveAnalyzer()
        self._sentiment = sentiment or SentimentAnalyzer()
        self._wordcloud = wordcloud or WordCloudGenerator()
        self._crosstab = crosstab or CrossTabAnalyzer()

    def build(self, survey, responses, title="Survey Report", output_dir=None):
        """Build complete analysis report with optional charts."""
        desc = self._descriptive.analyze(survey, responses)
        open_texts = self._collect_open_texts(survey, responses)
        sentiment_result = {}
        if open_texts:
            sentiment_result = self._sentiment.analyze_batch(open_texts)
        wordcloud_result, wordcloud_image = {}, None
        if open_texts and output_dir:
            wc_path = os.path.join(output_dir, "wordcloud.png")
            wordcloud_result = self._wordcloud.generate(open_texts, output_path=wc_path)
            wordcloud_image = wordcloud_result.get("image_path")
        cross_results = self._crosstab.auto_discover(survey, responses, max_pairs=3)

        # Generate charts for key distributions
        chart_paths = {}
        if output_dir:
            chart_paths = self._generate_charts(survey, desc, output_dir)

        report_md = self._render_markdown(survey, title, desc, sentiment_result,
                                          wordcloud_result, cross_results, chart_paths)
        return {
            "report": report_md,
            "statistics": desc,
            "sentiment": sentiment_result,
            "wordcloud": wordcloud_result,
            "cross_tabulations": cross_results,
            "wordcloud_image": wordcloud_image,
            "charts": chart_paths,
            "generated_at": datetime.now().isoformat(),
        }

    def _generate_charts(self, survey, desc, output_dir):
        """Generate bar charts for key distributions. Returns dict of question_id -> image path."""
        charts = {}
        try:
            from src.services.chart_generator import ChartGenerator, ChartConfig, ChartType
            gen = ChartGenerator()
            per_q = desc.get("per_question", {})
            for qid, qstats in per_q.items():
                dist = qstats.get("stats", {}).get("distribution", {})
                if not dist or len(dist) < 2:
                    continue
                labels = list(dist.keys())[:10]
                values = [dist[l].get("count", 0) for l in labels]
                chart_path = os.path.join(output_dir, f"chart_{qid}.png")
                result = gen.generate(ChartConfig(
                    chart_type=ChartType.BAR,
                    title=qstats.get("question_text", qid)[:60],
                    data={"categories": labels, "values": values},
                    xlabel="Response",
                    ylabel="Count",
                ))
                if result.success:
                    charts[qid] = result.image_path
        except Exception as e:
            pass
        return charts

    def _collect_open_texts(self, survey, responses):
        texts = []
        open_ids = [q.question_id for q in survey.questions if q.question_type == QuestionType.OPEN_ENDED]
        for r in responses:
            for qid in open_ids:
                ans = r.get_answer(qid)
                if ans and ans.answer_value:
                    texts.append(str(ans.answer_value))
        return texts

    def _render_markdown(self, survey, title, desc, sentiment, wordcloud, cross_results, charts):
        lines = [f"# {title}", "", f"**Survey**: {survey.title}",
                 f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
        lines.append("---")
        ov = desc.get("overall", {})
        lines.extend(["", "## 1. Overview", "",
                       f"- **Total responses**: {desc.get('total_responses', 0)}",
                       f"- **Valid responses**: {desc.get('valid_responses', 0)}",
                       f"- **Completion rate**: {ov.get('completion_rate', 0)*100:.1f}%",
                       f"- **Avg duration**: {ov.get('avg_duration_seconds', 0)}s", ""])
        lines.extend(["## 2. Per-Question Statistics", ""])
        for qid, qstats in desc.get("per_question", {}).items():
            lines.append(f"### Q: {qstats.get('question_text', '')}")
            lines.append(f"*Type: {qstats.get('question_type', '')} | Answered: {qstats.get('total', 0)} | Skipped: {qstats.get('skipped', 0)}*")
            lines.append("")
            # Embed chart if available
            if qid in charts:
                lines.append(f"![Chart]({charts[qid]})")
                lines.append("")
            stats = qstats.get("stats", {})
            if "distribution" in stats:
                lines.extend(["| Option | Count | % |", "|--------|-------|---|"])
                for opt, data in stats["distribution"].items():
                    lines.append(f"| {opt} | {data.get('count', 0)} | {data.get('percentage', 0)}% |")
                lines.append("")
            if "mean" in stats:
                lines.append(f"- **Mean**: {stats.get('mean', '')} | **Median**: {stats.get('median', '')} | **Std**: {stats.get('std', '')}")
                lines.append("")
            if "avg_length" in stats:
                lines.append(f"- **Avg words**: {stats.get('avg_length', 0)} | **Min**: {stats.get('min_length', 0)} | **Max**: {stats.get('max_length', 0)}")
                lines.append("")
        if sentiment:
            overall = sentiment.get("overall", {})
            lines.extend(["## 3. Sentiment Analysis", "",
                           f"- **Positive**: {overall.get('positive', 0)}%",
                           f"- **Neutral**: {overall.get('neutral', 0)}%",
                           f"- **Negative**: {overall.get('negative', 0)}%",
                           f"- **Avg score**: {sentiment.get('avg_score', 0):.3f}", ""])
        if wordcloud and wordcloud.get("frequencies"):
            lines.extend(["## 4. Top Keywords", "",
                           f"Total words: {wordcloud.get('total_words', 0)}, Unique: {wordcloud.get('unique_words', 0)}", "",
                           "| Word | Count | % |", "|------|-------|---|"])
            for item in wordcloud["frequencies"][:20]:
                lines.append(f"| {item['word']} | {item['count']} | {item['percentage']}% |")
            lines.append("")
            if wordcloud.get("image_path"):
                lines.append(f"![Wordcloud]({wordcloud['image_path']})")
                lines.append("")
        if cross_results:
            lines.extend(["## 5. Cross-Tabulations", ""])
            for cr in cross_results[:2]:
                lines.append(f"### {cr.get('row_question', '')} x {cr.get('col_question', '')}")
                lines.append("")
                # Show chi-square if available
                chi_sq = cr.get("chi_square")
                if chi_sq:
                    sig = "significant" if chi_sq.get("significant") else "not significant"
                    lines.append(f"*Chi-square test: χ²={chi_sq.get('chi2_stat', '')}, "
                                 f"p={chi_sq.get('p_value', '')} ({sig})*")
                    lines.append("")
                table = cr.get("table", {})
                if table:
                    cols = list(next(iter(table.values())).keys())
                    header = "| " + " | ".join(cols) + " | Total |"
                    sep = "|" + "|".join(["---"] * (len(cols) + 2)) + "|"
                    lines.extend([header, sep])
                    for row_label, col_data in table.items():
                        row_vals = [str(v.get("count", 0)) for v in col_data.values()]
                        row_total = str(sum(v.get("count", 0) for v in col_data.values()))
                        lines.append(f"| {row_label} | {' | '.join(row_vals)} | {row_total} |")
                lines.append("")
        lines.extend(["---", "*Generated by Zensers AI*"])
        return "\n".join(lines)
