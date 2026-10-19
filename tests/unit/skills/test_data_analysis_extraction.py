"""DataAnalysisSkill extraction: price bands and policy quotas are not company shares."""

from src.skills.analysis.data_analysis import DataAnalysisSkill


def test_price_band_and_policy_quota_are_not_company_shares():
    skill = DataAnalysisSkill()
    extracted = skill._extract_numbers(
        [
            {
                "title": "新能源汽车积分比例要求",
                "content": "2025年 中国 新能源汽车积分比例要求: 38% | 2024年度、2025年度的新能源汽车积分比例要求分别为28%和38%。",
                "data": {
                    "metric": "新能源汽车积分比例要求",
                    "value": "38%",
                    "unit": "",
                    "period": "2025年",
                    "geographic_scope": "中国",
                },
            },
            {
                "title": "600美元以上市场份额",
                "content": "2026年 中国 600美元以上市场份额: 35.9%市场份额百分比 | IDC预测，2026年中国智能手机市场600美元以上市场份额将达到35.9%",
                "data": {
                    "metric": "600美元以上市场份额",
                    "value": "35.9%",
                    "unit": "市场份额百分比",
                    "period": "2026年",
                    "geographic_scope": "中国",
                },
            },
            {
                "title": "400-600美元市场份额",
                "content": "2026年 中国 400-600美元市场份额: 10.1%市场份额百分比",
                "data": {
                    "metric": "400-600美元市场份额",
                    "value": "10.1%",
                    "unit": "市场份额百分比",
                    "period": "2026年",
                    "geographic_scope": "中国",
                },
            },
        ],
        topic="中国智能手机市场",
    )
    companies = " ".join(s["company"] for s in extracted["market_shares"])
    assert "新能源汽车积分比例要求" not in companies
    assert "600美元" not in companies
    assert "400-600" not in companies
    assert extracted["market_shares"] == []


def test_company_brand_shares_are_extracted():
    skill = DataAnalysisSkill()
    extracted = skill._extract_numbers(
        [
            {
                "title": "2026年Q1华为出货量",
                "content": "根据IDC数据，华为以1250万台的出货量、18.1%的市场份额问鼎榜首。紧随其后的是，vivo以1190万台出货量（市场份额17.3%）位居第二，OPPO以1070万台出货量（市场份额15.5%）",
                "data": {
                    "metric": "2026年Q1华为出货量",
                    "value": "1250万台",
                    "unit": "万台",
                    "period": "2026年Q1",
                    "geographic_scope": "中国",
                },
            }
        ],
        topic="中国智能手机市场",
    )
    by_company = {s["company"]: s["share"] for s in extracted["market_shares"]}
    assert by_company["华为"] == 18.1
    assert by_company["vivo"] == 17.3
    assert by_company["OPPO"] == 15.5


def test_concentration_refuses_when_share_sum_exceeds_105():
    skill = DataAnalysisSkill()
    result = skill._calc_concentration(
        [
            {"company": "A", "share": 50.0},
            {"company": "B", "share": 40.0},
            {"company": "C", "share": 30.0},
        ]
    )
    assert result.get("cr3") is None
    assert "rejected" in result
