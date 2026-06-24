"""
Skill keyword mapping table

Used for intelligent fuzzy matching, mapping user requirement keywords to appropriate Skills.

Design principles:
- Simple and practical, no vector search needed
- Supports Chinese and English keywords
- Supports synonyms and variants
- Falls back to llm_skill automatically when no match is found

Usage:
    from src.skills.skill_keywords import match_skills
    
    skills = match_skills("patent analysis")
    # Returns: ["lc_arxiv", "llm_skill"]
"""

from typing import List, Dict, Set
from difflib import get_close_matches
import logging

logger = logging.getLogger(__name__)


# ============================================================
# LangChain Skills keyword mapping table
# ============================================================

SKILL_KEYWORDS: Dict[str, Set[str]] = {
    # Search
    "lc_tavily_search": {
        "search", "web search", "internet search", "real-time search",
        "news search", "look up", "retrieve", "query", "find",
        "check", "browse",
    },
    
    "lc_wikipedia": {
        "wikipedia", "wiki", "encyclopedia", "knowledge",
        "concept", "definition", "term", "glossary",
        "reference",
    },
    
    # Academic
    "lc_arxiv": {
        "arxiv", "academic", "paper", "research paper",
        "journal", "publication", "preprint",
        "patent", "patent analysis",
        "scholarly", "literature", "research",
    },
    
    "lc_semantic_scholar": {
        "semantic scholar", "scholar", "citation",
        "semantic search", "academic search",
        "paper search", "cited by",
    },
    
    # Data analysis
    "lc_python_repl": {
        "python", "repl", "code execution", "script",
        "data analysis", "calculation", "statistics",
        "programming", "visualization",
        "data processing", "compute",
    },
    
    "lc_pandas": {
        "pandas", "dataframe", "table", "data cleaning",
        "tabular analysis", "data wrangling",
    },
    
    # Web scraping
    "lc_web_scraper": {
        "scrape", "scraper", "crawl", "extract",
        "web content", "html", "web scraping",
        "data collection", "scraping",
    },
    
    # Database
    "lc_sql_database": {
        "sql", "database", "db", "query",
        "database query", "database operation",
    },
    
    # Weather
    "lc_open_meteo": {
        "weather", "meteorology", "temperature", "forecast",
        "climate",
    },
    
    # Geography
    "lc_google_places": {
        "place", "location", "geo", "address", "map",
        "restaurant", "store", "venue",
        "geography", "places",
    },
    
    # --- Professional Analysis Skills ---
    "market_analysis": {
        "market analysis", "competitive landscape", "market share", "market size",
        "行业分析", "竞争格局", "市场份额", "市场规模",
    },
    "stock_data": {
        "stock data", "financial data", "akshare", "stock quote",
        "financial statement", "profit sheet", "balance sheet", "cash flow",
        "财务数据", "股票数据", "利润表", "资产负债表", "现金流量表",
    },
    "stock_analysis": {
        "stock analysis", "valuation analysis", "financial health",
        "growth analysis", "investment value",
        "股票分析", "估值分析", "财务健康", "成长性分析",
    },
    "data_analysis": {
        "data analysis", "statistical analysis", "quantitative analysis",
        "cagr", "cr3", "hhi", "descriptive statistics",
        "统计分析", "定量分析", "集中度", "描述性统计",
    },
    "policy_analysis": {
        "policy analysis", "regulation analysis", "compliance",
        "government policy", "regulatory impact",
        "政策分析", "监管分析", "合规分析",
    },
    "tech_trend": {
        "technology trend", "patent analysis",
        "innovation", "technology roadmap",
        "技术趋势", "专利分析", "技术路线",
    },
    "risk_analysis": {
        "risk analysis", "risk assessment", "risk factor",
        "risk management", "credit risk", "market risk",
        "风险分析", "风险评估", "风险管理",
    },
}

# ============================================================
# LLM Skill (universal fallback)
# ============================================================

LLM_FALLBACK_SKILL = "llm_skill"

LLM_KEYWORDS: Set[str] = {
    "analyze", "reasoning", "summarize", "explain",
    "describe", "write", "translate", "optimize",
    "compare", "evaluate", "judge", "recommend",
    "predict", "ai", "think", "understand",
    "draft", "rewrite", "polish", "improve",
    "contrast", "assess", "suggest", "forecast",
    "insight", "generate", "compose",
}


def match_skills(
    query: str,
    threshold: float = 0.6,
    max_matches: int = 3,
) -> List[str]:
    """
    Fuzzy match Skills
    
    Args:
        query: User query keywords (e.g. "patent analysis", "data analysis")
        threshold: Match threshold (0.0-1.0), default 0.6
        max_matches: Maximum number of Skills to return, default 3
        
    Returns:
        List of matched Skill names (e.g. ["lc_arxiv", "llm_skill"])
        
    Example:
        >>> match_skills("patent analysis")
        ["lc_arxiv", "llm_skill"]
        
        >>> match_skills("data analysis")
        ["lc_python_repl", "llm_skill"]
        
        >>> match_skills("quantum computing")
        ["llm_skill"]  # No match, falls back to LLM
    """
    query_lower = query.lower().strip()
    matched_skills: List[str] = []
    
    # 1. Exact match
    for skill_name, keywords in SKILL_KEYWORDS.items():
        if query_lower in keywords:
            matched_skills.append(skill_name)
            logger.debug(f"Exact match: '{query}' -> {skill_name}")
    
    # 2. Fuzzy match (using difflib)
    if len(matched_skills) < max_matches:
        all_keywords: List[str] = []
        keyword_to_skill: Dict[str, str] = {}
        
        for skill_name, keywords in SKILL_KEYWORDS.items():
            for kw in keywords:
                all_keywords.append(kw.lower())
                keyword_to_skill[kw.lower()] = skill_name
        
        # Find close matching keywords
        close_matches = get_close_matches(
            query_lower, 
            all_keywords, 
            n=max_matches,
            cutoff=threshold
        )
        
        for match in close_matches:
            skill = keyword_to_skill.get(match)
            if skill and skill not in matched_skills:
                matched_skills.append(skill)
                logger.debug(f"Fuzzy match: '{query}' ~ '{match}' -> {skill}")
    
    # 3. Check if LLM is needed
    # If the query contains LLM-related keywords, or no other match exists
    needs_llm = False
    
    for kw in LLM_KEYWORDS:
        if kw in query_lower:
            needs_llm = True
            break
    
    # If no LangChain Skill matched, or LLM is explicitly needed
    if needs_llm or len(matched_skills) == 0:
        if LLM_FALLBACK_SKILL not in matched_skills:
            matched_skills.append(LLM_FALLBACK_SKILL)
            logger.debug(f"LLM fallback: '{query}' needs reasoning")
    
    return matched_skills[:max_matches]


def get_skill_description(skill_name: str) -> str:
    """
    Get Skill description
    
    Args:
        skill_name: Skill name
        
    Returns:
        Skill description text
    """
    descriptions = {
        "lc_tavily_search": "Real-time web search, get the latest information",
        "lc_wikipedia": "Encyclopedia knowledge query, get concept definitions",
        "lc_arxiv": "Academic paper search, get research results",
        "lc_python_repl": "Python code execution, data analysis and computation",
        "lc_web_scraper": "Web content scraping, extract structured data",
        "llm_skill": "LLM reasoning analysis, intelligent understanding and generation",
        "market_analysis": "Market analysis with SWOT/PEST/Five Forces frameworks",
        "stock_data": "Stock and financial data retrieval via akshare",
        "stock_analysis": "Stock valuation and financial health analysis",
        "data_analysis": "Statistical and quantitative data analysis (CAGR, CR3, HHI)",
        "policy_analysis": "Policy and regulatory impact analysis",
        "tech_trend": "Technology trend and patent analysis",
        "risk_analysis": "Risk assessment and risk management analysis",
    }
    return descriptions.get(skill_name, f"Skill: {skill_name}")


def list_available_skills() -> Dict[str, str]:
    """
    List all available Skills (LangChain + Professional Analysis)
    
    Returns:
        {skill_name: description} dictionary
    """
    return {
        skill: get_skill_description(skill)
        for skill in SKILL_KEYWORDS.keys()
    }


def list_available_langchain_skills() -> Dict[str, str]:
    """
    List all available LangChain Skills
    
    Returns:
        {skill_name: description} dictionary
    """
    return {
        skill: get_skill_description(skill)
        for skill in SKILL_KEYWORDS.keys()
        if skill.startswith("lc_")
    }