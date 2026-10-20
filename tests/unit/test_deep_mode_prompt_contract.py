import inspect

from src.core.agents.generic_agent import GenericAgent
from src.core.orchestrator.execution import engine


def test_analysis_prompt_accepts_deep_mode_tables():
    signature = inspect.signature(GenericAgent._build_analysis_prompt_with_data)
    assert "deep_mode_tables" in signature.parameters


def test_analysis_prompt_injects_deep_mode_tables():
    agent = GenericAgent.__new__(GenericAgent)
    agent._context = {}
    table = "| 公司 | 市场份额 |\n|---|---|\n| 甲公司 | 30.0%* |"
    prompt = agent._build_analysis_prompt_with_data(
        topic="新能源汽车", aspect="竞争格局", aspects=["竞争格局"],
        data_points=[], sources=[], deep_mode_tables=table,
    )
    assert "深度模式结构化证据" in prompt
    assert "| 甲公司 | 30.0%* |" in prompt


def test_engine_get_tables_collapses_leaf_ids():
    source = inspect.getsource(engine.ExecutionEngine._execute_batch)
    assert source.count("_deep_parent_section_id(analysis_section_id)") >= 2
