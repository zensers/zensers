"""
执行引擎

组合所有控制机制和协调机制，提供统一的执行接口。

职责：
- 分类Agents
- 分阶段执行
- 并发控制
- 错误处理
- 结果收集

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/ORCHESTRATOR_REDESIGN.md
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

# 阶段三：导入 SectionType
from src.content.content_orchestrator import SectionType

# A-1/A-2修复：ResearchResultStore持久化
from src.core.storage import ResearchResultStore, ResearchStatus

# Harness constraint layer for agent output validation
from src.core.harness import check_agent_output

from src.core.data.canonical_registry import parse_entry_key

from .control import (
    ConcurrencyManager,
    ConcurrencyConfig,
    RetryManager,
    RetryConfig,
    TimeoutController,
    TimeoutConfig,
    BackgroundExecutor,
    BackgroundExecutorConfig,
    ResultValidator,
)
from .coordinator import (
    AgentCoordinator,
    CoordinatorConfig,
    TaskOptions,
)

if TYPE_CHECKING:
    from src.core.agents.base import BaseAgent
    from src.core.agents.protocol import IAgent
    from src.core.agents.agent_session import AgentSessionRegistry
    from src.core.communication import MessageBus, SharedMemory
    from src.core.content_lock import ContentLockManager  # 新增：智能路由内容锁

logger = logging.getLogger(__name__)


class AgentCategory(Enum):
    """
    Agent分类枚举
    
    替代脆弱的字符串匹配（如 "数据" in name）
    """
    DATA_COLLECTION = "data_collection"      # 数据收集
    ANALYSIS = "analysis"                     # 分析
    SYNTHESIS = "synthesis"                   # 综合（执行摘要、结论等依赖其他章节的章节）
    REPORT_GENERATION = "report_generation"   # 报告生成
    QUALITY_CHECK = "quality_check"           # 质量检查
    DOCUMENT_GENERATION = "document_generation"  # 文档生成
    UNKNOWN = "unknown"                       # 未知类型
    
    @classmethod
    def _missing_(cls, value):
        """处理不同命名风格的类别名称"""
        # 连字符转下划线
        normalized = value.replace("-", "_")
        
        # 类别名映射（CategoryRouter 使用的名称 -> 枚举值）
        category_mapping = {
            "market_analysis": cls.ANALYSIS,
            "data_analysis": cls.ANALYSIS,
            "financial_analysis": cls.ANALYSIS,
            "academic_research": cls.ANALYSIS,
            "visual_engineering": cls.ANALYSIS,
            "synthesis": cls.SYNTHESIS,  # 添加 synthesis 映射
            # **新增**: research 映射到 DATA_COLLECTION
            "research": cls.DATA_COLLECTION,
            "data": cls.DATA_COLLECTION,
            "data_collection": cls.DATA_COLLECTION,
            "analysis": cls.ANALYSIS,
            "report": cls.REPORT_GENERATION,
            "document": cls.DOCUMENT_GENERATION,
        }
        
        if normalized in category_mapping:
            return category_mapping[normalized]
        
        # 尝试直接匹配
        for member in cls:
            if member.value == normalized:
                return member
        
        return cls.UNKNOWN


class ExecutionStage(Enum):
    """执行阶段"""
    DATA_COLLECTION = "data_collection"
    ANALYSIS = "analysis"
    REPORT_GENERATION = "report_generation"


@dataclass
class ExecutionConfig:
    """执行配置"""
    max_concurrent: int = 10  # 增加并发数以支持更多Agent并行执行
    default_timeout: float = 300.0
    max_retries: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 60.0
    heartbeat_interval: float = 5.0
    heartbeat_timeout: float = 30.0
    circuit_breaker_threshold: int = 100


@dataclass
class ExecutionResult:
    """
    执行结果
    
    Attributes:
        task_id: 任务ID
        status: 状态
        started_at: 开始时间
        completed_at: 完成时间
        stage_results: 各阶段结果
        final_result: 最终结果
        errors: 错误列表
        stats: 执行统计
    """
    task_id: str
    status: str = "pending"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    stage_results: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    final_result: Optional[Dict[str, Any]] = None
    errors: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "stage_results": self.stage_results,
            "final_result": self.final_result,
            "errors": self.errors,
            "stats": self.stats,
        }


class ExecutionEngine:
    """
    执行引擎
    
    组合所有控制机制和协调机制
    
    职责：
    - 分类Agents
    - 分阶段执行
    - 并发控制
    - 错误处理
    - 结果收集
    
    使用示例:
        engine = ExecutionEngine(
            config=ExecutionConfig(),
            message_bus=message_bus,
            shared_memory=shared_memory,
        )
        
        result = await engine.execute(
            agents=[agent1, agent2, agent3],
            requirement={"topic": "...", "aspects": [...]},
        )
        
        print(result.status)  # "completed" or "failed"
    """
    
    # Agent分类关键词（用于辅助分类）
    CATEGORY_KEYWORDS = {
        AgentCategory.DATA_COLLECTION: [
            "data", "collect", "search", "fetch", "crawl", "scrape",
            "数据", "收集", "搜索", "获取",
        ],
        AgentCategory.ANALYSIS: [
            "analyze", "analysis", "process", "compute", "evaluate",
            "分析", "处理", "计算", "评估",
        ],
        AgentCategory.SYNTHESIS: [
            "synthesis", "summary", "conclusion", "综合", "摘要", "结论", "执行摘要", "研究结论",
        ],
        AgentCategory.REPORT_GENERATION: [
            "report", "generate", "write", "document",
            "报告", "生成", "撰写", "文档",
        ],
        AgentCategory.QUALITY_CHECK: [
            "quality", "check", "validate", "verify", "audit",
            "质量", "检查", "验证", "审核",
        ],
        AgentCategory.DOCUMENT_GENERATION: [
            "document", "docx", "pptx", "pdf", "format",
            "文档", "格式",
        ],
    }
    
    def __init__(
        self,
        config: ExecutionConfig,
        message_bus: "MessageBus",
        shared_memory: "SharedMemory",
        enable_quality_control: bool = True,  # 新增：是否启用质量控制
    ):
        self.config = config
        self.message_bus = message_bus
        self._shared_memory = shared_memory
        
        # 控制机制
        self.concurrency = ConcurrencyManager(ConcurrencyConfig(
            max_concurrent=config.max_concurrent,
        ))
        
        self.retry = RetryManager(RetryConfig(
            max_retries=config.max_retries,
            base_delay=config.retry_base_delay,
            max_delay=config.retry_max_delay,
        ))
        
        self.timeout = TimeoutController(TimeoutConfig(
            default_timeout=config.default_timeout,
        ))
        
        self.background = BackgroundExecutor(BackgroundExecutorConfig(
            max_concurrent_tasks=config.max_concurrent,
            default_timeout=config.default_timeout,
        ))
        
        # 使用适度的验证器配置，确保内容质量
        from .control.validator import ValidatorConfig
        self.validator = ResultValidator(ValidatorConfig(
            required_fields=[],           # 不要求必需字段
            success_required_fields=[],   # 成功结果不要求特定字段
            failure_required_fields=[],   # 失败结果不要求特定字段
            min_output_length=50,         # 最小输出长度50字符
            allow_empty_output=False,     # 不允许空输出
        ))
        
        # 数据边界控制器（用于代码级数据隔离）
        from .data_boundary_controller import DataBoundaryController
        self.data_boundary = DataBoundaryController()
        
        # 协调机制（每次执行创建）
        self._coordinator: Optional[AgentCoordinator] = None
        self._registry: Optional["AgentSessionRegistry"] = None
        
        # 取消/暂停管理器（全局单例）
        from .coordinator.cancel_manager import get_cancel_manager
        self._cancel_manager = get_cancel_manager()

        # 注入检查点：由 orchestrator 设置的 agent 创建回调
        self._inject_handler = None

        # 新增：质量控制组件
        self.enable_quality_control = enable_quality_control
        if enable_quality_control:
            from src.core.quality import (
                QualityMetadataExtractor,
                QualityFeedbackExecutor,
                DataCollectionQualityChecker,
                AnalysisQualityChecker,
                ReportQualityChecker,
            )
            from src.config.settings import settings
            
            # 质量元数据提取器
            self.metadata_extractor = QualityMetadataExtractor()
            
            # 反馈执行器
            self.quality_executor = QualityFeedbackExecutor(
                max_retries=settings.quality.max_retries,
                min_data_volume=settings.quality.min_data_volume,
            )
            
            # 三个检查器
            self.data_checker = DataCollectionQualityChecker(
                threshold=settings.quality.threshold_data_collection
            )
            self.analysis_checker = AnalysisQualityChecker(
                threshold=settings.quality.threshold_analysis
            )
            self.report_checker = ReportQualityChecker(
                threshold=settings.quality.threshold_report
            )
            
            logger.info(
                f"质量控制已启用: 阈值[data={settings.quality.threshold_data_collection}, "
                f"analysis={settings.quality.threshold_analysis}, "
                f"report={settings.quality.threshold_report}], "
                f"重试次数={settings.quality.max_retries}"
            )
        else:
            self.metadata_extractor = None
            self.quality_executor = None
            self.data_checker = None
            self.analysis_checker = None
            self.report_checker = None
    
    def classify_agent(self, agent: "IAgent") -> AgentCategory:
        """
        分类Agent
        
        使用Agent的配置属性进行分类，替代脆弱的字符串匹配
        
        Args:
            agent: Agent实例
            
        Returns:
            AgentCategory: Agent分类
        """
        # 1. 优先使用显式分类（如果存在）
        config = getattr(agent, "config", {}) or {}
        _agent_id_lower = getattr(agent, "agent_id", "").lower()
        
        if "category" in config:
            category_str = config.get("category")
            if isinstance(category_str, AgentCategory):
                return category_str
            # normal 章节（research_ 前缀）被误标为 data-collection，应映射为 analysis
            if category_str == "data-collection" and _agent_id_lower.startswith("research_"):
                return AgentCategory.ANALYSIS
            try:
                # 处理连字符 vs 下划线的差异
                normalized = category_str.replace("-", "_")
                return AgentCategory(normalized)
            except ValueError:
                # **新增**: 处理常见别名映射
                category_aliases = {
                    "market_analysis": AgentCategory.ANALYSIS,
                    "market-analysis": AgentCategory.ANALYSIS,
                    "research": AgentCategory.DATA_COLLECTION,  # 研究Agent需要数据收集
                    "data": AgentCategory.DATA_COLLECTION,
                    "analysis": AgentCategory.ANALYSIS,
                    "report": AgentCategory.REPORT_GENERATION,
                    "document": AgentCategory.DOCUMENT_GENERATION,
                }
                if category_str in category_aliases:
                    return category_aliases[category_str]
                # 尝试直接匹配（可能有新的枚举值）
                pass
        
        # 2. 使用capabilities分类
        capabilities = config.get("capabilities", [])
        if capabilities:
            for cap in capabilities:
                cap_lower = str(cap).lower()
                for category, keywords in self.CATEGORY_KEYWORDS.items():
                    if any(kw in cap_lower for kw in keywords):
                        return category
        
        # 3. 使用名称/描述辅助分类
        name = config.get("name", "").lower()
        description = config.get("description", "").lower()
        
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            if any(kw in name for kw in keywords):
                return category
            if any(kw in description for kw in keywords):
                return category
        
        # 4. 使用skills分类
        skills = config.get("skills", [])
        for skill in skills:
            skill_lower = str(skill).lower()
            for category, keywords in self.CATEGORY_KEYWORDS.items():
                if any(kw in skill_lower for kw in keywords):
                    return category
        
        # 5. **新增**: 根据Agent ID推断（综合研究Agent → 数据收集）
        agent_id = getattr(agent, "agent_id", "").lower()
        if agent_id.startswith("research_"):
            # 综合研究Agent需要先收集数据
            return AgentCategory.DATA_COLLECTION
        elif agent_id.startswith("analysis_"):
            return AgentCategory.ANALYSIS
        elif agent_id.startswith("report_") or agent_id.startswith("document_"):
            return AgentCategory.REPORT_GENERATION
        
        return AgentCategory.UNKNOWN
    
    def classify_agents(
        self,
        agents: List["IAgent"]
    ) -> Tuple[List["IAgent"], List["IAgent"], List["IAgent"], List["IAgent"]]:
        """
        分类Agents
        
        Returns:
            (数据收集Agents, 分析Agents, 综合Agents, 报告生成Agents)
        """
        data_agents = []
        analysis_agents = []
        synthesis_agents = []
        report_agents = []
        
        for agent in agents:
            category = self.classify_agent(agent)
            
            if category == AgentCategory.DATA_COLLECTION:
                data_agents.append(agent)
            elif category == AgentCategory.SYNTHESIS:
                synthesis_agents.append(agent)
            elif category == AgentCategory.ANALYSIS:
                analysis_agents.append(agent)
            elif category in (
                AgentCategory.REPORT_GENERATION,
                AgentCategory.DOCUMENT_GENERATION,
            ):
                report_agents.append(agent)
            else:
                # UNKNOWN类型加入分析（默认）
                logger.warning(
                    f"Agent {agent.agent_id} has unknown category, "
                    f"assigning to analysis group"
                )
                analysis_agents.append(agent)
        
        logger.info(
            f"Classified agents: data={len(data_agents)}, "
            f"analysis={len(analysis_agents)}, synthesis={len(synthesis_agents)}, report={len(report_agents)}"
        )
        
        return data_agents, analysis_agents, synthesis_agents, report_agents
    
    async def execute(
        self,
        agents: List["IAgent"],
        requirement: Dict[str, Any],
        session_registry: Optional["AgentSessionRegistry"] = None,
    ) -> ExecutionResult:
        """
        执行Agent任务（委托给 execute_with_scheduler）
        
        **Path A 清理**: 移除遗留的 _build_data_task/_build_analysis_task 等代码路径，
        统一使用 scheduler 驱动执行。
        
        Args:
            agents: Agent列表
            requirement: 需求定义
            session_registry: Session注册表
            
        Returns:
            ExecutionResult: 执行结果
        """
        import uuid
        task_id = f"exec_{uuid.uuid4().hex[:8]}"
        
        result = ExecutionResult(
            task_id=task_id,
            started_at=datetime.now(),
        )
        
        try:
            # Create coordinator
            self._registry = session_registry
            
            self._coordinator = AgentCoordinator(
                message_bus=self.message_bus,
                shared_memory=self._shared_memory,
                session_registry=self._registry,
                config=CoordinatorConfig(
                    max_concurrent=self.config.max_concurrent,
                    default_timeout=self.config.default_timeout,
                    max_retries=self.config.max_retries,
                    heartbeat_interval=self.config.heartbeat_interval,
                    heartbeat_timeout=self.config.heartbeat_timeout,
                ),
            )
            
            await self._coordinator.setup()
            
            # Use scheduler-driven execution (Path B)
            from .scheduler import ExecutionScheduler
            scheduler = ExecutionScheduler()
            
            exec_result = await self.execute_with_scheduler(
                agents=agents,
                requirement=requirement,
                scheduler=scheduler,
                decomposition_plan=None,
                session_registry=session_registry,
            )
            
            result.status = exec_result.status
            result.completed_at = exec_result.completed_at
            result.stage_results = exec_result.stage_results
            result.final_result = exec_result.final_result
            result.stats = exec_result.stats
            result.errors = exec_result.errors
            
            if result.status == "failed":
                logger.warning(f"Execution {task_id} completed with FAILED status (quality check blocked)")
            else:
                logger.info(f"Execution {task_id} completed successfully")
            return result
            
        except Exception as e:
            logger.error(f"Execution {task_id} failed: {e}")
            result.status = "failed"
            result.completed_at = datetime.now()
            result.errors.append(str(e))
            return result
            
        finally:
            # Cleanup resources
            if self._coordinator:
                await self._coordinator.shutdown()
    
    async def _execute_stage(
        self,
        stage_name: str,
        agents: List["IAgent"],
        task_builder: Callable,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        执行一个阶段（已废弃，保留为向后兼容）
        
        **Path A 清理**: 此方法不再被 execute() 调用。
        统一使用 execute_with_scheduler() 路径。
        """
        logger.warning(f"_execute_stage 被调用（遗留路径）: {stage_name}")
        return []
    
    def set_inject_handler(self, handler) -> None:
        """设置注入检查点回调（由 orchestrator 调用）
        
        Args:
            handler: 异步可调用对象，接收 (session_id, requirement) 返回新增 Agent 列表
        """
        self._inject_handler = handler

    def _extract_aspect_from_agent_id(self, agent_id: str) -> str:
        """
        从 agent_id 提取目标章节名称
        
        支持格式:
        - research_市场规模_1          → "市场规模"      (旧, 数字索引)
        - deep_analysis_0_市场规模     → "市场规模"      (新, 数字索引)
        - inject_市场规模_a1b2c3d4     → "市场规模"      (注入, UUID后缀)
        - replan_市场规模_xyz789       → "市场规模"      (replan, 字母数字ID)
        - analysis_market_size_1      → "market_size"    (英文, 数字索引)
        - synthesis_summary_1         → "执行摘要"       (英文映射)
        """
        parts = agent_id.split("_")
        if len(parts) < 2:
            return agent_id
        
        # 英文→中文映射
        aspect_mapping = {
            "summary": "执行摘要", "executivesummary": "执行摘要",
            "execsummary": "执行摘要", "conclusion": "研究结论",
            "findings": "研究结论", "recommendation": "建议",
        }
        
        # 判断最后一段是否为索引/ID (数字 / UUID / 字母数字ID)
        last = parts[-1]
        is_index = last.isdigit() or (
            len(last) >= 6
            and all(c in '0123456789abcdef' for c in last.lower())
        )
        
        if is_index and len(parts) >= 3:
            # 去掉前缀 + 索引，取中间部分
            middle = "_".join(parts[1:-1])
            # 检查中间部分是否有英文映射
            if middle.lower() in aspect_mapping:
                return aspect_mapping[middle.lower()]
            return middle
        
        # 最后一段不是索引：尝试映射，否则直接返回
        if last.lower() in aspect_mapping:
            return aspect_mapping[last.lower()]
        return last
    
    def _build_synthesis_task(
        self,
        requirement: Dict[str, Any],
        previous_results: List[Dict[str, Any]],
        target_aspect: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        构建综合分析任务（已废弃）
        
        **Path A 清理**: 此方法不再被调用。
        """
        logger.warning("_build_synthesis_task 被调用（遗留路径）")
        return {}

    def _build_report_task(
        self,
        requirement: Dict[str, Any],
        previous_results: List[Dict[str, Any]],
        **kwargs
    ) -> Dict[str, Any]:
        """
        构建报告生成任务（已废弃）
        
        **Path A 清理**: 此方法不再被调用。
        """
        logger.warning("_build_report_task 被调用（遗留路径）")
        return {}
    
    def _extract_section_name(self, agent_id: str) -> str:
        """
        从agent_id提取章节名称
        
        支持多种格式:
        - deep_analysis_1_市场规模 → "市场规模"
        - analysis_市场规模_2 → "市场规模"
        - analysis_竞争格局 → "竞争格局"
        - market_analysis_新能源汽车 → "新能源汽车"
        
        Args:
            agent_id: Agent标识符
            
        Returns:
            提取的章节名称
        """
        if "_" not in agent_id:
            return agent_id
        
        parts = agent_id.split("_")
        
        # phase_N_agent_M 格式：无意义章节名，返回原始值
        if len(parts) >= 4 and parts[0] == "phase" and parts[-2] == "agent":
            return agent_id
        
        # 过滤掉纯数字部分（编号）
        non_numeric_parts = [p for p in parts if not p.isdigit()]
        
        # 过滤掉已知的前缀类型
        prefix_types = {
            "deep", "analysis", "market", "financial", "policy", 
            "technical", "competitive", "industry", "company",
            "data", "research", "synthesis", "report"
        }
        meaningful_parts = [p for p in non_numeric_parts if p.lower() not in prefix_types]
        
        if meaningful_parts:
            # 返回最后一个有意义的部分（通常是章节名）
            return meaningful_parts[-1]
        
        # 如果没有有意义部分，返回最后一个非数字部分
        if non_numeric_parts:
            return non_numeric_parts[-1]
        
        # 兜底：返回最后一部分
        return parts[-1]
    
    def _determine_section_type(self, agent_id: str, category: Optional[AgentCategory] = None) -> SectionType:
        """
        根据 agent_id 和 category 确定章节类型
        
        **阶段三新增**：替代脆弱的字符串匹配
        
        Args:
            agent_id: Agent 标识符
            category: Agent 分类（可选）
            
        Returns:
            SectionType 枚举值
        """
        # 防御性检查：agent_id 为空或非字符串
        if not agent_id or not isinstance(agent_id, str):
            return SectionType.UNKNOWN
        
        agent_id_lower = agent_id.lower()
        
        # 优先使用 category 判断
        if category == AgentCategory.SYNTHESIS:
            # 进一步区分执行摘要和研究结论
            if "执行摘要" in agent_id or "summary" in agent_id_lower or "exec" in agent_id_lower:
                return SectionType.EXECUTIVE_SUMMARY
            elif "结论" in agent_id or "conclusion" in agent_id_lower:
                return SectionType.CONCLUSION
            else:
                # 默认 synthesis 视为结论
                return SectionType.CONCLUSION
        
        if category == AgentCategory.DATA_COLLECTION:
            return SectionType.DATA_SOURCE
        if category == AgentCategory.ANALYSIS:
            return SectionType.BODY
        
        # 回退到 agent_id 字符串判断（兼容旧逻辑）
        if "exec_summary" in agent_id_lower or "执行摘要" in agent_id:
            return SectionType.EXECUTIVE_SUMMARY
        if "conclusion" in agent_id_lower or "研究结论" in agent_id or "结论" in agent_id:
            return SectionType.CONCLUSION
        if "appendix" in agent_id_lower or "附录" in agent_id:
            return SectionType.APPENDIX
        if "data_source" in agent_id_lower or "数据来源" in agent_id:
            return SectionType.DATA_SOURCE
        if "research" in agent_id_lower or "data_collection" in agent_id_lower:
            return SectionType.DATA_SOURCE
        
        # 默认为正文章节
        return SectionType.BODY
    
    def _build_report_task(
        self,
        requirement: Dict[str, Any],
        previous_results: List[Dict[str, Any]],
        **kwargs
    ) -> Dict[str, Any]:
        """构建报告任务
        
        **修复**：按类型分离章节，避免摘要重复和顺序颠倒
        
        **阶段三增强**：使用 SectionType 枚举替代字符串匹配
        
        数据流：
        - body_sections: 仅包含 analysis 阶段的正文章节
        - exec_summary_content: 执行摘要内容（单独传递）
        - conclusion_content: 研究结论内容（单独传递）
        
        跳过：
        - research/data_collection: 原始数据不应出现在报告中
        """
        body_sections = []
        exec_summary_content = None
        conclusion_content = None
        all_data_points = []
        all_sources = []
        
        for r in previous_results:
            if not r.get("success"):
                continue
            
            agent_id = r.get("agent_id", "")
            
            # **阶段三**：使用 SectionType 判断章节类型
            # 优先使用结果中的 category 字段（如果有）
            category_value = r.get("category")
            try:
                category = AgentCategory(category_value) if category_value else None
            except (ValueError, TypeError):
                # 无效的 category 值，回退到 agent_id 匹配
                category = None
            section_type = self._determine_section_type(agent_id, category)
            
            # 跳过数据收集阶段的结果
            if section_type == SectionType.DATA_SOURCE:
                # 但仍然收集 data_points 和 sources
                if "data_points" in r:
                    all_data_points.extend(r["data_points"])
                if "sources" in r:
                    all_sources.extend(r["sources"])
                continue
            
            # 提取章节内容
            content = (
                r.get("content") or 
                r.get("result") or 
                r.get("output") or
                ""
            )
            if not content or not isinstance(content, str):
                continue
            
            # **阶段三**：使用 SectionType 分离章节
            if section_type == SectionType.EXECUTIVE_SUMMARY:
                exec_summary_content = content
                logger.debug(f"[Report] 执行摘要: {agent_id}")
            elif section_type == SectionType.CONCLUSION:
                conclusion_content = content
                logger.debug(f"[Report] 研究结论: {agent_id}")
            elif section_type == SectionType.APPENDIX:
                # 附录暂不处理，可扩展
                logger.debug(f"[Report] 附录: {agent_id}")
            else:
                # 正文章节放入 body_sections（包括 UNKNOWN 类型）
                if section_type == SectionType.UNKNOWN:
                    logger.warning(f"[Report] 未知章节类型，作为正文处理: {agent_id}")
                section_name = self._extract_section_name(agent_id)
                    
                body_sections.append({
                    "id": agent_id,
                    "title": section_name,
                    "content": content,
                    "type": section_type.value,  # 传递类型信息
                })
            
            # 收集 data_points 和 sources
            if "data_points" in r:
                all_data_points.extend(r["data_points"])
            if "sources" in r:
                all_sources.extend(r["sources"])
        
        logger.info(
            f"[Report] 章节分类: 正文={len(body_sections)}, "
            f"执行摘要={'有' if exec_summary_content else '无'}, "
            f"研究结论={'有' if conclusion_content else '无'}"
        )
        
        return {
            "action": "produce_document",
            "task_id": requirement.get("task_id", f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"),
            "topic": requirement.get("topic"),
            "sections": body_sections,  # 仅正文章节
            "exec_summary": exec_summary_content,  # 执行摘要（单独传递）
            "conclusion": conclusion_content,  # 研究结论（单独传递）
            "output_format": requirement.get("output_format", "docx"),
            "research_result": {
                "topic": requirement.get("topic"),
                "sections": body_sections,
                "data_points": all_data_points,
                "sources": all_sources,
            },
        }
    
    def _aggregate_results(
        self,
        results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """聚合结果"""
        return {
            "total_results": len(results),
            "successful": sum(1 for r in results if r.get("success")),
            "failed": sum(1 for r in results if not r.get("success")),
            "data": results,
        }
    
    def _check_batch_quality(
        self,
        batch_results: List[Dict[str, Any]],
        batch_index: int,
    ) -> bool:
        """
        检查批次质量
        
        Args:
            batch_results: 批次结果
            batch_index: 批次索引
            
        Returns:
            质量是否通过
        """
        # 统计成功率和数据量
        success_count = sum(1 for r in batch_results if r.get("success"))
        total_count = len(batch_results)
        
        # 统计数据点数量
        total_data_points = 0
        total_sources = 0
        total_content_length = 0
        
        for r in batch_results:
            if r.get("success"):
                total_data_points += len(r.get("data_points", []))
                total_sources += len(r.get("sources", []))
                content = r.get("content", "") or r.get("result", "")
                if isinstance(content, str):
                    total_content_length += len(content)
        
        # 质量标准
        MIN_SUCCESS_RATE = 0.5  # 至少50%成功
        MIN_CONTENT_LENGTH = 100  # 每个成功的结果至少100字符
        
        # 计算质量分数
        success_rate = success_count / total_count if total_count > 0 else 0
        avg_content_length = total_content_length / success_count if success_count > 0 else 0
        
        quality_passed = (
            success_rate >= MIN_SUCCESS_RATE and
            avg_content_length >= MIN_CONTENT_LENGTH
        )
        
        logger.info(
            f"批次 {batch_index + 1} 质量检查: "
            f"成功率={success_rate:.1%}, "
            f"平均内容长度={avg_content_length:.0f}, "
            f"数据点={total_data_points}, "
            f"来源={total_sources}, "
            f"通过={quality_passed}"
        )
        
        return quality_passed
    
    def _build_stats(self) -> Dict[str, Any]:
        """构建执行统计"""
        stats = {
            "concurrency": self.concurrency.get_stats(),
            "retry": self.retry.get_stats(),
            "background": self.background.get_stats(),
            "validator": self.validator.get_stats(),
        }
        
        if self._coordinator:
            stats["coordinator"] = self._coordinator.get_stats()
        
        return stats
    
    async def execute_in_background(
        self,
        agents: List["IAgent"],
        requirement: Dict[str, Any],
    ) -> str:
        """
        后台执行
        
        Args:
            agents: Agent列表
            requirement: 需求定义
            
        Returns:
            后台任务ID
        """
        async def run_execution() -> Dict[str, Any]:
            result = await self.execute(agents, requirement)
            return result.to_dict() if hasattr(result, 'to_dict') else {
                "task_id": result.task_id,
                "status": result.status,
                "final_result": result.final_result,
            }
        
        task_id = await self.background.launch(
            execute_func=run_execution,
            parent_session_id="background_execution",
        )
        
        logger.info(f"Started background execution: {task_id}")
        
        return task_id
    
    async def get_background_result(
        self,
        task_id: str,
        timeout: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """获取后台执行结果"""
        return await self.background.wait_for_result(task_id, timeout)
    
    def get_background_status(self, task_id: str) -> Optional[str]:
        """获取后台执行状态"""
        status = self.background.get_task_status(task_id)
        return status.value if status else None
    
    def get_stats(self) -> Dict[str, Any]:
        """获取引擎统计"""
        return self._build_stats()
    
    async def execute_with_scheduler(
        self,
        agents: List["IAgent"],
        requirement: Dict[str, Any],
        scheduler: Any,  # ExecutionScheduler
        decomposition_plan: Optional[Any] = None,  # DecompositionPlan
        session_registry: Optional["AgentSessionRegistry"] = None,
        content_lock: Optional["ContentLockManager"] = None,  # 新增：内容锁管理器
    ) -> "ExecutionResult":
        """
        使用调度器执行任务（基于任务分解计划）
        
        **正确的执行流程**：
        1. 数据收集阶段 - 所有 research Agent 并行执行
        2. 数据评估阶段 - 检查数据质量
        3. 分析阶段 - research Agent 进行数据分析
        4. 分析评估阶段 - 检查分析结果质量
        5. 综合阶段 - 执行摘要、研究结论（依赖所有分析结果）
        6. 报告生成阶段 - 合并所有章节，生成报告
        
        Args:
            agents: Agent列表
            requirement: 需求定义
            scheduler: 执行调度器
            decomposition_plan: 任务分解计划（可选）
            session_registry: 会话注册表
            content_lock: 内容锁管理器（可选，用于智能路由）
            
        Returns:
            ExecutionResult
        """
        # 动态导入避免循环依赖
        try:
            from .scheduler import ExecutionState
        except ImportError:
            ExecutionState = None
        
        # 初始化结果
        result = ExecutionResult(
            task_id=f"scheduled_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            status="running",
            started_at=datetime.now(),
            stage_results={},
            final_result={},
            errors=[],
        )
        
        try:
            # 设置协调器
            self._registry = session_registry
            
            self._coordinator = AgentCoordinator(
                message_bus=self.message_bus,
                shared_memory=self._shared_memory,
                session_registry=self._registry,
                config=CoordinatorConfig(
                    max_concurrent=self.config.max_concurrent,
                    default_timeout=self.config.default_timeout,
                    max_retries=self.config.max_retries,
                    heartbeat_interval=self.config.heartbeat_interval,
                    heartbeat_timeout=self.config.heartbeat_timeout,
                ),
            )
            
            await self._coordinator.setup()
            
            # B-FIX-4: subscribe to MessageBus data events
            from src.core.orchestrator.execution.data_collector import DataCollector
            self._data_collector = DataCollector()
            if self.message_bus:
                await self.message_bus.subscribe("data.canonical.updated", self._data_collector.on_canonical_updated)
                await self.message_bus.subscribe("data.conflict.detected", self._data_collector.on_conflict_detected)
            
            # P1-R2修复：使用调度器的批次结果驱动执行
            # 生成执行批次（基于依赖关系的拓扑排序）
            # 优先使用分解计划（支持多阶段调度），回退到基于依赖的拓扑排序
            if decomposition_plan:
                execution_batches = scheduler.schedule_from_decomposition(decomposition_plan, agents)
                logger.info(f"[execute_with_scheduler] 使用分解计划生成 {len(execution_batches)} 个批次")
            else:
                execution_batches = scheduler.schedule_from_agents(agents)
                logger.info(f"[execute_with_scheduler] 使用依赖拓扑生成 {len(execution_batches)} 个批次")
            for i, batch in enumerate(execution_batches):
                logger.info(f"  批次{i+1}: {batch}")
            
            # S-FIX-2/3: init canonical data registry for cross-agent data sharing
            from src.core.data.canonical_registry import CanonicalDataRegistry
            self._canonical_registry = CanonicalDataRegistry()
            self._active_canonical_data: Dict = {}
            # Determine target currency from report region: zh→CNY, en→USD
            _region = (requirement.get("region") or "") if isinstance(requirement, dict) else getattr(requirement, 'region', '')
            self._target_currency = {"中国": "CNY", "China": "CNY", "美国": "USD", "United States": "USD",
                                      "欧洲": "EUR", "Europe": "EUR"}.get(_region, "CNY")
            # Clear cross-run stale data from SharedMemory
            if self._shared_memory and hasattr(self._shared_memory, 'set'):
                self._shared_memory.set("_canonical_registry", {})
            
            all_results = []
            
            # 按批次执行（每批次内并行，批次间串行）
            # C-FIX-1: build section_id→agent mapping from all agents
            _section_to_agent = {}
            for _a in agents:
                _sid = self._get_section_id_from_agent(_a)
                if _sid:
                    _section_to_agent[_sid] = _a
            
            for batch_index, batch_agent_ids in enumerate(execution_batches):
                logger.info(f"[批次{batch_index + 1}/{len(execution_batches)}] 执行: {batch_agent_ids}")
                
                # 获取批次中的 Agent
                batch_agents = []
                pending_unlocked = []  # C-FIX-1: agents unlocked by content_lock
                batch_agent_originals = []  # CR-FIX-1: copy for cache QC re-exec
                completed_results = []  # cached agent results to inject
                skipped_sections = []  # 记录被跳过的章节
                
                # Resume: load completed agent results from persisted AgentSessions.
                # Uses ASPECT as the cache key (not agent_id) so that framework
                # modifications (add/delete/reorder chapters) still match:
                #   Old: ["A","B","C"] → research_A_1, research_B_2, research_C_3
                #   New: ["A","C"]     → research_A_1, research_C_2  ← C matches by aspect
                cached_by_aspect = {}  # aspect -> result dict
                if self._registry:
                    from src.core.agents.agent_session import AgentSessionStatus
                    # Build aspect→result map from ALL completed sessions
                    if hasattr(self._registry, 'child_sessions'):
                        for sid, session in self._registry.child_sessions.items():
                            if session.status != AgentSessionStatus.COMPLETED or not session.result:
                                continue
                            # Extract aspect from session context or task
                            ctx = session.context or {}
                            task = session.task or {}
                            aspect = ctx.get("aspect") or task.get("aspect") or ""
                            if aspect:
                                # CR-FIX-3: skip stale cache (session completed before task start)
                                _task_start = requirement.get("started_at")
                                if _task_start and hasattr(session, 'completed_at') and session.completed_at:
                                    import datetime as _datetime
                                    _ts = _task_start if isinstance(_task_start, _datetime.datetime) else None
                                    _cs = session.completed_at if isinstance(session.completed_at, _datetime.datetime) else None
                                    if _ts and _cs and _cs < _ts:
                                        continue
                                cached_by_aspect[aspect] = session.result
                    if cached_by_aspect:
                        logger.info(
                            f"[批次{batch_index + 1}] Loaded {len(cached_by_aspect)} cached aspects"
                        )
                    # CR-FIX-2: fallback to disk recovery
                    from pathlib import Path
                    _reg_path = Path("data") / "registries" / f"{requirement.get('task_id','')}.json"
                    if _reg_path.exists():
                        try:
                            from src.core.agents.agent_session import AgentSessionRegistry
                            _loaded = AgentSessionRegistry.load(str(_reg_path))
                            if _loaded:
                                for _child in _loaded.child_sessions.values():
                                    if _child.status == getattr(AgentSessionStatus, 'COMPLETED', None):
                                        _aspect = (_child.context or {}).get("aspect","") or \
                                                  (_child.task or {}).get("aspect","") or \
                                                  _child.agent_id or ""
                                        if _aspect and _aspect not in cached_by_aspect:
                                            cached_by_aspect[_aspect] = _child.result
                        except Exception as _e:
                            logger.warning(f"CR-FIX-2 disk recovery failed: {_e}")
                
                for agent_id in batch_agent_ids:
                    agent = scheduler.get_agent_by_id(agent_id)
                    if agent is not None:
                        # Resume: check if this aspect was already completed in a prior run.
                        # Uses aspect name (not agent_id) as key, so framework changes
                        # (add/delete/reorder chapters) don't break cache matching.
                        agent_aspect = ""
                        try:
                            agent_ctx = getattr(agent, 'config', {}).get("context", {})
                            agent_aspect = agent_ctx.get("aspect", "")
                        except Exception:
                            pass
                        cached_result = cached_by_aspect.get(agent_aspect) if agent_aspect else None
                        if cached_result:
                            content = cached_result.get("content") or cached_result.get("result") or ""
                            logger.info(
                                f"[批次{batch_index + 1}] Agent {agent_id} aspect '{agent_aspect}' "
                                f"cached, skipping execution ({len(content)} chars)"
                            )
                            section_id = self._get_section_id_from_agent(agent)
                            completed_results.append({
                                "success": True,
                                "agent_id": agent_id,
                                "section_id": section_id,
                                "content": content[:50000],
                                "data_points": cached_result.get("data_points", []),
                                "sources": cached_result.get("sources", []),
                                "charts": cached_result.get("charts", []),
                                "cached": True,
                            })
                            continue
                        # 检查内容锁（如果启用）
                        if content_lock is not None:
                            section_id = self._get_section_id_from_agent(agent)
                            can_execute, lock_reason = content_lock.can_execute(section_id)
                            if not can_execute:
                                logger.info(f"[批次{batch_index + 1}] [内容锁] Agent {agent_id} 对应章节 {section_id} 被锁定: {lock_reason}")
                                skipped_sections.append((agent_id, section_id, lock_reason))
                                continue
                            # 标记章节为运行中
                            try:
                                content_lock.mark_running(section_id)
                            except Exception as e:
                                logger.error(f"[内容锁] 标记运行失败: {section_id}, {e}")
                                content_lock.mark_failed(section_id, str(e))
                        batch_agents.append(agent)
                
                # CR-FIX-1: save original agents for cache QC re-exec
                batch_agent_originals = batch_agents.copy()
                
                if not batch_agents:
                    if completed_results:
                        # All agents in this batch have cached results — use them directly
                        logger.info(
                            f"[批次{batch_index + 1}] All agents completed from cache "
                            f"({len(completed_results)} results)"
                        )
                        batch_results = completed_results
                        for agent_result in batch_results:
                            scheduler.mark_completed(agent_result.get("agent_id", ""), agent_result)
                            if content_lock is not None:
                                agent = scheduler.get_agent_by_id(agent_result.get("agent_id", ""))
                                if agent:
                                    section_id = self._get_section_id_from_agent(agent)
                                    content_lock.mark_completed(section_id, 1.0)
                        all_results.extend(batch_results)
                        result.stage_results[f"batch_{batch_index + 1}"] = batch_results
                        
                        # CR-FIX-1: cache hit must also pass quality check
                        if self.enable_quality_control and batch_agent_originals:
                            cache_checker = self._select_checker_for_batch(batch_results)
                            if cache_checker:
                                import datetime as _datetime
                                _combined = "\n\n".join([
                                    r.get("content","") or r.get("result","")
                                    for r in batch_results if r.get("success")
                                ])
                                _sources = []
                                _dps = []
                                for r in batch_results:
                                    if r.get("success"):
                                        _sources.extend(r.get("sources",[]))
                                        _dps.extend(r.get("data_points",[]))
                                _cd = {"content":_combined,"sources":_sources,"data_points":_dps,
                                       "quality_metadata":{"data_volume":len(_dps)or len(_sources),
                                                           "sources":_sources,"quality_score":50.0}}
                                _qr = cache_checker.check(_cd, {"batch_index":batch_index})
                                if not _qr.passed:
                                    logger.warning(f"Cached results failed QC for batch {batch_index+1}, re-executing")
                                    batch_results = await self._execute_agents_batch(
                                        batch_agent_originals, requirement, all_results,
                                        scheduler, f"batch_{batch_index+1}_cache_rerun"
                                    )
                                    for agent_result in batch_results:
                                        agent_id = agent_result.get("agent_id", "")
                                        agent = scheduler.get_agent_by_id(agent_id)
                                        section_id = self._get_section_id_from_agent(agent) if agent else self._get_section_id_from_agent_id(agent_id)
                                        agent_result["section_id"] = section_id
                        continue
                    logger.warning(f"[批次{batch_index + 1}] 没有有效的Agent，跳过")
                    result.stage_results[f"batch_{batch_index + 1}"] = []
                    if skipped_sections:
                        result.errors.append(f"批次{batch_index + 1}被内容锁跳过: {len(skipped_sections)}个章节")
                    continue
                
                # ============================================================
                # 取消检查点：批次开始前
                # ============================================================
                session_id = requirement.get("session_id") or requirement.get("task_id", "")
                if self._cancel_manager.is_cancelled(session_id):
                    logger.info(f"[CTRL] CHECKPOINT batch={batch_index + 1} cancelled=True paused=False")
                    result.status = "cancelled"
                    break

                # ============================================================
                # 暂停检查点
                # ============================================================
                if self._cancel_manager.is_paused(session_id):
                    logger.info(f"[CTRL] CHECKPOINT batch={batch_index + 1} cancelled=False paused=True")
                    logger.info(f"Paused at batch {batch_index + 1}, waiting...")
                    pause_result = await self._cancel_manager.wait_for_resume_or_cancel(session_id)
                    if pause_result == "cancelled":
                        result.status = "cancelled"
                        break
                    logger.info(f"Resumed at batch {batch_index + 1}")

                # 二次检查：暂停期间可能收到取消（防御性检查）
                if self._cancel_manager.is_cancelled(session_id):
                    result.status = "cancelled"
                    break

                # ============================================================
                # 注入检查点：检查是否有新的章节注入
                # ============================================================
                if self._inject_handler is not None:
                    try:
                        new_agents = await self._inject_handler(session_id, requirement)
                        if new_agents:
                            scheduler.merge_agents(new_agents)
                            execution_batches = scheduler.reschedule_all()
                            logger.info(
                                f"[CTRL] INJECT checkpoint batch={batch_index + 1}: "
                                f"added {len(new_agents)} agents, "
                                f"rescheduled {len(execution_batches)} batches"
                            )
                    except Exception as e:
                        logger.error(f"[CTRL] Inject checkpoint failed: {e}", exc_info=True)

                # 执行批次
                batch_results = await self._execute_agents_batch(
                    agents=batch_agents,
                    requirement=requirement,
                    previous_results=all_results,
                    scheduler=scheduler,
                    stage_name=f"batch_{batch_index + 1}",
                )
                
                # 更新调度状态和内容锁
                for agent_result in batch_results:
                    agent_id = agent_result.get("agent_id", "")
                    # 注入 section_id 供下游聚合 key 映射使用
                    agent = scheduler.get_agent_by_id(agent_id)
                    section_id = self._get_section_id_from_agent(agent) if agent else self._get_section_id_from_agent_id(agent_id)
                    agent_result["section_id"] = section_id
                    if agent_result.get("success"):
                        scheduler.mark_completed(agent_id, agent_result)
                        # 通知内容锁管理器章节完成
                        if content_lock is not None:
                            quality_score = self._extract_quality_score(agent_result)
                            unlocked_sections = content_lock.mark_completed(section_id, quality_score)
                            if unlocked_sections:
                                logger.info(f"[内容锁] 章节 {section_id} 完成，解锁章节: {unlocked_sections}")
                                # C-FIX-1: find newly unlocked agents in scheduler (not just batch_agents)
                                for _usid in unlocked_sections:
                                    _ua = _section_to_agent.get(_usid)
                                    if _ua:
                                        pending_unlocked.append(_ua)
                    else:
                        scheduler.mark_failed(agent_id, agent_result.get("error", "Unknown error"))
                        # 通知内容锁管理器章节失败
                        if content_lock is not None:
                            content_lock.mark_failed(section_id, agent_result.get("error", ""))
                
                # S-FIX-2: auto-populate canonical registry from agent data_points
                # Safety: only raw search snippets (data_points) are processed, not content (analysis text).
                # ANALYSIS agents pass through DC data_points unchanged → registration is idempotent (key-dedup).
                # Cross-task leakage prevented by SharedMemory clear at execute_with_scheduler() start.
                _has_dc_data = any(r.get("data_points") for r in batch_results if r.get("success"))
                if _has_dc_data and hasattr(self, '_canonical_registry'):
                    try:
                        from src.core.data.metric_extractor import MetricExtractor
                        from src.core.data.canonical_registry import CanonicalDataEntry
                        _ex = MetricExtractor()
                        for _r in batch_results:
                            if _r.get("success") and _r.get("data_points"):
                                _entries = _ex.extract(_r["data_points"])
                                for _ent in _entries:
                                    _ce = CanonicalDataEntry(
                                        metric=_ent["metric"], value=_ent["value"],
                                        unit=_ent.get("unit",""),
                                        currency=_ent.get("currency",""),
                                        caliber=_ent.get("caliber",""),
                                        year=str(_ent.get("year","")), source=_ent.get("source",""),
                                        confidence=_ent.get("confidence", 0.5),
                                    )
                                    await self._canonical_registry.register(_ce)
                        self._active_canonical_data = {
                            k: {"value": v.value, "unit": v.unit, "caliber": v.caliber,
                                "source": v.source, "year": v.year}
                            for k, v in self._canonical_registry.get_all().items()
                        }
                        # Broadcast to SharedMemory for real-time agent access
                        if self._shared_memory and hasattr(self._shared_memory, 'set'):
                            self._shared_memory.set("_canonical_registry", self._active_canonical_data)
                    except Exception as _sce:
                        logger.warning(f"S-FIX-2: canonical data extraction failed: {_sce}")
                
                # Output structure validation (ported from PhaseOrchestrator SchemaValidator)
                # Ensures each agent result has the minimum required fields
                for agent_result in batch_results:
                    self._validate_agent_output(agent_result, batch_index)
                
                # Basic quality check: success rate and data volume
                batch_quality = self._check_stage_quality(batch_results, f"batch_{batch_index + 1}")
                
                # Specialized quality checkers: route to appropriate checker based on batch content
                if self.enable_quality_control and batch_quality:
                    try:
                        checker = self._select_checker_for_batch(batch_results)
                        if checker:
                            quality_context = {
                                "batch_index": batch_index,
                                "total_batches": len(execution_batches),
                                "topic": requirement.get("topic", ""),
                            }
                            # Build check_data in the format checkers expect
                            # (AnalysisQualityChecker reads data["content"],
                            #  DataCollectionQualityChecker reads data["quality_metadata"])
                            combined_content = "\n\n".join([
                                r.get("content", "") or r.get("result", "")
                                for r in batch_results if r.get("success")
                            ])
                            all_sources = []
                            all_data_points = []
                            for r in batch_results:
                                if r.get("success"):
                                    all_sources.extend(r.get("sources", []))
                                    all_data_points.extend(r.get("data_points", []))
                            check_data = {
                                "content": combined_content,
                                "sources": all_sources,
                                "data_points": all_data_points,
                                "quality_metadata": {
                                    "data_volume": len(all_data_points) or len(all_sources),
                                    "sources": all_sources,
                                    "quality_score": 50.0,
                                },
                            }
                            quality_result = checker.check(
                                check_data,
                                quality_context,
                            )
                            if not quality_result.passed:
                                error_msg = (
                                    f"Quality check failed for batch {batch_index + 1}: "
                                    f"score={quality_result.score:.1f}/{quality_result.threshold}, "
                                    f"issues={quality_result.issues[:3]}"
                                )
                                logger.warning(error_msg)
                                # Store quality issues for downstream use
                                for r in batch_results:
                                    if r.get("success"):
                                        r["quality_issues"] = quality_result.issues[:3]
                                        r["quality_score"] = quality_result.score
                                # L-FIX-1: retry before failing (max 1 retry to avoid data accumulation)
                                _max_retries = getattr(self.config, 'max_retries', 1)
                                _qc_retries = 0
                                while _qc_retries < _max_retries:
                                    _qc_retries += 1
                                    logger.info(f"QC retry {_qc_retries}/{_max_retries} for batch {batch_index+1}")
                                    for _a in batch_agents:
                                        if hasattr(_a, 'reset'):
                                            await _a.reset()
                                        if hasattr(_a, '_context') and isinstance(_a._context, dict):
                                            _a._context["retry_attempt"] = _qc_retries
                                    _retry_results = await self._execute_agents_batch(
                                        batch_agents, requirement, all_results, scheduler,
                                        f"batch_{batch_index+1}_qc_retry{_qc_retries}"
                                    )
                                    _retry_combined = "\n\n".join([
                                        r.get("content","") or r.get("result","")
                                        for r in _retry_results if r.get("success")
                                    ])
                                    _retry_src = []
                                    _retry_dp = []
                                    for r in _retry_results:
                                        if r.get("success"):
                                            _retry_src.extend(r.get("sources",[]))
                                            _retry_dp.extend(r.get("data_points",[]))
                                    _retry_check = {
                                        "content": _retry_combined,
                                        "sources": _retry_src,
                                        "data_points": _retry_dp,
                                        "quality_metadata": {
                                            "data_volume": len(_retry_dp) or len(_retry_src),
                                            "sources": _retry_src,
                                            "quality_score": 50.0,
                                        },
                                    }
                                    _retry_qr = checker.check(_retry_check, quality_context)
                                    if _retry_qr.passed:
                                        logger.info(f"QC retry {_qc_retries} PASSED")
                                        batch_results = _retry_results
                                        break
                                else:
                                    # All retries exhausted — quality is advisory, not blocking
                                    # Continue with available results for revision workflow
                                    # quality_issues already injected on agent results (L1397-1400)
                                    logger.warning(
                                        f"QC all retries exhausted for batch {batch_index+1}, "
                                        f"continuing: {error_msg}"
                                    )
                            else:
                                logger.info(f"Quality check PASSED for batch {batch_index + 1}: score={quality_result.score:.1f}")
                    except Exception as qe:
                        logger.warning(f"Quality checker exception for batch {batch_index + 1}: {qe}")
                
                if not batch_quality:
                    success_count = sum(1 for r in batch_results if r.get("success"))
                    total_count = len(batch_results)
                    if total_count > 0 and success_count == 0:
                        error_msg = f"Batch {batch_index + 1} all failed ({total_count}/{total_count}), aborting"
                        logger.error(error_msg)
                        result.status = "failed"
                        result.errors.append(error_msg)
                        break
                    else:
                        logger.warning(f"Batch {batch_index + 1} partial failure ({total_count - success_count}/{total_count}), continuing")
            
            # Bug-3-4c: extend all_results + stage_results AFTER QC (avoid failed-result accumulation)
            all_results.extend(batch_results)
            result.stage_results[f"batch_{batch_index + 1}"] = batch_results
            
            # C-FIX-1: execute newly unlocked agents at batch end
            if pending_unlocked and result.status != "failed":
                logger.info(f"Re-executing {len(pending_unlocked)} newly unlocked agents")
                _unlock_results = await self._execute_agents_batch(
                    pending_unlocked, requirement, all_results,
                    scheduler, f"batch_{batch_index+1}_unlock"
                )
                batch_results.extend(_unlock_results)
                all_results.extend(_unlock_results)
                pending_unlocked.clear()
            
            # Pre-generation consistency gate: detect inconsistency, auto-fix data_points only
            # Auto-fix targets structured data_points, NOT narrative content text.
            # Content text is never modified — only data_points are reconciled to canonical values.
            if result.status != "failed" and self.enable_quality_control and all_results and self._active_canonical_data:
                try:
                    from src.core.quality.checkers import NumericConsistencyGate
                    _gate = NumericConsistencyGate(threshold=80.0)
                    _gate_sections = [
                        {"id": r.get("agent_id", f"agent_{i}"), "content": r.get("content", "") or r.get("result", "")}
                        for i, r in enumerate(all_results) if r.get("success")
                    ]
                    _gate_result = _gate.check({"sections": _gate_sections})
                    if not _gate_result.passed:
                        logger.warning(f"Consistency gate: {_gate_result.score:.1f}/80, reconciling data_points to canonical values")
                        _fix_count = 0
                        for _metric_key, _canon in self._active_canonical_data.items():
                            _kp = parse_entry_key(_metric_key)
                            _cv = str(_canon.get("value", ""))
                            if not _cv:
                                continue
                            _metric_name = _kp["metric"]
                            # Only fix data_points (structured metadata), never touch content text
                            for _r in all_results:
                                if not _r.get("success"):
                                    continue
                                for _dp in _r.get("data_points", []):
                                    if _dp.get("metric", "").lower() == _metric_name.lower():
                                        _dp_year = str(_dp.get("year", ""))
                                        _dp_caliber = _dp.get("caliber", "") or ""
                                        _canon_year = str(_kp.get("year", ""))
                                        _canon_caliber = _canon.get("caliber", "") or ""
                                        if _canon_year and _dp_year and _dp_year != _canon_year:
                                            continue
                                        if _canon_caliber and _dp_caliber and _dp_caliber != _canon_caliber:
                                            continue
                                        _old_val = str(_dp.get("value", ""))
                                        if _old_val != "" and _old_val != _cv:
                                            _dp["value"] = _cv
                                            _fix_count += 1
                        if _fix_count > 0:
                            logger.info(f"Consistency gate: reconciled {_fix_count} data_points to canonical values (content text unchanged)")
                except ImportError:
                    pass
            
            # 构建最终结果（若 QC 在循环内已置为 failed，不再覆盖）
            if result.status != "failed":
                result.status = "completed"
                result.final_result = self._aggregate_results(all_results)
                result.stats = self._build_stats()
            result.completed_at = datetime.now()
            
            logger.info(f"执行完成: 成功={sum(1 for r in all_results if r.get('success'))}, "
                       f"失败={sum(1 for r in all_results if not r.get('success'))}")
            
            return result

        except asyncio.CancelledError:
            logger.info(f"Execution cancelled externally: {result.task_id}")
            result.status = "cancelled"
            result.completed_at = datetime.now()
            return result

        except Exception as e:
            result.status = "failed"
            result.completed_at = datetime.now()
            result.errors.append(str(e))

            logger.error(f"调度执行失败: {e}")

            return result

        finally:
            # 清理 CancelManager 资源（session级，不影响其他session）
            sid = requirement.get("session_id") or requirement.get("task_id", "")
            if sid:
                self._cancel_manager.cleanup(sid)

    async def execute_with_skip(
        self,
        agents: List["IAgent"],
        requirement: Dict[str, Any],
        decomposition_plan: Optional[Any] = None,
        skip_phases: Optional[List[str]] = None,
        existing_results: Optional[Dict[str, Any]] = None,
        session_registry: Optional["AgentSessionRegistry"] = None,
    ) -> ExecutionResult:
        """
        Execute agents with phase skipping for incremental revision.

        Filters out agents belonging to completed phases, executes only
        the new/changed phases, and injects existing_results into the
        stage_results for downstream aggregation.

        Args:
            agents: Full list of agents (some will be filtered out)
            requirement: Research requirement dict
            decomposition_plan: Task decomposition plan
            skip_phases: Phase IDs to skip (completed phases)
            existing_results: Previously completed section data {section_name: content}
            session_registry: Agent session registry

        Returns:
            ExecutionResult with filtered execution + existing data injected
        """
        from src.core.orchestrator.execution.scheduler import ExecutionScheduler

        # Filter agents: skip those belonging to completed phases
        agents_to_execute = list(agents)
        if decomposition_plan is not None and skip_phases:
            # Map decomposition_plan phases to agent indices
            skip_indices: set = set()
            for i, phase in enumerate(decomposition_plan.execution_order):
                phase_id = phase.value if hasattr(phase, 'value') else str(phase)
                if phase_id in skip_phases:
                    skip_indices.add(i)

            if skip_indices:
                agents_to_execute = [
                    a for i, a in enumerate(agents) if i not in skip_indices
                ]
                logger.info(
                    f"Skip {len(skip_indices)} completed phases: {skip_phases}, "
                    f"agents filtered: {len(agents)} -> {len(agents_to_execute)}"
                )

        # Execute remaining agents
        exec_result = await self.execute_with_scheduler(
            agents=agents_to_execute,
            requirement=requirement,
            scheduler=ExecutionScheduler(),
            decomposition_plan=decomposition_plan,
            session_registry=session_registry,
        )

        # Inject existing results for aggregation
        if existing_results:
            if exec_result.stage_results is None:
                exec_result.stage_results = {}
            exec_result.stage_results["_existing_data"] = [
                {
                    "success": True,
                    "content": content,
                    "agent_id": f"existing_{key}",
                    "source": "existing",
                }
                for key, content in existing_results.items()
            ]

        return exec_result

    async def _execute_agents_batch(
        self,
        agents: List["IAgent"],
        requirement: Dict[str, Any],
        previous_results: List[Dict[str, Any]],
        scheduler: Any,
        stage_name: str,
    ) -> List[Dict[str, Any]]:
        """
        执行一批Agent（阶段内并行执行）
        
        Args:
            agents: Agent列表
            requirement: 需求定义
            previous_results: 前序结果
            scheduler: 调度器
            stage_name: 阶段名称
            
        Returns:
            执行结果列表
        """
        logger.info(f"[{stage_name}] 开始执行 {len(agents)} 个Agent")
        
        # 标记Agent为运行中
        for agent in agents:
            scheduler.mark_running(agent.agent_id)
        
        # 并行执行
        batch_results = await self._execute_batch(
            agents=agents,
            requirement=requirement,
            previous_results=previous_results,
            scheduler=scheduler,
            stage_name=stage_name,  # 传递阶段名称
        )
        
        # 更新调度状态
        for agent_result in batch_results:
            agent_id = agent_result.get("agent_id", "")
            if agent_result.get("success"):
                scheduler.mark_completed(agent_id, agent_result)
            else:
                scheduler.mark_failed(agent_id, agent_result.get("error", "Unknown error"))
        
        # 检查失败情况
        failed = [r for r in batch_results if not r.get("success")]
        if failed:
            logger.warning(f"[{stage_name}] {len(failed)}/{len(batch_results)} 个Agent失败")
        
        return batch_results
    
    def _select_checker_for_batch(self, batch_results: List[Dict[str, Any]]) -> Optional[Any]:
        """Select the appropriate quality checker based on batch content.
        
        Analyzes batch results to determine the execution phase and routes
        to the corresponding specialized checker.
        
        Args:
            batch_results: Results from the completed batch
            
        Returns:
            Quality checker instance, or None if no suitable checker is available
        """
        if not self.enable_quality_control:
            return None
        
        # Count result types to infer the phase
        has_data_points = any(r.get("data_points") for r in batch_results if r.get("success"))
        has_sources = any(r.get("sources") for r in batch_results if r.get("success"))
        has_content = any(
            r.get("content") or r.get("result") for r in batch_results if r.get("success")
        )
        has_validation = any(
            r.get("validation") for r in batch_results if r.get("success")
        )
        
        # Data collection phase: results have data_points/sources but little content
        if has_data_points and has_sources and not has_content:
            return self.data_checker
        
        # Analysis phase: results have substantial content with analysis
        if has_content:
            # G3-FIX-1: wrap with CompositeChecker + LLMJudgeChecker for semantic evaluation
            try:
                from src.core.quality.llm_judge import LLMJudgeChecker
                from src.core.quality.checkers import CompositeChecker
                return CompositeChecker([self.analysis_checker, LLMJudgeChecker(threshold=75.0)], [0.7, 0.3])
            except ImportError:
                return self.analysis_checker
        
        # Validation phase
        if has_validation:
            return self.data_checker
        
        # Default: use data checker for safety
        return self.data_checker
    
    def _validate_agent_output(self, result: Dict[str, Any], batch_index: int) -> None:
        """Validate agent output has minimum required fields.
        
        Lightweight output validation ported from PhaseOrchestrator's SchemaValidator.
        Checks that each agent result contains the necessary structure for downstream
        consumption. Missing fields are logged but do not block execution.
        
        Args:
            result: Agent execution result dict
            batch_index: Current batch index for logging context
        """
        agent_id = result.get("agent_id", "unknown")
        issues = []
        
        # Check required top-level fields
        if "success" not in result:
            issues.append("missing 'success' field")
        
        # For successful results, check content or data_points
        if result.get("success"):
            has_content = bool(result.get("content") or result.get("result"))
            has_data = bool(result.get("data_points"))
            has_validation = bool(result.get("validation"))
            
            if not (has_content or has_data or has_validation):
                issues.append("successful result has no content, data_points, or validation")
        
        # Check agent_id is present and non-empty
        if not agent_id or agent_id == "unknown":
            issues.append("missing or invalid agent_id")
        
        if issues:
            result["validation_issues"] = issues
            logger.warning(f"Output validation issues for {agent_id} in batch {batch_index + 1}: {issues}")
    
    def _check_stage_quality(
        self,
        results: List[Dict[str, Any]],
        stage_name: str,
    ) -> bool:
        """
        检查阶段质量
        
        Args:
            results: 阶段结果
            stage_name: 阶段名称
            
        Returns:
            质量是否通过
        """
        success_count = sum(1 for r in results if r.get("success"))
        total_count = len(results)
        
        # 统计数据量
        total_data_points = sum(len(r.get("data_points", [])) for r in results if r.get("success"))
        total_sources = sum(len(r.get("sources", [])) for r in results if r.get("success"))
        total_content = sum(len(r.get("content", "") or r.get("result", "")) for r in results if r.get("success"))
        
        # 质量标准
        MIN_SUCCESS_RATE = 0.5
        success_rate = success_count / total_count if total_count > 0 else 0
        
        quality_passed = success_rate >= MIN_SUCCESS_RATE
        
        logger.info(
            f"[{stage_name}] 质量检查: "
            f"成功率={success_rate:.1%} ({success_count}/{total_count}), "
            f"数据点={total_data_points}, "
            f"来源={total_sources}, "
            f"内容={total_content}字符, "
            f"通过={quality_passed}"
        )
        
        return quality_passed
    
    async def _execute_batch(
        self,
        agents: List["IAgent"],
        requirement: Dict[str, Any],
        previous_results: List[Dict[str, Any]],
        scheduler: Any,
        stage_name: str = "",  # 新增：阶段名称，用于持久化记录
    ) -> List[Dict[str, Any]]:
        """
        执行一批Agent（并行执行）
        
        Args:
            agents: Agent列表
            requirement: 需求定义
            previous_results: 前序结果
            scheduler: 调度器
            stage_name: 阶段名称（可选，用于持久化记录）
            
        Returns:
            执行结果列表
        """
        # **关键修复**：提取并合并前序结果中的数据
        # 这是数据传递链路的关键环节！
        # **重要**: 即使前序结果失败，也要提取其中已收集的数据
        aggregated_data_points = []
        aggregated_sources = []
        aggregated_content = []
        research_sections = []  # 新增：收集各章节内容
        
        # 同时按 agent_id 索引数据点，用于后续按依赖过滤
        data_points_by_agent: Dict[str, List[Dict]] = {}
        sources_by_agent: Dict[str, List[Dict]] = {}
        
        for prev_result in previous_results:
            agent_id = prev_result.get("agent_id", "")
            
            # **修复**: 不再跳过失败的结果，而是尝试提取其中的数据
            # 失败的 Agent 可能已经收集了部分数据
            
            # 提取data_points（即使结果失败也要提取）
            if "data_points" in prev_result:
                aggregated_data_points.extend(prev_result["data_points"])
                data_points_by_agent.setdefault(agent_id, []).extend(prev_result["data_points"])
            
            # 提取sources（即使结果失败也要提取）
            if "sources" in prev_result:
                aggregated_sources.extend(prev_result["sources"])
                sources_by_agent.setdefault(agent_id, []).extend(prev_result["sources"])
            
            # 只有成功的结果才提取content
            if prev_result.get("success"):
                # 提取content（LLM分析结果）
                content = (
                    prev_result.get("content") or 
                    prev_result.get("result") or 
                    prev_result.get("output") or
                    ""
                )
                if content and isinstance(content, str):
                    aggregated_content.append({
                        "agent_id": agent_id,
                        "content": content[:2000],  # 限制长度
                    })
                    
                    # 收集章节内容（用于报告生成）
                    # 从agent_id提取章节名
                    if "_" in agent_id:
                        section_name = agent_id.split("_", 1)[-1]  # 去掉前缀
                    else:
                        section_name = agent_id
                        
                    research_sections.append({
                        "id": agent_id,
                        "title": section_name,
                        "content": content,
                    })
        
        # 确保协调器已初始化
        assert self._coordinator is not None
        
        # 并行分发任务
        task_ids = []
        agent_task_map = {}
        
        for agent in agents:
            try:
                # **关键修复**：根据Agent类型构建不同的任务
                agent_category = self.classify_agent(agent)
                
                if agent_category in (AgentCategory.REPORT_GENERATION, AgentCategory.DOCUMENT_GENERATION):
                    # 报告生成Agent需要特殊格式的任务
                    task = {
                        "action": "produce_document",
                        "task_id": requirement.get("task_id", f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"),
                        "output_format": requirement.get("output_format", "docx"),
                        "output_dir": requirement.get("output_dir"),
                        "research_result": {
                            "topic": requirement.get("topic"),
                            "sections": research_sections,
                            "data_points": aggregated_data_points,
                            "sources": aggregated_sources,
                            "total_word_count": sum(len(s.get("content", "")) for s in research_sections),
                        },
                    }
                    logger.info(f"[_execute_batch] 报告生成任务: sections={len(research_sections)}, "
                               f"data_points={len(aggregated_data_points)}")
                elif agent_category == AgentCategory.SYNTHESIS:
                    # **正确修复**: 基于 scheduler 中定义的依赖关系过滤数据
                    # synthesis agent 只接收其依赖的 agent 的结果
                    
                    # 优先使用 section_id，fallback 到 agent_id 解析
                    target_aspect = getattr(agent, 'section_id', None) or self._extract_aspect_from_agent_id(agent.agent_id)
                    
                    # 从调度器获取该 agent 的依赖
                    scheduled_agent = scheduler.get_scheduled_agent(agent.agent_id)
                    dependencies = []
                    if scheduled_agent:
                        dependencies = scheduled_agent.dependencies
                        logger.info(f"[_execute_batch] synthesis Agent {agent.agent_id} 依赖: {dependencies}")
                    
                    # 注册数据边界
                    from .data_boundary_controller import create_boundary_for_synthesis
                    boundary = create_boundary_for_synthesis(
                        synthesis_agent_id=agent.agent_id,
                        target_aspect=target_aspect,
                        all_agent_ids=list(scheduler._scheduled_agents.keys()) if hasattr(scheduler, '_scheduled_agents') else [],
                        configured_dependencies=dependencies,
                    )
                    await self.data_boundary.register_boundary(boundary)
                    
                    # 基于依赖过滤数据
                    if dependencies:
                        # 只保留依赖的 agent 的结果
                        filtered_previous_results = [
                            prev for prev in previous_results
                            if prev.get("agent_id") in dependencies
                        ]
                        filtered_content = [
                            item for item in aggregated_content
                            if item.get("agent_id") in dependencies
                        ]
                        # **污染修复**: 按依赖过滤数据点，只传依赖 agent 收集的数据
                        filtered_data_points = []
                        filtered_sources = []
                        for dep_agent_id in dependencies:
                            if dep_agent_id in data_points_by_agent:
                                filtered_data_points.extend(data_points_by_agent[dep_agent_id])
                            if dep_agent_id in sources_by_agent:
                                filtered_sources.extend(sources_by_agent[dep_agent_id])
                        logger.info(f"[_execute_batch] synthesis 基于依赖过滤: {len(filtered_previous_results)} 结果, "
                                   f"{len(filtered_content)} 内容, {len(filtered_data_points)} 数据点 (依赖: {dependencies})")
                    else:
                        # 如果没有定义依赖，默认接收所有非 synthesis 结果
                        filtered_previous_results = [
                            prev for prev in previous_results
                            if not prev.get("agent_id", "").startswith("synthesis_")
                        ]
                        filtered_content = [
                            item for item in aggregated_content
                            if not item.get("agent_id", "").startswith("synthesis_")
                        ]
                        # 无依赖时取所有非 synthesis 数据点
                        filtered_data_points = [
                            dp for aid, dps in data_points_by_agent.items()
                            if not aid.startswith("synthesis_")
                            for dp in dps
                        ]
                        filtered_sources = [
                            src for aid, srcs in sources_by_agent.items()
                            if not aid.startswith("synthesis_")
                            for src in srcs
                        ]
                        logger.info(f"[_execute_batch] synthesis 无显式依赖，使用默认过滤")
                    
                    # 污染修复：synthesis agent 只接收 target_aspect 作为 aspects
                    # 避免所有章节名称混淆 LLM
                    synthesis_aspects = [target_aspect] if target_aspect else requirement.get("aspects", [])
                    
                    # 数据边界验证：确保 filtered_data 在边界内
                    boundary_filtered = await self.data_boundary.get_allowed_data(
                        agent_id=agent.agent_id,
                        all_data=filtered_content,
                        data_type="content",
                    )
                    if boundary_filtered:
                        filtered_content = boundary_filtered
                    
                    task = {
                        "action": "execute",
                        "topic": requirement.get("topic"),
                        "aspects": synthesis_aspects,  # 只传目标章节
                        "data": filtered_previous_results,
                        "aggregated_data_points": filtered_data_points,  # 按依赖过滤
                        "aggregated_sources": filtered_sources,  # 按依赖过滤
                        "aggregated_content": filtered_content,
                        "target_aspect": target_aspect,  # 传递目标章节
                    }
                    
                    logger.info(f"[_execute_batch] synthesis任务: agent={agent.agent_id}, "
                               f"target_aspect={target_aspect}, "
                               f"filtered_content={len(filtered_content)}")
                else:
                    # **正确修复**: 基于 scheduler 中定义的依赖关系过滤数据
                    # 每个 agent 只接收其依赖的 agent 的结果
                    
                    # 从调度器获取该 agent 的依赖
                    scheduled_agent = scheduler.get_scheduled_agent(agent.agent_id)
                    dependencies = []
                    if scheduled_agent:
                        dependencies = scheduled_agent.dependencies
                        logger.info(f"[_execute_batch] Agent {agent.agent_id} 依赖: {dependencies}")
                    
                    # 基于依赖过滤数据
                    if dependencies:
                        # 只保留依赖的 agent 的结果
                        filtered_previous_results = [
                            prev for prev in previous_results
                            if prev.get("agent_id") in dependencies
                        ]
                        filtered_content = [
                            item for item in aggregated_content
                            if item.get("agent_id") in dependencies
                        ]
                        # **污染修复**: 按依赖过滤数据点，只传依赖 agent 收集的数据
                        filtered_data_points = []
                        filtered_sources = []
                        for dep_agent_id in dependencies:
                            if dep_agent_id in data_points_by_agent:
                                filtered_data_points.extend(data_points_by_agent[dep_agent_id])
                            if dep_agent_id in sources_by_agent:
                                filtered_sources.extend(sources_by_agent[dep_agent_id])
                        logger.info(f"[_execute_batch] 基于依赖过滤: {len(filtered_previous_results)} 结果, "
                                   f"{len(filtered_content)} 内容, {len(filtered_data_points)} 数据点 (依赖: {dependencies})")
                    else:
                        # 无依赖的 agent（如 data_collection）不接收前序结果
                        filtered_previous_results = []
                        filtered_content = []
                        filtered_data_points = []
                        filtered_sources = []
                        logger.info(f"[_execute_batch] Agent {agent.agent_id} 无依赖，不接收前序结果")
                    
                    # **污染修复**: 优先使用 section_id，fallback 到 agent_id 解析
                    # 避免 LLM 看到所有章节名后混淆输出
                    agent_aspect = getattr(agent, 'section_id', None) or self._extract_aspect_from_agent_id(agent.agent_id)
                    if agent_aspect:
                        agent_aspects = [agent_aspect]
                        logger.info(f"[_execute_batch] Agent {agent.agent_id} 目标章节: {agent_aspect}")
                    else:
                        agent_aspects = requirement.get("aspects", [])
                    
                    # 数据边界验证（非 synthesis agent）
                    from .data_boundary_controller import create_boundary_for_analysis
                    dep_list = dependencies if dependencies else []
                    analysis_boundary = create_boundary_for_analysis(
                        analysis_agent_id=agent.agent_id,
                        target_aspect=agent_aspect or "",
                        all_agent_ids=list(scheduler._scheduled_agents.keys()) if hasattr(scheduler, '_scheduled_agents') else [],
                    )
                    # 更新允许的 agents 为实际依赖
                    analysis_boundary.allowed_agents = set(dep_list)
                    await self.data_boundary.register_boundary(analysis_boundary)
                    boundary_filtered = await self.data_boundary.get_allowed_data(
                        agent_id=agent.agent_id,
                        all_data=filtered_content,
                        data_type="content",
                    )
                    if boundary_filtered:
                        filtered_content = boundary_filtered
                    
                    task = {
                        "action": "execute",
                        "topic": requirement.get("topic"),
                        "aspects": agent_aspects,
                        "data": filtered_previous_results,
                        "aggregated_data_points": filtered_data_points,
                        "aggregated_sources": filtered_sources,
                        # S-FIX-3: inject canonical data for cross-agent consistency
                        "canonical_data": self._active_canonical_data,
                        "target_currency": self._target_currency,
                    }
                    
                    # P1-1: Enhanced data injection for agents with no dependencies.
                    # Attempts to recover data from ResearchResultStore (persisted by
                    # understanding phase or previous batch saves).
                    if not filtered_data_points and not filtered_sources:
                        injected_data = False
                        try:
                            task_id_from_req = requirement.get("task_id")
                            if task_id_from_req:
                                result_store = ResearchResultStore(storage_path="data")
                                saved = result_store.load_result(task_id_from_req)
                                if saved:
                                    saved_dps = saved.get("data_points", [])
                                    saved_srcs = saved.get("sources", [])
                                    if saved_dps and len(saved_dps) > 0:
                                        seen_urls = set()
                                        deduped = []
                                        for dp in saved_dps:
                                            url = dp.get("url", "") if isinstance(dp, dict) else ""
                                            if url and url in seen_urls:
                                                continue
                                            if url:
                                                seen_urls.add(url)
                                            deduped.append(dp)
                                        task["aggregated_data_points"] = deduped[:5000]
                                        injected_data = True
                                    if saved_srcs and len(saved_srcs) > 0:
                                        seen_urls = set()
                                        deduped = []
                                        for src in saved_srcs:
                                            url = src.get("url", "") if isinstance(src, dict) else ""
                                            if url and url in seen_urls:
                                                continue
                                            if url:
                                                seen_urls.add(url)
                                            deduped.append(src)
                                        task["aggregated_sources"] = deduped[:5000]
                                        injected_data = True
                                    if injected_data:
                                        logger.info(
                                            f"[_execute_batch] Injected {len(saved.get('data_points',[]))} "
                                            f"data points from ResearchResultStore to {agent.agent_id}"
                                        )
                        except Exception as e:
                            logger.warning(f"[_execute_batch] Data store recovery failed: {e}")
                    
                    logger.info(f"[_execute_batch] 通用任务: data_points={len(task.get('aggregated_data_points', []))}, "
                               f"sources={len(task.get('aggregated_sources', []))}, "
                               f"filtered_content={len(filtered_content)}")
                
                # 防御性获取配置
                agent_config = getattr(agent, 'config', {}) or {}
                
                # 数据收集/分析/综合agent需要更长超时（数据量大，LLM处理时间长）
                default_timeout = self.config.default_timeout
                if agent_category in (AgentCategory.DATA_COLLECTION, AgentCategory.ANALYSIS, AgentCategory.SYNTHESIS):
                    default_timeout = 7200  # 2小时，确保大数据量处理不超时
                
                task_id = await self._coordinator.dispatch_task(
                    agent=agent,
                    task=task,
                    options=TaskOptions(
                        timeout=agent_config.get("timeout", default_timeout),
                        max_retries=agent_config.get("max_retries", self.config.max_retries),
                    ),
                )
                task_ids.append(task_id)
                agent_task_map[task_id] = agent.agent_id
            except Exception as e:
                logger.error(f"分发任务失败 {agent.agent_id}: {e}")
                # ER-FIX-2: add error result so downstream can detect failure
                error_result = {"success": False, "error": f"Task dispatch failed: {e}",
                                "agent_id": agent.agent_id, "action": task.get("action", "")}
        
        # 等待完成
        results = await self._coordinator.wait_for_completion(task_ids)
        
        # Apply harness constraint checks on each agent result
        for task_id in task_ids:
            task_result = results.get(task_id)
            if task_result and task_result.get("success"):
                constraint_result = check_agent_output(task_result)
                task_result["quality_metadata"] = {
                    "harness": {
                        "passed": constraint_result.passed,
                        "errors": constraint_result.errors,
                        "warnings": constraint_result.warnings,
                        "source_validation": constraint_result.source_validation,
                        "cross_validation": (
                            constraint_result.cross_validation.to_dict()
                            if hasattr(constraint_result.cross_validation, 'to_dict')
                            else constraint_result.cross_validation
                        ),
                        "confidence": constraint_result.confidence_assessment,
                        "fact_traces": constraint_result.fact_traces,
                        "checked_at": constraint_result.checked_at,
                    }
                }
                if not constraint_result.passed:
                    logger.warning(
                        f"Harness constraint check failed: agent={task_result.get('agent_id')}, "
                        f"errors={constraint_result.errors}"
                    )
        
        # 提取结果
        batch_results = []
        for task_id in task_ids:
            task_result = results.get(task_id)
            if task_result:
                # 确保结果包含agent_id
                if "agent_id" not in task_result:
                    task_result["agent_id"] = agent_task_map.get(task_id, "")
                batch_results.append(task_result)
        
        # A-1修复：将批次结果持久化到 ResearchResultStore（JSON文件）
        try:
            task_id_for_store = requirement.get("task_id")
            if task_id_for_store:
                result_store = ResearchResultStore(storage_path="data")
                batch_data_points = []
                batch_sources = []
                # Per-agent content storage for resume (saves each agent's
                # LLM-generated analysis so we can skip completed agents on resume)
                agent_contents = {}
                for r in batch_results:
                    _dp = r.get("data_points")
                    if _dp is not None and len(_dp) > 0:
                        batch_data_points.extend(_dp)
                    _src = r.get("sources")
                    if _src is not None and len(_src) > 0:
                        batch_sources.extend(_src)
                    agent_id = r.get("agent_id", "")
                    if agent_id and r.get("success"):
                        content = r.get("content") or r.get("result") or ""
                        if content and isinstance(content, str) and len(content) > 50:
                            agent_contents[agent_id] = {
                                "agent_id": agent_id,
                                "content": content[:50000],  # cap per agent
                                "success": True,
                                "phase": stage_name,
                            }
                
                batch_completed = [{
                    "agent_id": r.get("agent_id", ""),
                    "success": r.get("success", False),
                    "phase": stage_name,
                } for r in batch_results]
                
                if batch_data_points or batch_sources or agent_contents:
                    result_store.save_result(
                        task_id=task_id_for_store,
                        result={
                            "topic": requirement.get("topic", ""),
                            "sections": [],
                            "data_points": batch_data_points,
                            "sources": batch_sources,
                            "completed_agents": batch_completed,
                            "agent_contents": agent_contents,  # per-agent content for resume
                        },
                        status=ResearchStatus.COLLECTING,
                    )
                    logger.info(
                        f"[_execute_batch] ResearchResultStore persisted: "
                        f"{len(batch_data_points)} data_points, "
                        f"{len(batch_sources)} sources, "
                        f"{len(agent_contents)} agent results"
                    )
        except Exception as e:
            logger.warning(f"[_execute_batch] ResearchResultStore持久化失败: {e}")
        
        return batch_results
    
    async def shutdown(self) -> None:
        """关闭引擎"""
        logger.info("Shutting down ExecutionEngine")
        
        # 关闭协调器
        if self._coordinator:
            await self._coordinator.shutdown()
        
        # 关闭后台执行器
        await self.background.shutdown()
        
        # 清理
        self.concurrency.clear()
        self.retry.clear_task("all")
    
    # ============================================================
    # 质量控制相关方法
    # ============================================================
    
    async def _execute_stage_with_quality(
        self,
        stage_name: str,
        agents: List["IAgent"],
        checker,
        task_builder: Callable,
        requirement: Dict[str, Any],
        previous_results: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        带质量控制的阶段执行
        
        Args:
            stage_name: 阶段名称
            agents: Agent列表
            checker: 质量检查器
            task_builder: 任务构建函数
            requirement: 需求定义
            previous_results: 前一阶段结果
            
        Returns:
            执行结果列表
        """
        if not self.enable_quality_control:
            # 未启用质量控制，直接执行
            return await self._execute_stage(
                stage_name=stage_name,
                agents=agents,
                task_builder=task_builder,
                requirement=requirement,
                previous_results=previous_results or [],
            )
        
        async def execute_func(context: Dict[str, Any]) -> Dict[str, Any]:
            """执行函数"""
            results = await self._execute_stage(
                stage_name=stage_name,
                agents=agents,
                task_builder=task_builder,
                requirement=context.get("requirement", requirement),
                previous_results=context.get("previous_results", previous_results or []),
            )
            
            # 提取质量元数据
            for result in results:
                if result.get("success"):
                    # 兼容多种输出格式
                    raw_output = self._extract_raw_output(result)
                    quality_metadata = self.metadata_extractor.extract(
                        raw_output, 
                        skill_name=result.get("agent_id", "")
                    )
                    result["quality_metadata"] = quality_metadata.to_dict()
            
            # 聚合结果
            aggregated = self._aggregate_stage_results(results)
            return aggregated
        
        # 构建上下文
        context = {
            "requirement": requirement,
            "previous_results": previous_results or [],
        }
        
        # 使用反馈执行器
        data, quality_result = await self.quality_executor.execute_with_retry(
            stage=stage_name,
            execute_func=execute_func,
            checker=checker,
            context=context,
        )
        
        # 记录质量结果
        if quality_result:
            logger.info(
                f"[{stage_name}] 质量检查完成: "
                f"score={quality_result.score:.1f}, passed={quality_result.passed}"
            )
        
        return data.get("results", [])
    
    def _aggregate_stage_results(
        self,
        results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        聚合阶段结果
        
        Args:
            results: 阶段结果列表
            
        Returns:
            聚合后的结果
        """
        successful = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]
        
        # 聚合质量元数据
        quality_metadatas = [
            r.get("quality_metadata", {})
            for r in successful
            if r.get("quality_metadata")
        ]
        
        # 合并数据量
        total_volume = sum(
            qm.get("data_volume", 0)
            for qm in quality_metadatas
        )
        
        # 合并来源
        all_sources = []
        for qm in quality_metadatas:
            all_sources.extend(qm.get("sources", []))
        
        # 去重来源
        seen_urls = set()
        unique_sources = []
        for s in all_sources:
            if s.get("url") not in seen_urls:
                seen_urls.add(s["url"])
                unique_sources.append(s)
        
        # 计算平均质量分数
        scores = [
            qm.get("quality_score", 50)
            for qm in quality_metadatas
        ]
        avg_score = sum(scores) / len(scores) if scores else 50
        
        return {
            "success": len(successful) > 0,
            "results": results,
            "quality_metadata": {
                "data_volume": total_volume,
                "sources": unique_sources,
                "quality_score": avg_score,
                "extraction_confidence": 1.0 if quality_metadatas else 0.0,
            },
            "stats": {
                "total": len(results),
                "successful": len(successful),
                "failed": len(failed),
            },
        }
    
    def _extract_raw_output(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        从结果中提取原始输出（兼容多种格式）
        
        Args:
            result: 执行结果
            
        Returns:
            原始输出字典
        """
        # 兼容多种输出格式
        raw_output = (
            result.get("result") or 
            result.get("content") or 
            result.get("output") or 
            result.get("data") or 
            {}
        )
        
        # **修复**: 确保返回字典类型
        if isinstance(raw_output, dict):
            return raw_output
        elif isinstance(raw_output, str):
            # 如果是字符串，尝试解析为JSON，否则包装为字典
            try:
                import json
                parsed = json.loads(raw_output)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                pass
            # 无法解析，包装为字典
            return {"raw_text": raw_output}
        elif isinstance(raw_output, list):
            # 如果是列表，包装为字典
            return {"items": raw_output}
        else:
            return {}
    
    def get_quality_summary(self) -> Dict[str, Any]:
        """
        获取质量执行摘要
        
        Returns:
            质量执行摘要
        """
        if not self.enable_quality_control or not self.quality_executor:
            return {"enabled": False}
        
        return {
            "enabled": True,
            "summary": self.quality_executor.get_summary(),
        }
    
    # === 内容锁辅助方法 ===
    
    def _get_section_id_from_agent(self, agent: "IAgent") -> str:
        """
        从 Agent 提取章节 ID
        
        Args:
            agent: Agent 实例
            
        Returns:
            章节ID
        """
        # 优先使用 section_id 属性
        if hasattr(agent, 'section_id') and agent.section_id:
            return agent.section_id
        
        # 回退到 agent_id
        return agent.agent_id
    
    def _get_section_id_from_agent_id(self, agent_id: str) -> str:
        """
        从 agent_id 提取章节 ID
        
        Args:
            agent_id: Agent ID
            
        Returns:
            章节ID
        """
        # agent_id 格式通常是: phase_section_index
        # 例如: research_市场规模_2, synthesis_执行摘要_1
        # 我们需要提取中间的章节名
        
        parts = agent_id.split("_")
        if len(parts) >= 4 and parts[0] == "phase" and parts[-2] == "agent":
            # phase_N_agent_M 格式：无意义章节名，返回自身
            return agent_id
        if len(parts) >= 3:
            # 检查最后一部分是否是数字索引
            if parts[-1].isdigit():
                # 旧格式: research_市场规模_2 → 市场规模
                return "_".join(parts[1:-1])
            else:
                # 新格式: deep_analysis_0_市场规模 → 市场规模
                return parts[-1]
        elif len(parts) == 2:
            # 格式: type_aspect → aspect
            return parts[1]
        
        # P1修复：无法解析时返回带前缀的标识，便于追踪
        logger.warning(f"无法从agent_id提取章节ID: {agent_id}，使用原始值")
        return agent_id
    
    def _extract_quality_score(self, agent_result: Dict[str, Any]) -> float:
        """
        从 Agent 结果提取质量分数
        
        Args:
            agent_result: Agent 执行结果
            
        Returns:
            质量分数 (0-1)
        """
        # 尝试多种路径获取质量分数
        quality_score = agent_result.get("quality_score")
        
        # P1修复：添加类型守卫
        if quality_score is None:
            result_data = agent_result.get("result")
            if isinstance(result_data, dict):
                quality_score = result_data.get("quality_score")
        
        if quality_score is None:
            content_data = agent_result.get("content")
            if isinstance(content_data, dict):
                quality_score = content_data.get("quality_score")
        
        # 默认满分
        if quality_score is None:
            quality_score = 1.0
        
        # 确保在有效范围内
        try:
            score = float(quality_score)
            return max(0.0, min(1.0, score))
        except (TypeError, ValueError):
            return 1.0