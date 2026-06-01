"""
验证 _check_hallucinations 重复值检测的误报问题

re 匹配：r'(\d+\.\d+)' → 匹配所有小数，阈值 5
合法小数在财务报告中跨章节出现 5+ 次是正常的
"""
import pytest
from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent


class TestHallucinationFPExact:
    """精确验证触发边界"""

    @pytest.mark.asyncio
    async def test_legitimate_decimal_5_times_not_flagged(self):
        """
        合法小数出现 5 次不应标记为幻觉
        
        例如：40.85 表示出口量 40.85万辆
        分别在 国际化、财务、销量、对标、风险 五个章节出现
        """
        agent = QualityCheckAgent(agent_id="test", storage_path="/tmp")

        # 40.85 在 5 个不同章节出现，都是合法数据
        content = """
        国际化：2025年出口40.85万辆。
        财务：归母净利润40.85亿元。
        销量：其中出口部分为40.85万辆。
        对标：竞争对手出口约40.85万辆。
        风险：出口40.85万辆面临汇率波动风险。
        """.strip().replace("\n        ", "\n")
        
        report = {
            "title": "test",
            "content": content,
            "sections": [{"title": f"s{idx}", "content": content} for idx in range(5)],
        }

        result = await agent.execute({"report": report})
        hallucination_issues = [
            i for i in result.get("issues", [])
            if "可能为幻觉" in i.get("message", "")
        ]

        # 当前可能误报 → 修复后不应误报
        if hallucination_issues:
            print(f"⚠️ 当前误报: {[i['message'] for i in hallucination_issues]}")
        # 这个测试验证：合法数据即使出现 5 次也不应误报
        # 如果失败（误报），说明检测逻辑需要修复
        assert len(hallucination_issues) == 0, \
            f"合法小数出现 5 次不应误报: {[i['message'] for i in hallucination_issues]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=long"])
