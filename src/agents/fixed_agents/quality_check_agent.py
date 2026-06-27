"""
Quality Check Agent
===================

Responsible for checking report quality and ensuring output meets standards.

Responsibilities:
1. Check content completeness (all sections present)
2. Check data accuracy (reasonable values)
3. Check logical consistency (no contradictions)
4. Check format compliance (follows template)
5. Generate quality score and improvement suggestions
6. Auto-fix quality issues (Phase 8 integration)

Input:
{
    "report": dict,             # Report content
    "checklist": list,          # Checklist items (optional)
    "standards": dict,          # Quality standards (optional)
}

Output:
{
    "success": bool,
    "quality_score": float,     # Quality score 0-100
    "passed": bool,             # Whether check passed
    "issues": list,             # List of issues
    "suggestions": list,        # Improvement suggestions
    "check_details": dict,      # Detailed check results
}
"""

import logging
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime
from pathlib import Path
from .base_fixed_agent import FixedAgent

from src.core.adjustment import RevisionService
from src.core.i18n import I18n

# Layer 1: 章节类型分析要素定义
# 每种章节类型有独立的要素清单，替代硬编码7关键词
SECTION_ELEMENT_REQUIREMENTS = {
    "market_size": [
        {"id": "current_scale", "patterns": [r"\d+\.?\d*\s*(亿|万|千亿)", r"市场规模", r"总量"], "weight": 0.20},
        {"id": "growth", "patterns": [r"(?:CAGR|增速|增长|增长率|增长速度)"], "weight": 0.15},
        {"id": "structure", "patterns": [r"(?:其中|占比|份额|segment|拆分|结构)"], "weight": 0.15},
        {"id": "drivers", "patterns": [r"(?:驱动|拉动|推动|driver|catalyst|因素)"], "weight": 0.15},
        {"id": "cross_validation", "patterns": [r"(?:交叉|验证|三角|triangulat|另据|对比)"], "weight": 0.15},
        {"id": "forecast", "patterns": [r"(?:假设|预测|预计|forecast|assumption|展望)"], "weight": 0.10},
        {"id": "uncertainty", "patterns": [r"(?:不确定|风险|边界|sensitivity|波动|区间)"], "weight": 0.10},
    ],
    "competition": [
        {"id": "market_share", "patterns": [r"(?:市占率|份额|集中度|CR\d|HHI|concentration)"], "weight": 0.20},
        {"id": "barriers", "patterns": [r"(?:壁垒|门槛|护城河|moat|barrier)"], "weight": 0.15},
        {"id": "rivalry", "patterns": [r"(?:竞争|对手|rival|五力|five.?force)"], "weight": 0.20},
        {"id": "positioning", "patterns": [r"(?:定位|差异化|strategy|战略|布局)"], "weight": 0.15},
        {"id": "substitutes", "patterns": [r"(?:替代|威胁|threat|颠覆)"], "weight": 0.15},
        {"id": "supplier_power", "patterns": [r"(?:供应商|议价|bargain|上游)"], "weight": 0.15},
    ],
    "technology": [
        {"id": "maturity", "patterns": [r"(?:成熟度|TRL|技术阶段|发展历程|iteration)"], "weight": 0.20},
        {"id": "trend", "patterns": [r"(?:趋势|方向|前沿|trend|roadmap|路线图)"], "weight": 0.20},
        {"id": "comparison", "patterns": [r"(?:对比|比较|vs?|versus|替代方案)"], "weight": 0.20},
        {"id": "ip", "patterns": [r"(?:专利|IP|知识产权|论文|publication)"], "weight": 0.15},
        {"id": "adoption", "patterns": [r"(?:应用|落地|商业化|adopt|渗透率)"], "weight": 0.15},
        {"id": "limits", "patterns": [r"(?:局限|瓶颈|挑战|limit|challenge|难题)"], "weight": 0.10},
    ],
    "risk": [
        {"id": "identification", "patterns": [r"(?:风险|risk|威胁|隐患)"], "weight": 0.20},
        {"id": "probability", "patterns": [r"(?:概率|可能性|likelihood|频率)"], "weight": 0.15},
        {"id": "impact", "patterns": [r"(?:影响|冲击|损失|impact|severity)"], "weight": 0.20},
        {"id": "mitigation", "patterns": [r"(?:应对|缓解|对冲|mitigat|控制)"], "weight": 0.20},
        {"id": "scenario", "patterns": [r"(?:情景|场景|scenario|假设)"], "weight": 0.15},
        {"id": "monitoring", "patterns": [r"(?:监控|预警|trigger|指标)"], "weight": 0.10},
    ],
    "financial_analysis": [
        {"id": "revenue", "patterns": [r"(?:营收|收入|revenue|销售额)"], "weight": 0.15},
        {"id": "profitability", "patterns": [r"(?:利润|利润率|净利|毛利|EBIT|margin)"], "weight": 0.20},
        {"id": "cash_flow", "patterns": [r"(?:现金流|现金流|cash.?flow|营运资金)"], "weight": 0.15},
        {"id": "leverage", "patterns": [r"(?:负债|杠杆|debt|D/E|偿债)"], "weight": 0.15},
        {"id": "efficiency", "patterns": [r"(?:周转|效率|turnover|ROA|ROE)"], "weight": 0.15},
        {"id": "growth_metrics", "patterns": [r"(?:增长|CAGR|增速|复合)"], "weight": 0.10},
        {"id": "valuation", "patterns": [r"(?:估值|P/E|P/B|EV|折现|DCF)"], "weight": 0.10},
    ],
    "policy": [
        {"id": "regulation", "patterns": [r"(?:政策|法规|regulation|监管|规制)"], "weight": 0.25},
        {"id": "impact_assessment", "patterns": [r"(?:影响|效果|impact|catalyst|利好)"], "weight": 0.20},
        {"id": "timeline", "patterns": [r"(?:时间表|实施|生效|阶段|过渡期)"], "weight": 0.15},
        {"id": "stakeholders", "patterns": [r"(?:利益相关方|stakeholder|主体|参与方)"], "weight": 0.15},
        {"id": "comparative", "patterns": [r"(?:国际|海外|compar|对比|借鉴)"], "weight": 0.15},
        {"id": "uncertainty_policy", "patterns": [r"(?:不确定|变数|调整|修订|博弈)"], "weight": 0.10},
    ],
    "enterprise": [
        {"id": "business_model", "patterns": [r"(?:商业模式|business.?model|盈利模式|变现)"], "weight": 0.20},
        {"id": "competitive_advantage", "patterns": [r"(?:优势|护城河|moat|壁垒|核心竞争力)"], "weight": 0.20},
        {"id": "financial_health", "patterns": [r"(?:财务|营收|利润|负债|现金流)"], "weight": 0.15},
        {"id": "strategy", "patterns": [r"(?:战略|strategy|规划|布局|方向)"], "weight": 0.15},
        {"id": "management", "patterns": [r"(?:管理|团队|管理层|治理|governance)"], "weight": 0.10},
        {"id": "growth_drivers", "patterns": [r"(?:增长|驱动|catalyst|引擎|扩张)"], "weight": 0.10},
        {"id": "risks", "patterns": [r"(?:风险|挑战|威胁|不确定)"], "weight": 0.10},
    ],
    "industry_chain": [
        {"id": "chain_structure", "patterns": [r"(?:产业链|价值链|value.?chain|上下游)"], "weight": 0.25},
        {"id": "value_distribution", "patterns": [r"(?:利润|价值|利润分配|利润池|pool)"], "weight": 0.20},
        {"id": "bargaining_power", "patterns": [r"(?:议价|bargain|话语权|定价权)"], "weight": 0.20},
        {"id": "bottlenecks", "patterns": [r"(?:瓶颈|制约|卡脖子|短板)"], "weight": 0.15},
        {"id": "integration", "patterns": [r"(?:整合|集成|协同|纵向|横向)"], "weight": 0.10},
        {"id": "ecosystem", "patterns": [r"(?:生态|ecosystem|平台|network)"], "weight": 0.10},
    ],
    "trend": [
        {"id": "historical", "patterns": [r"(?:历史|过去|回顾|变迁|演进)"], "weight": 0.15},
        {"id": "current_state", "patterns": [r"(?:当前|现状|目前|现有)"], "weight": 0.15},
        {"id": "driving_forces", "patterns": [r"(?:驱动|推动|force|catalyst|深层)"], "weight": 0.20},
        {"id": "future_projection", "patterns": [r"(?:预测|展望|forecast|趋势|预计)"], "weight": 0.20},
        {"id": "signals", "patterns": [r"(?:信号|sign|迹象|early|苗头)"], "weight": 0.15},
        {"id": "disruption", "patterns": [r"(?:颠覆|变革|disrupt|范式|转折)"], "weight": 0.15},
    ],
}

# 通用要素：所有章节类型都应包含的基础分析要素
GENERIC_ELEMENTS = [
    {"id": "core_conclusion", "patterns": [r"(?:核心结论|核心判断|结论|观点|看法|我们认为)"], "weight": 0.30},
    {"id": "argument_analysis", "patterns": [r"(?:论证|推导|逻辑|原因|因为|因此|分析|hence)"], "weight": 0.25},
    {"id": "data_support", "patterns": [r"(?:数据|数据支持|数据来源|据|统计)"], "weight": 0.25},
    {"id": "risk_disclosure", "patterns": [r"(?:风险提示|风险|不确定性|数据缺口|假设|然而|但需注意)"], "weight": 0.20},
]

logger = logging.getLogger(__name__)


class QualityCheckAgent(FixedAgent):
    """Quality Check Agent.
    
    Responsible for checking research report quality, ensuring content
    completeness, data accuracy, and logical consistency. This is the
    final checkpoint before report publication.
    """
    
    agent_type = "quality_check"
    version = "1.0.0"
    capabilities = [
        "Completeness check",
        "Data accuracy check",
        "Logical consistency check",
        "Format compliance check",
        "Quality scoring",
        "Improvement suggestions",
    ]

    # 融合权重（普通类变量，非 field；便于子类配置覆盖）
    FUSION_WEIGHTS: Dict[str, float] = {
        "quality_score": 0.6,
        "section_overall": 0.4,
    }
    
    # Default quality standards
    DEFAULT_STANDARDS = {
        "min_sections": 3,               # Minimum number of sections
        "max_error_rate": 0.05,          # Maximum error rate
        "required_sections": [],         # Required sections (empty = no hard requirement)
        "data_validation": {             # Data validation rules
            "check_numbers": True,       # Check number reasonableness
            "check_dates": True,         # Check date format
            "check_sources": False,      # Check data sources
        },
    }
    
    def validate_input(self, task_input: Dict[str, Any]) -> tuple[bool, str]:
        """Validate input parameters."""
        valid, error = super().validate_input(task_input)
        if not valid:
            return valid, error
        
        if "report" not in task_input:
            return False, "Missing required field 'report'"
        
        return True, ""

    def _get_fusion_weights(self) -> Dict[str, float]:
        """
        获取融合权重，优先使用 config 中的配置。

        config 格式:
            config["fusion_weights"] = {"quality_score": 0.5, "section_overall": 0.5}
        """
        config_weights = self.config.get("fusion_weights", None)

        if isinstance(config_weights, dict):
            total = sum(config_weights.values())
            if abs(total - 1.0) < 0.01:
                return config_weights
            else:
                logger.warning(
                    f"Fusion weights {config_weights} sum to {total}, "
                    f"expected 1.0. Using defaults."
                )

        return dict(self.FUSION_WEIGHTS)

    async def execute(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute quality check (async).
        
        Args:
            task_input: {
                "report": {
                    "title": "...",
                    "content": "...",
                    "sections": [...],
                    "word_count": 5000,
                },
                "standards": {...},
            }
        """
        report = task_input["report"]
        standards = task_input.get("standards", self.DEFAULT_STANDARDS)
        html_content = task_input.get("html_content", "")
        
        # Merge HTML content into report content for deeper checks
        if html_content and report.get("content"):
            report["content"] += "\n" + html_content
        elif html_content:
            report["content"] = html_content
        
        # Publish start event
        await self.publish_event("quality_check_started", {})
        
        issues = []
        suggestions = []
        check_details = {}
        
        # 1. Completeness check
        completeness_result = self._check_completeness(report, standards)
        check_details["completeness"] = completeness_result
        issues.extend(completeness_result.get("issues", []))
        suggestions.extend(completeness_result.get("suggestions", []))
        
        # 2. Data accuracy check
        accuracy_result = self._check_accuracy(report, standards)
        check_details["accuracy"] = accuracy_result
        issues.extend(accuracy_result.get("issues", []))
        suggestions.extend(accuracy_result.get("suggestions", []))
        
        # 3. Logical consistency check
        consistency_result = self._check_consistency(report)
        check_details["consistency"] = consistency_result
        issues.extend(consistency_result.get("issues", []))
        suggestions.extend(consistency_result.get("suggestions", []))
        
        # 4. Format compliance check
        format_result = self._check_format(report, standards)
        check_details["format"] = format_result
        issues.extend(format_result.get("issues", []))
        suggestions.extend(format_result.get("suggestions", []))
        
        # Calculate quality score
        quality_score = self._calculate_score(check_details, len(issues))
        
        # 5. Section-level quality check (check_by_sections integration)
        sections = report.get("sections", [])
        if not sections:
            if "result" in report and isinstance(report["result"], dict):
                sections = report["result"].get("sections", [])
            elif "data" in report and isinstance(report["data"], dict):
                sections = report["data"].get("sections", [])
        
        section_quality = {}
        if sections and isinstance(sections, list):
            try:
                session_id = task_input.get("session_id", "")
                research_id = task_input.get("task_id", "")
                section_quality = await self.check_by_sections(
                    sections, session_id=session_id, research_id=research_id
                )
                check_details["section_quality"] = section_quality
                
                for s_name, s_data in section_quality.get("section_results", {}).items():
                    for s_issue in s_data.get("issues", []):
                        s_issue["_section"] = s_name
                        issues.append(s_issue)
                
                for o_issue in section_quality.get("overall_issues", []):
                    issues.append(o_issue)
                
                section_overall = section_quality.get("overall_score", 0)
                if section_overall > 0:
                    weights = self._get_fusion_weights()
                    quality_score = (
                        quality_score * weights["quality_score"]
                        + section_overall * weights["section_overall"]
                    )
            except Exception as e:
                logger.warning(f"Section-level quality check failed: {e}")
        
        # Determine if passed
        # Robust gate: score + structural completeness.
        # Individual missing recommended sections or format issues do not block.
        high_severity_issues = [i for i in issues if i.get("severity") == "high"]
        placeholder_issues = [i for i in high_severity_issues if "占位符" in i.get("message", "") or "placeholder" in i.get("message", "").lower()]
        
        passed = (
            quality_score >= 60
            and completeness_result.get("passed", False)
            and len(high_severity_issues) <= 1  # allow 1 high-severity issue (fuzzy border)
            and len(placeholder_issues) == 0   # placeholder content always fails
        )
        
        # If there are low-severity issues, log but don't block
        if issues and passed:
            logger.info(f"Quality check passed, {len(issues)} low-severity issues can be ignored")
        
        # Write to shared state
        await self.write_shared_state(f"agent.{self.agent_id}.last_check", {
            "quality_score": quality_score,
            "passed": passed,
        })
        
        # Publish completion event
        await self.publish_event("quality_check_completed", {"passed": passed, "score": quality_score})
        
        return {
            "success": True,
            "quality_score": round(quality_score, 1),
            "passed": passed,
            "issues": issues,
            "suggestions": suggestions,
            "check_details": check_details,
            "check_time": datetime.now().isoformat(),
        }
    
    def _check_completeness(
        self, 
        report: Dict, 
        standards: Dict
    ) -> Dict[str, Any]:
        """Check content completeness."""
        issues = []
        suggestions = []
        
        # Ensure standards is a dict
        if standards is None:
            standards = {}
        
        # Get sections (support multiple formats)
        sections = report.get("sections", [])
        if not sections:
            # Try extracting from other fields
            if "result" in report:
                result = report["result"]
                if isinstance(result, dict) and "sections" in result:
                    sections = result["sections"]
                elif isinstance(result, list):
                    sections = result
            elif "data" in report:
                data = report["data"]
                if isinstance(data, dict) and "sections" in data:
                    sections = data["sections"]
        
        # Calculate word_count if not present
        word_count = report.get("word_count", 0)
        if word_count == 0 and sections:
            # Calculate word count from sections
            for section in sections:
                content = section.get("content", "") if isinstance(section, dict) else str(section)
                word_count += len(content)
        elif word_count == 0:
            # Try calculating directly from report
            content = report.get("content", "") or report.get("result", "")
            if isinstance(content, str):
                word_count = len(content)
            elif isinstance(content, dict):
                word_count = len(str(content))
        
        # Check section count (word count threshold removed — it was arbitrary and fragile)
        min_sections = standards.get("min_sections", 3)
        if len(sections) < min_sections:
            issues.append({
                "type": "completeness",
                "severity": "high",
                "message": f"Insufficient sections: current {len(sections)}, minimum {min_sections} required",
            })
            suggestions.append(f"Add sections, at least {min_sections - len(sections)} more")
        
        # Check required sections (advisory only, not blocking)
        required = standards.get("required_sections", [])
        section_titles = [s.get("title", "") if isinstance(s, dict) else str(s) for s in sections]
        
        def _section_matches(required_name: str, title: str) -> bool:
            if required_name == title:
                return True
            for section_id, names in I18n.SECTION_NAMES.items():
                if required_name in names.values():
                    if title in names.values():
                        return True
            return False
        
        for req_section in required:
            matched = any(_section_matches(req_section, t) for t in section_titles)
            if not matched:
                issues.append({
                    "type": "completeness",
                    "severity": "low",
                    "message": f"Missing recommended section: {req_section}",
                    "section": req_section,
                })
                suggestions.append(f"Add '{req_section}' section if applicable")
        
        # Check for placeholder/degraded sections
        import re
        placeholder_count = 0
        for section in sections:
            sec_content = section.get("content", "") if isinstance(section, dict) else str(section)
            if re.search(r'本章节数据不足|数据不足.*无法生成|请检查上游数据采集', sec_content):
                placeholder_count += 1
        if placeholder_count > 0:
            issues.append({
                "type": "completeness",
                "severity": "high",
                "message": f"{placeholder_count}/{len(sections)} sections contain placeholder/degraded content, not actual analysis",
            })
            suggestions.append(f"Re-run research to generate actual content for {placeholder_count} sections")
        
        # completeness only blocks on severe structural defects
        completeness_passed = len(sections) >= min_sections
        
        return {
            "passed": completeness_passed,
            "issues": issues,
            "suggestions": suggestions,
            "word_count": word_count,
            "section_count": len(sections),
        }
    
    def _check_accuracy(
        self, 
        report: Dict, 
        standards: Dict
    ) -> Dict[str, Any]:
        """Check data accuracy."""
        issues = []
        suggestions = []
        
        # Ensure standards is a dict
        if standards is None:
            standards = {}
        
        content = report.get("content", "")
        data_validation = standards.get("data_validation", {})
        
        # Check number reasonableness
        if data_validation.get("check_numbers", True):
            number_issues = self._validate_numbers(content)
            issues.extend(number_issues)
        
        # Check date format
        if data_validation.get("check_dates", True):
            date_issues = self._validate_dates(content)
            issues.extend(date_issues)
        
        # Check for common hallucinations and placeholder values
        hallucination_issues = self._check_hallucinations(content)
        issues.extend(hallucination_issues)
        
        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "suggestions": suggestions,
        }
    
    def _check_hallucinations(self, content: str, section_count: int = 0) -> List[Dict]:
        """Check for common hallucination patterns and placeholder values."""
        import re
        from collections import Counter
        issues = []
        
        # Check for degradation placeholder content
        placeholder_patterns = [
            r'本章节数据不足，无法生成完整分析',
            r'请检查上游数据采集是否完整',
            r'数据不足.*无法生成',
            r'Data insufficient.*cannot generate',
        ]
        for pp in placeholder_patterns:
            m = re.search(pp, content)
            if m:
                matched_text = m.group()[:50]
                issues.append({
                    "type": "accuracy",
                    "severity": "high",
                    "message": f"检测到降级占位符内容: '{matched_text}'，章节内容未实际生成",
                    "auto_fixable": False,
                })
                break
        
        compound_patterns = [
            (r'(\d+\.\d+)\s*万辆', '万辆'),
            (r'(\d+\.\d+)\s*亿元', '亿元'),
        ]
        for pattern, unit in compound_patterns:
            matches = re.findall(pattern, content)
            if len(matches) >= 3:
                unique_values = set(matches)
                if len(unique_values) <= 2:
                    issues.append({
                        "type": "accuracy",
                        "severity": "medium",
                        "message": f"疑似占位符重复: '{matches[0]}{unit}' 出现 {len(matches)} 次且无变化",
                    })
        
        profit_unit_issues = re.findall(r'净利润.{0,10}?([\d.]+)\s*万辆', content)
        if profit_unit_issues:
            valid_profit_unit = False
            for m in profit_unit_issues:
                try:
                    if float(m) > 500:
                        valid_profit_unit = True
                        break
                except (ValueError, TypeError):
                    valid_profit_unit = True
                    break
            if valid_profit_unit:
                issues.append({
                    "type": "accuracy",
                    "severity": "high",
                    "message": f"利润数据使用了'万辆'作为单位（{len(profit_unit_issues)}处），应为'亿元'",
                })
        
        year_placeholder = re.findall(r'\d+\.\d+年(?:[^度]|$)', content)
        if year_placeholder:
            for match in year_placeholder[:3]:
                issues.append({
                    "type": "accuracy",
                    "severity": "high",
                    "message": f"疑似占位符年份: '{match}'",
                })
        
        all_numbers = re.findall(r'(\d+\.\d+)', content)
        number_counts = Counter(all_numbers)
        
        if section_count <= 0:
            section_markers = re.findall(
                r'(?:#{1,3}\s|第[一二三四五六七八九十]+章|一[、.]|二[、.]|三[、.]|\d+[、.]\s)',
                content
            )
            section_count = max(len(section_markers), 1)
        reasonable_repeat_per_section = 3
        
        for num, count in number_counts.most_common(5):
            if count < 12 or float(num) <= 0:
                continue
            if 2000 <= float(num) <= 2100:
                continue
            
            context_snippets = []
            for m in re.finditer(re.escape(num), content):
                start = max(0, m.start() - 40)
                end = min(len(content), m.end() + 40)
                context_snippets.append(content[start:end])
            
            is_percentage = any(f'{num}%' in s or f'{num}％' in s for s in context_snippets)
            has_metric_keyword = any(
                any(kw in s for kw in ['同比', '变动', '增长', '下降', '下滑', '降幅', '增幅', '变化'])
                for s in context_snippets
            )
            diverse_contexts = len(set(context_snippets)) > len(context_snippets) * 0.3
            
            if count <= section_count * reasonable_repeat_per_section:
                continue
            
            if is_percentage and has_metric_keyword:
                issues.append({
                    "type": "accuracy",
                    "severity": "low",
                    "message": f"数值 '{num}' 在全文中出现 {count} 次，伴随财务指标关键词，可能为多章节重复引用",
                })
                continue
            
            if diverse_contexts:
                issues.append({
                    "type": "accuracy",
                    "severity": "low",
                    "message": f"数值 '{num}' 出现 {count} 次但上下文多样，可能为正常引用",
                })
                continue
            
            issues.append({
                "type": "accuracy",
                "severity": "medium",
                "message": f"数值 '{num}' 在全文中出现 {count} 次且上下文单一，可能为幻觉占位符",
            })
        
        return issues
    
    def _validate_numbers(self, content: str) -> List[Dict]:
        """Validate number reasonableness.
        
        Check for obviously unreasonable values.
        """
        import re
        issues = []
        
        # Find percentages (simplified check)
        percentages = re.findall(r'(\d+(?:\.\d+)?)\s*%', content)
        for p in percentages:
            value = float(p)
            if value > 1000:  # Percentage over 1000% may be problematic
                issues.append({
                    "type": "accuracy",
                    "severity": "medium",
                    "message": f"Abnormally high percentage detected: {p}%",
                })
        
        # Find years (check if reasonable)
        years = re.findall(r'20\d{2}', content)
        current_year = datetime.now().year
        for year_str in years:
            year = int(year_str)
            if year > current_year + 10:  # Prediction beyond 10 years
                issues.append({
                    "type": "accuracy",
                    "severity": "low",
                    "message": f"Long-term forecast year detected: {year}",
                })
        
        return issues
    
    def _validate_dates(self, content: str) -> List[Dict]:
        """Validate date format."""
        # Simplified implementation, could use dateutil etc.
        return []
    
    def _check_consistency(self, report: Dict) -> Dict[str, Any]:
        """Check logical consistency."""
        issues = []
        suggestions = []
        
        content = report.get("content", "")
        
        # Check for contradictions (simplified version)
        # Actual implementation could use LLM for semantic analysis
        
        # Check data reference consistency
        import re
        
        # Find all referenced data
        data_refs = re.findall(r'(\d+(?:\.\d+)?)\s*billion', content)
        if len(data_refs) > 1:
            # Check for obviously contradictory data
            values = [float(v) for v in data_refs]
            if max(values) > min(values) * 1000:  # Difference over 1000x
                issues.append({
                    "type": "consistency",
                    "severity": "medium",
                    "message": "Detected excessive data magnitude difference, please check if units are consistent",
                })
                suggestions.append("Standardize data units, or explain the reason for discrepancies")
        
        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "suggestions": suggestions,
        }
    
    def _check_format(
        self, 
        report: Dict, 
        standards: Dict
    ) -> Dict[str, Any]:
        """Check format compliance."""
        issues = []
        suggestions = []
        
        content = report.get("content", "")
        
        # Check title format
        if "# " not in content:
            issues.append({
                "type": "format",
                "severity": "low",
                "message": "Report is missing a top-level heading",
                "auto_fixable": False,  # Marked as not auto-fixable
            })
            suggestions.append("Add a top-level heading, e.g. '# Research Report Title'")
        
        # Check paragraph length
        paragraphs = content.split('\n\n')
        long_paragraphs = [p for p in paragraphs if len(p) > 1000]
        if len(long_paragraphs) > 3:
            issues.append({
                "type": "format",
                "severity": "low",
                "message": f"Found {len(long_paragraphs)} excessively long paragraphs, consider splitting",
                "auto_fixable": False,  # Marked as not auto-fixable
            })
            suggestions.append("Split long paragraphs into shorter ones to improve readability")
        
        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "suggestions": suggestions,
        }
    
    def _calculate_score(
        self, 
        check_details: Dict, 
        total_issues: int
    ) -> float:
        """Calculate quality score.
        
        Calculate comprehensive score based on all check results.
        """
        base_score = 100.0
        
        # Deduct based on issue count
        issue_penalty = min(total_issues * 5, 50)  # Max 50 point deduction
        
        # Adjust based on check pass rate
        passed_count = sum(
            1 for detail in check_details.values() 
            if detail.get("passed", False)
        )
        total_checks = len(check_details)
        
        if total_checks > 0:
            pass_rate = passed_count / total_checks
            score = base_score * pass_rate - issue_penalty
        else:
            score = base_score - issue_penalty
        
        return max(0, min(100, score))
    
    # ==================== Phase 8 Integration ====================
    
    async def execute_and_fix(
        self,
        task_input: Dict[str, Any],
        document_path: str,
        max_fix_rounds: int = 3,
        quality_threshold: float = 70.0,
        content_generator: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Execute quality check and auto-fix issues
        
        Phase 8 Integration: Use RevisionService for auto-fixing
        
        Args:
            task_input: Quality check input
            document_path: Document path
            max_fix_rounds: Maximum fix rounds
            quality_threshold: Quality threshold
            content_generator: Content generation callback (optional)
            
        Returns:
            Final check result and fix history
        """
        logger.info(f"Starting quality check with auto-fix for: {document_path}")
        
        # Initialize RevisionService
        revision_service = RevisionService(
            storage_path=str(Path(document_path).parent / "revisions"),
        )
        
        # Set content generation callback
        if content_generator:
            revision_service.set_content_generator(content_generator)
        
        fix_history = []
        current_path = document_path
        round_num = 0
        
        while round_num < max_fix_rounds:
            round_num += 1
            logger.info(f"Quality check round {round_num}")
            
            # Execute quality check
            check_result = await self.execute(task_input)
            quality_score = check_result.get("quality_score", 0)
            issues = check_result.get("issues", [])
            
            # Check if passed
            if quality_score >= quality_threshold and len(issues) == 0:
                logger.info(f"Quality check passed with score {quality_score}")
                return {
                    "success": True,
                    "final_score": quality_score,
                    "passed": True,
                    "document_path": current_path,
                    "fix_rounds": round_num,
                    "fix_history": fix_history,
                    "check_details": check_result.get("check_details", {}),
                }
            
            # Not passed, attempt fix
            logger.info(f"Quality issues found: {len(issues)}, attempting fix")
            
            # Convert issues to revision requests
            fix_result = await self._auto_fix_issues(
                issues=issues,
                document_path=current_path,
                revision_service=revision_service,
                task_id=task_input.get("task_id", "unknown"),
            )
            
            if not fix_result.get("success"):
                logger.warning(f"Auto-fix failed: {fix_result.get('error')}")
                break
            
            # Update path and history
            current_path = fix_result.get("revised_path", current_path)
            fix_history.append({
                "round": round_num,
                "issues_fixed": len(issues),
                "quality_before": quality_score,
                "quality_after": fix_result.get("new_quality_score"),
                "revised_path": current_path,
            })
            
            # Update document path in task_input
            if "report" in task_input:
                task_input["report"]["document_path"] = current_path
        
        # Reached max rounds without passing
        final_check = await self.execute(task_input)
        return {
            "success": False,
            "final_score": final_check.get("quality_score", 0),
            "passed": False,
            "document_path": current_path,
            "fix_rounds": round_num,
            "fix_history": fix_history,
            "remaining_issues": final_check.get("issues", []),
            "check_details": final_check.get("check_details", {}),
            "message": f"Reached max fix rounds ({max_fix_rounds}) without meeting threshold",
        }
    
    async def _auto_fix_issues(
        self,
        issues: List[Dict[str, Any]],
        document_path: str,
        revision_service: RevisionService,
        task_id: str,
    ) -> Dict[str, Any]:
        """
        Auto-fix quality issues
        
        Args:
            issues: List of issues
            document_path: Document path
            revision_service: Revision service
            task_id: Task ID
            
        Returns:
            Fix result
        """
        if not issues:
            return {"success": True, "revised_path": document_path}
        
        # Sort by severity
        sorted_issues = sorted(
            issues,
            key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("severity", "low"), 2)
        )
        
        # Execute fix for each section
        current_path = document_path
        fixes_applied = 0
        
        try:
            # Call RevisionService's correct API
            # revise_from_quality_check is an async method, needs await
            results = await revision_service.revise_from_quality_check(
                document_path=current_path,
                task_id=task_id,
                issues=sorted_issues,
                suggestions=[issue.get("suggestion", "") for issue in sorted_issues if issue.get("suggestion")],
                auto_fix=True,
            )
            
            # Process returned List[RevisionResult]
            for result in results:
                if result.success:
                    # RevisionResult uses document_path attribute
                    if result.document_path:
                        current_path = result.document_path
                    fixes_applied += 1
                    logger.info(f"Fixed issue: {result.revision_id}")
                else:
                    logger.warning(f"Failed to fix issue: {result.error}")
                    
        except Exception as e:
            logger.error(f"Auto-fix failed with exception: {e}", exc_info=True)
            return {
                "success": False,
                "revised_path": current_path,
                "fixes_applied": fixes_applied,
                "error": str(e),
            }
        
        return {
            "success": fixes_applied > 0,
            "revised_path": current_path,
            "fixes_applied": fixes_applied,
        }
    
    def _build_fix_feedback(self, issues: List[Dict[str, Any]]) -> str:
        """
        Build fix feedback text
        
        Convert issue list to natural language feedback
        """
        if not issues:
            return ""
        
        feedback_parts = ["Please fix the following quality issues:"]
        
        for i, issue in enumerate(issues, 1):
            issue_type = issue.get("type", "unknown")
            message = issue.get("message", "")
            severity = issue.get("severity", "low")
            
            feedback_parts.append(f"{i}. [{issue_type}] {message} (Severity: {severity})")
        
        return "\n".join(feedback_parts)

    def _check_placeholders(self, content: str) -> List[Dict]:
        """检测全量文本中的占位符模式"""
        import re
        issues = []
        
        compound_patterns = [
            (r'(\d+\.\d+)\s*万辆', '万辆'),
            (r'(\d+\.\d+)\s*亿元', '亿元'),
        ]
        for pattern, unit in compound_patterns:
            matches = re.findall(pattern, content)
            if len(matches) >= 3:
                unique_values = set(matches)
                if len(unique_values) <= 2:
                    issues.append({
                        "type": "accuracy",
                        "severity": "medium",
                        "message": f"疑似占位符重复: '{matches[0]}{unit}' 出现 {len(matches)} 次且无变化",
                    })
        
        year_placeholder = re.findall(r'\d+\.\d+年(?:[^度]|$)', content)
        if year_placeholder:
            for match in year_placeholder[:3]:
                issues.append({
                    "type": "accuracy",
                    "severity": "high",
                    "message": f"疑似占位符年份: '{match}'",
                })
        
        return issues

    def _calculate_section_score(self, content: str, issues: List[Dict],
                                  section_type: str = "generic") -> float:
        """Layer 1: 基于分析要素的章节质量评分

        按章节类型评估分析要素完整性，替代原7关键词计数。

        Args:
            content: 章节内容
            issues: 已有问题列表
            section_type: 章节类型 (market_size, competition, 等)

        Returns:
            0-100 分数
        """
        import re

        if not content or len(content.strip()) < 50:
            return max(0, 30 - sum(1 for i in issues if i.get("severity") == "high") * 10)

        # 选择该章节类型的要素清单
        elements = SECTION_ELEMENT_REQUIREMENTS.get(section_type, GENERIC_ELEMENTS)

        element_score = 0.0
        for elem in elements:
            matched = any(re.search(p, content) for p in elem["patterns"])
            if matched:
                element_score += elem["weight"]

        base_score = element_score * 100.0

        # 数据密度奖励（有数字说明有量化分析）
        numbers = re.findall(r'\d+\.?\d*', content)
        data_bonus = min(len(numbers) * 2, 10)

        # 问题惩罚
        severity_weights = {"high": 15, "medium": 5, "low": 1}
        penalty = sum(severity_weights.get(i.get("severity", "low"), 1) for i in issues)
        penalty = min(penalty, 40)

        score = base_score + data_bonus - penalty
        return max(0, min(100, score))

    def _generate_summary(self, section_results: Dict, overall_score: float) -> Dict:
        """生成质检汇总信息"""
        
        sorted_sections = sorted(
            section_results.items(), key=lambda x: x[1]["score"]
        )
        
        low_score_sections = [
            {"name": name, "score": data["score"],
             "main_issue": data["issues"][0]["message"] if data["issues"] else ""}
            for name, data in sorted_sections
            if data["score"] < 60
        ]
        
        high_score_sections = [
            {"name": name, "score": data["score"]}
            for name, data in sorted_sections
            if data["score"] >= 80
        ]
        
        fix_suggestions = []
        for name, data in sorted_sections:
            if data["score"] < 60:
                issue_types = set(i["type"] for i in data["issues"])
                if "completeness" in issue_types:
                    fix_suggestions.append({
                        "section": name,
                        "action": "补充分析框架",
                        "description": "该章节缺少核心判断或数据支持",
                    })
                if "accuracy" in issue_types:
                    fix_suggestions.append({
                        "section": name,
                        "action": "核实数据准确性",
                        "description": "该章节存在数据异常",
                    })
        
        return {
            "overall_score": overall_score,
            "overall_status": "passed" if overall_score >= 60 else "warning",
            "total_sections": len(section_results),
            "passed_sections": sum(1 for d in section_results.values() if d["score"] >= 60),
            "warning_sections": sum(1 for d in section_results.values() if d["score"] < 60),
            "low_score_sections": low_score_sections,
            "high_score_sections": high_score_sections,
            "fix_suggestions": fix_suggestions,
        }

    def _detect_section_type(self, section: Dict) -> str:
        """从 section id/title 推断章节类型"""
        sid = section.get("id", "")
        title = section.get("title", "")
        for known_type in SECTION_ELEMENT_REQUIREMENTS:
            if known_type in sid.lower() or known_type in title.lower():
                return known_type
        return "generic"

    async def check_by_sections(self, sections: List[Dict],
                                 session_id: str = "",
                                 research_id: str = "") -> Dict:
        """分章节质检（支持 per-agent 统计）"""
        import re
        section_results = {}
        agent_stats = {}
        
        for section in sections:
            section_name = section.get("title", "unknown")
            section_content = section.get("content", "")
            agent_id = section.get("agent_id", "unknown")
            section_type = self._detect_section_type(section)
            
            if not section_content or len(section_content.strip()) < 50:
                section_results[section_name] = {
                    "score": 0, "status": "empty", "issues": [],
                }
                agent_stats[agent_id] = {
                    "score": 0, "section": section_name, "status": "empty",
                }
                continue
            
            issues = []
            
            numbers = re.findall(r'\d+\.?\d*', section_content)
            if len(numbers) < 3:
                issues.append({
                    "type": "completeness",
                    "severity": "low",
                    "message": "章节数据密度偏低，建议补充量化支撑",
                })
            
            hallucination_issues = self._check_hallucinations(section_content)
            issues.extend(hallucination_issues)
            
            section_score = self._calculate_section_score(section_content, issues, section_type)
            
            from src.core.quality.quality_state import generate_issue_id
            for issue in issues:
                issue["id"] = generate_issue_id(section_name, issue.get("type", ""), issue.get("message", ""))
                issue["section"] = section_name
                issue["agent_id"] = agent_id
                if "state" not in issue:
                    issue["state"] = "open"
            
            section_results[section_name] = {
                "score": section_score,
                "status": "passed" if section_score >= 60 else "warning",
                "issues": issues,
                "content_length": len(section_content),
                "data_points_count": len(numbers),
                "agent_id": agent_id,
                "section_type": section_type,
            }
            
            agent_stats[agent_id] = {
                "score": section_score,
                "section": section_name,
                "status": "passed" if section_score >= 60 else "warning",
                "section_type": section_type,
            }
            
            if session_id:
                try:
                    from src.core.session_streamer import SessionStreamer
                    SessionStreamer.push_section_quality(session_id, section_name, section_results[section_name])
                except Exception:
                    pass
        
        overall_issues = []
        
        from src.core.quality.checkers import ReportQualityChecker
        checker = ReportQualityChecker(threshold=80.0)
        consistency_score = checker._check_cross_chapter_consistency(sections)
        if consistency_score < 80:
            overall_issues.append({
                "type": "consistency",
                "severity": "medium" if consistency_score < 60 else "low",
                "message": f"跨章节数值一致性评分: {consistency_score:.0f}/100",
            })
        
        report_dict = {"content": "\n".join(s.get("content", "") for s in sections)}
        format_issues = self._check_format(report_dict, self.DEFAULT_STANDARDS).get("issues", [])
        overall_issues.extend(format_issues)
        
        full_content = "\n".join(s.get("content", "") for s in sections)
        placeholder_issues = self._check_placeholders(full_content)
        overall_issues.extend(placeholder_issues)
        
        from src.core.quality.quality_state import generate_issue_id
        for issue in overall_issues:
            if "id" not in issue:
                issue["id"] = generate_issue_id("overall", issue.get("type", ""), issue.get("message", ""))
            if "section" not in issue:
                issue["section"] = "overall"
            if "state" not in issue:
                issue["state"] = "open"
        
        section_scores = []
        for r in section_results.values():
            score = r["score"]
            section_scores.append(score if score > 0 else 30)
        
        section_avg = sum(section_scores) / len(section_scores) if section_scores else 50
        
        overall_score = (
            section_avg * 0.7
            + consistency_score * 0.2
            + (100 - min(len(overall_issues) * 5, 30)) * 0.1
        )
        
        result = {
            "overall_score": round(overall_score, 1),
            "overall_status": "passed" if overall_score >= 60 else "warning",
            "overall_issues": overall_issues,
            "section_results": section_results,
            "agent_stats": agent_stats,
            "summary": self._generate_summary(section_results, overall_score),
        }
        
        if session_id:
            try:
                from src.core.session_streamer import SessionStreamer
                SessionStreamer.push_quality_result(session_id, result)
            except Exception:
                pass
        
        return result
