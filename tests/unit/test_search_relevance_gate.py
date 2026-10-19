"""Regression tests for search-result relevance gating."""

from src.core.search_quality_filter import SearchQualityFilter


def test_irrelevant_result_is_filtered_even_when_source_is_valid():
    result = {
        "title": "YouTube Music",
        "body": "Listen to music and videos online.",
        "href": "https://www.youtube.com/",
    }
    score = SearchQualityFilter()._calculate_quality_score(result, "鸡蛋价格走势")
    assert score.is_filtered is True
    assert score.filter_reason == "Insufficient query relevance"


def test_relevant_result_survives_relevance_gate():
    result = {
        "title": "鸡蛋价格走势与市场行情",
        "body": "鸡蛋价格近期走势和市场价格变化分析。",
        "href": "https://example.com/egg-price",
    }
    score = SearchQualityFilter()._calculate_quality_score(result, "鸡蛋价格走势")
    assert score.is_filtered is False
    assert score.relevance_score >= 20
