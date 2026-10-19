"""
Report Generation Agent
=======================

Integrates analysis results and generates complete research reports.

Responsibilities:
1. Receive output results from various analysis Agents
2. Organize content according to chapter structure
3. Generate coherent, professional report text
4. Add transition paragraphs to ensure logical flow

Input:
{
    "title": str,               # Report title
    "sections": list,           # List of chapters and content
    "template_type": str,       # Template type
    "style_guide": dict,        # Style guide (optional)
    "language": str,            # Output language (optional, default: "zh")
}

Output:
{
    "success": bool,
    "report": {
        "title": str,
        "content": str,         # Complete report content (Markdown format)
        "sections": list,       # Content of each chapter
        "word_count": int,      # Word count
        "estimated_pages": int, # Estimated pages
    },
    "metadata": {
        "generation_time": str,
        "version": str,
    }
}
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from .base_fixed_agent import FixedAgent
from src.core.i18n import get_localized_text, set_language, get_language, Language


# Report labels for i18n
REPORT_LABELS = {
    "research_report": {
        "zh": "研究报告",
        "en": "Research Report",
        "ja": "研究報告",
        "ko": "연구 보고서",
    },
    "publish_date": {
        "zh": "发布日期",
        "en": "Publish Date",
        "ja": "公開日",
        "ko": "발행일",
    },
    "report_type": {
        "zh": "报告类型",
        "en": "Report Type",
        "ja": "報告種別",
        "ko": "보고서 유형",
    },
    "disclaimer_short": {
        "zh": "本报告仅供参考，不构成投资建议",
        "en": "This report is for reference only and does not constitute investment advice",
        "ja": "本報告書は参考用であり、投資アドバイスを構成しません",
        "ko": "본 보고서는 참고용이며 투자 조언을 구성하지 않습니다",
    },
    "toc": {
        "zh": "目录",
        "en": "Table of Contents",
        "ja": "目次",
        "ko": "목차",
    },
    "exec_summary": {
        "zh": "执行摘要",
        "en": "Executive Summary",
        "ja": "エグゼクティブサマリー",
        "ko": "요약",
    },
    "conclusion": {
        "zh": "研究结论",
        "en": "Conclusion",
        "ja": "結論",
        "ko": "결론",
    },
    "appendix": {
        "zh": "附录",
        "en": "Appendix",
        "ja": "付録",
        "ko": "부록",
    },
    "chapter": {
        "zh": "章节",
        "en": "Chapter",
        "ja": "章",
        "ko": "장",
    },
    "chapter_summary": {
        "zh": "本章小结",
        "en": "Chapter Summary",
        "ja": "章のまとめ",
        "ko": "장 요약",
    },
    "data_sources": {
        "zh": "数据来源",
        "en": "Data Sources",
        "ja": "データソース",
        "ko": "데이터 출처",
    },
    "methodology": {
        "zh": "研究方法",
        "en": "Research Methodology",
        "ja": "研究方法",
        "ko": "연구 방법",
    },
    "desk_research": {
        "zh": "桌面研究：收集整理公开资料",
        "en": "Desk Research: Collect and organize public information",
        "ja": "デスクリサーチ：公開資料の収集・整理",
        "ko": "데스크 리서치: 공개 정보 수집 및 정리",
    },
    "data_analysis_method": {
        "zh": "数据分析：运用统计方法处理数据",
        "en": "Data Analysis: Apply statistical methods to process data",
        "ja": "データ分析：統計手法を用いたデータ処理",
        "ko": "데이터 분석: 통계적 방법 적용",
    },
    "expert_interview": {
        "zh": "专家访谈：补充定性洞察",
        "en": "Expert Interview: Supplement qualitative insights",
        "ja": "専門家インタビュー：定性的洞察の補完",
        "ko": "전문가 인터뷰: 정성적 통찰 보완",
    },
    "data_source_text": {
        "zh": "本报告数据来源于公开市场信息、行业数据库及专家访谈。",
        "en": "Data in this report comes from public market information, industry databases, and expert interviews.",
        "ja": "本報告書のデータは、公開市場情報、業界データベース、専門家インタビューから得ています。",
        "ko": "본 보고서의 데이터는 공개 시장 정보, 산업 데이터베이스 및 전문가 인터뷰에서 얻었습니다.",
    },
}

# Report type names for i18n
REPORT_TYPE_NAMES = {
    "market_research": {
        "zh": "市场研究报告",
        "en": "Market Research Report",
        "ja": "市場研究報告",
        "ko": "시장 연구 보고서",
    },
    "investment": {
        "zh": "投资研究报告",
        "en": "Investment Research Report",
        "ja": "投資研究報告",
        "ko": "투자 연구 보고서",
    },
    "policy": {
        "zh": "政策分析报告",
        "en": "Policy Analysis Report",
        "ja": "政策分析報告",
        "ko": "정책 분석 보고서",
    },
    "competitor": {
        "zh": "竞品分析报告",
        "en": "Competitor Analysis Report",
        "ja": "競合分析報告",
        "ko": "경쟁사 분석 보고서",
    },
    "technology": {
        "zh": "技术调研报告",
        "en": "Technology Research Report",
        "ja": "技術調査報告",
        "ko": "기술 조사 보고서",
    },
}


def _t(key: str, lang: Language) -> str:
    """Get localized text from REPORT_LABELS."""
    label_dict = REPORT_LABELS.get(key, {})
    return get_localized_text(label_dict, lang)


class ReportGenerationAgent(FixedAgent):
    """Report Generation Agent.
    
    Responsible for integrating outputs from various analysis Agents into a 
    complete, coherent research report. Ensures clear structure, logical flow,
    and consistent style.
    """
    
    agent_type = "report_generation"
    version = "1.0.0"
    capabilities = [
        "content_integration",
        "structure_organization",
        "style_unification",
        "logical_flow",
        "report_formatting",
    ]
    
    # Report templates
    REPORT_TEMPLATES = {
        "market_research": {
            "structure": [
                "cover", "toc", "exec_summary", "body", "appendix"
            ],
            "style": "formal",
            "tone": "professional",
        },
        "investment": {
            "structure": [
                "cover", "exec_summary", "body", "financials", "risk_factors"
            ],
            "style": "concise",
            "tone": "persuasive",
        },
        "policy": {
            "structure": [
                "cover", "toc", "overview", "analysis", "recommendations"
            ],
            "style": "formal",
            "tone": "neutral",
        },
    }
    
    def validate_input(self, task_input: Dict[str, Any]) -> tuple[bool, str]:
        """Validate input parameters."""
        valid, error = super().validate_input(task_input)
        if not valid:
            return valid, error
        
        required_fields = ["title", "sections"]
        for field in required_fields:
            if field not in task_input:
                return False, f"Missing required field '{field}'"
        
        if not isinstance(task_input["sections"], list):
            return False, "'sections' must be a list"
        
        return True, ""
    
    async def execute(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute report generation (async).
        
        **Fix**: Separate rendering by type to avoid duplicate summary and reversed order.
        
        Args:
            task_input: {
                "title": "Energy Storage Industry Research Report",
                "sections": [                    # Body chapters only (analysis phase)
                    {"id": "market_size", "title": "Market Size", "content": "..."},
                    ...
                ],
                "exec_summary": "...",           # Executive summary content (optional, pre-generated)
                "conclusion": "...",             # Conclusion content (optional, pre-generated)
                "template_type": "market_research",
                "style_guide": {...},
                "language": "zh",                # Output language (optional)
            }
        """
        title = task_input["title"]
        sections = task_input["sections"]
        exec_summary_content = task_input.get("exec_summary")  # Pre-generated executive summary
        conclusion_content = task_input.get("conclusion")      # Pre-generated conclusion
        template_type = task_input.get("template_type", "market_research")
        style_guide = task_input.get("style_guide", {})
        
        # Set output language
        language = task_input.get("language", "zh")
        if isinstance(language, str):
            try:
                lang = Language(language.lower())
            except ValueError:
                lang = Language.ZH
        else:
            lang = language
        set_language(lang)
        
        # Publish start event
        await self.publish_event("report_generation_started", {"title": title})
        self._report_progress(f"Generating report: {title}", "writing")
        
        # 1. Generate cover
        cover = self._generate_cover(title, template_type, lang)
        
        # 2. Generate table of contents
        toc = self._generate_toc(
            sections, 
            has_exec_summary=bool(exec_summary_content), 
            has_conclusion=bool(conclusion_content),
            lang=lang
        )
        
        # 3. Generate executive summary
        # Prefer pre-generated summary content, otherwise generate from sections
        if exec_summary_content:
            exec_summary = self._format_exec_summary(exec_summary_content, lang)
        else:
            exec_summary = self._generate_exec_summary(sections, lang)
        
        # 4. Integrate body content
        body_content = self._integrate_body(sections, style_guide, lang)
        
        # 5. Generate conclusion
        # Prefer pre-generated conclusion content
        if conclusion_content:
            conclusion = self._format_conclusion(conclusion_content, lang)
        else:
            conclusion = ""
        
        # 6. Generate appendix (if any)
        appendix = self._generate_appendix(sections, lang)
        
        # 7. Assemble complete report
        full_report = self._assemble_report(
            cover, toc, exec_summary, body_content, conclusion, appendix
        )
        
        # 8. Calculate statistics
        word_count = len(full_report)
        estimated_pages = word_count // 800 + 1  # Rough estimate
        
        # Write to shared state
        await self.write_shared_state(f"agent.{self.agent_id}.last_report", {
            "title": title,
            "word_count": word_count,
        })
        
        return {
            "success": True,
            "report": {
                "title": title,
                "content": full_report,
                "sections": [
                    {
                        "id": s.get("id", ""),
                        "title": s.get("title", ""),
                        "word_count": len(s.get("content", "")),
                    }
                    for s in sections
                ],
                "word_count": word_count,
                "estimated_pages": estimated_pages,
            },
            "metadata": {
                "generation_time": datetime.now().isoformat(),
                "version": self.version,
                "template_type": template_type,
                "language": lang.value,
            }
        }
    
    def _generate_cover(self, title: str, template_type: str, lang: Language) -> str:
        """Generate cover page."""
        # Format date based on language
        if lang == Language.ZH:
            date_str = datetime.now().strftime("%Y年%m月")
        elif lang == Language.JA:
            date_str = datetime.now().strftime("%Y年%m月")
        elif lang == Language.KO:
            date_str = datetime.now().strftime("%Y년 %m월")
        else:
            date_str = datetime.now().strftime("%B %Y")
        
        cover = f"""# {title}

**{_t("research_report", lang)}**

---

**{_t("publish_date", lang)}**：{date_str}

**{_t("report_type", lang)}**：{self._get_report_type_name(template_type, lang)}

**{_t("disclaimer_short", lang)}**

---

"""
        return cover
    
    def _get_report_type_name(self, template_type: str, lang: Language) -> str:
        """Get report type name."""
        type_dict = REPORT_TYPE_NAMES.get(template_type, REPORT_TYPE_NAMES.get("market_research", {}))
        return get_localized_text(type_dict, lang)
    
    def _generate_toc(
        self, 
        sections: List[Dict], 
        has_exec_summary: bool = True, 
        has_conclusion: bool = False,
        lang: Language = Language.ZH
    ) -> str:
        """Generate table of contents with three-level support."""
        toc_lines = [f"## {_t('toc', lang)}\n"]
        
        chapter_num = 1
        
        # Executive summary
        if has_exec_summary:
            exec_summary_label = _t("exec_summary", lang)
            toc_lines.append(f"{chapter_num}. [{exec_summary_label}](#{exec_summary_label})")
            chapter_num += 1
        
        # Each chapter
        for section in sections:
            title = section.get("title", f"{_t('chapter', lang)}{chapter_num}")
            anchor = self._generate_anchor(title)
            toc_lines.append(f"{chapter_num}. [{title}](#{anchor})")
            
            subsections = section.get("subsections", [])
            for j, subsec in enumerate(subsections, start=1):
                sub_title = subsec.get("title", "")
                if sub_title:
                    sub_anchor = self._generate_anchor(sub_title)
                    toc_lines.append(f"   {chapter_num}.{j} [{sub_title}](#{sub_anchor})")
            
            chapter_num += 1
        
        # Conclusion
        if has_conclusion:
            conclusion_label = _t("conclusion", lang)
            toc_lines.append(f"{chapter_num}. [{conclusion_label}](#{conclusion_label})")
            chapter_num += 1
        
        # Appendix
        appendix_label = _t("appendix", lang)
        toc_lines.append(f"{chapter_num}. [{appendix_label}](#{appendix_label})")
        
        toc_lines.append("\n---\n")
        return "\n".join(toc_lines)
    
    def _generate_anchor(self, title: str) -> str:
        """Generate Markdown anchor."""
        # Simple handling: remove special characters, convert to lowercase
        anchor = title.lower().replace(" ", "-").replace("&", "")
        return anchor
    
    def _generate_exec_summary(self, sections: List[Dict], lang: Language) -> str:
        """Generate executive summary.
        
        Generate key findings summary based on chapter content.
        Actual implementation can use LLM for smarter summaries.
        """
        summary_parts = [f"## {_t('exec_summary', lang)}\n"]
        
        # Extract key findings (simplified version)
        key_findings = []
        for section in sections:
            title = section.get("title", "")
            content = section.get("content", "")
            
            # Extract first two sentences as key findings
            if lang == Language.ZH or lang == Language.JA:
                sentences = content.split("。")[:2]
                if sentences:
                    finding = f"- **{title}**：{sentences[0]}。"
                    key_findings.append(finding)
            else:
                sentences = content.split(". ")[:2]
                if sentences:
                    finding = f"- **{title}**: {sentences[0]}."
                    key_findings.append(finding)
        
        summary_parts.extend(key_findings)
        summary_parts.append("\n---\n")
        
        return "\n".join(summary_parts)
    
    def _format_exec_summary(self, content: str, lang: Language) -> str:
        """Format pre-generated executive summary.
        
        Args:
            content: Pre-generated executive summary content
            lang: Target language
            
        Returns:
            Formatted executive summary (with title and separator)
        """
        exec_summary_label = _t("exec_summary", lang)
        
        # If content already contains executive summary title, use directly
        if content.strip().startswith(f"## {exec_summary_label}") or content.strip().startswith(f"# {exec_summary_label}"):
            return f"{content.strip()}\n\n---\n"
        
        # Otherwise add title
        return f"## {exec_summary_label}\n\n{content.strip()}\n\n---\n"
    
    def _format_conclusion(self, content: str, lang: Language) -> str:
        """Format conclusion.
        
        Args:
            content: Pre-generated conclusion content
            lang: Target language
            
        Returns:
            Formatted conclusion (with title and separator)
        """
        conclusion_label = _t("conclusion", lang)
        
        # If content already contains conclusion title, use directly
        if content.strip().startswith(f"## {conclusion_label}") or content.strip().startswith(f"# {conclusion_label}"):
            return f"{content.strip()}\n\n---\n"
        
        # Otherwise add title
        return f"## {conclusion_label}\n\n{content.strip()}\n\n---\n"
    
    def _integrate_body(self, sections: List[Dict], style_guide: Dict, lang: Language) -> str:
        """Integrate body content with three-level structure support."""
        sections = self._apply_content_quality(sections)
        
        body_parts = []
        
        for i, section in enumerate(sections, start=1):
            title = section.get("title", f"{_t('chapter', lang)} {i}")
            content = section.get("content", "")
            subsections = section.get("subsections", [])
            
            # Level 1: chapter title
            body_parts.append(f"## {i}. {title}\n")
            
            if subsections:
                # Three-level mode: render subsections with ### and points with ####
                for j, subsec in enumerate(subsections, start=1):
                    sub_title = subsec.get("title", "")
                    sub_content = subsec.get("content", "")
                    sub_points = subsec.get("points", [])
                    
                    if sub_title:
                        body_parts.append(f"### {i}.{j} {sub_title}\n")
                    
                    if sub_content:
                        body_parts.append(sub_content)
                    
                    if sub_points:
                        for pt in sub_points:
                            if isinstance(pt, str):
                                pt_text = pt
                            elif isinstance(pt, dict):
                                if lang == Language.ZH:
                                    pt_text = pt.get("zh", pt.get("en", str(pt)))
                                else:
                                    pt_text = pt.get("en", pt.get("zh", str(pt)))
                            else:
                                pt_text = str(pt)
                            if pt_text:
                                body_parts.append(f"#### {pt_text}\n")
            else:
                # One-level fallback: just add flat content
                body_parts.append(content)
            
            if section.get("include_summary", False):
                summary = self._generate_section_summary(content)
                body_parts.append(f"\n> **{_t('chapter_summary', lang)}**：{summary}\n")
            
            body_parts.append("\n---\n")
        
        return "\n".join(body_parts)
    
    def _apply_content_quality(self, sections: List[Dict]) -> List[Dict]:
        """
        Apply content quality pipeline.
        
        Args:
            sections: Original chapter list
            
        Returns:
            Cleaned chapter list
        """
        if not sections:
            return sections
        
        try:
            from src.core.orchestrator.aggregation.content_quality import create_default_pipeline
            pipeline = create_default_pipeline()
            return pipeline.process_sections(sections)
        except ImportError:
            # Fallback: try relative import
            try:
                from ...core.orchestrator.aggregation.content_quality import create_default_pipeline
                pipeline = create_default_pipeline()
                return pipeline.process_sections(sections)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Content quality pipeline not available: {e}")
                return sections
    
    def _generate_section_summary(self, content: str) -> str:
        """Generate chapter summary.
        
        Actual implementation can use LLM for more accurate summaries.
        """
        # Simplified version: return first 50 characters
        if len(content) > 50:
            return content[:50] + "..."
        return content
    
    def _generate_appendix(self, sections: List[Dict], lang: Language) -> str:
        """Generate appendix."""
        appendix_parts = [f"## {_t('appendix', lang)}\n"]
        
        # Data sources
        appendix_parts.append(f"### {_t('data_sources', lang)}\n")
        appendix_parts.append(_t("data_source_text", lang))
        appendix_parts.append("\n")
        
        # Research methodology
        appendix_parts.append(f"### {_t('methodology', lang)}\n")
        appendix_parts.append(f"- {_t('desk_research', lang)}")
        appendix_parts.append(f"- {_t('data_analysis_method', lang)}")
        appendix_parts.append(f"- {_t('expert_interview', lang)}")
        appendix_parts.append("\n")
        
        return "\n".join(appendix_parts)
    
    def _assemble_report(
        self,
        cover: str,
        toc: str,
        exec_summary: str,
        body: str,
        conclusion: str,
        appendix: str
    ) -> str:
        """Assemble complete report.
        
        **Fix**: Support conclusion section.
        
        Assembly order: Cover → TOC → Executive Summary → Body → Conclusion → Appendix
        """
        parts = [
            cover,
            toc,
            exec_summary,
            body,
        ]
        
        # Add conclusion (if any)
        if conclusion:
            parts.append(conclusion)
        
        parts.append(appendix)
        
        return "\n".join(parts)
