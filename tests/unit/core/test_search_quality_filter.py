import pytest
from src.core.search_quality_filter import SearchQualityFilter


class TestSplitQueryTerms:
    def test_english_space_split(self):
        terms = SearchQualityFilter._split_query_terms("AI chip market")
        assert "ai" in terms
        assert "chip" in terms
        assert "market" in terms

    def test_chinese_jieba_segmentation(self):
        terms = SearchQualityFilter._split_query_terms("新能源汽车市场")
        assert any(t in terms for t in ["新能源", "汽车", "市场", "新能源汽车"])

    def test_chinese_stopwords_removed(self):
        terms = SearchQualityFilter._split_query_terms("中国的市场")
        assert "的" not in terms

    def test_mixed_chinese_english(self):
        terms = SearchQualityFilter._split_query_terms("AI芯片国产化")
        assert any("芯片" in t or "国产" in t or "ai" in t.lower() for t in terms)

    def test_jieba_fallback_bigram(self):
        import unittest.mock
        with unittest.mock.patch.dict("sys.modules", {"jieba": None}):
            terms = SearchQualityFilter._split_query_terms("新能源汽车")
            assert any(len(t) >= 2 for t in terms if any('\u4e00' <= c <= '\u9fff' for c in t))


class TestAssessFreshness:
    def setup_method(self):
        self.filter = SearchQualityFilter()

    def test_standard_date_format(self):
        from datetime import datetime, timedelta
        recent = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        score = self.filter._assess_freshness({"date": recent})
        assert score == 100.0

    def test_chinese_date_format(self):
        from datetime import datetime, timedelta
        recent = (datetime.now() - timedelta(days=10)).strftime("%Y年%m月%d日")
        score = self.filter._assess_freshness({"date": recent})
        assert score == 100.0

    def test_dot_date_format(self):
        from datetime import datetime, timedelta
        recent = (datetime.now() - timedelta(days=20)).strftime("%Y.%m.%d")
        score = self.filter._assess_freshness({"date": recent})
        assert score == 100.0

    def test_iso_date_format(self):
        from datetime import datetime, timedelta
        recent = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%dT%H:%M:%S")
        score = self.filter._assess_freshness({"date": recent})
        assert score == 100.0

    def test_relative_date_days_ago(self):
        score = self.filter._assess_freshness({"date": "3天前"})
        assert score == 100.0

    def test_relative_date_months_ago(self):
        score = self.filter._assess_freshness({"date": "2月前"})
        assert score == 80.0

    def test_relative_date_yesterday(self):
        score = self.filter._assess_freshness({"date": "昨天"})
        assert score == 100.0

    def test_old_date_low_score(self):
        from datetime import datetime, timedelta
        old = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
        score = self.filter._assess_freshness({"date": old})
        assert score == 20.0

    def test_no_date_defaults_medium(self):
        score = self.filter._assess_freshness({})
        assert score == 60.0

    def test_unparseable_date_defaults_medium(self):
        score = self.filter._assess_freshness({"date": "recently"})
        assert score == 60.0

    def test_published_field_used(self):
        from datetime import datetime, timedelta
        recent = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        score = self.filter._assess_freshness({"published": recent})
        assert score == 100.0
