from src.core.decomposition.strategies import SectionDataSpec, SubSectionSpec
from src.core.deep_mode.config import DeepModeConfig
from src.core.deep_mode.planner import DeepModePlanner
from src.core.deep_mode.query_builder import DeepQueryBuilder

SECTIONS = [
    {
        "id": "competitive_landscape",
        "name": "竞争格局",
        "points": ["头部企业市场份额及变化", "CR4/CR8 集中度"],
    },
    {
        "id": "technology_trends",
        "name": "技术趋势",
        "points": ["BOM 成本拆解", "关键技术突破"],
    },
    {
        "id": "value_chain",
        "name": "产业链",
        "points": ["关键供应商与议价能力"],
    },
]


def test_plan_maps_sections():
    planner = DeepModePlanner(DeepModeConfig())

    plan = planner.build_plan(
        "新能源汽车",
        SECTIONS,
        "industry_report",
        companies=["比亚迪", "特斯拉"],
    )

    assert plan is not None
    assert plan.sections["company_share"] == "competitive_landscape"
    assert plan.sections["bom_item"] == "technology_trends"
    assert plan.sections["supplier"] == "value_chain"
    assert plan.companies == ["比亚迪", "特斯拉"]
    assert "动力电池" in plan.bom_systems


def test_non_industry_returns_none():
    planner = DeepModePlanner(DeepModeConfig())

    assert planner.build_plan("宁德时代", SECTIONS, "company_report") is None


def test_query_builder_respects_budget_and_types():
    planner = DeepModePlanner(DeepModeConfig(max_searches=10))
    plan = planner.build_plan(
        "新能源汽车",
        SECTIONS,
        "industry_report",
        companies=["比亚迪", "特斯拉", "蔚来"],
    )
    builder = DeepQueryBuilder()

    queries = builder.build("新能源汽车", plan, DeepModeConfig(max_searches=10), year=2025)

    assert 0 < len(queries) <= 10
    assert {query.record_type for query in queries} == {
        "company_share",
        "bom_item",
        "supplier",
    }
    assert all(query.query.strip() for query in queries)


def _section_spec(section_id: str, name: str, needs: list[str]) -> SectionDataSpec:
    return SectionDataSpec(
        section_id=section_id,
        name=name,
        sub_sections=[
            SubSectionSpec(
                sub_section_id=f"{section_id}_1",
                name=name,
                data_needs=needs,
            )
        ],
    )


def test_plan_maps_distinct_production_sections():
    specs = [
        _section_spec(
            "section_1",
            "竞争格局",
            ["头部企业市场份额及变化", "技术壁垒与专利护城河", "供应商议价能力"],
        ),
        _section_spec("section_2", "技术趋势", ["BOM成本拆解", "关键技术突破"]),
        _section_spec("section_3", "产业链", ["上游原材料供应格局", "关键供应商与议价能力"]),
    ]

    plan = DeepModePlanner(DeepModeConfig()).build_plan(
        "新能源汽车", specs, "industry_report"
    )

    assert plan is not None
    assert plan.sections == {
        "company_share": "section_1",
        "bom_item": "section_2",
        "supplier": "section_3",
    }


def test_plan_supports_nested_mapping_sections():
    specs = [
        {
            "id": "section_1",
            "name": "竞争格局",
            "sub_sections": [{"data_needs": ["市场份额", "技术壁垒"]}],
        },
        {
            "id": "section_2",
            "name": "技术趋势",
            "sub_sections": [{"data_needs": ["BOM 成本拆解"]}],
        },
        {
            "id": "section_3",
            "name": "产业链",
            "sub_sections": [{"data_needs": ["关键供应商"]}],
        },
    ]

    plan = DeepModePlanner(DeepModeConfig()).build_plan(
        "新能源汽车", specs, "industry_report"
    )

    assert plan is not None
    assert plan.sections == {
        "company_share": "section_1",
        "bom_item": "section_2",
        "supplier": "section_3",
    }


def test_plan_prefers_strong_name_match_over_earlier_decoy_needs():
    specs = [
        _section_spec("section_1", "行业概览", ["产业链定位与上下游关系"]),
        _section_spec("section_2", "政策环境", ["补贴政策"]),
        _section_spec("section_3", "竞争格局", ["头部企业市场份额及变化", "技术壁垒"]),
        _section_spec("section_4", "产业链分析", ["关键供应商与议价能力"]),
        _section_spec("section_5", "增长驱动", ["技术驱动与消费升级"]),
        _section_spec("section_6", "技术趋势", ["BOM成本拆解"]),
    ]

    plan = DeepModePlanner(DeepModeConfig()).build_plan(
        "新能源汽车", specs, "industry_report"
    )

    assert plan is not None
    assert plan.sections == {
        "company_share": "section_3",
        "bom_item": "section_6",
        "supplier": "section_4",
    }


def test_query_builder_honors_configured_minimum_above_five():
    config = DeepModeConfig(
        min_queries_per_section=8,
        max_queries_per_section=8,
        max_searches=24,
    )
    plan = DeepModePlanner(config).build_plan(
        "新能源汽车", SECTIONS, "industry_report"
    )
    assert plan is not None

    queries = DeepQueryBuilder().build("新能源汽车", plan, config, year=2025)
    counts = {
        record_type: sum(query.record_type == record_type for query in queries)
        for record_type in ("company_share", "bom_item", "supplier")
    }

    assert counts == {"company_share": 8, "bom_item": 8, "supplier": 8}
