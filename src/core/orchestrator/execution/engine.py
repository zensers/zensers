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
import copy
import hashlib
import json
import logging
import re
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
from src.core.orchestrator.execution.task_utils import safe_create_task
from src.core.manifest_contract import ManifestContractError
from src.core.failure_audit import FailureAudit


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
from .evidence_scope import EvidenceScope

if TYPE_CHECKING:
    from src.core.agents.base import BaseAgent
    from src.core.agents.protocol import IAgent
    from src.core.agents.agent_session import AgentSessionRegistry
    from src.core.communication import MessageBus, SharedMemory
    from src.core.content_lock import ContentLockManager  # 新增：智能路由内容锁

from src.core.content_lock import SectionState  # R-FIX-10: 用于 mark_section_state

logger = logging.getLogger(__name__)


def _canonical_runtime_section_id(section_id: Any) -> str:
    """Collapse legacy ``section_N_<aspect>`` IDs to ``section_N``."""
    value = str(section_id or "").strip()
    match = re.match(r"^(section|synthesis)_(\d+)(?:_|$)", value)
    return f"{match.group(1)}_{match.group(2)}" if match else value


def _evidence_record_key(record: Any, kind: str) -> str:
    """Stable identity for evidence carried forward between batches."""
    if not isinstance(record, dict):
        return f"{kind}:value:{str(record)}"
    for field in ("evidence_id", "provenance_id", "data_id"):
        stable_id = str(record.get(field) or "").strip()
        if stable_id:
            # Stable evidence identity must survive later enrichment of value,
            # scope, or source URL across collection batches.
            payload = f"{field}:{stable_id}"
            return f"{kind}:identity:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"
    url = str(record.get("url") or record.get("source_url") or "").strip()
    title = str(record.get("title") or record.get("name") or "").strip()
    content = record.get("content", record.get("data", ""))
    try:
        content_text = json.dumps(content, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        content_text = str(content)
    payload = f"{url}\x1f{title}\x1f{content_text}"
    return f"{kind}:hash:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


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
    CALIBRATION = "calibration"               # M5-b: 数据校准
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
        search_gateway: Any = None,
    ):
        self.config = config
        self.message_bus = message_bus
        self._shared_memory = shared_memory
        self.shared_memory = shared_memory
        self.search_gateway = search_gateway
        
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
            # Long-running research must be governed by session/task control,
            # not an implicit background timeout.
            default_timeout=None,
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
                DataCollectionQualityChecker,
                AnalysisQualityChecker,
                ReportQualityChecker,
            )
            from src.config.settings import settings
            
            # 质量元数据提取器
            self.metadata_extractor = QualityMetadataExtractor()
            
            # 反馈执行器（已废弃，保留为None）
            self.quality_executor = None
            
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
        
        aspect_mapping = {
            "summary": "执行摘要", "executivesummary": "执行摘要",
            "execsummary": "执行摘要", "conclusion": "研究结论",
            "findings": "研究结论", "recommendation": "建议",
        }
        
        if len(parts) >= 4 and parts[-2] == "agent" and parts[0] in ("phase", "batch"):
            return agent_id
        
        last = parts[-1]
        is_index = last.isdigit() or (
            len(last) >= 6
            and all(c in '0123456789abcdef' for c in last.lower())
        )
        
        if is_index and len(parts) >= 3:
            middle = "_".join(parts[1:-1])
            if middle.lower() in aspect_mapping:
                return aspect_mapping[middle.lower()]
            return middle
        
        if parts[0] in ("inject", "replan") and len(parts) >= 3:
            middle = "_".join(parts[1:-1])
            if middle.lower() in aspect_mapping:
                return aspect_mapping[middle.lower()]
            return middle
        
        if last.lower() in aspect_mapping:
            return aspect_mapping[last.lower()]
        return last
    
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

        # When the router provides a frozen manifest, it is the only source
        # of reportable chapter identity and order.  Results are joined by
        # exact section_id; missing results remain visible as failed chapter
        # records so the report writer and L0 can distinguish omission from
        # successful delivery.
        section_manifest = requirement.get("section_manifest") or []
        if isinstance(section_manifest, list) and section_manifest:
            manifest_ids = [
                _canonical_runtime_section_id(item.get("section_id"))
                for item in section_manifest
                if isinstance(item, dict) and item.get("section_id")
            ]
            duplicate_manifest_ids = {
                section_id for section_id in manifest_ids
                if manifest_ids.count(section_id) > 1
            }
            if duplicate_manifest_ids:
                raise ManifestContractError(
                    "duplicate_section_id", {"ids": sorted(duplicate_manifest_ids)}
                )
            planned_ids = set(manifest_ids)
            results_by_section = {}
            for result in previous_results:
                if not isinstance(result, dict):
                    continue
                result_section_id = result.get("section_id") or result.get("_section_id")
                if not result_section_id:
                    continue
                result_section_id = _canonical_runtime_section_id(result_section_id)
                if result_section_id not in planned_ids:
                    raise ManifestContractError(
                        "unknown_section_id", {"ids": [result_section_id]}
                    )
                # First result wins only for duplicate successful writes; a
                # later non-empty result may replace an empty/failed record.
                content = result.get("content") or result.get("result") or result.get("output") or ""
                if isinstance(content, dict):
                    content = str(content)
                old = results_by_section.get(result_section_id)
                if old is None or (not old.get("content") and content):
                    results_by_section[result_section_id] = {
                        "result": result,
                        "content": content if isinstance(content, str) else "",
                    }
                if isinstance(result.get("data_points"), list):
                    all_data_points.extend(result["data_points"])
                if isinstance(result.get("sources"), list):
                    all_sources.extend(result["sources"])

            manifest_body_sections = []
            manifest_exec_summary = None
            manifest_conclusion = None
            manifest_missing = []
            for item in section_manifest:
                if not isinstance(item, dict):
                    continue
                section_id = _canonical_runtime_section_id(item.get("section_id", ""))
                if not section_id:
                    continue
                title = str(item.get("title") or item.get("display_title") or section_id)
                role = str(item.get("role") or "analysis").lower()
                joined = results_by_section.get(section_id)
                content = joined.get("content", "") if joined else ""
                source_result = joined.get("result", {}) if joined else {}
                section_record = {
                    "id": section_id,
                    "section_id": section_id,
                    "title": title,
                    "content": content,
                    "type": role,
                    "status": "ready" if content.strip() and source_result.get("success", True) else "failed",
                    "error": "" if content.strip() else "planned_section_result_missing",
                    "required_metrics": item.get("required_metrics", []),
                }
                if not content.strip():
                    manifest_missing.append(section_id)
                output_slot = str(item.get("output_slot") or "").strip().lower()
                if output_slot not in {"body", "exec_summary", "conclusion"}:
                    # Compatibility for manifests created before output_slot;
                    # identity remains exact section_id even in this fallback.
                    title_lower = title.lower()
                    if role in {"summary", "executive_summary"} or "摘要" in title or "summary" in title_lower:
                        output_slot = "exec_summary"
                    elif role == "conclusion" or "结论" in title or "conclusion" in title_lower or "总结" in title:
                        output_slot = "conclusion"
                    else:
                        output_slot = "body"
                if output_slot == "exec_summary":
                    manifest_exec_summary = content or manifest_exec_summary
                elif output_slot == "conclusion":
                    manifest_conclusion = content or manifest_conclusion
                else:
                    # Every planned body chapter remains visible.  A failed
                    # result is represented by status/error, never removed
                    # from the report input by a truthiness filter.
                    manifest_body_sections.append(section_record)

            logger.info(
                "[Report] Manifest assembly: planned=%d actual=%d missing=%d",
                len([i for i in section_manifest if isinstance(i, dict) and i.get("section_id")]),
                len(results_by_section), len(manifest_missing),
            )
            return {
                "action": "produce_document",
                "task_id": requirement.get("task_id", f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"),
                "topic": requirement.get("topic"),
                "sections": manifest_body_sections,
                "exec_summary": manifest_exec_summary,
                "conclusion": manifest_conclusion,
                "section_manifest": section_manifest,
                "missing_section_ids": manifest_missing,
                "output_format": requirement.get("output_format", "docx"),
                "research_result": {
                    "topic": requirement.get("topic"),
                    "sections": manifest_body_sections,
                    "data_points": all_data_points,
                    "sources": all_sources,
                    "section_manifest": section_manifest,
                    "missing_section_ids": manifest_missing,
                },
            }
        
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
            if isinstance(content, dict):
                content = str(content)
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

        _memory_scope_token = None
        _subscribed_data_handlers = []

        # Keep one authoritative semantic mapping for boundary checks in the
        # scheduler path. Scheduler agent ids (for example phase_1_agent_0)
        # are opaque; deriving an aspect from them is not reliable.
        agent_aspect_map = {}
        agent_section_map = {}
        _requirement_aspects = requirement.get("aspects", []) if isinstance(requirement, dict) else []
        _dependent_names = {
            "summary", "conclusion", "executive_summary", "key_insights",
            "research_summary", "research_conclusion", "synthesis",
            "key_findings", "insights", "synthesis_analysis", "core_findings",
            "key_discoveries", "strategic_intent", "strategic intent",
            "战略意图", "战略意图推断", "执行摘要", "摘要", "结论",
        }
        _data_aspects = [
            str(_aspect) for _aspect in _requirement_aspects
            if str(_aspect).strip().lower() not in _dependent_names
        ]
        _aspect_section_map = {
            aspect: f"section_{index}"
            for index, aspect in enumerate(_data_aspects)
        }
        _synthesis_index = 0
        for _agent in agents:
            _config = getattr(_agent, "config", {}) or {}
            _context = getattr(_agent, "_context", {}) or {}
            if not _context:
                _context = _config.get("context", {}) if isinstance(_config, dict) else {}
            _section_ids = list(getattr(_agent, "section_ids", []) or [])
            _metadata = (_config.get("section_metadata", {})
                         if isinstance(_config, dict) else {}) or {}
            _explicit_section_id = (
                _context.get("section_id")
                or getattr(_agent, "section_id", "")
                or (_section_ids[0] if _section_ids else "")
                or _metadata.get("section_id", "")
            )
            _aspect = (
                _context.get("aspect")
                or _metadata.get("title")
                or getattr(_agent, "aspect", "")
                or _explicit_section_id
            )
            if (not _aspect or _aspect == _agent.agent_id or
                    (_agent.agent_id.startswith("phase_") and "_agent_" in _agent.agent_id)):
                try:
                    _agent_index = int(_agent.agent_id.rsplit("_", 1)[-1])
                except (ValueError, AttributeError):
                    _agent_index = -1
                if 0 <= _agent_index < len(_requirement_aspects):
                    _aspect = _requirement_aspects[_agent_index]
            if _aspect:
                agent_aspect_map[_agent.agent_id] = _aspect
                if _explicit_section_id:
                    agent_section_map[_agent.agent_id] = _canonical_runtime_section_id(_explicit_section_id)
                elif str(_aspect).strip().lower() in _dependent_names:
                    agent_section_map[_agent.agent_id] = f"synthesis_{_synthesis_index}"
                    _synthesis_index += 1
                else:
                    agent_section_map[_agent.agent_id] = _aspect_section_map.get(
                        str(_aspect), f"section_{len(agent_section_map)}"
                    )
        self._agent_aspect_map = agent_aspect_map
        self._agent_section_map = agent_section_map
        
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
            
            # Bind the execution scope before subscribing to the shared data
            # bus so concurrent runs receive only their own canonical events.
            from src.core.communication import set_memory_scope
            _memory_scope = requirement.get("session_id") or requirement.get("task_id", "")
            _memory_scope_token = set_memory_scope(_memory_scope)

            # B-FIX-4: subscribe to MessageBus data events
            from src.core.orchestrator.execution.data_collector import DataCollector
            self._data_collector = DataCollector(scope=_memory_scope)
            if self.message_bus:
                _canonical_handler = self._data_collector.on_canonical_updated
                _conflict_handler = self._data_collector.on_conflict_detected
                await self.message_bus.subscribe("data.canonical.updated", _canonical_handler)
                _subscribed_data_handlers.append(("data.canonical.updated", _canonical_handler))
                await self.message_bus.subscribe("data.conflict.detected", _conflict_handler)
                _subscribed_data_handlers.append(("data.conflict.detected", _conflict_handler))
            
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
            # Bind canonical SharedMemory operations to this research session;
            # the same Engine may execute multiple sessions concurrently.
            from src.core.data.canonical_registry import CanonicalDataRegistry
            self._canonical_registry = CanonicalDataRegistry()
            self._active_canonical_data: Dict = {}
            self._section_data_specs = (getattr(decomposition_plan, 'section_data_specs', []) or []) if decomposition_plan else []
            if self._section_data_specs and isinstance(self._section_data_specs[0], dict):
                from src.core.decomposition.strategies import _convert_specs_from_dicts
                self._section_data_specs = _convert_specs_from_dicts(self._section_data_specs)
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
            self._agent_id_to_section_id: Dict[str, str] = {}
            for _a in agents:
                _sid = self._get_section_id_from_agent(_a)
                if _sid:
                    _section_to_agent[_sid] = _a
                    self._agent_id_to_section_id[_a.agent_id] = _sid
            
            _esid = requirement.get("session_id") or requirement.get("task_id", "")
            _total_batches = len(execution_batches)

            for batch_index, batch_agent_ids in enumerate(execution_batches):
                logger.info(f"[批次{batch_index + 1}/{len(execution_batches)}] 执行: {batch_agent_ids}")

                _batch_progress = 0.2 + (batch_index / max(_total_batches, 1)) * 0.5
                if _esid:
                    try:
                        from src.core.progress_streamer import update_progress as _up
                        _up(_esid, _batch_progress, phase_id="execution",
                            message=f"Executing batch {batch_index+1}/{_total_batches}...")
                    except Exception:
                        pass

                for _aid in batch_agent_ids:
                    _a = scheduler.get_agent_by_id(_aid)
                    if _a and _esid:
                        try:
                            from src.core.session_streamer import SessionStreamer
                            _aname = _a.config.get("context", {}).get("aspect", "") or _a.agent_type
                            SessionStreamer.push_agent_message(_esid, {
                                "agent_id": _a.agent_id,
                                "agent_name": _aname,
                                "action": "analyzing",
                                "content": f"Starting {_aname}...",
                            })
                        except Exception:
                            pass
                
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
                            _loaded = AgentSessionRegistry.load(_reg_path)
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
                            if isinstance(content, dict):
                                content = str(content)
                            logger.info(
                                f"[批次{batch_index + 1}] Agent {agent_id} aspect '{agent_aspect}' "
                                f"cached, skipping execution ({len(content)} chars)"
                            )
                            section_id = _canonical_runtime_section_id(self._get_section_id_from_agent(agent))
                            completed_results.append({
                                "success": True,
                                "agent_id": agent_id,
                                "section_id": section_id,
                                "_section_id": section_id,  # R-FIX-13
                                "content": content[:50000],
                                "data_points": cached_result.get("data_points", []),
                                "sources": cached_result.get("sources", []),
                                "charts": cached_result.get("charts", []),
                                "cached": True,
                            })
                            continue
                        # 检查内容锁（如果启用）
                        if content_lock is not None:
                            section_id = _canonical_runtime_section_id(self._get_section_id_from_agent(agent))
                            if not section_id and hasattr(self, '_agent_id_to_section_id'):
                                section_id = self._agent_id_to_section_id.get(agent_id, "")
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
                                    section_id = _canonical_runtime_section_id(self._get_section_id_from_agent(agent))
                                    if not section_id and hasattr(self, '_agent_id_to_section_id'):
                                        section_id = self._agent_id_to_section_id.get(agent_id, "")
                                    agent_result["_section_id"] = section_id
                                    _cat = agent.config.get("category", "") if agent else ""
                                    if not _cat and agent:
                                        _aid = agent.agent_id or ""
                                        if _aid.startswith("phase_1_"):
                                            _cat = "research"
                                        elif _aid.startswith("phase_2_"):
                                            _cat = "analysis"
                                    _is_dc_cache = (
                                        _cat == "research"
                                        or _cat == "data_collection"
                                        or (not _cat and agent and not agent_result.get("content") and agent_result.get("data_points"))
                                    )
                                    if _is_dc_cache:
                                        content_lock.mark_section_state(section_id, SectionState.DATA_COLLECTED, 1.0)
                                    else:
                                        content_lock.mark_completed(section_id, 1.0)
                        all_results.extend(batch_results)
                        result.stage_results[f"batch_{batch_index + 1}"] = batch_results
                        
                        # CR-FIX-1: cache hit must also pass quality check
                        if self.enable_quality_control and batch_agent_originals:
                            cache_checker = self._select_checker_for_batch(
                                batch_results, batch_agent_originals
                            )
                            if cache_checker:
                                import datetime as _datetime
                                _cp = []
                                for r in batch_results:
                                    if not r.get("success"):
                                        continue
                                    _c = r.get("content","") or r.get("result","")
                                    if isinstance(_c, dict):
                                        _c = str(_c)
                                    if _c:
                                        _cp.append(str(_c))
                                _combined = "\n\n".join(_cp)
                                _sources = []
                                _dps = []
                                for r in batch_results:
                                    if r.get("success"):
                                        _sources.extend(r.get("sources",[]))
                                        _dps.extend(r.get("data_points",[]))
                                _cd = {"content":_combined,"sources":_sources,"data_points":_dps,
                                       "quality_metadata":{"data_volume":len(_dps)or len(_sources),
                                                           "sources":_sources,"quality_score":50.0}}
                                _qr = await asyncio.to_thread(
                                    cache_checker.check,
                                    _cd,
                                    {"batch_index": batch_index},
                                )
                                if not _qr.passed:
                                    logger.warning(f"Cached results failed QC for batch {batch_index+1}, re-executing")
                                    batch_results = await self._execute_agents_batch(
                                        batch_agent_originals, requirement, all_results,
                                        scheduler, f"batch_{batch_index+1}_cache_rerun"
                                    )
                                    for agent_result in batch_results:
                                        agent_id = agent_result.get("agent_id", "")
                                        agent = scheduler.get_agent_by_id(agent_id)
                                        section_id = _canonical_runtime_section_id(
                                            self._get_section_id_from_agent(agent)
                                            if agent else self._get_section_id_from_agent_id(agent_id)
                                        )
                                        if not section_id or section_id == agent_id or (len(section_id) < 5 and "_agent_" in section_id):
                                            _aspects = requirement.get("aspects", []) if isinstance(requirement, dict) else []
                                            if _aspects and "_agent_" in agent_id:
                                                try:
                                                    _idx = int(agent_id.split("_agent_")[-1])
                                                    if 0 <= _idx < len(_aspects):
                                                        section_id = f"section_{_idx}"
                                                except (ValueError, IndexError):
                                                    pass
                                        agent_result["section_id"] = section_id
                                        agent_result["_section_id"] = section_id  # R-FIX-13
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

                for _ar in batch_results:
                    if _ar.get("success") and _esid:
                        _arid = _ar.get("agent_id", "")
                        _aobj = scheduler.get_agent_by_id(_arid)
                        _arname = (_aobj.config.get("context", {}).get("aspect", "") or _aobj.agent_type) if _aobj else _arid
                        try:
                            from src.core.session_streamer import SessionStreamer
                            SessionStreamer.push_agent_message(_esid, {
                                "agent_id": _arid,
                                "agent_name": _arname,
                                "action": "completed",
                                "content": f"{_arname} completed.",
                            })
                        except Exception:
                            pass
                
                # 更新调度状态和内容锁
                for agent_result in batch_results:
                    agent_id = agent_result.get("agent_id", "")
                    # 注入 section_id 供下游聚合 key 映射使用
                    agent = scheduler.get_agent_by_id(agent_id)
                    section_id = _canonical_runtime_section_id(
                        self._get_section_id_from_agent(agent)
                        if agent else self._get_section_id_from_agent_id(agent_id)
                    )
                    # Fallback: when section_id is empty or meaningless (e.g. "2_agent" from phase_2_agent_0),
                    # use aspect list index mapping: phase_1/2_agent_{i} -> aspects[i]
                    if not section_id or section_id == agent_id or (len(section_id) < 5 and "_agent_" in section_id):
                        _aspects = requirement.get("aspects", []) if isinstance(requirement, dict) else []
                        if _aspects and "_agent_" in agent_id:
                            try:
                                _idx = int(agent_id.split("_agent_")[-1])
                                if 0 <= _idx < len(_aspects):
                                    section_id = f"section_{_idx}"
                            except (ValueError, IndexError):
                                pass
                    agent_result["section_id"] = section_id
                    agent_result["_section_id"] = section_id  # R-FIX-13
                    if agent_result.get("success"):
                        scheduler.mark_completed(agent_id, agent_result)
                        if content_lock is not None:
                            quality_score = self._extract_quality_score(agent_result)
                            # R-FIX-10: 区分 data_collection 和 analysis 的完成状态
                            _category = (agent_result.get("category", "")
                                         or (agent.config.get("category", "") if agent else ""))
                            if not _category and agent:
                                _aid = agent.agent_id or ""
                                if _aid.startswith("phase_1_"):
                                    _category = "research"
                                elif _aid.startswith("phase_2_"):
                                    _category = "analysis"
                            # R-FIX-10b: data_collection agents (no content, only data_points)
                            # should always mark as DATA_COLLECTED, never COMPLETED
                            _is_dc = (
                                _category == "research"
                                or _category == "data_collection"
                                or (not _category and agent and not agent_result.get("content") and agent_result.get("data_points"))
                            )
                            if _is_dc:
                                content_lock.mark_section_state(section_id, SectionState.DATA_COLLECTED, quality_score)
                            else:
                                unlocked_sections = content_lock.mark_completed(section_id, quality_score)
                                if unlocked_sections:
                                    logger.info(f"[内容锁] 章节 {section_id} 完成，解锁章节: {unlocked_sections}")
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
                                        period=str(_ent.get("period", "") or ""),
                                        geographic_scope=str(_ent.get("geographic_scope", "") or ""),
                                        population=str(_ent.get("population", "") or _ent.get("statistical_object", "") or ""),
                                        statistical_object=str(_ent.get("statistical_object", "") or ""),
                                        source_url=str(_ent.get("source_url", "") or _ent.get("url", "") or ""),
                                        evidence_id=str(_ent.get("evidence_id", "") or ""),
                                        provenance_id=str(_ent.get("provenance_id", "") or ""),
                                    )
                                    await self._canonical_registry.register(_ce)
                        self._active_canonical_data = {
                            k: {
                                "value": v.value, "unit": v.unit, "caliber": v.caliber,
                                "source": v.source, "year": v.year,
                                "period": v.period,
                                "geographic_scope": v.geographic_scope,
                                "population": v.population or v.statistical_object,
                                "source_url": v.source_url,
                                "evidence_id": v.evidence_id,
                                "provenance_id": v.provenance_id,
                            }
                            for k, v in self._canonical_registry.get_all().items()
                        }
                        # Broadcast to SharedMemory for real-time agent access
                        if self._shared_memory and hasattr(self._shared_memory, 'set'):
                            self._shared_memory.set("_canonical_registry", self._active_canonical_data)
                    except Exception as _sce:
                        logger.warning(f"S-FIX-2: canonical data extraction failed: {_sce}")
                
                # === Phase C/D: 对账 + 补充搜索（仅 DATA_COLLECTION batch 完成后） ===
                _batch_is_dc = any(
                    (scheduler.get_agent_by_id(aid) and 
                     getattr(scheduler.get_agent_by_id(aid).config if scheduler.get_agent_by_id(aid) else {}, 'get', lambda k, d=None: d)('category', '') == 'research')
                    for aid in batch_agent_ids
                )
                if _batch_is_dc and hasattr(self, '_section_data_specs') and self._section_data_specs:
                    try:
                        supplement_results = await self._supplement_missing_data(batch_results, requirement)
                        if supplement_results:
                            for need, supp in supplement_results.items():
                                for _res in batch_results:
                                    agent_id = _res.get("agent_id", "")
                                    spec = self._get_section_spec_by_agent_id(agent_id)
                                    if spec and need in spec.all_data_needs:
                                        _res.setdefault("data_points", []).extend(supp.get("data_points", []))
                                        _res.setdefault("sources", []).extend(supp.get("sources", []))
                            logger.info(f"[Phase D] supplemented {len(supplement_results)} missing data needs")
                    except Exception as _supp_err:
                        logger.warning(f"[Phase D] supplement search failed: {_supp_err}")
                
                # Output structure validation (ported from PhaseOrchestrator SchemaValidator)
                # Ensures each agent result has the minimum required fields
                for agent_result in batch_results:
                    self._validate_agent_output(agent_result, batch_index)
                
                # Basic quality check: success rate and data volume
                batch_quality = self._check_stage_quality(batch_results, f"batch_{batch_index + 1}")
                
                # Specialized quality checkers: route to appropriate checker based on batch content
                if self.enable_quality_control and batch_quality:
                    try:
                        checker = self._select_checker_for_batch(batch_results, batch_agents)
                        if checker:
                            quality_context = {
                                "batch_index": batch_index,
                                "total_batches": len(execution_batches),
                                "topic": requirement.get("topic", ""),
                            }
                            # Build check_data in the format checkers expect
                            # (AnalysisQualityChecker reads data["content"],
                            #  DataCollectionQualityChecker reads data["quality_metadata"])
                            # R1-FIX: content/result may be dict (Phase1 metadata),
                            # ensure str before join to avoid "expected str instance, dict found"
                            _content_parts = []
                            for r in batch_results:
                                if not r.get("success"):
                                    continue
                                _c = r.get("content", "") or r.get("result", "")
                                if isinstance(_c, dict):
                                    _c = str(_c)
                                if _c:
                                    _content_parts.append(str(_c))
                            combined_content = "\n\n".join(_content_parts)
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
                            # Checkers may call the synchronous LLM bridge.
                            # Keep that work off the event loop so agent tasks,
                            # heartbeats and cancellation remain responsive.
                            quality_result = await asyncio.to_thread(
                                checker.check,
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
                                # Unified retry: handle infrastructure + quality failures
                                _max_retries = getattr(self.config, 'max_retries', 1)
                                # A calibration-only batch cannot improve when
                                # upstream produced no evidence. Retrying the
                                # same empty input only adds LLM latency and
                                # can consume the whole E2E timeout budget.
                                _is_calibration_only = bool(batch_agents) and all(
                                    self.classify_agent(a) == AgentCategory.CALIBRATION
                                    for a in batch_agents
                                )
                                _is_data_collection_only = bool(batch_agents) and all(
                                    self.classify_agent(a) == AgentCategory.DATA_COLLECTION
                                    for a in batch_agents
                                )
                                _is_phase1_evidence = bool(batch_agents) and all(
                                    str(getattr(a, "agent_id", "")).startswith("phase_1_")
                                    for a in batch_agents
                                ) and bool(all_data_points or all_sources)
                                if _is_calibration_only and not all_data_points and not all_sources:
                                    _max_retries = 0
                                # Collection quality is evaluated after the
                                # search result is already available.  When a
                                # collection batch has evidence, re-running
                                # the same Agent only repeats search and can
                                # block calibration/report stages.  Preserve
                                # the evidence and continue; retry only when
                                # the collection produced no evidence at all.
                                if _is_data_collection_only and (all_data_points or all_sources):
                                    _max_retries = 0
                                if _is_phase1_evidence:
                                    _max_retries = 0
                                _retry_count = 0
                                _current_batch = batch_results
                                _current_agents = list(batch_agents)
                                while _retry_count < _max_retries:
                                    _retry_count += 1
                                    _failed = self._identify_failed_agents(_current_batch, checker, _current_agents, quality_context)
                                    if not _failed:
                                        break
                                    logger.info(
                                        f"Unified retry {_retry_count}/{_max_retries} for batch {batch_index+1}: "
                                        f"{len(_failed)} agents failed"
                                    )
                                    for _fa in _failed:
                                        if hasattr(_fa["agent"], 'reset'):
                                            await _fa["agent"].reset()
                                    self._inject_retry_feedback(_failed, _retry_count)
                                    _retry_agents = [_fa["agent"] for _fa in _failed]
                                    _retry_results = await self._execute_agents_batch(
                                        _retry_agents, requirement, all_results, scheduler,
                                        f"batch_{batch_index+1}_retry{_retry_count}",
                                        # Quality retries are still Agent work;
                                        # never inject the historical 120s
                                        # per-Agent deadline here.
                                        timeout_override=None,
                                    )
                                    _current_batch = self._merge_retry_results(_current_batch, _retry_results)
                                else:
                                    logger.warning(
                                        f"Unified retry exhausted for batch {batch_index+1}, "
                                        f"continuing: {error_msg}"
                                    )
                                    # I2: 低质数据静默入库（有日志无状态传播）
                                    FailureAudit.record(
                                        stage="engine.batch",
                                        subject_id=f"batch_{batch_index + 1}",
                                        action="continue_degraded",
                                        reason="quality retry exhausted",
                                        task_id=str(requirement.get("task_id") or requirement.get("session_id") or ""),
                                    )
                                # Always apply merged results whether retry succeeded or exhausted
                                batch_results = _current_batch
                            else:
                                logger.info(f"Quality check PASSED for batch {batch_index + 1}: score={quality_result.score:.1f}")
                    except Exception as qe:
                        logger.warning(f"Quality checker exception for batch {batch_index + 1}: {qe}")
                        # I2: 质检器异常吞掉后批次免检放行（零留痕）
                        FailureAudit.record(
                            stage="engine.batch",
                            subject_id=f"batch_{batch_index + 1}",
                            action="skip_quality_check",
                            reason=f"checker error: {qe}",
                            severity="blocking",
                            task_id=str(requirement.get("task_id") or requirement.get("session_id") or ""),
                        )
                
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
                # R2-FIX: 必须在 for 循环内（indent 16），否则只保存最后一个 batch 的结果
                all_results.extend(batch_results)
                result.stage_results[f"batch_{batch_index + 1}"] = batch_results
                
                # B-FIX-6: 跨批次冲突告警 + 注入下游 context (defect 4.3)
                if hasattr(self, '_data_collector') and self._data_collector:
                    _dc_conflicts = self._data_collector.get_conflicts()
                    if _dc_conflicts:
                        logger.warning(
                            f"Cross-batch data conflicts: {len(_dc_conflicts)} conflicts detected"
                        )
                        for _c in _dc_conflicts[:10]:
                            logger.warning(
                                f"  Conflict: metric={_c.get('metric','?')}, "
                                f"values={_c.get('values',[])}, sources={_c.get('sources',[])}"
                            )
                        _conflict_summary = "; ".join(
                            f"{_c.get('metric','?')}: {len(_c.get('values',[]))} versions"
                            for _c in _dc_conflicts
                        )
                        if self._shared_memory and hasattr(self._shared_memory, 'write_canonical'):
                            await self._shared_memory.write_canonical(
                                metric="cross_batch_conflicts",
                                value={"count": len(_dc_conflicts), "summary": _conflict_summary},
                                caliber="llm_inference",
                                source="reconciliation",
                                publisher="engine",
                            )
                
                # C-FIX-1: execute newly unlocked agents at batch end
                if pending_unlocked and result.status != "failed":
                    logger.info(f"Re-executing {len(pending_unlocked)} newly unlocked agents")
                    _unlock_results = await self._execute_agents_batch(
                        pending_unlocked, requirement, all_results,
                        scheduler, f"batch_{batch_index+1}_unlock"
                    )
                    batch_results.extend(_unlock_results)
                    all_results.extend(_unlock_results)
                    # E-P1-9 FIX: inject section_id for unlocked agents
                    _ul_aspects = requirement.get("aspects", []) if isinstance(requirement, dict) else []
                    for _ur in _unlock_results:
                        _uaid = _ur.get("agent_id", "")
                        if _ur.get("section_id"):
                            continue
                        _uagent = scheduler.get_agent_by_id(_uaid)
                        _usid = self._get_section_id_from_agent(_uagent) if _uagent else self._get_section_id_from_agent_id(_uaid)
                        if not _usid or _usid == _uaid or (len(_usid) < 5 and "_agent_" in _usid):
                            if _ul_aspects and "_agent_" in _uaid:
                                try:
                                    _uidx = int(_uaid.split("_agent_")[-1])
                                    if 0 <= _uidx < len(_ul_aspects):
                                        _usid = str(_ul_aspects[_uidx])
                                except (ValueError, IndexError):
                                    pass
                        _ur["section_id"] = _usid
                        _ur["_section_id"] = _usid
                    pending_unlocked.clear()
                
                # M5-a: Enhanced consistency gate — fixes content + data_points via MetricExtractor
                if result.status != "failed" and self.enable_quality_control and all_results and self._active_canonical_data:
                    try:
                        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical
                        _target_cur = getattr(self, '_target_currency', 'CNY')
                        _gate_result = fix_content_from_canonical(
                            all_results, self._active_canonical_data, _target_cur
                        )
                        all_results = _gate_result["all_results"]
                        _cal_report = _gate_result["calibration_report"]
                        if _cal_report["auto_fixed"] or _cal_report["currency_converted"]:
                            logger.info(
                                f"M5-a calibration gate: {len(_cal_report['auto_fixed'])} content fixes, "
                                f"{len(_cal_report['currency_converted'])} currency conversions, "
                                f"{_cal_report['total_metrics_checked']} metrics checked"
                            )
                    except ImportError:
                        pass
            
            # 构建最终结果（若 QC 在循环内已置为 failed，不再覆盖）
            if result.status != "failed":
                result.status = "completed"
                result.final_result = self._aggregate_results(all_results)
                result.stats = self._build_stats()
                # B-FIX-6: 消费 metric_conflict_details（L3 对账结果）(defect 4.3)
                if isinstance(result.final_result, dict):
                    _agg_stats = result.final_result.get("stats", {})
                    _mc_details = _agg_stats.get("metric_conflict_details", [])
                    if _mc_details:
                        logger.warning(
                            f"Metric-level conflicts: {len(_mc_details)} across agents"
                        )
                        for _mcd in _mc_details[:5]:
                            logger.warning(
                                f"  {_mcd['key']}({_mcd['year']}): "
                                f"values={_mcd['values']}, agents={_mcd['sources']}"
                            )
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
            if self.message_bus:
                for _topic, _handler in _subscribed_data_handlers:
                    try:
                        await self.message_bus.unsubscribe(_topic, _handler)
                    except Exception as _unsubscribe_error:
                        logger.warning(
                            "Failed to unsubscribe execution data handler (%s): %s",
                            _topic,
                            _unsubscribe_error,
                        )
            if _memory_scope_token is not None:
                from src.core.communication import reset_memory_scope
                reset_memory_scope(_memory_scope_token)

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
        timeout_override: Optional[float] = None,
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
            timeout_override=timeout_override,
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
    
    def _select_checker_for_batch(
        self,
        batch_results: List[Dict[str, Any]],
        batch_agents: Optional[List["IAgent"]] = None,
    ) -> Optional[Any]:
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
        
        # Prefer the scheduler's explicit Agent category over result shape.
        # A data-collection Agent may intentionally return an analysis-shaped
        # narrative together with raw data; inferring the phase from content
        # would route it to semantic analysis QC and trigger pointless retries.
        if batch_agents:
            # The decomposition plan historically labels phase_1 as
            # ``analysis`` even though it performs search and emits raw
            # evidence. Route evidence-producing phase_1 batches to data QC;
            # otherwise semantic QC retries the same search agent and delays
            # downstream calibration.
            _phase1_evidence_agents = all(
                str(getattr(agent, "agent_id", "")).startswith("phase_1_")
                for agent in batch_agents
            ) and any(
                r.get("data_points") or r.get("sources")
                for r in batch_results if r.get("success")
            )
            if _phase1_evidence_agents:
                return self.data_checker

            categories = {self.classify_agent(agent) for agent in batch_agents}
            if categories and categories <= {
                AgentCategory.DATA_COLLECTION,
            }:
                return self.data_checker
            if categories and categories <= {
                AgentCategory.REPORT_GENERATION,
                AgentCategory.DOCUMENT_GENERATION,
            }:
                return self.report_checker

        # Count result types to infer the phase only for legacy callers that do
        # not provide the scheduler's Agent objects.
        has_data_points = any(r.get("data_points") for r in batch_results if r.get("success"))
        has_sources = any(r.get("sources") for r in batch_results if r.get("success"))
        # R1-FIX: result may be dict (metadata), only count as content if it's a non-trivial string
        has_content = any(
            (isinstance(c, str) and len(c) > 50) or (isinstance(c, dict) and len(str(c)) > 50)
            for r in batch_results if r.get("success")
            for c in [r.get("content") or r.get("result") or ""]
        )
        has_any_content = any(
            bool(r.get("content") or r.get("result"))
            for r in batch_results if r.get("success")
        )
        has_validation = any(
            r.get("validation") for r in batch_results if r.get("success")
        )
        
        # Data collection phase: results have data_points/sources but little content
        if has_data_points and has_sources and not has_content:
            return self.data_checker
        
        # Analysis phase: results have substantial content with analysis
        if has_content or has_any_content:
            # Track B: three-layer semantic scoring (L1+L2+L3), fallback to analysis_checker
            try:
                from src.core.quality.semantic_adapter import SemanticQualityAdapter
                return SemanticQualityAdapter(
                    threshold=75.0,
                    fallback_checker=self.analysis_checker,
                )
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
        total_content = sum(
            len(str(r.get("content", "") or r.get("result", "")))
            for r in results if r.get("success")
        )
        
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
    
    async def _wait_for_completion_with_pause_check(
        self,
        task_ids: List[str],
        session_id: str,
        poll_interval: float = 2.0,
        grace_timeout: float = 30.0,
        requirement: Optional[Dict[str, Any]] = None,
        stage_name: str = "",
        agent_task_map: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        wait_for_completion 的暂停/取消感知版本。
        每 poll_interval 秒检查一次暂停/取消标志。
        检测到暂停/取消后，给正在运行的 agent grace_timeout 秒完成，
        超时后返回部分结果（已完成的agent有结果，未完成的为None）。
        """
        if not task_ids:
            return {}
        
        wait_task = safe_create_task(
            self._coordinator.wait_for_completion(task_ids),
            name="engine._wait_for_completion_with_pause_check"
        )
        
        _total_agents_in_batch = len(task_ids)
        _completed_in_batch = 0
        _checkpointed_task_ids = set()
        
        interrupted = False
        interrupted_reason = ""
        try:
            while not wait_task.done():
                if self._cancel_manager.is_cancelled(session_id):
                    logger.info(f"[CTRL] _wait_for_completion: cancelled, returning partial results immediately")
                    interrupted = True
                    interrupted_reason = "cancelled"
                    break
                if self._cancel_manager.is_paused(session_id):
                    logger.info(f"[CTRL] _wait_for_completion: paused, giving agents {grace_timeout}s to finish")
                    interrupted = True
                    interrupted_reason = "paused"
                    break
                _prev_completed = _completed_in_batch
                _completed_in_batch = sum(
                    1 for tid in task_ids
                    if self._coordinator._active_tasks.get(tid) is not None
                    and self._coordinator._active_tasks[tid].status == "completed"
                )
                # Persist each completed agent immediately.  A later agent in
                # the same batch may hang; completed evidence must still be
                # available for resume and report generation.
                if requirement:
                    for _tid in task_ids:
                        if _tid in _checkpointed_task_ids:
                            continue
                        _active = self._coordinator._active_tasks.get(_tid)
                        if _active and _active.status == "completed" and _active.result:
                            _result = dict(_active.result)
                            _result.setdefault("agent_id", (agent_task_map or {}).get(_tid, ""))
                            self._persist_agent_checkpoint(requirement, _result, stage_name)
                            _checkpointed_task_ids.add(_tid)
                if _completed_in_batch != _prev_completed and session_id and _total_agents_in_batch > 0:
                    try:
                        from src.core.progress_streamer import update_progress as _up
                        _sched = getattr(self, '_execution_scheduler', None)
                        if _sched and hasattr(_sched, 'get_execution_stats'):
                            stats = _sched.get_execution_stats()
                            total = stats.get("total", _total_agents_in_batch) or _total_agents_in_batch
                            done = stats.get("completed", _completed_in_batch) or _completed_in_batch
                        else:
                            total = _total_agents_in_batch
                            done = _completed_in_batch
                        _agent_progress = 0.2 + (done / max(total, 1)) * 0.5
                        _up(session_id, min(_agent_progress, 0.69),
                            phase_id="execution",
                            message=f"Agent {done}/{total} completed")
                    except Exception:
                        pass
                await asyncio.sleep(poll_interval)
            
            if not interrupted and wait_task.done():
                # The completion task can finish all agents between two
                # polling iterations. Flush once more before returning so a
                # fast/simultaneous batch cannot bypass agent checkpoints.
                if requirement:
                    for _tid in task_ids:
                        if _tid in _checkpointed_task_ids:
                            continue
                        _active = self._coordinator._active_tasks.get(_tid)
                        if _active and _active.status == "completed" and _active.result:
                            _result = dict(_active.result)
                            _result.setdefault("agent_id", (agent_task_map or {}).get(_tid, ""))
                            self._persist_agent_checkpoint(requirement, _result, stage_name)
                            _checkpointed_task_ids.add(_tid)
                try:
                    return wait_task.result()
                except Exception:
                    pass
            
            if interrupted:
                if interrupted_reason == "paused":
                    try:
                        await asyncio.wait_for(asyncio.shield(wait_task), timeout=grace_timeout)
                    except asyncio.TimeoutError:
                        logger.info(f"[CTRL] _wait_for_completion: grace timeout exceeded, returning partial results")
                        wait_task.cancel()
                    except Exception:
                        wait_task.cancel()
                else:
                    wait_task.cancel()
                
                if wait_task.done():
                    try:
                        return wait_task.result()
                    except Exception:
                        pass
        except asyncio.CancelledError:
            wait_task.cancel()
        
        partial_results: Dict[str, Optional[Dict[str, Any]]] = {}
        for tid in task_ids:
            active_task = self._coordinator._active_tasks.get(tid)
            if active_task:
                if active_task.result is not None:
                    partial_results[tid] = active_task.result
                elif active_task.error:
                    partial_results[tid] = {
                        "success": False,
                        "error": active_task.error,
                        "agent_id": active_task.agent.agent_id,
                    }
                else:
                    partial_results[tid] = None
            else:
                partial_results[tid] = None
        
        logger.info(
            f"[CTRL] _wait_for_completion: partial results — "
            f"completed={sum(1 for v in partial_results.values() if v is not None)}, "
            f"pending={sum(1 for v in partial_results.values() if v is None)}"
        )
        return partial_results
    
    async def _execute_batch(
        self,
        agents: List["IAgent"],
        requirement: Dict[str, Any],
        previous_results: List[Dict[str, Any]],
        scheduler: Any,
        stage_name: str = "",  # 新增：阶段名称，用于持久化记录
        timeout_override: Optional[float] = None,
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
        # === 统一查询规划（ISSUE-H: 通过 agent category 判断 DATA_COLLECTION） ===
        preloaded_data: Dict[str, List[Dict]] = {}
        _is_data_collection = any(
            getattr(getattr(a, 'config', None), 'get', lambda k, d=None: d)('category', '') == 'research'
            for a in agents
        )
        if _is_data_collection and hasattr(self, '_section_data_specs') and self._section_data_specs:
            try:
                preloaded_data = await self._unified_search(agents, requirement)
            except Exception as e:
                logger.warning(f"[_execute_batch] unified search failed: {e}")
        
        # **关键修复**：提取并合并前序结果中的数据
        # 这是数据传递链路的关键环节！
        # **重要**: 即使前序结果失败，也要提取其中已收集的数据
        aggregated_data_points = []
        aggregated_sources = []
        aggregated_content = []
        seen_data_point_keys = set()
        seen_source_keys = set()
        
        # 同时按 agent_id 索引数据点，用于后续按依赖过滤
        data_points_by_agent: Dict[str, List[Dict]] = {}
        sources_by_agent: Dict[str, List[Dict]] = {}
        
        for prev_result in previous_results:
            agent_id = prev_result.get("agent_id", "")
            
            # **修复**: 不再跳过失败的结果，而是尝试提取其中的数据
            # 失败的 Agent 可能已经收集了部分数据
            
            # 提取data_points（即使结果失败也要提取）
            if "data_points" in prev_result:
                for data_point in prev_result["data_points"] or []:
                    scoped_data_point = dict(data_point) if isinstance(data_point, dict) else data_point
                    if isinstance(scoped_data_point, dict):
                        scoped_data_point.setdefault("source_agent_id", agent_id)
                        if prev_result.get("section_id"):
                            scoped_data_point.setdefault("section_id", prev_result.get("section_id"))
                    key = _evidence_record_key(scoped_data_point, "data_point")
                    if key not in seen_data_point_keys:
                        seen_data_point_keys.add(key)
                        aggregated_data_points.append(scoped_data_point)
                    agent_points = data_points_by_agent.setdefault(agent_id, [])
                    if not any(_evidence_record_key(item, "data_point") == key for item in agent_points):
                        agent_points.append(scoped_data_point)
            
            # 提取sources（即使结果失败也要提取）
            if "sources" in prev_result:
                for source in prev_result["sources"] or []:
                    key = _evidence_record_key(source, "source")
                    if key not in seen_source_keys:
                        seen_source_keys.add(key)
                        aggregated_sources.append(source)
                    agent_sources = sources_by_agent.setdefault(agent_id, [])
                    if not any(_evidence_record_key(item, "source") == key for item in agent_sources):
                        agent_sources.append(source)
            
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
                    
        
        # 确保协调器已初始化
        assert self._coordinator is not None
        
        # 提取 session_id 用于暂停/取消检查
        _session_id_for_pause = requirement.get("session_id") or requirement.get("task_id", "")
        
        # 并行分发任务
        task_ids = []
        agent_task_map = {}
        
        for agent in agents:
            # 暂停/取消检查：在分发每个agent前检查
            if self._cancel_manager.is_cancelled(_session_id_for_pause):
                logger.info(f"[CTRL] _execute_batch: cancelled before dispatching agent {agent.agent_id}")
                break
            if self._cancel_manager.is_paused(_session_id_for_pause):
                logger.info(f"[CTRL] _execute_batch: paused before dispatching agent {agent.agent_id}, waiting...")
                pause_result = await self._cancel_manager.wait_for_resume_or_cancel(_session_id_for_pause)
                if pause_result == "cancelled":
                    logger.info(f"[CTRL] _execute_batch: cancelled while paused, skipping remaining agents")
                    break
            try:
                # **关键修复**：根据Agent类型构建不同的任务
                agent_category = self.classify_agent(agent)
                
                if agent_category in (AgentCategory.REPORT_GENERATION, AgentCategory.DOCUMENT_GENERATION):
                    # The report boundary has one assembly path.  Do not
                    # rebuild sections from agent_id here: that legacy path
                    # silently loses planned chapters and prevents the report
                    # agent from seeing the full evidence pool.
                    task = self._build_report_task(requirement, previous_results)
                    task["output_dir"] = requirement.get("output_dir")
                    task["section_manifest"] = requirement.get("section_manifest") or []
                    task["allow_supplementary_research"] = True
                    task["supplementary_search_scope"] = "missing_manifest_sections"
                    # Read-only evidence context: the writer may use any raw
                    # evidence to repair a missing planned chapter, but any
                    # produced chapter must still carry its exact section_id.
                    task["raw_data"] = list(previous_results)
                    task["raw_results"] = list(previous_results)
                    task["aggregated_content"] = list(aggregated_content)
                    task["aggregated_data_points"] = list(aggregated_data_points)
                    task["aggregated_sources"] = list(aggregated_sources)
                    task["research_result"].update({
                        "raw_data": list(previous_results),
                        "raw_results": list(previous_results),
                        "aggregated_content": list(aggregated_content),
                        "allow_supplementary_research": True,
                        "supplementary_search_scope": "missing_manifest_sections",
                    })
                    # M5-b: Inject calibration results into Report agent task
                    _calib = [r for r in previous_results if r.get("category") == "calibration" and r.get("success")]
                    if _calib:
                        _calib_data = _calib[0]
                        task["calibration_report"] = _calib_data.get("calibration_report", {})
                        task["unified_data_reference"] = _calib_data.get("unified_data_reference", {})
                        logger.info(f"[_execute_batch] Report agent: injected calibration results from {_calib[0].get('agent_id', 'unknown')}")
                    logger.info(f"[_execute_batch] 报告生成任务: planned="
                               f"{len(task.get('section_manifest') or [])}, "
                               f"sections={len(task.get('sections') or [])}, "
                               f"missing={len(task.get('missing_section_ids') or [])}, "
                               f"raw_results={len(previous_results)}")
                elif agent_category == AgentCategory.CALIBRATION:
                    task = {
                        "action": "calibration",
                        "parameters": {
                            "all_results": previous_results,
                            "canonical_data": getattr(self, '_active_canonical_data', {}),
                            "target_currency": getattr(self, '_target_currency', 'CNY'),
                        }
                    }
                    logger.info(f"[_execute_batch] calibration agent {agent.agent_id}: "
                                f"receiving {len(previous_results)} prior results, "
                                f"{len(getattr(self, '_active_canonical_data', {}))} canonical entries")
                elif agent_category == AgentCategory.SYNTHESIS:
                    # **正确修复**: 基于 scheduler 中定义的依赖关系过滤数据
                    # synthesis agent 只接收其依赖的 agent 的结果
                    
                    # Keep the stable section_id for registry/boundary identity,
                    # but use the semantic aspect from Agent context for prompts.
                    # Passing "section_6" as the aspect makes the LLM lose the
                    # actual research dimension and breaks section matching.
                    agent_context = getattr(agent, '_context', {}) or {}
                    if not agent_context:
                        _agent_config = getattr(agent, "config", {}) or {}
                        agent_context = _agent_config.get("context", {}) if isinstance(_agent_config, dict) else {}
                    target_section_id = getattr(agent, 'section_id', None) or ""
                    _agent_section_ids = list(getattr(agent, 'section_ids', []) or [])
                    _agent_config = getattr(agent, "config", {}) or {}
                    _agent_metadata = (_agent_config.get("section_metadata", {})
                                       if isinstance(_agent_config, dict) else {}) or {}
                    target_aspect = (
                        agent_context.get("aspect")
                        or _agent_metadata.get("title")
                        or target_section_id
                        or (_agent_section_ids[0] if _agent_section_ids else "")
                        or self._extract_aspect_from_agent_id(agent.agent_id)
                    )
                    
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
                        # [P0-6] Annual report document context injection
                        "document_context": "",
                        "document_tables": [],
                    }
                    
                    # [P0-6] Inject annual report data from Agent context
                    if agent_context.get("document_context"):
                        task["document_context"] = agent_context["document_context"]
                    if agent_context.get("document_tables"):
                        task["document_tables"] = agent_context["document_tables"]
                    
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
                    
                    # Use the semantic aspect for collection/analysis prompts.
                    # section_id remains an internal identity only.
                    agent_context = getattr(agent, '_context', {}) or {}
                    agent_section_id = getattr(agent, 'section_id', None) or ""
                    agent_section_ids = list(getattr(agent, 'section_ids', []) or [])
                    agent_config = getattr(agent, 'config', {}) or {}
                    agent_metadata = (agent_config.get('section_metadata', {})
                                      if isinstance(agent_config, dict) else {}) or {}
                    agent_aspect = (
                        agent_context.get("aspect")
                        or agent_metadata.get("title")
                        or agent_section_id
                        or (agent_section_ids[0] if agent_section_ids else "")
                        or self._extract_aspect_from_agent_id(agent.agent_id)
                    )
                    if (agent_aspect == agent.agent_id or
                            (agent.agent_id.startswith("phase_") and "_agent_" in agent.agent_id)):
                        try:
                            _agent_index = int(agent.agent_id.rsplit("_", 1)[-1])
                        except (ValueError, AttributeError):
                            _agent_index = -1
                        _requirement_aspects = requirement.get("aspects", []) if isinstance(requirement, dict) else []
                        if 0 <= _agent_index < len(_requirement_aspects):
                            agent_aspect = _requirement_aspects[_agent_index]
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
                        # The boundary resolver expects agent -> semantic
                        # aspect, while section identity is used separately
                        # for persistence/report joins.  Pass the semantic
                        # map here; the section map must not be substituted.
                        agent_section_map=getattr(self, "_agent_aspect_map", {}),
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
                        # [P0-6] Annual report document context injection
                        "document_context": "",
                        "document_tables": [],
                    }

                    if agent_category == AgentCategory.ANALYSIS:
                        analysis_section_id = _canonical_runtime_section_id(
                            getattr(self, "_agent_section_map", {}).get(agent.agent_id)
                            or getattr(agent, "section_id", "")
                        )
                        section_spec = self._get_section_spec_map().get(analysis_section_id)
                        required_metrics = set(section_spec.all_data_needs) if section_spec else set()
                        evidence_scope = EvidenceScope(
                            section_id=analysis_section_id,
                            allowed_source_agents=set(dependencies),
                            required_metrics=required_metrics,
                        )
                        scoped_points, evidence_audit = evidence_scope.select(
                            task["aggregated_data_points"]
                        )
                        task["aggregated_data_points"] = scoped_points
                        task["evidence_scope"] = {
                            "section_id": analysis_section_id,
                            "required_metrics": sorted(required_metrics),
                            "allowed_source_agents": sorted(dependencies),
                            "audit": evidence_audit,
                        }
                        task["required_metrics"] = sorted(required_metrics)
                        logger.info(
                            "[_execute_batch] analysis evidence scope: agent=%s section=%s %s",
                            agent.agent_id, analysis_section_id, evidence_audit,
                        )
                    
                    # [P0-6] Inject annual report data from Agent context
                    agent_context = getattr(agent, '_context', {})
                    if agent_context.get("document_context"):
                        task["document_context"] = agent_context["document_context"]
                    if agent_context.get("document_tables"):
                        task["document_tables"] = agent_context["document_tables"]
                    
                    # Inject preloaded search results (Phase B: unified query planning)
                    if agent.agent_id in preloaded_data:
                        task["preloaded_search_results"] = preloaded_data[agent.agent_id]
                    
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
                                        # M2: 按 agent 的 aspect 过滤 data_points
                                        recovered_points = self._filter_data_by_aspect(
                                            deduped, agent_aspect
                                        )
                                        if agent_category == AgentCategory.ANALYSIS:
                                            recovery_scope = EvidenceScope(
                                                section_id=str(task.get("evidence_scope", {}).get("section_id") or ""),
                                                allowed_source_agents=set(task.get("evidence_scope", {}).get("allowed_source_agents") or []),
                                                required_metrics=set(task.get("evidence_scope", {}).get("required_metrics") or []),
                                            )
                                            recovered_points, recovery_audit = recovery_scope.select(recovered_points)
                                            task["evidence_scope"]["recovery_audit"] = recovery_audit
                                        task["aggregated_data_points"] = recovered_points
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
                
                # Agent execution has no implicit deadline.  Do not replace
                # the old 120s limit with another hidden per-agent limit;
                # cancellation must come from the task/session controller.
                task_timeout = None
                if timeout_override is not None:
                    # An explicit caller deadline remains supported for
                    # bounded orchestration operations.
                    task_timeout = float(timeout_override)

                task_id = await self._coordinator.dispatch_task(
                    agent=agent,
                    task=task,
                    options=TaskOptions(
                        timeout=task_timeout,
                        max_retries=agent_config.get("max_retries", self.config.max_retries),
                    ),
                )
                task_ids.append(task_id)
                agent_task_map[task_id] = agent.agent_id
            except Exception as e:
                logger.error(f"分发任务失败 {agent.agent_id}: {e}")
                error_result = {"success": False, "error": f"Task dispatch failed: {e}",
                                "agent_id": agent.agent_id, "action": task.get("action", "")}
                batch_results.append(error_result)
                scheduler.mark_failed(agent.agent_id, str(e))
        
        # 等待完成（带暂停/取消检查）
        results = await self._wait_for_completion_with_pause_check(
            task_ids,
            _session_id_for_pause,
            requirement=requirement,
            stage_name=stage_name,
            agent_task_map=agent_task_map,
        )
        
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
        
        # E-P1-5/E-P1-6 FIX: Inject section_id BEFORE persistence
        # so ResearchResultStore gets the correct mapping
        _aspects = requirement.get("aspects", []) if isinstance(requirement, dict) else []
        for _ar in batch_results:
            _aid = _ar.get("agent_id", "")
            if _ar.get("section_id") or _ar.get("_section_id"):
                continue
            _agent = scheduler.get_agent_by_id(_aid)
            _sid = _canonical_runtime_section_id(
                getattr(self, "_agent_section_map", {}).get(_aid)
                or (self._get_section_id_from_agent(_agent) if _agent else "")
                or self._get_section_id_from_agent_id(_aid)
            )
            if not _sid or _sid == _aid or (len(_sid) < 5 and "_agent_" in _sid):
                if _aspects and "_agent_" in _aid:
                    try:
                        _idx = int(_aid.split("_agent_")[-1])
                        if 0 <= _idx < len(_aspects):
                            _sid = f"section_{_idx}"
                    except (ValueError, IndexError):
                        pass
            _ar["section_id"] = _sid
            _ar["_section_id"] = _sid
        
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
                        _content_from_dict = False
                        # R3-FIX: content may be dict (Phase1 metadata), normalize to str
                        if isinstance(content, dict):
                            content = str(content)
                            _content_from_dict = True
                        if not content or (isinstance(content, str) and len(content) <= 50):
                            _r_dp = r.get("data_points")
                            if _r_dp and isinstance(_r_dp, list) and len(_r_dp) > 0:
                                _fmt_parts = []
                                for _dp_item in _r_dp[:80]:
                                    if isinstance(_dp_item, dict):
                                        _m = _dp_item.get("metric", _dp_item.get("title", ""))
                                        _v = _dp_item.get("value", "")
                                        _u = _dp_item.get("unit", "")
                                        if _m and _v:
                                            _line = f"- {_m}: {_v}"
                                            if _u:
                                                _line += f" ({_u})"
                                            _fmt_parts.append(_line)
                                    elif isinstance(_dp_item, str) and len(_dp_item) > 10:
                                        _fmt_parts.append(f"- {_dp_item[:300]}")
                                _fmt_text = "\n".join(_fmt_parts)
                                if _content_from_dict and _fmt_parts:
                                    content = _fmt_text
                                elif len(_fmt_text) > len(content or ""):
                                    content = _fmt_text
                        if content and isinstance(content, str) and len(content) > 50:
                            agent_contents[agent_id] = {
                                "agent_id": agent_id,
                                "content": content[:50000],
                                "success": True,
                                "phase": stage_name,
                                "section_id": r.get("section_id", ""),
                            }
                
                batch_completed = [{
                    "agent_id": r.get("agent_id", ""),
                    "success": r.get("success", False),
                    "phase": stage_name,
                    "section_id": r.get("section_id", ""),
                    "_section_id": r.get("_section_id", ""),
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

    def _persist_agent_checkpoint(
        self,
        requirement: Dict[str, Any],
        agent_result: Dict[str, Any],
        stage_name: str,
    ) -> None:
        """Persist one completed agent result without waiting for its batch."""
        task_id = requirement.get("task_id") if isinstance(requirement, dict) else None
        agent_id = str(agent_result.get("agent_id", "") or "")
        if not task_id or not agent_id or not agent_result.get("success"):
            return
        content = agent_result.get("content") or agent_result.get("result") or ""
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        agent_contents = {}
        if isinstance(content, str) and len(content) > 50:
            agent_contents[agent_id] = {
                "agent_id": agent_id,
                "content": content[:50000],
                "success": True,
                "phase": stage_name,
                "section_id": agent_result.get("section_id", ""),
            }
        try:
            ResearchResultStore(storage_path="data").save_result(
                task_id=task_id,
                result={
                    "topic": requirement.get("topic", ""),
                    "data_points": list(agent_result.get("data_points") or []),
                    "sources": list(agent_result.get("sources") or []),
                    "completed_agents": [{
                        "agent_id": agent_id,
                        "success": True,
                        "phase": stage_name,
                        "section_id": agent_result.get("section_id", ""),
                        "_section_id": agent_result.get("_section_id", ""),
                    }],
                    "agent_contents": agent_contents,
                },
                status=ResearchStatus.COLLECTING,
            )
            logger.info("[_execute_batch] agent checkpoint persisted: %s", agent_id)
        except Exception as exc:
            logger.warning("[_execute_batch] agent checkpoint failed for %s: %s", agent_id, exc)

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
            return _canonical_runtime_section_id(agent.section_id)

        section_ids = list(getattr(agent, "section_ids", []) or [])
        if section_ids:
            return _canonical_runtime_section_id(section_ids[0])

        config = getattr(agent, "config", {}) or {}
        if isinstance(config, dict):
            metadata = config.get("section_metadata") or {}
            if isinstance(metadata, dict) and metadata.get("section_id"):
                return _canonical_runtime_section_id(metadata["section_id"])
        
        return ""
    
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
        if len(parts) >= 4 and parts[-2] == "agent" and parts[0] in ("phase", "batch"):
            # phase_N_agent_M / batch_N_agent_M 格式：无意义章节名，返回自身
            return agent_id
        if len(parts) >= 3:
            last = parts[-1]
            is_index = last.isdigit() or (
                len(last) >= 6 and all(c in '0123456789abcdef' for c in last.lower())
            )
            if is_index:
                return "_".join(parts[1:-1])
            else:
                if parts[0] in ("inject", "replan"):
                    return "_".join(parts[1:-1])
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
            质量分数 (0-100)
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
        
        # 默认中等质量
        if quality_score is None:
            quality_score = 50.0
        
        # 确保在有效范围内 (0-100)，使用统一归一化
        try:
            from src.core.quality.normalizer import normalize_quality_score
            return normalize_quality_score(float(quality_score), default=50.0)
        except (TypeError, ValueError):
            return 50.0

    def _identify_failed_agents(
        self,
        batch_results: List[Dict[str, Any]],
        checker: Any,
        batch_agents: List["IAgent"],
        quality_context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """区分 infrastructure 和 quality 失败，返回失败agent列表

        Returns:
            list of dict: [
                {"type": "infrastructure", "reason": "timeout|exception",
                 "error": str, "partial_output": ..., "agent": IAgent},
                {"type": "quality", "score": float, "issues": List[str],
                 "agent": IAgent},
            ]
        """
        agent_map = {a.agent_id: a for a in batch_agents}
        failed = []

        for r in batch_results:
            agent = agent_map.get(r.get("agent_id", ""))
            if not agent:
                continue

            if not r.get("success"):
                # infrastructure failure
                failed.append({
                    "type": "infrastructure",
                    "reason": r.get("failure_type", "unknown"),
                    "error": r.get("error", "Unknown error"),
                    "partial_output": r.get("partial_output", {}),
                    "agent": agent,
                })
            else:
                # quality check on successful result
                try:
                    combined = r.get("content", "") or r.get("result", "")
                    if isinstance(combined, dict):
                        combined = str(combined)
                    check_data = {
                        "content": combined,
                        "sources": r.get("sources", []),
                        "data_points": r.get("data_points", []),
                    }
                    qr = checker.check(check_data, quality_context or {})
                    if not qr.passed:
                        failed.append({
                            "type": "quality",
                            "score": qr.score,
                            "issues": qr.issues,
                            "agent": agent,
                        })
                except Exception:
                    continue

        return failed

    def _inject_retry_feedback(
        self,
        failed_agents: List[Dict[str, Any]],
        retry_count: int,
    ) -> None:
        """根据失败类型向 agent._context 注入 feedback"""
        for fa in failed_agents:
            agent = fa["agent"]
            if not hasattr(agent, '_context') or not isinstance(agent._context, dict):
                continue

            agent._context["retry_attempt"] = retry_count

            if fa["type"] == "infrastructure":
                agent._context["retry_reason"] = fa["reason"]
                agent._context["previous_error"] = fa.get("error", "")
                agent._context["quality_feedback"] = {
                    "score": 0,
                    "issues": [f"Agent failed with {fa['reason']}: {fa.get('error', 'unknown')}"],
                    "previous_attempt": retry_count - 1,
                }
            else:
                agent._context["quality_feedback"] = {
                    "score": fa["score"],
                    "issues": fa["issues"][:5],
                    "previous_attempt": retry_count - 1,
                }

    def _merge_retry_results(
        self,
        batch_results: List[Dict[str, Any]],
        retry_results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """将重试结果替换到原始 batch 结果中对应位置"""
        merged = list(batch_results)
        for rr in retry_results:
            for i, br in enumerate(merged):
                if br.get("agent_id") == rr.get("agent_id"):
                    merged[i] = rr
                    break
        return merged

    # M2: Aspect-based data filtering for P1-1 fallback injection
    SYNONYM_MAP = {
        "财务": ["营收", "利润", "毛利率", "净利", "收入", "成本", "费用"],
        "销量": ["销量", "出货", "出货量", "交付", "交付量", "市场份额", "市占率"],
        "竞争": ["竞争对手", "竞争格局", "市场格局", "份额"],
        "研发": ["研发投入", "R&D", "专利", "技术创新"],
        "风险": ["风险", "负债", "现金流", "财务健康"],
        "国际化": ["海外", "出口", "国际化", "出海"],
        "预测": ["预测", "展望", "趋势", "前景"],
    }

    def _filter_data_by_aspect(self, data_points: list, aspect: str) -> list:
        """按 aspect 关键词对 data_points 做相关性评分和过滤"""
        if not data_points:
            return []
        if not aspect:
            # Missing chapter identity is unsafe for a recovery path.  Do not
            # guess by taking a prefix from the global cache.
            logger.warning("[_filter_data_by_aspect] missing aspect; refusing cache injection")
            return []

        aspect_clean = aspect.replace("section_", "").replace("_", " ")
        aspect_keywords = set(aspect_clean.split())
        expanded_keywords = set(aspect_keywords)
        for kw in aspect_keywords:
            for syn_key, syn_vals in self.SYNONYM_MAP.items():
                if syn_key in kw or kw in syn_key:
                    expanded_keywords.update(syn_vals)

        scored = []
        for dp in data_points:
            dp_text = (dp.get("content", "") + " " + dp.get("title", "")).lower()
            overlap = sum(1 for kw in expanded_keywords if kw.lower() in dp_text)
            scored.append((overlap, dp))

        scored.sort(key=lambda x: -x[0])
        relevant = [dp for score, dp in scored if score > 0][:500]
        if relevant:
            return relevant
        # Never inject an arbitrary prefix when semantic matching fails.  The
        # old fallback returned the first 200 records, which could silently
        # feed an unrelated chapter's evidence into analysis.  An empty set
        # is safer: the caller can mark the chapter as uncovered and trigger
        # targeted supplementary search.
        logger.warning(
            "[_filter_data_by_aspect] no relevant evidence for aspect=%s; refusing unrelated fallback",
            aspect,
        )
        return []

    async def _unified_search(
        self,
        agents: List["IAgent"],
        requirement: Dict[str, Any],
    ) -> Dict[str, List[Dict]]:
        from src.core.search.query_deduplicator import SearchQueryDeduplicator
        from src.core.decomposition.strategies import SectionDataSpec
        from datetime import datetime

        self._search_deduplicator = SearchQueryDeduplicator(self.search_gateway)
        deduplicator = self._search_deduplicator
        topic = requirement.get("topic", "")
        current_year = str(datetime.now().year)

        search_skill = None if self.search_gateway is not None else self._get_search_skill()
        if not search_skill and self.search_gateway is None:
            logger.warning("[_unified_search] no search skill available")
            return {}

        section_spec_map = self._get_section_spec_map()
        unique_queries: Dict[str, tuple] = {}
        agent_section_map: Dict[str, str] = {}
        search_topic = self._extract_keywords(topic)

        for agent in agents:
            section_id = _canonical_runtime_section_id(self._get_section_id_from_agent(agent))
            section_spec = section_spec_map.get(section_id)
            if not section_spec:
                continue
            agent_section_map[agent.agent_id] = section_id
            for need in section_spec.search_data_needs:
                q1 = f"{search_topic} {need} {current_year}"
                q2 = f"{search_topic} {need} 数据"
                for q in [q1, q2]:
                    normalized = deduplicator._normalize_query(q)
                    if normalized not in unique_queries:
                        unique_queries[normalized] = (q, [section_id])
                    else:
                        existing = unique_queries[normalized]
                        unique_queries[normalized] = (existing[0], existing[1] + [section_id])
            q_agg = f"{search_topic} {section_spec.name} {current_year}"
            norm_agg = deduplicator._normalize_query(q_agg)
            if norm_agg not in unique_queries:
                unique_queries[norm_agg] = (q_agg, [section_id])

        async def _search_one(original_query, section_ids, skill):
            result = await deduplicator.search(
                original_query,
                section_ids[0],
                skill,
                scope="execution_engine",
            )
            return original_query, section_ids, result

        search_tasks = [
            _search_one(q, sids, search_skill)
            for q, (q, sids) in unique_queries.items()
        ]
        if search_tasks:
            all_search_results = await asyncio.gather(*search_tasks)
        else:
            all_search_results = []

        preloaded_data: Dict[str, List[Dict]] = {}
        for original_query, section_ids, result in all_search_results:
            is_shared = len(section_ids) > 1
            for agent_id, sec_id in agent_section_map.items():
                if sec_id in section_ids:
                    results_list = result.get("results", [])
                    entry = {"query": original_query, "results": copy.deepcopy(results_list)}
                    preloaded_data.setdefault(agent_id, []).append(entry)

        shared = deduplicator.get_shared_queries()
        if shared:
            logger.info(f"[_unified_search] {len(shared)} queries shared across sections")

        return preloaded_data

    def _get_search_skill(self) -> Any:
        if hasattr(self, '_skill_registry') and self._skill_registry:
            for name in ["web_search", "multi_search", "search_skill"]:
                skill = self._skill_registry.get(name)
                if skill:
                    return skill
        return None

    def _extract_keywords(self, topic: str) -> str:
        if not topic:
            return ""
        keywords = topic.strip()
        for suffix in ["行业研究报告", "行业研究", "研究报告", "分析报告", "报告", "研究", "分析"]:
            if keywords.endswith(suffix):
                keywords = keywords[:-len(suffix)].strip()
                break
        return keywords

    def _get_section_spec_map(self) -> Dict[str, Any]:
        from src.core.decomposition.strategies import SectionDataSpec
        return {spec.section_id: spec for spec in self._section_data_specs}

    def _get_section_spec(self, agent: Any) -> Any:
        from src.core.decomposition.strategies import SectionDataSpec
        section_id = self._get_section_id_from_agent(agent)
        spec_map = self._get_section_spec_map()
        return spec_map.get(section_id)

    def _get_section_spec_by_agent_id(self, agent_id: str) -> Any:
        if not hasattr(self, '_section_data_specs') or not self._section_data_specs:
            return None
        spec_map = self._get_section_spec_map()
        if hasattr(self, '_agent_id_to_section_id') and agent_id in self._agent_id_to_section_id:
            section_id = self._agent_id_to_section_id[agent_id]
            if section_id in spec_map:
                return spec_map[section_id]
        section_id = self._get_section_id_from_agent_id(agent_id)
        if section_id and section_id in spec_map:
            return spec_map[section_id]
        if section_id:
            for sid, spec in spec_map.items():
                if section_id in sid or sid in section_id:
                    return spec
        return None

    def _get_covered_needs(self, section_data_needs: List[str], data_points: List[Dict]) -> set:
        covered = set()
        dp_texts = []
        for dp in data_points:
            t = dp.get("content", "") + dp.get("title", "")
            if t:
                dp_texts.append(t)
        for need in section_data_needs:
            if len(need) < 2:
                continue
            need_variants = {str(need).lower()}
            # Coverage must use the same synonym vocabulary as result
            # filtering.  Otherwise an evidence item found through an
            # expanded query (e.g. 交付量 for 出货量) is counted as missing and
            # triggers redundant supplementation.
            for syn_key, syn_vals in self.SYNONYM_MAP.items():
                normalized_values = [str(value).lower() for value in syn_vals]
                normalized_key = str(syn_key).lower()
                if (
                    str(need).lower() == normalized_key
                    or str(need).lower() in normalized_values
                    or any(
                        str(need).lower() in value or value in str(need).lower()
                        for value in normalized_values
                    )
                ):
                    need_variants.update([normalized_key, *normalized_values])
            for text in dp_texts:
                text_lower = text.lower()
                if any(variant in text_lower for variant in need_variants):
                    covered.add(need)
                    break
        return covered

    async def _supplement_missing_data(
        self,
        batch_results: List[Dict],
        requirement: Dict[str, Any],
        max_rounds: int = 2,
        coverage_threshold: float = 0.8,
    ) -> Dict[str, Dict]:
        from src.core.decomposition.strategies import SectionDataSpec
        from datetime import datetime

        if not hasattr(self, '_section_data_specs') or not self._section_data_specs:
            return {}

        deduplicator = getattr(self, '_search_deduplicator', None)
        if not deduplicator:
            from src.core.search.query_deduplicator import SearchQueryDeduplicator
            deduplicator = SearchQueryDeduplicator(self.search_gateway)
            self._search_deduplicator = deduplicator

        topic = requirement.get("topic", "")
        current_year = str(datetime.now().year)
        search_topic = self._extract_keywords(topic)
        search_skill = None if self.search_gateway is not None else self._get_search_skill()
        if not search_skill and self.search_gateway is None:
            return {}
        all_data_points = []
        for r in batch_results:
            if r.get("success"):
                all_data_points.extend(r.get("data_points", []))
        for r in getattr(self, '_previous_all_results', []):
            if isinstance(r, dict) and r.get("success"):
                all_data_points.extend(r.get("data_points", []))

        supplement_results: Dict[str, Dict] = {}
        for round_idx in range(max_rounds):
            total_needs = 0
            total_covered = 0
            needs_to_supplement = []

            for spec in self._section_data_specs:
                search_needs = spec.search_data_needs
                if not search_needs:
                    continue
                covered = self._get_covered_needs(search_needs, all_data_points)
                missing = [n for n in search_needs if n not in covered]
                total_needs += len(search_needs)
                total_covered += len(covered)
                for need in missing:
                    if need not in supplement_results:
                        needs_to_supplement.append((need, spec.section_id))

            if total_needs == 0:
                break
            coverage = total_covered / total_needs
            if coverage >= coverage_threshold:
                logger.info(f"[Phase D] coverage {coverage:.1%} >= {coverage_threshold:.0%}, stopping")
                break
            if not needs_to_supplement:
                break

            logger.info(f"[Phase D] round {round_idx + 1}: {len(needs_to_supplement)} needs missing, coverage {coverage:.1%}")

            async def _supp_search_one(need, section_id, skill):
                query = f"{search_topic} {need} {current_year}"
                try:
                    result = await deduplicator.search(
                        query,
                        section_id,
                        skill,
                        scope="execution_engine",
                    )
                    return need, result
                except Exception as e:
                    logger.warning(f"[Phase D] supplement search failed for '{need}': {e}")
                    return need, None

            search_tasks = [_supp_search_one(n, sid, search_skill) for n, sid in needs_to_supplement]
            results = await asyncio.gather(*search_tasks)

            for need, result in results:
                if result and result.get("results"):
                    def _evidence_fields(item: Dict[str, Any]) -> Dict[str, Any]:
                        return {
                            "evidence_id": item.get("evidence_id", ""),
                            "provenance_id": item.get("provenance_id", ""),
                            "evidence_excerpt": item.get("evidence_excerpt", "")
                            or item.get("excerpt", "")
                            or item.get("snippet", ""),
                            "locator": item.get("locator", "")
                            or item.get("href", "")
                            or item.get("url", ""),
                            "task_id": item.get("task_id", ""),
                            "request_id": item.get("request_id", ""),
                            "retrieved_at": item.get("retrieved_at"),
                        }

                    supplement_results[need] = {
                        "data_points": [{
                            "title": f"Supplement: {search_topic} {need}",
                            "content": item.get("body", "") or item.get("snippet", ""),
                            "url": item.get("href", "") or item.get("url", ""),
                            "quality_score": item.get("quality_score", 0),
                            "credibility": "supplement_search",
                            **_evidence_fields(item),
                        } for item in result.get("results", [])],
                        "sources": [{
                            "title": f"Supplement: {search_topic} {need}",
                            "url": item.get("href", "") or item.get("url", ""),
                            "type": "web",
                            **_evidence_fields(item),
                        } for item in result.get("results", [])],
                    }
                    all_data_points.extend(supplement_results[need]["data_points"])

        return supplement_results
