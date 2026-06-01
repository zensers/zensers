"""
研究框架管理器
============

根据研究类型加载差异化配置，影响Agent行为：
- 搜索深度和来源优先级
- 分析重点和关键指标
- 内容要求和章节权重

使用示例：
    from src.core.research_framework_manager import ResearchFrameworkManager
    
    manager = ResearchFrameworkManager()
    config = manager.get_framework_config("industry_report")
    
    # 获取搜索配置
    search_config = config.agent_config.search
    max_queries = search_config.max_queries_per_section
    
    # 获取章节权重
    weight = config.get_section_weight("market_size")
"""
import yaml
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 配置文件路径
FRAMEWORK_CONFIG_PATH = Path("config/research_frameworks.yaml")


@dataclass
class SearchConfig:
    """搜索配置"""
    max_queries_per_section: int = 10
    max_results_per_query: int = 20
    max_total_searches: int = 100  # P0-3新增：总搜索次数上限
    priority_sources: List[str] = field(default_factory=list)


@dataclass
class AnalysisConfig:
    """分析配置"""
    depth: str = "ultra_deep"  # shallow/medium/deep/ultra_deep
    focus_areas: List[str] = field(default_factory=list)
    metrics: List[str] = field(default_factory=list)


@dataclass
class ContentConfig:
    """内容配置"""
    min_section_length: int = 2000  # 提高默认最小字数
    require_data_points: bool = True
    require_charts: bool = True
    require_sources: bool = True
    require_multiple_sources: bool = True  # P0-3新增：要求多来源验证
    require_inline_citations: bool = False  # 是否在正文中标注来源（学术报告需要）


@dataclass
class AgentConfig:
    """Agent配置"""
    search: SearchConfig = field(default_factory=SearchConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    content: ContentConfig = field(default_factory=ContentConfig)


@dataclass
class ResearchFrameworkConfig:
    """研究框架配置"""
    name: str = "通用研究报告"
    description: str = "标准研究报告配置"
    agent_config: AgentConfig = field(default_factory=AgentConfig)
    section_weights: Dict[str, float] = field(default_factory=dict)
    # NEW: 交互参数配置，存储原始字典，由 InteractionParameterSet 解析
    interaction_parameters: Dict[str, Any] = field(default_factory=dict)
    
    def get_section_weight(self, section_id: str) -> float:
        """获取章节权重"""
        return self.section_weights.get(section_id, 1.0)
    
    def get_max_queries(self) -> int:
        """获取每章节最大搜索次数"""
        return self.agent_config.search.max_queries_per_section
    
    def get_max_results(self) -> int:
        """获取每次搜索最大结果数"""
        return self.agent_config.search.max_results_per_query
    
    def get_max_total_searches(self) -> int:
        """获取总搜索次数上限"""
        return self.agent_config.search.max_total_searches
    
    def get_priority_sources(self) -> List[str]:
        """获取优先数据源"""
        return self.agent_config.search.priority_sources
    
    def get_analysis_depth(self) -> str:
        """获取分析深度"""
        return self.agent_config.analysis.depth
    
    def get_focus_areas(self) -> List[str]:
        """获取重点分析领域"""
        return self.agent_config.analysis.focus_areas
    
    def get_key_metrics(self) -> List[str]:
        """获取关键指标"""
        return self.agent_config.analysis.metrics
    
    def get_min_section_length(self) -> int:
        """获取章节最小字数"""
        return self.agent_config.content.min_section_length
    
    def requires_data_points(self) -> bool:
        """是否要求数据支撑"""
        return self.agent_config.content.require_data_points
    
    def requires_charts(self) -> bool:
        """是否要求图表"""
        return self.agent_config.content.require_charts
    
    def requires_sources(self) -> bool:
        """是否要求来源标注"""
        return self.agent_config.content.require_sources
    
    def requires_multiple_sources(self) -> bool:
        """是否要求多来源验证"""
        return self.agent_config.content.require_multiple_sources
    
    def requires_inline_citations(self) -> bool:
        """是否要求正文内引用标注（学术报告需要）"""
        return self.agent_config.content.require_inline_citations

    def get_interaction_parameters(self) -> Dict[str, Any]:
        """获取交互参数配置字典"""
        return self.interaction_parameters if self.interaction_parameters else {}

    def has_interaction_parameters(self) -> bool:
        """是否有交互参数配置"""
        return bool(self.interaction_parameters)


class ResearchFrameworkManager:
    """
    研究框架管理器
    
    根据研究类型加载差异化配置。
    """
    
    def __init__(self, config_path: Path = None):
        self.config_path = config_path or FRAMEWORK_CONFIG_PATH
        self._configs: Dict[str, ResearchFrameworkConfig] = {}
        self._loaded = False
    
    def load_configs(self) -> Dict[str, ResearchFrameworkConfig]:
        """加载所有框架配置"""
        if self._loaded:
            return self._configs
        
        if not self.config_path.exists():
            logger.warning(f"Framework config not found: {self.config_path}, using defaults")
            self._configs = {"default": ResearchFrameworkConfig()}
            self._loaded = True
            return self._configs
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            for framework_id, framework_data in data.items():
                config = self._parse_framework_config(framework_id, framework_data)
                self._configs[framework_id] = config
                logger.info(f"Loaded framework config: {framework_id}")
            
            self._loaded = True
            return self._configs
            
        except Exception as e:
            logger.error(f"Failed to load framework configs: {e}")
            self._configs = {"default": ResearchFrameworkConfig()}
            self._loaded = True
            return self._configs
    
    def _parse_framework_config(self, framework_id: str, data: Dict) -> ResearchFrameworkConfig:
        """解析框架配置"""
        agent_data = data.get("agent_config", {})
        
        # 解析搜索配置
        search_data = agent_data.get("search", {})
        search_config = SearchConfig(
            max_queries_per_section=search_data.get("max_queries_per_section", 10),
            max_results_per_query=search_data.get("max_results_per_query", 20),
            max_total_searches=search_data.get("max_total_searches", 100),
            priority_sources=search_data.get("priority_sources", []),
        )
        
        # 解析分析配置
        analysis_data = agent_data.get("analysis", {})
        analysis_config = AnalysisConfig(
            depth=analysis_data.get("depth", "ultra_deep"),
            focus_areas=analysis_data.get("focus_areas", []),
            metrics=analysis_data.get("metrics", []),
        )
        
        # 解析内容配置
        content_data = agent_data.get("content", {})
        content_config = ContentConfig(
            min_section_length=content_data.get("min_section_length", 2000),
            require_data_points=content_data.get("require_data_points", True),
            require_charts=content_data.get("require_charts", True),
            require_sources=content_data.get("require_sources", True),
            require_multiple_sources=content_data.get("require_multiple_sources", True),
            require_inline_citations=content_data.get("require_inline_citations", False),
        )
        
        # 组装Agent配置
        agent_config = AgentConfig(
            search=search_config,
            analysis=analysis_config,
            content=content_config,
        )
        
        # 解析交互参数配置（NEW）
        interaction_params_raw = data.get("interaction_parameters", {})

        return ResearchFrameworkConfig(
            name=data.get("name", framework_id),
            description=data.get("description", ""),
            agent_config=agent_config,
            section_weights=data.get("section_weights", {}),
            interaction_parameters=interaction_params_raw,
        )
    
    def get_framework_config(self, output_type: str) -> ResearchFrameworkConfig:
        """
        根据输出类型获取框架配置
        
        Args:
            output_type: 输出类型（如 industry_report, company_research）
            
        Returns:
            ResearchFrameworkConfig 配置对象
        """
        configs = self.load_configs()
        
        # 尝试精确匹配
        if output_type in configs:
            return configs[output_type]
        
        # 尝试去掉后缀匹配（如 industry_report_standard -> industry_report）
        base_type = output_type.replace("_standard", "").replace("_detailed", "").replace("_brief", "")
        if base_type in configs:
            return configs[base_type]
        
        # 返回默认配置
        logger.info(f"Using default framework config for: {output_type}")
        return configs.get("default", ResearchFrameworkConfig())
    
    def get_all_framework_ids(self) -> List[str]:
        """获取所有框架ID"""
        return list(self.load_configs().keys())


# 全局管理器实例
_framework_manager = None


def get_framework_manager() -> ResearchFrameworkManager:
    """获取全局框架管理器"""
    global _framework_manager
    if _framework_manager is None:
        _framework_manager = ResearchFrameworkManager()
    return _framework_manager


def get_framework_config(output_type: str) -> ResearchFrameworkConfig:
    """便捷函数：获取框架配置"""
    return get_framework_manager().get_framework_config(output_type)


__all__ = [
    "ResearchFrameworkManager",
    "ResearchFrameworkConfig",
    "AgentConfig",
    "SearchConfig",
    "AnalysisConfig",
    "ContentConfig",
    "get_framework_manager",
    "get_framework_config",
]