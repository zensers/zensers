# -*- coding: utf-8 -*-
import sys, os, asyncio
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\market_report_systerm")

async def main():
    from src.skills.analysis.stock_data import StockDataSkill
    skill = StockDataSkill()
    
    print("=== Test 1: company_info ===")
    r = await skill.execute(action="company_info", symbol="600519")
    print(f"  success: {r.get('success')}")
    if r.get("success"):
        data = r["data"]
        print(f"  keys: {list(data.keys())[:5]}")
        print(f"  content[:200]: {r['content'][:200]}")
    else:
        print(f"  error: {r.get('error', '')[:200]}")
    
    print("\n=== Test 2: financials ===")
    r = await skill.execute(action="financials", symbol="600519")
    print(f"  success: {r.get('success')}")
    if r.get("success"):
        data = r["data"]
        for k in data:
            print(f"  {k}: {len(data[k])} records, cols[:3]={list(data[k][0].keys())[:3]}")
    else:
        print(f"  error: {r.get('error', '')[:200]}")
    
    print("\n=== Test 3: key_metrics ===")
    r = await skill.execute(action="key_metrics", symbol="600519")
    print(f"  success: {r.get('success')}")
    if r.get("success"):
        data = r["data"]
        periods = data.get("periods", [])
        print(f"  periods: {len(periods)}")
        if periods:
            print(f"  first period keys[:5]: {list(periods[0].keys())[:5]}")
            for k, v in list(periods[0].items())[:5]:
                print(f"    {k}: {v}")
        print(f"  content[:300]: {r['content'][:300]}")
    else:
        print(f"  error: {r.get('error', '')[:200]}")
    
    print("\n=== Test 4: price_history ===")
    r = await skill.execute(action="price_history", symbol="600519")
    print(f"  success: {r.get('success')}")
    if r.get("success"):
        data = r["data"]
        print(f"  records: {len(data)}")
        if data:
            print(f"  first record keys: {list(data[0].keys())}")
    else:
        print(f"  error: {r.get('error', '')[:200]}")

    print("\n=== Format test with GenericAgent ===")
    from src.core.agents.generic_agent import GenericAgent
    agent = GenericAgent(agent_id="test", agent_type="dynamic", config={"skills": [], "context": {}})
    
    r2 = await skill.execute(action="key_metrics", symbol="600519")
    if r2.get("success"):
        formatted = agent._format_structured_data(r2["data"], "key_metrics", "600519")
        print(f"  formatted len: {len(formatted)}")
        print(f"  formatted:")
        print(formatted)

    r3 = await skill.execute(action="financials", symbol="600519")
    if r3.get("success"):
        formatted = agent._format_structured_data(r3["data"], "financials", "600519")
        print(f"\n  financials formatted len: {len(formatted)}")
        print(f"  financials formatted:")
        print(formatted[:500])

asyncio.run(main())
