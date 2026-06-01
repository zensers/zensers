"""
需求解析Agent

负责解析用户的研究需求，提取关键参数，生成研究计划。
属于基础设施层Agent。
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import re

from src.core.agents.base import BaseAgent, AgentState


class RequirementParserAgent(BaseAgent):
    """
    需求解析Agent
    
    将用户的自然语言研究需求转换为结构化的研究计划。
    包括：
    - 研究主题提取
    - 研究范围界定
    - 输出格式确定
    - 时间范围解析
    - 数据源偏好
    """
    
    def __init__(
        self,
        agent_id: str,
        name: str = "RequirementParser",
        description: str = "解析研究需求，生成研究计划"
    ):
        super().__init__(agent_id, name, description)
        self.parsed_requirements: List[Dict[str, Any]] = []
    
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行需求解析
        
        Args:
            input_data: 包含用户需求的字典
                - requirement: 用户原始需求描述（字符串）
                - context: 可选的上下文信息
                
        Returns:
            解析后的研究计划
        """
        self.set_state(AgentState.RUNNING)
        
        try:
            requirement_text = input_data.get("requirement", "")
            context = input_data.get("context", {})
            
            if not requirement_text:
                raise ValueError("需求描述不能为空")
            
            # 解析需求
            parsed = self._parse_requirement(requirement_text, context)
            
            # 生成研究计划
            research_plan = self._generate_research_plan(parsed)
            
            # 保存解析记录
            self.parsed_requirements.append({
                "original": requirement_text,
                "parsed": parsed,
                "plan": research_plan,
                "timestamp": datetime.now().isoformat()
            })
            
            self.set_state(AgentState.COMPLETED)
            
            return {
                "status": "success",
                "parsed_requirement": parsed,
                "research_plan": research_plan,
                "confidence": self._calculate_confidence(parsed)
            }
            
        except Exception as e:
            self.set_state(AgentState.ERROR)
            return {
                "status": "error",
                "error": str(e),
                "parsed_requirement": None,
                "research_plan": None
            }
    
    def _parse_requirement(
        self,
        requirement_text: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        解析需求文本
        
        Args:
            requirement_text: 用户原始需求
            context: 上下文信息
            
        Returns:
            解析后的需求结构
        """
        parsed = {
            "original_text": requirement_text,
            "research_topic": None,
            "industry": None,
            "time_range": None,
            "geographic_scope": None,
            "analysis_types": [],
            "output_format": "report",
            "special_requirements": [],
            "data_sources_preference": []
        }
        
        # 提取研究主题
        parsed["research_topic"] = self._extract_topic(requirement_text)
        
        # 识别行业
        parsed["industry"] = self._extract_industry(requirement_text)
        
        # 解析时间范围
        parsed["time_range"] = self._extract_time_range(requirement_text)
        
        # 解析地理范围
        parsed["geographic_scope"] = self._extract_geographic_scope(requirement_text)
        
        # 识别分析类型
        parsed["analysis_types"] = self._extract_analysis_types(requirement_text)
        
        # 识别输出格式
        parsed["output_format"] = self._extract_output_format(requirement_text)
        
        # 提取特殊要求
        parsed["special_requirements"] = self._extract_special_requirements(requirement_text)
        
        # 数据源偏好
        parsed["data_sources_preference"] = context.get("data_sources", [])
        
        return parsed
    
    def _extract_topic(self, text: str) -> str:
        """提取研究主题"""
        # 简单的主题提取：取前50个字符或第一句话
        text = text.strip()
        
        # 尝试找到"研究"、"分析"、"报告"等关键词前的内容
        patterns = [
            r"(?:关于|针对|对)(.+?)(?:的|进行|做)",
            r"(.+?)(?:行业|市场|企业|产品)(?:研究|分析|报告)",
            r"(.+?)(?:研究|分析|报告|调研)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                topic = match.group(1).strip()
                if len(topic) > 3:
                    return topic
        
        # 默认返回前50个字符
        return text[:50] + "..." if len(text) > 50 else text
    
    def _extract_industry(self, text: str) -> Optional[str]:
        """识别行业"""
        industries = {
            "新能源汽车": ["新能源汽车", "电动车", "电动汽车", "NEV"],
            "人工智能": ["人工智能", "AI", "大模型", "机器学习"],
            "半导体": ["半导体", "芯片", "集成电路"],
            "生物医药": ["生物医药", "医药", "医疗器械", "制药"],
            "互联网": ["互联网", "电商", "在线教育", "互联网金融"],
            "金融科技": ["金融科技", "FinTech", "区块链", "数字金融"],
            "制造业": ["制造业", "智能制造", "工业4.0"],
            "消费品": ["消费品", "快消品", "零售", "食品饮料"],
            "房地产": ["房地产", "地产", "建筑", "物业"],
            "能源": ["能源", "石油", "天然气", "电力", "新能源"],
        }
        
        for industry, keywords in industries.items():
            for keyword in keywords:
                if keyword in text:
                    return industry
        
        return None
    
    def _extract_time_range(self, text: str) -> Optional[Dict[str, Any]]:
        """解析时间范围"""
        time_range = {
            "start_year": None,
            "end_year": None,
            "start_date": None,
            "end_date": None,
            "description": None
        }
        
        current_year = datetime.now().year
        
        # 匹配"2020-2024年"或"2020到2024年"
        year_range_pattern = r"(\d{4})\s*(?:-|到|至)\s*(\d{4})\s*年?"
        match = re.search(year_range_pattern, text)
        if match:
            time_range["start_year"] = int(match.group(1))
            time_range["end_year"] = int(match.group(2))
            time_range["description"] = f"{match.group(1)}-{match.group(2)}年"
            return time_range
        
        # 匹配"近5年"、"过去3年"
        recent_pattern = r"(?:近|过去|最近)\s*(\d+)\s*年"
        match = re.search(recent_pattern, text)
        if match:
            years = int(match.group(1))
            time_range["start_year"] = current_year - years
            time_range["end_year"] = current_year
            time_range["description"] = f"近{years}年"
            return time_range
        
        # 匹配"2024年"
        single_year_pattern = r"(\d{4})\s*年"
        match = re.search(single_year_pattern, text)
        if match:
            year = int(match.group(1))
            time_range["start_year"] = year
            time_range["end_year"] = year
            time_range["description"] = f"{year}年"
            return time_range
        
        # 默认：近3年
        time_range["start_year"] = current_year - 3
        time_range["end_year"] = current_year
        time_range["description"] = "近3年"
        return time_range
    
    def _extract_geographic_scope(self, text: str) -> Optional[str]:
        """解析地理范围"""
        scopes = {
            "中国": ["中国", "国内", "全国", "中国大陆"],
            "全球": ["全球", "世界", "国际", "海外"],
            "北美": ["北美", "美国", "加拿大"],
            "欧洲": ["欧洲", "欧盟", "德国", "法国", "英国"],
            "亚太": ["亚太", "亚洲", "日本", "韩国", "东南亚"],
        }
        
        for scope, keywords in scopes.items():
            for keyword in keywords:
                if keyword in text:
                    return scope
        
        return "中国"  # 默认中国
    
    def _extract_analysis_types(self, text: str) -> List[str]:
        """识别分析类型"""
        types = []
        
        type_keywords = {
            "市场分析": ["市场规模", "市场份额", "市场增长", "市场趋势", "市场分析"],
            "竞争分析": ["竞争", "竞争对手", "竞争格局", "竞争力", "市场份额"],
            "财务分析": ["财务", "营收", "利润", "盈利能力", "财务指标"],
            "政策分析": ["政策", "法规", "监管", "政策环境"],
            "技术分析": ["技术", "技术路线", "技术趋势", "技术创新", "研发"],
            "供应链分析": ["供应链", "产业链", "上下游", "供应商"],
            "消费者分析": ["消费者", "用户", "客户需求", "市场调研"],
            "风险分析": ["风险", "风险评估", "风险因素", "不确定性"],
        }
        
        for analysis_type, keywords in type_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    types.append(analysis_type)
                    break
        
        # 如果没有识别到任何类型，默认添加市场分析
        if not types:
            types.append("市场分析")
        
        return types
    
    def _extract_output_format(self, text: str) -> str:
        """识别输出格式"""
        formats = {
            "report": ["报告", "研究报告", "分析报告"],
            "brief": ["简报", "摘要", "概述"],
            "presentation": ["PPT", "演示文稿", "汇报"],
            "data": ["数据", "Excel", "表格", "数据集"],
        }
        
        for fmt, keywords in formats.items():
            for keyword in keywords:
                if keyword in text:
                    return fmt
        
        return "report"  # 默认报告格式
    
    def _extract_special_requirements(self, text: str) -> List[str]:
        """提取特殊要求"""
        requirements = []
        
        # 字数要求
        word_count_pattern = r"(\d+)\s*字"
        match = re.search(word_count_pattern, text)
        if match:
            requirements.append(f"字数要求：{match.group(1)}字")
        
        # 页数要求
        page_count_pattern = r"(\d+)\s*页"
        match = re.search(page_count_pattern, text)
        if match:
            requirements.append(f"页数要求：{match.group(1)}页")
        
        # 交付时间
        deadline_pattern = r"(\d{1,2})\s*天内|本周|下周|本月"
        match = re.search(deadline_pattern, text)
        if match:
            requirements.append(f"交付时间：{match.group(0)}")
        
        # 深度要求
        if "深度" in text or "详细" in text:
            requirements.append("深度分析")
        if "简要" in text or "简单" in text:
            requirements.append("简要分析")
        
        return requirements
    
    def _generate_research_plan(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成研究计划
        
        Args:
            parsed: 解析后的需求
            
        Returns:
            研究计划
        """
        plan = {
            "plan_id": f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "research_topic": parsed["research_topic"],
            "industry": parsed["industry"],
            "objectives": self._generate_objectives(parsed),
            "methodology": self._generate_methodology(parsed),
            "deliverables": self._generate_deliverables(parsed),
            "timeline": self._generate_timeline(parsed),
            "required_agents": self._determine_required_agents(parsed),
            "data_requirements": self._determine_data_requirements(parsed),
            "quality_criteria": self._determine_quality_criteria(parsed)
        }
        
        return plan
    
    def _generate_objectives(self, parsed: Dict[str, Any]) -> List[str]:
        """生成研究目标"""
        objectives = []
        
        topic = parsed.get("research_topic", "该领域")
        
        if "市场分析" in parsed.get("analysis_types", []):
            objectives.append(f"分析{topic}的市场规模、增长趋势和细分市场结构")
        
        if "竞争分析" in parsed.get("analysis_types", []):
            objectives.append(f"识别{topic}的主要竞争对手，分析竞争格局和竞争力")
        
        if "财务分析" in parsed.get("analysis_types", []):
            objectives.append(f"评估{topic}相关企业的财务健康状况和盈利能力")
        
        if "政策分析" in parsed.get("analysis_types", []):
            objectives.append(f"梳理影响{topic}的政策法规环境")
        
        if "技术分析" in parsed.get("analysis_types", []):
            objectives.append(f"分析{topic}的技术发展趋势和创新方向")
        
        # 默认目标
        if not objectives:
            objectives.append(f"全面了解{topic}的发展现状和趋势")
        
        return objectives
    
    def _generate_methodology(self, parsed: Dict[str, Any]) -> List[str]:
        """生成研究方法"""
        methods = [
            "文献研究：收集行业报告、学术论文、政策文件",
            "数据分析：收集和分析市场数据、财务数据",
            "专家访谈：整理行业专家观点和预测",
        ]
        
        if "竞争分析" in parsed.get("analysis_types", []):
            methods.append("竞争情报：收集竞争对手公开信息")
        
        if "消费者分析" in parsed.get("analysis_types", []):
            methods.append("消费者调研：分析消费者行为和偏好")
        
        return methods
    
    def _generate_deliverables(self, parsed: Dict[str, Any]) -> List[str]:
        """生成交付物清单"""
        fmt = parsed.get("output_format", "report")
        
        deliverables = []
        
        if fmt == "report":
            deliverables.append("行业研究报告（Word格式）")
            deliverables.append("执行摘要")
            deliverables.append("数据附录")
        elif fmt == "brief":
            deliverables.append("研究简报")
        elif fmt == "presentation":
            deliverables.append("演示文稿（PPT格式）")
        elif fmt == "data":
            deliverables.append("数据集（Excel格式）")
            deliverables.append("数据字典")
        
        return deliverables
    
    def _generate_timeline(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """生成时间线"""
        # 默认3天完成
        return {
            "total_days": 3,
            "phases": [
                {"phase": "需求确认", "duration": "0.5天", "order": 1},
                {"phase": "数据收集", "duration": "1天", "order": 2},
                {"phase": "分析研究", "duration": "1天", "order": 3},
                {"phase": "报告撰写", "duration": "0.5天", "order": 4},
            ]
        }
    
    def _determine_required_agents(self, parsed: Dict[str, Any]) -> List[str]:
        """确定需要的Agent"""
        agents = ["requirement_parser", "data_collector"]
        
        analysis_types = parsed.get("analysis_types", [])
        
        if "市场分析" in analysis_types:
            agents.append("market_analyst")
        
        if "竞争分析" in analysis_types:
            agents.append("competitive_analyst")
        
        if "财务分析" in analysis_types:
            agents.append("financial_analyst")
        
        # 报告流水线
        agents.extend(["report_writer", "report_formatter", "quality_checker"])
        
        return agents
    
    def _determine_data_requirements(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """确定数据需求"""
        return {
            "market_data": "市场分析" in parsed.get("analysis_types", []),
            "financial_data": "财务分析" in parsed.get("analysis_types", []),
            "company_data": "竞争分析" in parsed.get("analysis_types", []),
            "policy_data": "政策分析" in parsed.get("analysis_types", []),
            "time_range": parsed.get("time_range"),
            "geographic_scope": parsed.get("geographic_scope")
        }
    
    def _determine_quality_criteria(self, parsed: Dict[str, Any]) -> List[str]:
        """确定质量标准"""
        return [
            "所有关键数据必须有可信来源",
            "市场数据更新至最近季度",
            "竞争分析覆盖主要玩家",
            "报告通过质量闸门检查"
        ]
    
    def _calculate_confidence(self, parsed: Dict[str, Any]) -> float:
        """
        计算解析置信度
        
        Returns:
            置信度分数 (0-1)
        """
        score = 0.5  # 基础分
        
        # 识别到主题
        if parsed.get("research_topic"):
            score += 0.15
        
        # 识别到行业
        if parsed.get("industry"):
            score += 0.15
        
        # 识别到时间范围
        if parsed.get("time_range") and parsed["time_range"].get("description"):
            score += 0.1
        
        # 识别到分析类型
        if parsed.get("analysis_types"):
            score += min(0.1 * len(parsed["analysis_types"]), 0.2)
        
        return min(1.0, score)
    
    def get_parsed_history(self) -> List[Dict[str, Any]]:
        """获取解析历史"""
        return self.parsed_requirements.copy()
