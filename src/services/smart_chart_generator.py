# -*- coding: utf-8 -*-
"""
Smart Chart Generator
=====================

Automatically analyzes section content, identifies data suitable for visualization, and generates professional charts.

Core features:
1. Data pattern recognition - Extract visualizable data from text
2. Chart type recommendation - Recommend appropriate chart types based on data characteristics
3. Auto chart generation - Call ChartGenerator to generate charts

Trigger conditions (auto-detection):
- Market share, proportion data → Pie/Bar chart
- Trends, growth, changes → Line chart
- Comparison, ranking → Bar/Horizontal bar chart
- Multi-dimensional evaluation → Radar chart
- Time series → Line/Bar chart
"""

import logging
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.services.chart_generator import ChartGenerator, ChartType, ChartConfig

logger = logging.getLogger(__name__)


@dataclass
class ChartSuggestion:
    """Chart suggestion"""
    chart_type: ChartType
    title: str
    data: Dict[str, Any]
    caption: str
    confidence: float  # 0.0 - 1.0
    reason: str  # Why this chart is recommended


class SmartChartGenerator:
    """
    Smart Chart Generator
    
    Automatically analyzes content, identifies data patterns, recommends and generates charts.
    
    Usage example:
        generator = SmartChartGenerator()
        
        # Analyze section content
        suggestions = generator.analyze_content(
            section_title="Market Share Analysis",
            content="BYD market share 31.8%, Tesla 6.4%..."
        )
        
        # Generate charts
        for suggestion in suggestions:
            result = generator.generate_chart(suggestion)
    """
    
    # Data pattern definitions
    DATA_PATTERNS = {
        # Market share pattern
        "market_share": {
            "patterns": [
                r"market share[：:]\s*(\d+(?:\.\d+)?)\s*[%％]",
                r"share[：:]\s*(\d+(?:\.\d+)?)\s*[%％]",
                r"(\d+(?:\.\d+)?)\s*[%％]\s*market share",
                r"share rate[：:]\s*(\d+(?:\.\d+)?)\s*[%％]",
            ],
            "chart_type": ChartType.PIE,
            "keywords": ["market share", "share", "proportion", "percentage"],
        },
        
        # Sales/volume pattern
        "sales_volume": {
            "patterns": [
                r"sales\s*(\d+(?:\.\d+)?)\s*(million|billion|K)",
                r"(\d+(?:\.\d+)?)\s*(million|billion|K)\s*sales",
                r"sold\s*(\d+(?:\.\d+)?)\s*(million|billion|K)",
            ],
            "chart_type": ChartType.BAR,
            "keywords": ["sales", "volume", "scale", "production"],
        },
        
        # Growth trend pattern
        "growth_trend": {
            "patterns": [
                r"YoY growth\s*(\d+(?:\.\d+)?)\s*[%％]",
                r"growth\s*(\d+(?:\.\d+)?)\s*[%％]",
                r"increase\s*(\d+(?:\.\d+)?)\s*[%％]",
                r"decline\s*(\d+(?:\.\d+)?)\s*[%％]",
            ],
            "chart_type": ChartType.LINE,
            "keywords": ["growth", "trend", "YoY", "QoQ", "change"],
        },
        
        # Ranking comparison pattern
        "ranking": {
            "patterns": [
                r"ranked\s*#?(\d+)",
                r"TOP\s*(\d+)",
                r"top\s*(\d+)\s*",
            ],
            "chart_type": ChartType.HBAR,
            "keywords": ["rank", "TOP", "leading", "first", "second", "top three"],
        },
        
        # Price range pattern
        "price_range": {
            "patterns": [
                r"(\d+(?:\.\d+)?)\s*[-~to]\s*(\d+(?:\.\d+)?)\s*(K|USD)",
                r"price range[：:]?\s*(\d+(?:\.\d+)?)\s*[-~to]\s*(\d+(?:\.\d+)?)",
            ],
            "chart_type": ChartType.BAR,
            "keywords": ["price", "range", "cost", "valuation"],
        },
    }
    
    # Section type to recommended chart mapping
    SECTION_CHART_MAPPING = {
        "市场规模": [ChartType.BAR, ChartType.LINE, ChartType.PIE],
        "市场份额": [ChartType.PIE, ChartType.BAR],
        "竞争格局": [ChartType.BAR, ChartType.HBAR, ChartType.QUADRANT],
        "行业趋势": [ChartType.LINE, ChartType.BAR_LINE],
        "财务分析": [ChartType.BAR, ChartType.WATERFALL, ChartType.LINE],
        "用户分析": [ChartType.PIE, ChartType.BAR, ChartType.RADAR],
        "技术对比": [ChartType.RADAR, ChartType.BAR],
        "区域分布": [ChartType.PIE, ChartType.BAR],
        "增长分析": [ChartType.LINE, ChartType.BAR_LINE],
        "投资分析": [ChartType.BAR, ChartType.LINE, ChartType.QUADRANT],
        "销量分析": [ChartType.BAR, ChartType.LINE],
        "企业对比": [ChartType.BAR, ChartType.HBAR],
        "Market Size": [ChartType.BAR, ChartType.LINE, ChartType.PIE],
        "Market Share": [ChartType.PIE, ChartType.BAR],
        "Competitive Landscape": [ChartType.BAR, ChartType.HBAR, ChartType.QUADRANT],
        "Industry Trend": [ChartType.LINE, ChartType.BAR_LINE],
        "Financial Analysis": [ChartType.BAR, ChartType.WATERFALL, ChartType.LINE],
        "User Analysis": [ChartType.PIE, ChartType.BAR, ChartType.RADAR],
        "Technology Comparison": [ChartType.RADAR, ChartType.BAR],
        "Regional Distribution": [ChartType.PIE, ChartType.BAR],
        "Growth Analysis": [ChartType.LINE, ChartType.BAR_LINE],
        "Investment Analysis": [ChartType.BAR, ChartType.LINE, ChartType.QUADRANT],
    }
    
    def __init__(self, output_dir: Optional[str] = None):
        """
        Initialize smart chart generator
        
        Args:
            output_dir: Chart output directory
        """
        self.chart_generator = ChartGenerator()
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            _chart_root = Path(__file__).resolve().parent.parent.parent / "output" / "charts"
            self.output_dir = _chart_root
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _extract_from_tables(
        self,
        content: str,
        section_title: str,
        section_charts: List[ChartType]
    ) -> List[ChartSuggestion]:
        """Extract chart data from Markdown tables in content"""
        try:
            from src.services.table_data_extractor import TableDataExtractor
            tables = TableDataExtractor.extract_all(content)
        except ImportError:
            return []
        
        suggestions = []
        for table in tables:
            chart_data = table.to_chart_data()
            if not chart_data:
                continue
            
            chart_type = self._recommend_chart_type_for_table(table, section_charts)
            if not chart_type:
                continue
            
            title = self._generate_table_title(section_title, table)
            caption = f"图：{section_title} - 数据对比（{len(table.rows)}项）"
            
            suggestion = ChartSuggestion(
                chart_type=chart_type,
                title=title,
                data=chart_data,
                caption=caption,
                confidence=0.95,  # Table data is high confidence
                reason=f"Extracted {len(table.rows)} rows from Markdown table"
            )
            suggestions.append(suggestion)
        
        return suggestions
    
    def _recommend_chart_type_for_table(
        self,
        table,
        section_charts: List[ChartType]
    ) -> Optional[ChartType]:
        """Recommend chart type based on table structure"""
        has_year = any(h for h in table.headers if "年" in h or "year" in h.lower() or "time" in h.lower())
        if has_year and len(table.numeric_columns) >= 1:
            if ChartType.LINE in section_charts:
                return ChartType.LINE
            return ChartType.LINE
        
        if len(table.numeric_columns) >= 2 and len(table.rows) >= 2:
            if ChartType.BAR in section_charts:
                return ChartType.BAR
            return ChartType.BAR
        
        if len(table.rows) <= 6:
            if ChartType.PIE in section_charts:
                return ChartType.PIE
            return ChartType.PIE
        
        return ChartType.BAR
    
    def _generate_table_title(self, section_title: str, table) -> str:
        """Generate title for table-sourced chart"""
        caption = table.caption or ""
        if caption:
            return f"{section_title} - {caption}"
        headers_str = "、".join(str(h) for h in table.headers[:3])
        return f"{section_title} - {headers_str}对比"
    
    def analyze_content(
        self,
        section_title: str,
        content: str,
        data_points: Optional[List[Dict]] = None
    ) -> List[ChartSuggestion]:
        """
        Analyze section content and recommend charts
        
        Args:
            section_title: Section title
            content: Section content
            data_points: Pre-extracted data points (optional)
            
        Returns:
            List of chart suggestions
        """
        suggestions = []
        
        # 1. Recommend chart types based on section title
        section_charts = self._get_section_charts(section_title)
        
        # 2. P0-2: Extract data from Markdown tables (highest priority)
        table_suggestions = self._extract_from_tables(content, section_title, section_charts)
        suggestions.extend(table_suggestions)
        
        # 3. Extract data from content via regex (fallback)
        extracted_data = self._extract_data_from_content(content)
        
        # 4. Extract data from data points
        if data_points:
            points_data = self._extract_data_from_points(data_points)
            for data_type, data in points_data:
                if data_type in extracted_data:
                    existing = extracted_data[data_type]
                    if "categories" in existing and "categories" in data:
                        existing["categories"].extend(data["categories"])
                        existing["values"].extend(data["values"])
                else:
                    extracted_data[data_type] = data
        
        # 4b. P1: Validate extracted data quality
        validated_data = {}
        for data_type, data in extracted_data.items():
            if self._validate_extracted_data(data_type, data):
                validated_data[data_type] = data
            else:
                logger.debug(f"Data validation failed for {data_type}: {data}")
        extracted_data = validated_data
        
        # 5. Generate chart suggestions for each extracted data type
        for data_type, data in extracted_data.items():
            chart_type = self._recommend_chart_type(data_type, section_charts)
            
            if chart_type and data:
                suggestion = ChartSuggestion(
                    chart_type=chart_type,
                    title=self._generate_title(section_title, data_type),
                    data=data,
                    caption=self._generate_caption(data_type, data),
                    confidence=self._calculate_confidence(data_type, data),
                    reason=f"Detected {data_type} data, recommending {chart_type.value} chart"
                )
                suggestions.append(suggestion)
        
        # 6. Sort by confidence (table-sourced suggestions first due to higher confidence)
        suggestions.sort(key=lambda x: x.confidence, reverse=True)
        
        return suggestions
        
    def generate_chart(self, suggestion: ChartSuggestion) -> Optional[str]:
        """
        Generate chart
        
        Args:
            suggestion: Chart suggestion
            
        Returns:
            Chart file path, or None if failed
        """
        try:
            config = ChartConfig(
                chart_type=suggestion.chart_type,
                title=suggestion.title,
                data=suggestion.data,
                caption=suggestion.caption,
            )
            
            result = self.chart_generator.generate(config)
            
            if result.success and result.image_path:
                # Move to output directory
                src_path = Path(result.image_path)
                dst_path = self.output_dir / src_path.name
                if src_path.exists() and src_path != dst_path:
                    import shutil
                    shutil.move(str(src_path), str(dst_path))
                return str(dst_path)
            
            return None
            
        except Exception:
            logger.exception("Failed to generate chart")
            return None
    
    def _get_section_charts(self, section_title: str) -> List[ChartType]:
        """Get recommended chart types based on section title"""
        for keyword, charts in self.SECTION_CHART_MAPPING.items():
            if keyword.lower() in section_title.lower():
                return charts
        return [ChartType.BAR, ChartType.PIE]  # Default
    
    def _extract_data_from_content(self, content: str) -> Dict[str, Dict]:
        """
        Extract data from content
        
        Returns:
            {data_type: {chart_data}}
        """
        extracted = {}
        
        # Extract market share data
        market_share_data = self._extract_market_share(content)
        if market_share_data:
            extracted["market_share"] = market_share_data
        
        # Extract sales data
        sales_data = self._extract_sales_data(content)
        if sales_data:
            extracted["sales"] = sales_data
        
        # Extract growth data
        growth_data = self._extract_growth_data(content)
        if growth_data:
            extracted["growth"] = growth_data
        
        # Extract ranking data
        ranking_data = self._extract_ranking_data(content)
        if ranking_data:
            extracted["ranking"] = ranking_data
        
        # Chinese extraction — only when English extraction has no results
        if "market_share" not in extracted:
            cn_market_share = self._extract_cn_market_share(content)
            if cn_market_share:
                extracted["market_share"] = cn_market_share
        
        if "sales" not in extracted:
            cn_sales = self._extract_cn_sales_data(content)
            if cn_sales:
                extracted["sales"] = cn_sales
        
        if "growth" not in extracted:
            cn_growth = self._extract_cn_growth_data(content)
            if cn_growth:
                extracted["growth"] = cn_growth
        
        if "ranking" not in extracted:
            cn_ranking = self._extract_cn_ranking_data(content)
            if cn_ranking:
                extracted["ranking"] = cn_ranking
        
        # 通用数值 fallback（仅当上文无任何匹配时）
        if not extracted:
            cn_numeric = self._extract_cn_numeric_data(content)
            if cn_numeric:
                extracted["numeric"] = cn_numeric
        
        return extracted
    
    def _extract_market_share(self, content: str) -> Optional[Dict]:
        """Extract market share data"""
        # Match pattern: company name + number%
        pattern = r"([^\s，。、]+?)[：:]?\s*(\d+(?:\.\d+)?)\s*[%％]"
        matches = re.findall(pattern, content)
        
        if len(matches) >= 2:  # At least 2 data points
            categories = []
            values = []
            for name, value in matches[:8]:  # Max 8
                # Clean name
                name = re.sub(r"[的其]", "", name)
                if len(name) > 15:
                    name = name[:15]
                categories.append(name)
                values.append(float(value))
            
            return {
                "categories": categories,
                "values": values,
            }
        
        return None
    
    def _extract_sales_data(self, content: str) -> Optional[Dict]:
        """Extract sales data"""
        # Match pattern: company name + number + unit
        pattern = r"([^\s，。、]+?)[：:]?\s*(\d+(?:\.\d+)?)\s*(million|billion|K)"
        matches = re.findall(pattern, content)
        
        if len(matches) >= 2:
            categories = []
            values = []
            for name, value, unit in matches[:8]:
                name = re.sub(r"[的其销量销售]", "", name)
                if len(name) > 15:
                    name = name[:15]
                categories.append(name)
                # Normalize to thousands
                if unit == "billion":
                    values.append(float(value) * 10000)
                else:
                    values.append(float(value))
            
            return {
                "categories": categories,
                "values": values,
                "ylabel": "Sales (K)",
            }
        
        return None
    
    def _extract_growth_data(self, content: str) -> Optional[Dict]:
        """Extract growth data"""
        # Match year + growth rate
        pattern = r"(20\d{2})?.*?(?:YoY growth|growth|increase)[：:]?\s*(-?\d+(?:\.\d+)?)\s*[%％]"
        matches = re.findall(pattern, content)
        
        if len(matches) >= 2:
            years = []
            values = []
            for year, value in matches:
                years.append(year if year else "N/A")
                values.append(float(value))
            
            return {
                "categories": years,
                "values": values,
                "ylabel": "YoY Growth Rate (%)",
            }
        
        return None
    
    def _extract_ranking_data(self, content: str) -> Optional[Dict]:
        """Extract ranking data"""
        # Match TOP N company data
        pattern = r"([^\s，。、]+?)[：:]?\s*(\d+(?:\.\d+)?)\s*(million|billion|K|%)"
        matches = re.findall(pattern, content)
        
        if len(matches) >= 3:
            categories = []
            values = []
            for name, value, unit in matches[:10]:
                name = re.sub(r"[的其]", "", name)
                if len(name) > 15:
                    name = name[:15]
                categories.append(name)
                values.append(float(value))
            
            return {
                "categories": categories[::-1],  # Horizontal bar chart, reverse order
                "values": values[::-1],
            }
        
        return None
    
    def _extract_cn_market_share(self, content: str) -> Optional[Dict]:
        patterns = [
            r"([^\s，。、：:]+?)(?:市场份额|市占率|占比|渗透率)(?:为|达|约|超|提升|下降|增长|减少)?[：:]?\s*(\d+(?:\.\d+)?)\s*(?:个百分点|[%％])",
            r"(?:市场份额|市占率|占比|渗透率)[：:]\s*([^\s，。、：:]+?)(?:为|达|约|超|提升|下降|增长|减少)?[：:]?\s*(\d+(?:\.\d+)?)\s*(?:个百分点|[%％])",
            r"([^\s，。、：:]+?)[：:]\s*(\d+(?:\.\d+)?)\s*(?:个百分点|[%％]).*?(?:市场份额|市占率|占比)",
        ]
        continuation_pattern = r"[，,]\s*([^\s，。、：:]+?)[为达约超]?[：:]?\s*(\d+(?:\.\d+)?)\s*[%％]"
        
        categories, values = [], []
        for pattern in patterns:
            matches = re.findall(pattern, content)
            for name, value in matches[:8]:
                name = re.sub(r"的|其", "", name)
                if len(name) > 15:
                    name = name[:15]
                if name not in categories:
                    categories.append(name)
                    values.append(float(value))
        
        non_entity_keywords = {"增长率", "满意度", "复购率", "利润率", "毛利率", "通过率", "留存率", "转化率"}
        if categories:
            for name, value in re.findall(continuation_pattern, content)[:8]:
                if any(kw in name for kw in non_entity_keywords):
                    continue
                name = re.sub(r"的|其", "", name)
                if len(name) > 15:
                    name = name[:15]
                if name not in categories:
                    categories.append(name)
                    values.append(float(value))
        
        if len(categories) >= 2:
            return {"categories": categories, "values": values}
        return None
    
    def _extract_cn_sales_data(self, content: str) -> Optional[Dict]:
        pattern = r"([^\s，。、：:]+?)(?:销量|销售额|产量)[为达约超]?[：:]?\s*(\d+(?:\.\d+)?)\s*(万辆|亿辆|万台|亿台|万|亿)"
        matches = re.findall(pattern, content)
        
        if len(matches) >= 2:
            categories, values = [], []
            for name, value, unit in matches[:8]:
                name = re.sub(r"的|其|销量|销售", "", name)
                if len(name) > 15:
                    name = name[:15]
                if name not in categories:
                    categories.append(name)
                    if unit in ("亿辆", "亿台", "亿"):
                        values.append(float(value) * 10000)
                    else:
                        values.append(float(value))
            return {"categories": categories, "values": values, "ylabel": "销量（万）"}
        return None
    
    def _extract_cn_growth_data(self, content: str) -> Optional[Dict]:
        growth_pattern = r"(20\d{2})年?[，,]?\s*[^，。！？\n]*?(?:同比|环比)(?:增长|增幅)[为达约近超]?\s*(\d+(?:\.\d+)?)\s*[%％]"
        decline_pattern = r"(20\d{2})年?[，,]?\s*[^，。！？\n]*?(?:同比|环比)(?:下降|下滑|减少)[为达约近超]?\s*(\d+(?:\.\d+)?)\s*[%％]"
        
        entries = []
        
        for match in re.finditer(growth_pattern, content):
            year = match.group(1)
            metric = "qoq_growth" if "环比" in match.group(0) else "yoy_growth"
            entries.append((year, metric, float(match.group(2))))
        
        for match in re.finditer(decline_pattern, content):
            year = match.group(1)
            metric = "qoq_decline" if "环比" in match.group(0) else "yoy_decline"
            entries.append((year, metric, -float(match.group(2))))
        
        if not entries:
            return None
        
        for metric_key in ["yoy_growth", "yoy_decline", "qoq_growth", "qoq_decline"]:
            group = [(y, v) for y, m, v in entries if m == metric_key]
            if len(group) >= 2:
                paired = sorted(group)
                return {
                    "categories": [p[0] for p in paired],
                    "values": [p[1] for p in paired],
                    "ylabel": "同比增长率（%）" if "yoy" in metric_key else "环比增长率（%）",
                }
        
        all_yoy = [(y, v) for y, m, v in entries if "yoy" in m]
        if len(all_yoy) >= 2:
            yoy_by_year = {}
            for y, v in all_yoy:
                if y not in yoy_by_year:
                    yoy_by_year[y] = v
            paired = sorted(yoy_by_year.items())
            return {
                "categories": [p[0] for p in paired],
                "values": [p[1] for p in paired],
                "ylabel": "同比增长率（%）",
            }
        
        return None
    
    def _extract_cn_ranking_data(self, content: str) -> Optional[Dict]:
        ranking_keywords = ["排名", "TOP", "前", "领先", "竞争", "市占", "份额"]
        has_ranking_context = any(kw in content for kw in ranking_keywords)
        if not has_ranking_context:
            return None
        
        pattern = r"([^\s，。、：:]+?)[：:]\s*(\d+(?:\.\d+)?)\s*(万辆|亿辆|万台|亿台|%|％|亿元)"
        matches = re.findall(pattern, content)
        
        if len(matches) >= 3:
            categories, values = [], []
            for name, value, unit in matches[:10]:
                name = re.sub(r"的|其", "", name)
                if len(name) > 15:
                    name = name[:15]
                if name not in categories:
                    categories.append(name)
                    values.append(float(value))
            return {"categories": categories[::-1], "values": values[::-1]}
        return None
    
    def _extract_cn_numeric_data(self, content: str) -> Optional[Dict]:
        """通用数值提取 - 提取 "中文名词+数字+单位" 模式"""
        pattern = r'([\u4e00-\u9fff]{2,10}?)(?:为|达|约|超|仅|累计|已达|已至|约合|已累积至|已累计至|已达至|已超)?\s*(\d+(?:\.\d+)?)\s*(万吨|亿|万|元/吨|元|％|%|吨|辆|台)'
        matches = re.findall(pattern, content)
        
        skip_words = {"增长", "下降", "上涨", "下跌", "提高", "降低", "增加", "减少", "同比", "环比"}
        categories, values = [], []
        for name, value, unit in matches[:10]:
            if any(skip in name for skip in skip_words):
                continue
            name = re.sub(r'[的其与和]', '', name)[:15]
            if name not in categories:
                categories.append(name)
                values.append(float(value))
        
        if len(categories) >= 2:
            return {"categories": categories, "values": values}
        return None
    
    def _extract_data_from_points(self, data_points: List[Dict]) -> List[Tuple[str, Dict]]:
        """Extract data from data points"""
        extracted: List[Tuple[str, Dict]] = []
        
        for point in data_points:
            metric = point.get("metric", "")
            value = point.get("value", "")
            unit = point.get("unit", "")
            
            if metric and value:
                # Determine data type
                if "%" in str(unit) or "rate" in metric.lower():
                    match = re.search(r'[\d.]+', str(value))
                    if match:
                        extracted.append(("market_share", {
                            "categories": [metric],
                            "values": [float(match.group())]
                        }))
        
        return extracted
    
    def _recommend_chart_type(
        self,
        data_type: str,
        section_charts: List[ChartType]
    ) -> Optional[ChartType]:
        """Recommend chart type"""
        type_mapping = {
            "market_share": ChartType.PIE,
            "sales": ChartType.BAR,
            "growth": ChartType.LINE,
            "ranking": ChartType.HBAR,
            "numeric": ChartType.BAR,
        }
        
        recommended = type_mapping.get(data_type)
        
        # If recommended type is in section recommendation list, use it
        if recommended in section_charts:
            return recommended
        
        # Otherwise use first section recommendation
        if section_charts:
            return section_charts[0]
        
        return recommended
    
    def _generate_title(self, section_title: str, data_type: str) -> str:
        section_clean = section_title.replace("（", "").replace("）", "").replace("(", "").replace(")", "")
        # Truncate long titles
        if len(section_clean) > 30:
            section_clean = section_clean[:30] + "..."
        
        cn_title_map = {
            "市场份额": f"{section_clean} - 份额分布",
            "市占率": f"{section_clean} - 市占率分布",
            "占比": f"{section_clean} - 占比分布",
            "渗透率": f"{section_clean} - 渗透率分布",
            "销量": f"{section_clean} - 销量对比",
            "销售额": f"{section_clean} - 销售额对比",
            "产量": f"{section_clean} - 产量对比",
            "增长": f"{section_clean} - 增长趋势",
            "增速": f"{section_clean} - 增速趋势",
            "排名": f"{section_clean} - 排名对比",
            "竞争": f"{section_clean} - 竞争格局",
            "规模": f"{section_clean} - 规模分析",
            "趋势": f"{section_clean} - 趋势分析",
            "价格": f"{section_clean} - 价格走势",
            "供需": f"{section_clean} - 供需对比",
            "贸易": f"{section_clean} - 贸易数据",
            "进口": f"{section_clean} - 进口分析",
            "出口": f"{section_clean} - 出口分析",
        }
        for kw, title in cn_title_map.items():
            if kw in section_title:
                return title
        
        data_labels = {
            "market_share": f"{section_clean} - 份额分布",
            "sales": f"{section_clean} - 销量对比",
            "growth": f"{section_clean} - 增长趋势",
            "ranking": f"{section_clean} - 排名对比",
            "numeric": f"{section_clean} - 数据对比",
        }
        return data_labels.get(data_type, f"{section_clean} - 数据分析")
    
    def _generate_caption(self, data_type: str, data: Dict) -> str:
        categories = data.get("categories", [])
        cn_captions = {
            "market_share": "份额对比",
            "sales": "销量/销售额对比",
            "growth": "增长率变化趋势",
            "ranking": "排名对比",
            "numeric": "数据对比",
        }
        base = cn_captions.get(data_type, "数据分析")
        if categories:
            return f"图：{base}（{len(categories)}项）"
        return f"图：{base}"
    
    def _validate_extracted_data(self, data_type: str, data: Dict) -> bool:
        """P1: Validate extracted data quality before chart generation"""
        categories = data.get("categories", [])
        values = data.get("values", [])
        
        if not categories or not values:
            return False
        if len(categories) != len(values):
            return False
        
        # Check semantic relevance: reject if any category looks like a year or index
        year_count = sum(1 for c in categories if re.match(r"^20\d{2}$", c) or re.match(r"^19\d{2}$", c))
        if year_count > len(categories) * 0.5:
            return False
        
        # Check unit consistency: all values should be in similar magnitude range
        if values:
            min_v, max_v = min(values), max(values)
            if max_v > 0 and min_v >= 0:
                ratio = max_v / max(min_v, 0.001)
                if ratio > 10000 and len(values) > 2:
                    return False
        
        return True
    
    def _calculate_confidence(self, data_type: str, data: Dict) -> float:
        """Calculate confidence"""
        categories = data.get("categories", [])
        values = data.get("values", [])
        
        if not categories or not values:
            return 0.0
        
        # More data points = higher confidence
        data_count = len(categories)
        if data_count >= 5:
            return 0.9
        elif data_count >= 3:
            return 0.7
        else:
            return 0.5


# Export
__all__ = ["SmartChartGenerator", "ChartSuggestion"]
