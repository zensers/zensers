"""
Search Result Quality Filter
============================

Performs quality assessment and filtering of search results, ensuring only high-quality data enters the analysis pipeline.

Quality assessment dimensions:
1. Source credibility (authority)
2. Content relevance (professionalism)
3. Content quality (depth)
4. Timeliness (freshness)
5. Originality (non-marketing content)
"""
import re
import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SourceCredibility(Enum):
    """Source credibility level"""
    TIER1_AUTHORITY = "tier1_authority"    # Government agencies, official statistics, regulatory bodies
    TIER2_PROFESSIONAL = "tier2_professional"  # Brokerage research, industry associations, renowned consulting
    TIER3_REPUTABLE = "tier3_reputable"    # Mainstream media, listed company announcements
    TIER4_GENERAL = "tier4_general"        # General websites, blogs
    TIER5_LOW_QUALITY = "tier5_low_quality"  # Marketing content, SEO spam, ads


@dataclass
class QualityScore:
    """Quality score result"""
    overall_score: float  # 0-100
    credibility: SourceCredibility
    relevance_score: float  # 0-100
    depth_score: float  # 0-100
    freshness_score: float  # 0-100
    is_filtered: bool  # Whether filtered out
    filter_reason: Optional[str] = None


# Authoritative data source configuration
AUTHORITY_SOURCES = {
    # Tier 1: Highest authority
    "tier1": {
        "government": [
            # Chinese government agencies
            "gov.cn", "stats.gov.cn", "miit.gov.cn", "ndrc.gov.cn",
            "mofcom.gov.cn", "pbc.gov.cn", "csrc.gov.cn", "sasac.gov.cn",
            "most.gov.cn", "mnr.gov.cn", "mee.gov.cn", "nhc.gov.cn",
            # International organizations
            "worldbank.org", "imf.org", "oecd.org", "un.org",
            "bis.org", "wto.org", "fao.org", "who.int",
        ],
        "regulators": [
            "csrc.gov.cn",  # China Securities Regulatory Commission
            "cbirc.gov.cn",  # China Banking and Insurance Regulatory Commission
            "pbc.gov.cn",   # People's Bank of China
            "sec.gov",      # US SEC
            "fca.org.uk",   # UK FCA
        ],
        "official_statistics": [
            "stats.gov.cn",
            "census.gov",
            "ons.gov.uk",
            "stat.go.jp",
            "destatis.de",
        ],
    },

    # Tier 2: Professional institutions
    "tier2": {
        "securities_research": [
            # Brokerage research sources
            "researchreport.cn", "eastmoney.com", "10jqka.com.cn",
            "xueqiu.com", "gelonghui.com", "yicai.com",
            # International investment banks
            "morganstanley.com", "goldmansachs.com", "jpmorgan.com",
            "ubs.com", "credit-suisse.com", "bankofamerica.com",
        ],
        "industry_associations": [
            "caam.org.cn",      # China Association of Automobile Manufacturers
            "cca.org.cn",       # China Consumers Association
            "cie.org.cn",       # Chinese Institute of Electronics
            "cast.org.cn",      # China Association for Science and Technology
        ],
        "consulting": [
            "mckinsey.com", "bcg.com", "bain.com",
            "deloitte.com", "pwc.com", "ey.com", "kpmg.com",
            "iresearch.com.cn", "analysys.cn", "iimedia.cn",
        ],
    },

    # Tier 3: Reputable media
    "tier3": {
        "financial_media": [
            "caixin.com", "yicai.com", "21jingji.com",
            "thepaper.cn", "jiemian.com", "finance.sina.com.cn",
            "ftchinese.com", "wsj.com", "bloomberg.com",
            "reuters.com", "economist.com",
        ],
        "company_ir": [
            "cninfo.com.cn",    # CNINFO
            "sse.com.cn",       # Shanghai Stock Exchange
            "szse.cn",          # Shenzhen Stock Exchange
            "hkexnews.hk",      # Hong Kong Stock Exchange
            "sec.gov",          # SEC EDGAR
        ],
    },

    # Tier 4: General sources
    "tier4": {
        "general_media": [
            "sina.com.cn", "sohu.com", "qq.com", "163.com",
            "ifeng.com", "people.com.cn", "xinhuanet.com",
        ],
        "knowledge_platforms": [
            "zhihu.com", "baidu.com", "baike.baidu.com",
            "wikipedia.org", "medium.com",
        ],
    },

    # Tier 5: Low quality sources (to be filtered)
    "tier5": {
        "marketing_sites": [
            # Marketing content hotspots
            "baijiahao.baidu.com",  # Baijiahao (heavy marketing content)
            "sohu.com/a/",          # Sohu Account
            "toutiao.com",          # Toutiao
            "kuaibao.qq.com",       # Kuaibao
        ],
        "seo_farms": [
            # Genuine content farms — full domains, not prefixes
            "seo.", "contentfarm", "spam",
        ],
    },
}


# Low quality content patterns
LOW_QUALITY_PATTERNS = {
    # Ad keywords
    "ad_keywords": [
        "广告", "推广", "赞助", "合作", "招商", "加盟",
        "限时优惠", "点击购买", "立即咨询", "免费领取",
        "advertisement", "sponsored", "promoted",
    ],

    # SEO spam patterns
    "seo_patterns": [
        r"点击这里.*了解更多",
        r"相关推荐.*\d+篇",
        r"猜你喜欢",
        r"热门推荐",
        r"大家都在看",
        r"\d+个相关结果",
    ],

    # Marketing content patterns
    "marketing_patterns": [
        r"【.*?】.*?咨询",
        r"咨询热线[:：]\d+",
        r"联系电话[:：]\d+",
        r"微信[:：][a-zA-Z0-9]+",
        r"扫码.*关注",
        r"转发.*抽奖",
    ],

    # Low quality title patterns
    "clickbait_patterns": [
        r"震惊[！!].*",
        r"必看[！!].*",
        r"不看后悔.*",
        r"你绝对想不到",
        r"惊呆了",
        r"疯传.*",
    ],
}


class SearchQualityFilter:
    """
    Search Result Quality Filter

    Performs multi-dimensional quality assessment on search results:
    1. Source credibility assessment
    2. Content relevance assessment
    3. Content quality assessment
    4. Timeliness assessment
    """

    def __init__(self, min_quality_score: Optional[float] = None):
        """
        Initialize quality filter.
        Reads default threshold from config/settings.yaml if not specified.

        Args:
            min_quality_score: Minimum quality score threshold (0-100).
                              If None, reads from settings.yaml or defaults to 40.0.
        """
        if min_quality_score is None:
            try:
                import yaml
                _config_path = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"
                if _config_path.exists():
                    with open(_config_path, encoding="utf-8") as _f:
                        _cfg = yaml.safe_load(_f)
                    min_quality_score = _cfg.get("search", {}).get("min_quality_score", 40.0)
                else:
                    min_quality_score = 40.0
            except Exception:
                min_quality_score = 40.0
        self._min_quality_score = max(float(min_quality_score), 30.0)
    
    @property
    def min_quality_score(self) -> float:
        """Get minimum quality score threshold."""
        return self._min_quality_score
    
    @min_quality_score.setter
    def min_quality_score(self, value: float):
        """Set minimum quality score threshold (clamped to >= 30.0)."""
        self._min_quality_score = max(float(value), 30.0)

    def filter_results(
        self,
        results: List[Dict[str, Any]],
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], List[QualityScore]]:
        """
        Filter search results, return high-quality results with adaptive threshold.

        If the fixed threshold yields too few results (< 33% pass rate),
        the threshold is dynamically lowered to the 50th percentile score
        to avoid overly aggressive filtering.

        Args:
            results: Original search results list
            query: Search query
            context: Additional context (e.g., research topic, keywords)

        Returns:
            (Filtered results list, quality scores list)
        """
        quality_scores = []

        for result in results:
            score = self._calculate_quality_score(result, query, context)
            quality_scores.append(score)

        # Use fixed threshold — never adapt downward
        # When quality is uniformly low, better to return fewer results
        # than let garbage through. The caller (search_skill.py) has a
        # fallback that scores and returns top-N if filtering is too aggressive.
        effective_threshold = self.min_quality_score

        # Apply the effective threshold
        filtered_results = []
        for i, result in enumerate(results):
            score = quality_scores[i]

            if score.is_filtered:
                logger.debug(f"Filtered low quality result: {result.get('title', '')[:30]}... Reason: {score.filter_reason}")
                continue

            if score.overall_score < effective_threshold:
                logger.debug(f"Filtered low score result: {score.overall_score:.1f} < {effective_threshold:.0f}")
                continue

            result_with_score = result.copy()
            result_with_score["quality_score"] = score.overall_score
            result_with_score["credibility"] = score.credibility.value
            filtered_results.append(result_with_score)

        # Sort by quality score
        filtered_results.sort(key=lambda x: x.get("quality_score", 0), reverse=True)

        logger.info(f"Quality filtering: {len(results)} -> {len(filtered_results)} results (threshold={effective_threshold:.0f})")

        return filtered_results, quality_scores

    def _calculate_quality_score(
        self,
        result: Dict[str, Any],
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> QualityScore:
        """Calculate quality score for single result"""

        # 1. Source credibility assessment
        credibility, is_filtered, filter_reason = self._assess_credibility(result)

        # If filtered, return directly
        if is_filtered:
            return QualityScore(
                overall_score=0,
                credibility=credibility,
                relevance_score=0,
                depth_score=0,
                freshness_score=0,
                is_filtered=True,
                filter_reason=filter_reason,
            )

        # 2. Content relevance assessment
        relevance_score = self._assess_relevance(result, query, context)

        # 3. Content quality assessment
        depth_score = self._assess_depth(result)

        # 4. Timeliness assessment
        freshness_score = self._assess_freshness(result)

        # 5. Overall score (weighted average)
        credibility_weight = {
            SourceCredibility.TIER1_AUTHORITY: 100,
            SourceCredibility.TIER2_PROFESSIONAL: 85,
            SourceCredibility.TIER3_REPUTABLE: 70,
            SourceCredibility.TIER4_GENERAL: 50,
            SourceCredibility.TIER5_LOW_QUALITY: 20,
        }

        credibility_score = credibility_weight.get(credibility, 40)

        # Weighted total score
        overall_score = (
            credibility_score * 0.35 +    # Source credibility weight 35%
            relevance_score * 0.30 +       # Relevance weight 30%
            depth_score * 0.25 +           # Content depth weight 25%
            freshness_score * 0.10         # Timeliness weight 10%
        )

        return QualityScore(
            overall_score=overall_score,
            credibility=credibility,
            relevance_score=relevance_score,
            depth_score=depth_score,
            freshness_score=freshness_score,
            is_filtered=False,
        )

    def _assess_credibility(
        self,
        result: Dict[str, Any],
    ) -> Tuple[SourceCredibility, bool, Optional[str]]:
        """
        Assess source credibility

        Returns:
            (Credibility level, whether to filter, filter reason)
        """
        url = result.get("href", "") or result.get("url", "")
        title = result.get("title", "")
        body = result.get("body", "") or result.get("snippet", "")

        if not url:
            return SourceCredibility.TIER4_GENERAL, False, None

        # Parse domain
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
        except (ValueError, AttributeError):
            domain = url.lower()

        # Check if low quality source
        for pattern in AUTHORITY_SOURCES["tier5"]["marketing_sites"]:
            if pattern in domain:
                return SourceCredibility.TIER5_LOW_QUALITY, True, "Marketing content source"

        # Check ad keywords
        combined_text = f"{title} {body}".lower()
        for ad_kw in LOW_QUALITY_PATTERNS["ad_keywords"]:
            if ad_kw in combined_text:
                # If contains multiple ad keywords, filter
                ad_count = sum(1 for kw in LOW_QUALITY_PATTERNS["ad_keywords"] if kw in combined_text)
                if ad_count >= 2:
                    return SourceCredibility.TIER5_LOW_QUALITY, True, "Advertisement content"

        # Check SEO spam patterns
        for pattern in LOW_QUALITY_PATTERNS["seo_patterns"]:
            if re.search(pattern, combined_text, re.IGNORECASE):
                return SourceCredibility.TIER5_LOW_QUALITY, True, "SEO spam content"

        # Check clickbait
        for pattern in LOW_QUALITY_PATTERNS["clickbait_patterns"]:
            if re.search(pattern, title, re.IGNORECASE):
                return SourceCredibility.TIER5_LOW_QUALITY, True, "Clickbait title"

        # Check authoritative sources
        for tier, sources in AUTHORITY_SOURCES.items():
            if tier == "tier5":
                continue
            for category, domains in sources.items():
                for auth_domain in domains:
                    if auth_domain in domain:
                        if tier == "tier1":
                            return SourceCredibility.TIER1_AUTHORITY, False, None
                        elif tier == "tier2":
                            return SourceCredibility.TIER2_PROFESSIONAL, False, None
                        elif tier == "tier3":
                            return SourceCredibility.TIER3_REPUTABLE, False, None
                        elif tier == "tier4":
                            return SourceCredibility.TIER4_GENERAL, False, None

        # Default to general source
        return SourceCredibility.TIER4_GENERAL, False, None

    @staticmethod
    def _split_query_terms(query: str) -> set:
        """Split query into terms, handling both English (space) and Chinese."""
        terms = set(query.lower().split())
        # Chinese text has no spaces — extract individual CJK characters
        cjk_chars = set()
        for ch in query:
            if '\u4e00' <= ch <= '\u9fff' or '\u3000' <= ch <= '\u303f':
                cjk_chars.add(ch)
        if cjk_chars:
            terms.update(cjk_chars)
        return terms

    def _assess_relevance(
        self,
        result: Dict[str, Any],
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> float:
        """
        Assess content relevance

        Returns:
            Relevance score 0-100
        """
        title = result.get("title", "").lower()
        body = result.get("body", "") or result.get("snippet", "")
        body = body.lower()

        query_terms = self._split_query_terms(query)

        if not query_terms:
            return 50.0

        # Title matching
        title_matches = sum(1 for term in query_terms if term in title)
        title_score = min(100, title_matches / len(query_terms) * 100)

        # Body matching
        body_matches = sum(1 for term in query_terms if term in body)
        body_score = min(100, body_matches / len(query_terms) * 100)

        # Context matching (if available)
        context_score = 0
        if context:
            focus_areas = context.get("focus_areas", [])
            if focus_areas:
                for area in focus_areas:
                    if area.lower() in title or area.lower() in body:
                        context_score += 20
                context_score = min(100, context_score)

        # Weighted average
        if context_score > 0:
            return title_score * 0.4 + body_score * 0.3 + context_score * 0.3
        else:
            return title_score * 0.6 + body_score * 0.4

    def _assess_depth(
        self,
        result: Dict[str, Any],
    ) -> float:
        """
        Assess content depth

        Returns:
            Depth score 0-100
        """
        body = result.get("body", "") or result.get("snippet", "")

        if not body:
            return 20.0

        # Based on content length
        length = len(body)
        if length < 100:
            return 20.0
        elif length < 300:
            return 40.0
        elif length < 500:
            return 60.0
        elif length < 1000:
            return 80.0
        else:
            return 100.0

    def _assess_freshness(
        self,
        result: Dict[str, Any],
    ) -> float:
        """
        Assess timeliness

        Returns:
            Timeliness score 0-100
        """
        # If has date field, calculate based on date
        date_str = result.get("date", "") or result.get("published", "")

        if date_str:
            # Try to parse date
            try:
                from datetime import datetime, timedelta
                # Common date formats
                for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"]:
                    try:
                        pub_date = datetime.strptime(date_str, fmt)
                        days_ago = (datetime.now() - pub_date).days

                        if days_ago < 30:
                            return 100.0
                        elif days_ago < 90:
                            return 80.0
                        elif days_ago < 180:
                            return 60.0
                        elif days_ago < 365:
                            return 40.0
                        else:
                            return 20.0
                    except ValueError:
                        continue
            except (ValueError, OverflowError, ImportError):
                pass

        # Default to medium timeliness score
        return 60.0


def create_quality_filter(
    min_quality_score: float = 40.0,
) -> SearchQualityFilter:
    """Create quality filter instance"""
    return SearchQualityFilter(min_quality_score=min_quality_score)


__all__ = [
    "SearchQualityFilter",
    "QualityScore",
    "SourceCredibility",
    "AUTHORITY_SOURCES",
    "LOW_QUALITY_PATTERNS",
    "create_quality_filter",
]
