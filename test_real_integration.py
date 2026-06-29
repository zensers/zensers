import asyncio
from src.core.entity_resolver import EntityResolver, get_entity_resolver

async def test():
    resolver = get_entity_resolver()
    
    # Test 1: Multi-entity listed companies
    print("=== Test 1: Multi-entity listed companies ===")
    result = await resolver.resolve("比亚迪与宁德时代财务对比")
    for e in result:
        print(f"  {e.name}: code={e.resolved_code}, listed={e.is_listed}")
    
    # Test 2: Non-listed (no suffix, not in A-share table)
    print("\n=== Test 2: Non-listed company ===")
    result2 = await resolver.resolve("华为技术路线分析")
    for e in result2:
        print(f"  {e.name}: code={e.resolved_code}, listed={e.is_listed}")
    if not result2:
        print("  (no entities extracted - expected for non-listed)")
    
    # Test 3: Full decompose -> stock_data injection
    print("\n=== Test 3: decompose() with real akshare data ===")
    from src.core.decomposition.strategies import IndustryResearchStrategy, ResearchPhase
    from dataclasses import dataclass, field as f
    
    @dataclass
    class FakeReq:
        topic: str = "比亚迪股份有限公司竞争格局"
        aspects: list = f(default_factory=lambda: ["竞争格局"])
    
    strategy = IndustryResearchStrategy()
    plan = await strategy.decompose(FakeReq(), None, {})
    
    dc_agents = plan.phases.get(ResearchPhase.DATA_COLLECTION, [])
    if dc_agents:
        agent = dc_agents[0]
        print(f"  DC agent skills: {agent.skills}")
        ent = agent.context.get("entities", [])
        print(f"  DC agent entities: {ent}")
        print(f"  stock_data in skills: {'stock_data' in agent.skills}")
    
    # Test 4: _fetch_structured_data with context entities
    print("\n=== Test 4: _fetch_structured_data with real resolved code ===")
    from src.core.agents.generic_agent import GenericAgent
    from unittest.mock import AsyncMock
    
    agent = GenericAgent.__new__(GenericAgent)
    agent.agent_id = "test"
    agent.agent_type = "research"
    agent._context = {
        "entities": [
            {"name": "比亚迪", "stock_code": "002594", "is_listed": True},
        ]
    }
    
    mock_skill = AsyncMock()
    mock_skill.execute.return_value = {
        "success": True,
        "data": {"revenue": "4240.6亿", "profit": "300.4亿"},
        "content": "",
    }
    
    result = await agent._fetch_structured_data(mock_skill, "比亚迪财务分析", "财务分析")
    print(f"  data_points: {len(result['data_points'])}")
    print(f"  sources: {len(result['sources'])}")
    if result["data_points"]:
        dp = result["data_points"][0]
        print(f"  first data_point title: {dp['title']}")
        print(f"  first data_point quality_score: {dp['quality_score']}")
        print(f"  first data_point credibility: {dp['credibility']}")
    
    # Test 5: Verify actual akshare data fetch
    print("\n=== Test 5: Actual akshare data fetch ===")
    from src.skills.analysis.stock_data import StockDataSkill
    skill = StockDataSkill()
    sr = await skill.execute(action="company_info", symbol="002594")
    if sr and sr.get("success"):
        data = sr.get("data", {})
        print(f"  Success! Data keys: {list(data.keys())[:10]}")
        content = sr.get("content", "")
        if content:
            print(f"  Content preview: {content[:200]}")
    else:
        print(f"  Failed or no data: {sr}")

asyncio.run(test())
