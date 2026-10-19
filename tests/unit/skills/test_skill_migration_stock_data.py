"""
Task 1.3 Step 1: stock_data SKILL.md 迁移测试 - TDD模式
验证 action_rules 与 _infer_stock_actions 完全等价
"""
import pytest
from pathlib import Path


class TestStockDataMigration:
    """验证 stock_data 的 SKILL.md 迁移"""

    def test_stock_data_dir_exists(self):
        assert Path("src/skills/stock_data").is_dir(), "src/skills/stock_data/ 目录不存在"

    def test_stock_data_md_exists(self):
        assert Path("src/skills/stock_data/SKILL.md").is_file(), "src/skills/stock_data/SKILL.md 不存在"

    def test_stock_data_py_exists(self):
        assert Path("src/skills/stock_data/skill.py").is_file(), "src/skills/stock_data/skill.py 不存在"

    def test_stock_data_md_parseable(self):
        import frontmatter
        post = frontmatter.load("src/skills/stock_data/SKILL.md")
        meta = post.metadata
        assert meta["name"] == "stock_data"
        assert meta["priority"] == "structured_db"
        assert "financial-analysis" in meta["categories"]
        assert "financials" in meta["capabilities"]
        assert "key_metrics" in meta["capabilities"]
        assert "company_info" in meta["capabilities"]
        assert "price_history" in meta["capabilities"]
        assert "industry_comparison" in meta["capabilities"]

    def test_stock_data_re_export(self):
        from src.skills.stock_data.skill import StockDataSkill
        from src.skills.analysis.stock_data import StockDataSkill as Original
        assert StockDataSkill is Original

    def test_discovery_finds_stock_data(self):
        from src.skills.discovery import SkillDiscovery
        d = SkillDiscovery()
        manifests = d.discover_all(Path("src/skills"))
        names = [m.name for m in manifests]
        assert "stock_data" in names


class TestStockDataActionRulesParity:
    """
    验证 SKILL.md action_rules 与 _infer_stock_actions() 完全等价。
    每个 _infer_stock_actions 的关键词组都必须在 action_rules 中有对应。
    """

    @pytest.fixture(autouse=True)
    def setup_skill(self):
        from src.skills.analysis.stock_data import StockDataSkill
        from src.skills.discovery import SkillDiscovery
        d = SkillDiscovery()
        manifests = {m.name: m for m in d.discover_all(Path("src/skills"))}
        assert "stock_data" in manifests, "stock_data manifest 未找到"
        self.skill = StockDataSkill()
        self.skill._manifest = manifests["stock_data"]

    def test_profit_keywords_match_financials(self):
        """_infer_stock_actions: 盈利/利润/营收/收入/研发/技术/创新/偿债/现金流/运营效率 → financials"""
        for kw in ["盈利", "利润", "营收", "收入", "研发", "技术", "创新", "偿债", "现金流", "运营效率"]:
            result = self.skill.infer_actions(f"{kw}分析", "SH600519")
            assert "financials" in result, f"关键词'{kw}'应触发 financials，实际: {result}"

    def test_valuation_keywords_match_key_metrics_and_financials(self):
        """_infer_stock_actions: 估值/价值/pe/pb/回报/roe/roa/roic/投资价值 → key_metrics + financials"""
        for kw in ["估值", "价值", "pe", "pb", "回报", "roe", "roa", "roic", "投资价值"]:
            result = self.skill.infer_actions(f"{kw}分析", "SH600519")
            assert "key_metrics" in result, f"关键词'{kw}'应触发 key_metrics，实际: {result}"
            assert "financials" in result, f"关键词'{kw}'应触发 financials，实际: {result}"

    def test_leverage_keywords_match_financials(self):
        """_infer_stock_actions: 杠杆/负债/资本结构/稳健 → financials"""
        for kw in ["杠杆", "负债", "资本结构", "稳健"]:
            result = self.skill.infer_actions(f"{kw}分析", "SH600519")
            assert "financials" in result, f"关键词'{kw}'应触发 financials，实际: {result}"

    def test_comparison_keywords_match_industry_comparison(self):
        """_infer_stock_actions: 对比/竞争/industry → industry_comparison"""
        for kw in ["对比", "竞争", "industry"]:
            result = self.skill.infer_actions(f"{kw}分析", "SH600519")
            assert "industry_comparison" in result, f"关键词'{kw}'应触发 industry_comparison，实际: {result}"

    def test_growth_keywords_match_financials_and_key_metrics(self):
        """_infer_stock_actions: 增长/增速/发展/成长性/growth → financials + key_metrics"""
        for kw in ["增长", "增速", "发展", "成长性", "growth"]:
            result = self.skill.infer_actions(f"{kw}分析", "SH600519")
            assert "financials" in result, f"关键词'{kw}'应触发 financials，实际: {result}"
            assert "key_metrics" in result, f"关键词'{kw}'应触发 key_metrics，实际: {result}"

    def test_sales_keywords_match_financials(self):
        """_infer_stock_actions: 销售/渠道/营收分析/sales → financials"""
        for kw in ["销售", "渠道", "营收分析", "sales"]:
            result = self.skill.infer_actions(f"{kw}分析", "SH600519")
            assert "financials" in result, f"关键词'{kw}'应触发 financials，实际: {result}"

    def test_market_share_keywords_match_industry_comparison(self):
        """_infer_stock_actions: 市场份额/市占率/market share → industry_comparison"""
        for kw in ["市场份额", "市占率", "market share"]:
            result = self.skill.infer_actions(f"{kw}分析", "SH600519")
            assert "industry_comparison" in result, f"关键词'{kw}'应触发 industry_comparison，实际: {result}"

    def test_company_keywords_match_company_info(self):
        """_infer_stock_actions: 公司/企业/company → company_info"""
        for kw in ["公司", "企业", "company"]:
            result = self.skill.infer_actions(f"{kw}分析", "SH600519")
            assert "company_info" in result, f"关键词'{kw}'应触发 company_info，实际: {result}"

    def test_price_keywords_match_price_history(self):
        """_infer_stock_actions: 股价/行情/走势/市值变动/market_cap/price → price_history"""
        for kw in ["股价", "行情", "走势", "市值变动", "market_cap", "price"]:
            result = self.skill.infer_actions(f"{kw}分析", "SH600519")
            assert "price_history" in result, f"关键词'{kw}'应触发 price_history，实际: {result}"

    def test_default_fallback_is_company_info_and_financials(self):
        """_infer_stock_actions: 无关键词匹配时默认返回 company_info + financials"""
        result = self.skill.infer_actions("未知维度分析", "SH600519")
        assert "company_info" in result, f"兜底应包含 company_info，实际: {result}"
        assert "financials" in result, f"兜底应包含 financials，实际: {result}"

    def test_cumulative_matching_profit_plus_valuation(self):
        """累加匹配: '盈利估值分析' 应同时触发 financials + key_metrics"""
        result = self.skill.infer_actions("盈利估值分析", "SH600519")
        assert "financials" in result
        assert "key_metrics" in result

    def test_cumulative_matching_growth_plus_valuation(self):
        """累加匹配: '增长估值分析' 应触发 financials + key_metrics"""
        result = self.skill.infer_actions("增长估值分析", "SH600519")
        assert "financials" in result
        assert "key_metrics" in result

    def test_cumulative_dedup(self):
        """去重: '盈利估值' 匹配多个 rule，financials 不应重复"""
        result = self.skill.infer_actions("盈利估值分析", "SH600519")
        assert result.count("financials") == 1, f"financials 不应重复，实际: {result}"
        assert result.count("key_metrics") == 1, f"key_metrics 不应重复，实际: {result}"


class TestStockDataDataSourceKeywords:
    """验证 stock_data SKILL.md 的 data_source_keywords 与 DATA_SOURCE_SKILL_MAP 一致"""

    def test_data_source_keywords_match(self):
        from src.skills.discovery import SkillDiscovery
        from src.core.decomposition.strategies import DATA_SOURCE_SKILL_MAP
        d = SkillDiscovery()
        manifests = {m.name: m for m in d.discover_all(Path("src/skills"))}
        assert "stock_data" in manifests
        manifest = manifests["stock_data"]
        manifest_keywords = set(manifest.data_source_keywords)
        for keyword, skills in DATA_SOURCE_SKILL_MAP.items():
            if "stock_data" in skills:
                assert keyword in manifest_keywords, \
                    f"DATA_SOURCE_SKILL_MAP 中 '{keyword}' 映射到 stock_data，但 SKILL.md 的 data_source_keywords 缺少此关键词"
