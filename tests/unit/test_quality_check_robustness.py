"""
验证 Quality Check 鲁棒性

问题诊断：
  日志中 quality score = 40 的根因不是 Executive Summary（实际 standards=None 时不会检查）
  而是：聚合 key 碰撞 → 8 章节全占位符（50字符）→ word_count=400 < 1000 → 失败

现在聚合 key 和标点匹配已修复 → 正常内容下 quality check 得 70 分已通过。

需要验证的鲁棒性场景：
1. 内容正常 → 应通过（基线）
2. 部分章节内容较短 → 不应全盘崩溃
3. 单章节占位符 → 不应全盘崩溃
4. 所有数值都不同（无幻觉误报）→ 应通过
"""
import pytest
from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent


# 模拟 8 个 agent 产出的真实内容
SECTION_CONTENTS = {
    "核心财务指标与盈利能力": "2025年比亚迪实现营业收入约7771亿元，同比增长21.04%。其中汽车业务收入占比约80%。"
    "归母净利润402.54亿元，同比增长34.04%。毛利率18.81%，净利率5.18%。"
    "每股收益12.89元，加权平均净资产收益率16.72%。财务费用约19.08亿元。",

    "研发与创新投入": "2025年比亚迪研发投入约542亿元，同比增长35.16%，研发投入占营收比例约6.97%。"
    "研发人员超过10万人，累计专利申请量已突破5万件。"
    "在刀片电池、DM-i超级混动、e平台3.0、云辇、易四方等核心技术上持续迭代。"
    "2025年研发投入产出效率持续提升，单车研发成本约1.27万元。",

    "供应链成本效率": "2025年比亚迪垂直整合率持续提升，除轮胎、玻璃等少数部件外，核心零部件自制率超过80%。"
    "规模效应显著，单车成本同比下降约5%。产能利用率维持在85%以上。"
    "与上游锂矿、芯片等供应商签订长期协议，锁定关键资源价格。"
    "库存周转天数降至45天，运营效率行业领先。",

    "销量与市场份额": "2025年全年新能源汽车销量427.21万辆，同比增长40.87%。"
    "其中纯电动车型占比52%，插电混动车型占比48%。"
    "国内新能源汽车市占率33.2%，较2024年提升1.5个百分点。"
    "乘用车出口40.85万辆，覆盖全球70多个国家和地区。"
    "高端品牌仰望、方程豹、腾势合计销量占比约8%，ASP持续提升。",

    "国际化与出口": "2025年比亚迪汽车出口40.85万辆，同比增长58.44%。"
    "海外市场收入约1800亿元，占比提升至23%。"
    "在泰国、巴西、匈牙利、印尼等国家建设海外工厂，本地化产能逐步释放。"
    "出口车型以元PLUS（ATTO 3）、海豚、海鸥等为主，在欧洲、东南亚、拉美市场表现突出。",

    "财务健康、风险评估与季度业绩波动": "2025年末资产负债率70.94%，较上年下降2.1个百分点。"
    "经营活动现金流净额1869.94亿元，同比增长32.6%。"
    "货币资金储备约1200亿元，短期偿债能力充足。"
    "2025年Q1-Q4单季度营收分别为：1704亿元、1802亿元、1965亿元、2300亿元，呈逐季增长态势。"
    "主要风险点：价格战加剧压缩利润空间、地缘政治风险影响海外扩张、汇率波动。",

    "行业对标与竞争格局": "2025年比亚迪销量427.21万辆，特斯拉178.46万辆，差距持续扩大。"
    "吉利汽车新能源销量185万辆，长安汽车130万辆，长城汽车80万辆。"
    "比亚迪在国内新能源市场份额33.2%，排名第一；全球市场份额约18.5%，仅次于特斯拉。"
    "在20-30万元价格带，比亚迪以汉、唐、海豹等车型保持竞争优势。",

    "财务预测": "2026年预计营业收入9000-9500亿元，同比增长约15-22%。"
    "净利润预计550-600亿元，同比增长约37-49%。"
    "销量目标500-550万辆，新增海外产能30万辆。"
    "研发投入预计650亿元以上。毛利率预计维持在18-20%区间。"
    "风险提示：新能源汽车补贴退坡、原材料价格波动、行业竞争加剧。",
}


class TestQualityCheckWithRealContent:
    """用真实风格的内容验证 quality check"""

    @pytest.mark.asyncio
    async def test_baseline_passes(self):
        """基线：8 章节完整内容 → 应通过"""
        agent = QualityCheckAgent(agent_id="test", storage_path="/tmp")
        sections = [{"title": k, "content": v} for k, v in SECTION_CONTENTS.items()]
        all_text = "\n\n".join(v for v in SECTION_CONTENTS.values())

        result = await agent.execute({
            "report": {"title": "比亚迪财务分析", "content": all_text, "sections": sections},
            "standards": None,
        })

        score = result.get("quality_score", 0)
        passed = result.get("passed", False)
        print(f"\n基线测试: 得分={score}, 通过={passed}")
        for i in result.get("issues", []):
            print(f"  [{i.get('severity','?')}] {i.get('message','')[:80]}")
        assert passed, f"正常内容应通过，得分 {score}"

    @pytest.mark.asyncio
    async def test_one_short_section_passes(self):
        """一个章节内容极短 → 不应全盘崩溃"""
        agent = QualityCheckAgent(agent_id="test", storage_path="/tmp")
        contents = dict(SECTION_CONTENTS)
        contents["财务健康、风险评估与季度业绩波动"] = "数据不足，本章节待补充。"

        sections = [{"title": k, "content": v} for k, v in contents.items()]
        all_text = "\n\n".join(v for v in contents.values())

        result = await agent.execute({
            "report": {"title": "比亚迪财务分析", "content": all_text, "sections": sections},
            "standards": None,
        })

        score = result.get("quality_score", 0)
        passed = result.get("passed", False)
        print(f"\n单章节较短: 得分={score}, 通过={passed}")
        for i in result.get("issues", []):
            print(f"  [{i.get('severity','?')}] {i.get('message','')[:80]}")

        # 7 个章节完整 + 1 个短 → word_count 仍大幅超过 1000，应通过
        assert passed, f"仅一章较短时仍应通过，得分 {score}"

    @pytest.mark.asyncio
    async def test_no_hallucination_false_positive(self):
        """合法数据不应被 hallucination 检测误报"""
        agent = QualityCheckAgent(agent_id="test", storage_path="/tmp")
        sections = [{"title": k, "content": v} for k, v in SECTION_CONTENTS.items()]
        all_text = "\n\n".join(v for v in SECTION_CONTENTS.values())

        result = await agent.execute({
            "report": {"title": "比亚迪财务分析", "content": all_text, "sections": sections},
            "standards": None,
        })

        hallucination_issues = [
            i for i in result.get("issues", [])
            if i.get("type") in ("accuracy",) and "幻觉" in i.get("message", "")
        ]
        assert len(hallucination_issues) == 0, \
            f"合法内容不应有幻觉误报: {[i['message'] for i in hallucination_issues]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=long"])
