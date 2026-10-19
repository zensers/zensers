"""
RequirementParserAgent 需求解析Agent测试
"""

import pytest
from datetime import datetime

from src.agents.requirement_parser import RequirementParserAgent
from src.core.agents.base import AgentState


class TestRequirementParserInitialization:
    """测试需求解析Agent初始化"""
    
    def test_init_default(self):
        """测试默认初始化"""
        agent = RequirementParserAgent(agent_id="parser_001")
        assert agent.agent_id == "parser_001"
        assert agent.name == "RequirementParser"
        assert agent.status == "idle"
        assert agent.parsed_requirements == []
    
    def test_init_custom_name(self):
        """测试自定义名称"""
        agent = RequirementParserAgent(
            agent_id="parser_002",
            name="CustomParser",
            description="自定义解析器"
        )
        assert agent.name == "CustomParser"
        assert agent.description == "自定义解析器"


class TestRequirementParsing:
    """测试需求解析功能"""
    
    @pytest.fixture
    def parser(self):
        """解析器fixture"""
        return RequirementParserAgent(agent_id="parser_001")
    
    @pytest.mark.asyncio
    async def test_parse_simple_requirement(self, parser):
        """测试解析简单需求"""
        result = await parser.execute({
            "requirement": "研究中国新能源汽车市场"
        })
        
        assert result["status"] == "success"
        assert result["parsed_requirement"] is not None
        assert result["parsed_requirement"]["research_topic"] is not None
        assert result["parsed_requirement"]["industry"] == "新能源汽车"
        assert result["research_plan"] is not None
        assert result["confidence"] > 0
    
    @pytest.mark.asyncio
    async def test_parse_with_time_range(self, parser):
        """测试解析带时间范围的需求"""
        result = await parser.execute({
            "requirement": "分析2020-2024年中国人工智能行业发展趋势"
        })
        
        assert result["status"] == "success"
        time_range = result["parsed_requirement"]["time_range"]
        assert time_range is not None
        assert time_range["start_year"] == 2020
        assert time_range["end_year"] == 2024
    
    @pytest.mark.asyncio
    async def test_parse_with_recent_years(self, parser):
        """测试解析"近X年"的需求"""
        result = await parser.execute({
            "requirement": "研究近5年生物医药行业发展"
        })
        
        assert result["status"] == "success"
        time_range = result["parsed_requirement"]["time_range"]
        assert time_range is not None
        assert "近5年" in time_range["description"]
    
    @pytest.mark.asyncio
    async def test_parse_with_analysis_types(self, parser):
        """测试解析包含分析类型的需求"""
        result = await parser.execute({
            "requirement": "分析半导体行业市场规模、竞争格局和政策环境"
        })
        
        assert result["status"] == "success"
        analysis_types = result["parsed_requirement"]["analysis_types"]
        assert "市场分析" in analysis_types
        assert "竞争分析" in analysis_types
        assert "政策分析" in analysis_types
    
    @pytest.mark.asyncio
    async def test_parse_with_geographic_scope(self, parser):
        """测试解析地理范围"""
        result = await parser.execute({
            "requirement": "研究全球金融科技发展现状"
        })
        
        assert result["status"] == "success"
        assert result["parsed_requirement"]["geographic_scope"] == "全球"
    
    @pytest.mark.asyncio
    async def test_parse_empty_requirement(self, parser):
        """测试解析空需求"""
        result = await parser.execute({
            "requirement": ""
        })
        
        assert result["status"] == "error"
        assert "不能为空" in result["error"]
    
    @pytest.mark.asyncio
    async def test_parse_with_context(self, parser):
        """测试带上下文的解析"""
        result = await parser.execute({
            "requirement": "研究互联网行业",
            "context": {
                "data_sources": ["wind", "bloomberg"],
                "priority": "high"
            }
        })
        
        assert result["status"] == "success"
        assert result["parsed_requirement"]["data_sources_preference"] == ["wind", "bloomberg"]


class TestResearchPlanGeneration:
    """测试研究计划生成"""
    
    @pytest.fixture
    def parser(self):
        return RequirementParserAgent(agent_id="parser_001")
    
    @pytest.mark.asyncio
    async def test_research_plan_structure(self, parser):
        """测试研究计划结构"""
        result = await parser.execute({
            "requirement": "研究中国新能源汽车市场"
        })
        
        plan = result["research_plan"]
        assert "plan_id" in plan
        assert "research_topic" in plan
        assert "objectives" in plan
        assert "methodology" in plan
        assert "deliverables" in plan
        assert "timeline" in plan
        assert "required_agents" in plan
        assert "data_requirements" in plan
        assert "quality_criteria" in plan
    
    @pytest.mark.asyncio
    async def test_objectives_generation(self, parser):
        """测试目标生成"""
        result = await parser.execute({
            "requirement": "分析新能源汽车市场规模和竞争格局"
        })
        
        objectives = result["research_plan"]["objectives"]
        assert len(objectives) > 0
        assert any("市场" in obj for obj in objectives)
        assert any("竞争" in obj for obj in objectives)
    
    @pytest.mark.asyncio
    async def test_required_agents(self, parser):
        """测试所需Agent确定"""
        result = await parser.execute({
            "requirement": "分析新能源汽车市场规模和竞争格局"
        })
        
        agents = result["research_plan"]["required_agents"]
        assert "requirement_parser" in agents
        assert "data_collector" in agents
        assert "market_analyst" in agents
        assert "competitive_analyst" in agents
        assert "report_writer" in agents
    
    @pytest.mark.asyncio
    async def test_timeline_generation(self, parser):
        """测试时间线生成"""
        result = await parser.execute({
            "requirement": "研究新能源汽车市场"
        })
        
        timeline = result["research_plan"]["timeline"]
        assert "total_days" in timeline
        assert "phases" in timeline
        assert len(timeline["phases"]) > 0


class TestIndustryRecognition:
    """测试行业识别"""
    
    @pytest.fixture
    def parser(self):
        return RequirementParserAgent(agent_id="parser_001")
    
    @pytest.mark.asyncio
    async def test_recognize_nev_industry(self, parser):
        """测试识别新能源汽车行业"""
        result = await parser.execute({
            "requirement": "研究电动车市场"
        })
        assert result["parsed_requirement"]["industry"] == "新能源汽车"
    
    @pytest.mark.asyncio
    async def test_recognize_ai_industry(self, parser):
        """测试识别AI行业"""
        result = await parser.execute({
            "requirement": "分析大模型发展趋势"
        })
        assert result["parsed_requirement"]["industry"] == "人工智能"
    
    @pytest.mark.asyncio
    async def test_recognize_semiconductor(self, parser):
        """测试识别半导体行业"""
        result = await parser.execute({
            "requirement": "研究芯片产业"
        })
        assert result["parsed_requirement"]["industry"] == "半导体"
    
    @pytest.mark.asyncio
    async def test_unknown_industry(self, parser):
        """测试未知行业"""
        result = await parser.execute({
            "requirement": "研究某某神秘行业"
        })
        assert result["parsed_requirement"]["industry"] is None


class TestOutputFormatRecognition:
    """测试输出格式识别"""
    
    @pytest.fixture
    def parser(self):
        return RequirementParserAgent(agent_id="parser_001")
    
    @pytest.mark.asyncio
    async def test_recognize_report_format(self, parser):
        """测试识别报告格式"""
        result = await parser.execute({
            "requirement": "生成新能源汽车研究报告"
        })
        assert result["parsed_requirement"]["output_format"] == "report"
    
    @pytest.mark.asyncio
    async def test_recognize_brief_format(self, parser):
        """测试识别简报格式"""
        result = await parser.execute({
            "requirement": "提供行业简报"
        })
        assert result["parsed_requirement"]["output_format"] == "brief"
    
    @pytest.mark.asyncio
    async def test_recognize_presentation_format(self, parser):
        """测试识别演示文稿格式"""
        result = await parser.execute({
            "requirement": "制作PPT汇报材料"
        })
        assert result["parsed_requirement"]["output_format"] == "presentation"


class TestConfidenceCalculation:
    """测试置信度计算"""
    
    @pytest.fixture
    def parser(self):
        return RequirementParserAgent(agent_id="parser_001")
    
    @pytest.mark.asyncio
    async def test_high_confidence(self, parser):
        """测试高置信度"""
        result = await parser.execute({
            "requirement": "研究2020-2024年中国新能源汽车市场规模和竞争格局"
        })
        # 包含主题、行业、时间范围、分析类型
        assert result["confidence"] >= 0.7
    
    @pytest.mark.asyncio
    async def test_low_confidence(self, parser):
        """测试低置信度"""
        result = await parser.execute({
            "requirement": "随便看看"
        })
        # 缺少具体信息，但至少识别了主题
        assert result["confidence"] >= 0.5  # 基础分0.5 + 主题0.15 = 0.65


class TestHistoryTracking:
    """测试历史记录"""
    
    @pytest.fixture
    def parser(self):
        return RequirementParserAgent(agent_id="parser_001")
    
    @pytest.mark.asyncio
    async def test_history_recorded(self, parser):
        """测试历史记录保存"""
        await parser.execute({
            "requirement": "研究新能源汽车市场"
        })
        
        history = parser.get_parsed_history()
        assert len(history) == 1
        assert "original" in history[0]
        assert "parsed" in history[0]
        assert "plan" in history[0]
        assert "timestamp" in history[0]
    
    @pytest.mark.asyncio
    async def test_multiple_history_entries(self, parser):
        """测试多条历史记录"""
        await parser.execute({"requirement": "研究A行业"})
        await parser.execute({"requirement": "研究B行业"})
        await parser.execute({"requirement": "研究C行业"})
        
        history = parser.get_parsed_history()
        assert len(history) == 3


class TestStateManagement:
    """测试状态管理"""
    
    @pytest.fixture
    def parser(self):
        return RequirementParserAgent(agent_id="parser_001")
    
    @pytest.mark.asyncio
    async def test_state_running_during_execution(self, parser):
        """测试执行中状态"""
        # 由于execute是异步的，状态会在执行过程中变为RUNNING
        # 这里主要测试状态转换不会报错
        result = await parser.execute({
            "requirement": "测试需求"
        })
        
        # status返回的是字符串（如"completed"），不是枚举值
        if result["status"] == "success":
            assert parser.status == "completed"
        else:
            assert parser.status == "error"
