# tests/unit/search/test_keyword_deriver.py
from src.core.search.keyword_deriver import KeywordDeriver


def test_derive_core_words():
    deriver = KeywordDeriver()
    result = deriver.derive("中国新能源汽车市场深度研究")
    assert any("新能源汽车" in w for w in result["core"])
    assert any("出货量" in w or "销量" in w for w in result["caliber"])
    assert any("2025" in w or "2026" in w for w in result["time"])


def test_derive_exclusion_words():
    deriver = KeywordDeriver()
    result = deriver.derive("中国智能手机市场")
    assert "猪肉" not in result["core"]
    assert isinstance(result["exclude"], list)


def test_derive_empty_topic():
    deriver = KeywordDeriver()
    result = deriver.derive("")
    assert result["core"] == []
