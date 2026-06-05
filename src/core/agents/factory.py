"""
动态 Agent 工厂 V2

核心设计原则：
1. 不预设固定 Agent 类型 - 根据需求动态生成
2. 主控分析需求 → 工厂定制 Agent
3. 任意领域、任意任务都可支持
4. Agent Session 层级管理 - 追踪子 Agent 状态

v2.1 更新：
- GenericAgent 移至 generic_agent.py（Mixin组合模式）
- 使用IAgent Protocol作为类型注解
- 保持向后兼容

v2.2 更新（生命周期管理）：
- 添加create_batch()批量创建方法
- 添加hibernate_batch()批量休眠方法
- 添加restore_batch()批量恢复方法
- 创建新批次时自动休眠上一批次

使用示例:
    # 主控分析用户需求
    requirement = {
        "topic": "医疗AI市场",
        "aspects": ["市场规模", "政策环境", "竞争格局"],
        "output_format": "docx"
    }
    
    # 工厂动态创建所需 Agents
    factory = DynamicAgentFactory()
    agents = factory.create_agents_for_requirement(requirement)
    
    # 带 Session 创建（支持层级追踪）
    factory = DynamicAgentFactory(message_bus=message_bus, shared_memory=shared_memory)
    agent, session = factory.create_agent_with_session(
        agent_id="agent_001",
        capability=capability,
        parent_session_id="research_001"
    )
    
    # 批量创建（新功能）
    batch_result = await factory.create_batch(
        parent_session_id="research_001",
        batch_index=0,
        aspects=["市场规模", "政策环境"],
        previous_batch_agents=["agent_001", "agent_002"]  # 会先休眠这些
    )

设计文档: docs/AGENT_SESSION_MANAGEMENT.md
设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/AGENT_LIFECYCLE_AND_DATA_MANAGEMENT.md
重构文档: .sisyphus/plans/agent_mixin_refactor_plan.md
"""
import logging
from typing import Any, Dict, List, Optional, Tuple, Union, TYPE_CHECKING

from src.core.agents.base import BaseAgent, AgentFactory

logger = logging.getLogger(__name__)
from src.core.agents.protocol import IAgent
from src.core.agents.agent_session import (
    AgentSession,
    AgentSessionRegistry,
    AgentSessionStatus,
    SessionOrigin,
    generate_session_id,
)
from src.core.agents.generic_agent import GenericAgent
from src.core.agents.batch_structures import BatchCreationResult
from src.core.agents.lifecycle_state import AgentLifecycleState
from src.skills.registry import SkillRegistry
from src.core.communication import MessageBus, SharedMemory
from src.core.agents.session_persistence import SessionPersistenceManager

if TYPE_CHECKING:
    pass

# 类型别名：Agent可以是BaseAgent（旧）或实现IAgent Protocol（新）
AgentType = Union[BaseAgent, IAgent]


class AgentCapability:
    """
    Agent capability definition.
    
    Describes what an Agent can do: which Skills and MCP tools it needs.
    """
    def __init__(
        self,
        name: str,
        description: str,
        required_skills: List[str],
        optional_skills: Optional[List[str]] = None,
        skill_params: Optional[Dict[str, Dict]] = None,
        role: Optional[str] = None,
        goal: Optional[str] = None,
        backstory: Optional[str] = None,
        system_prompt: Optional[str] = None,
        mcp_tools: Optional[List[str]] = None,
    ):
        self.name = name
        self.description = description
        self.required_skills = required_skills
        self.optional_skills = optional_skills or []
        self.skill_params = skill_params or {}
        self.role = role
        self.goal = goal
        self.backstory = backstory
        self.system_prompt = system_prompt
        self.mcp_tools = mcp_tools or []


class DynamicAgentFactory(AgentFactory):
    """
    动态 Agent 工厂
    
    根据任务需求动态创建任意类型的 Agent，
    不局限于预定义的固定类型。
    
    扩展功能（Phase 3.9）：
    - Agent Session 层级管理
    - 通信能力注入（MessageBus, SharedMemory）
    - Session Registry 管理
    
    Attributes:
        _skill_registry: Skill 注册表
        _message_bus: MessageBus 实例（可选）
        _shared_memory: SharedMemory 实例（可选）
        _session_registries: Session 注册表映射
    """
    
    def __init__(
        self,
        skill_registry: Optional[SkillRegistry] = None,
        message_bus: Optional[MessageBus] = None,
        shared_memory: Optional[SharedMemory] = None,
        persistence: Optional[SessionPersistenceManager] = None,
        mcp_handler: Optional[Any] = None,
    ):
        super().__init__()
        self._skill_registry = skill_registry or SkillRegistry()
        
        # 自动注册核心 Skills（如果 registry 为空）
        if len(self._skill_registry._skills) == 0:
            registered = self._skill_registry.register_core_skills()
            logger.info(f"DynamicAgentFactory: 自动注册了 {registered} 个核心 Skills")
        
        self._message_bus = message_bus or MessageBus()
        self._shared_memory = shared_memory or SharedMemory()
        self._persistence = persistence
        self._mcp_handler = mcp_handler
        self._agents: Dict[str, AgentType] = {}
        self._created_count = 0
        
        # Session 层级管理（Phase 3.9）
        self._session_registries: Dict[str, AgentSessionRegistry] = {}
    
    # Skill name alias mapping: common shorthand → actual registry name.
    # Updated whenever new aliases are discovered via validation warnings.
    _SKILL_ALIAS_MAP: Dict[str, str] = {
        "search": "search_skill",
        "analysis": "llm_skill",
        "docx": "docx_skill",
        "pptx": "pptx_skill",
        "http": "http_skill",
        "file": "file_skill",
        "news": "news_search",
        "code_generation": "llm_skill",
        "code_fix": "llm_skill",
        "debugging": "llm_skill",
        "dialogue": "llm_skill",
        "comparison": "llm_skill",
    }

    def _validate_and_normalize_skills(
        self,
        agent_id: str,
        required_skills: List[str],
        optional_skills: List[str],
    ) -> Tuple[List[str], List[str]]:
        """
        Validate skill names against the SkillRegistry and normalize aliases.

        This is the defensive layer that prevents invalid skill names
        from reaching GenericAgent._available_skills and causing
        silent fallback to LLM-only generation.

        Args:
            agent_id: Agent ID for logging context
            required_skills: Skills specified as required
            optional_skills: Skills specified as optional

        Returns:
            (normalized_required, normalized_optional) tuple
        """
        registered_names = set(self._skill_registry._skills.keys())
        unknown_names: List[str] = []

        def _normalize(skills: List[str]) -> List[str]:
            result = []
            for skill in skills:
                if skill in registered_names:
                    result.append(skill)
                elif skill in self._SKILL_ALIAS_MAP:
                    resolved = self._SKILL_ALIAS_MAP[skill]
                    if resolved not in result:
                        result.append(resolved)
                    logger.warning(
                        f"Agent {agent_id}: skill alias '{skill}' resolved to '{resolved}'"
                    )
                else:
                    unknown_names.append(skill)
            return result

        norm_required = _normalize(required_skills)
        norm_optional = _normalize(optional_skills)

        if unknown_names:
            logger.error(
                f"Agent {agent_id}: UNKNOWN skills dropped: {unknown_names}. "
                f"Registered: {sorted(registered_names)}"
            )

        # Safety: if no valid skills remain, inject llm_skill as minimum
        if not norm_required and not norm_optional:
            logger.warning(
                f"Agent {agent_id}: no valid skills after validation, "
                f"injecting fallback 'llm_skill'"
            )
            norm_required = ["llm_skill"]

        # Ensure llm_skill is present for agents that need reasoning
        if "llm_skill" not in norm_required and "llm_skill" not in norm_optional:
            norm_optional.append("llm_skill")
            logger.debug(f"Agent {agent_id}: auto-added 'llm_skill' as optional")

        return norm_required, norm_optional

    def create_agent(
        self,
        agent_id: str,
        capability: AgentCapability,
        context: Optional[Dict[str, Any]] = None
    ) -> AgentType:
        """
        根据能力定义创建 Agent
        
        Args:
            agent_id: Agent 唯一标识
            capability: Agent 能力定义
            context: 上下文信息
            
        Returns:
            配置好的 Agent 实例（实现IAgent Protocol）
            
        Raises:
            ValueError: 如果 agent_id 已存在
        """
        # 检查 agent_id 是否已存在
        if agent_id in self._agents:
            raise ValueError(f"Agent ID '{agent_id}' already exists")
        
        # P0-2: Validate and normalize skill names against SkillRegistry
        validated_required, validated_optional = self._validate_and_normalize_skills(
            agent_id=agent_id,
            required_skills=capability.required_skills,
            optional_skills=capability.optional_skills,
        )
        
        all_skills = validated_required + validated_optional
        
        # 构建配置（包含专业能力和MCP工具字段）
        config = {
            "name": capability.name,
            "description": capability.description,
            "skills": all_skills,
            "required_skills": validated_required,
            "optional_skills": validated_optional,
            "skill_params": capability.skill_params,
            "skill_registry": self._skill_registry,
            "context": context or {},
            # 专业能力字段
            "role": capability.role,
            "goal": capability.goal,
            "backstory": capability.backstory,
            "system_prompt": capability.system_prompt,
            # MCP tool configuration
            "mcp_handler": self._mcp_handler,
            "mcp_tools": capability.mcp_tools,
        }
        
        # 将 context 中的 category 提升到 config 顶层（用于 Agent 分类）
        if context and "category" in context:
            config["category"] = context["category"]
        
        # 创建 Agent
        agent = GenericAgent(
            agent_id=agent_id,
            agent_type="dynamic",
            config=config
        )
        
        self._agents[agent_id] = agent
        self._created_count += 1
        
        return agent
    
    def create_agent_with_session(
        self,
        agent_id: str,
        capability: AgentCapability,
        parent_session_id: str,
        context: Optional[Dict[str, Any]] = None,
        category: Optional[str] = None,
    ) -> Tuple[AgentType, AgentSession]:
        """
        创建 Agent 并绑定 Session
        
        这是关键方法 - 解决了 Agent 创建后无追踪的问题。
        每个 Agent 创建时自动获得独立 Session，并注册到父 Session 的 Registry。
        
        Args:
            agent_id: Agent 唯一标识
            capability: Agent 能力定义
            parent_session_id: 父 Session ID（主控 Session）
            context: 执行上下文
            category: Agent 类别（用于按需加载 LangChain Skills）
            
        Returns:
            (Agent 实例, AgentSession 实例) 元组
            
        Side Effects:
            - 创建 AgentSession 并设置 parent_session_id
            - 注册 Session 到 AgentSessionRegistry
            - 注入通信能力到 Agent (_session, _message_bus, _shared_memory)
            - 按需加载 LangChain Skills
        """
        # 0. 按需加载 LangChain Skills（创建 capability 副本避免副作用）
        if category and self._skill_registry:
            loaded_skills = self._skill_registry.load_skills_for_category(category)
            if loaded_skills:
                # 创建新的 capability 副本，避免修改传入对象
                capability = AgentCapability(
                    name=capability.name,
                    description=capability.description,
                    required_skills=capability.required_skills.copy(),
                    optional_skills=list(set(
                        capability.optional_skills + loaded_skills
                    )),
                    skill_params=capability.skill_params.copy(),
                )
                logger.debug(f"Agent {agent_id}: loaded LangChain skills: {loaded_skills}")
        
        # 1. 创建 Agent（将 category 添加到 context 中）
        if context is None:
            context = {}
        if category:
            context["category"] = category
        agent = self.create_agent(agent_id, capability, context)
        
        # 2. 创建 Agent Session
        session = AgentSession(
            session_id=generate_session_id(prefix="agent"),
            agent_id=agent_id,
            parent_session_id=parent_session_id,
            origin=SessionOrigin.SPAWNED,
            task={
                "action": "research",
                "aspect": context.get("aspect") if context else None,
                "category": category,
            },
            context=context or {}
        )
        
        # 3. 注册到父 Session 的 Registry
        registry = self.get_or_create_registry(parent_session_id)
        registry.register(session)
        
        # 4. 持久化 Session 和 Registry
        if self._persistence:
            self._persistence.save_session(session)
            self._persistence.save_registry(registry)
        
        # 5. 注入通信能力到 Agent
        agent._session = session
        agent._message_bus = self._message_bus
        agent._shared_memory = self._shared_memory
        
        return agent, session
    
    def get_registry(self, parent_session_id: str) -> Optional[AgentSessionRegistry]:
        """
        获取指定父 Session 的 Registry
        
        Args:
            parent_session_id: 父 Session ID
            
        Returns:
            AgentSessionRegistry 实例，不存在返回 None
        """
        return self._session_registries.get(parent_session_id)
    
    def get_or_create_registry(self, parent_session_id: str) -> AgentSessionRegistry:
        """
        获取或创建 Registry
        
        如果 Registry 不存在，自动创建新 Registry。
        
        Args:
            parent_session_id: 父 Session ID
            
        Returns:
            AgentSessionRegistry 实例
        """
        if parent_session_id not in self._session_registries:
            self._session_registries[parent_session_id] = AgentSessionRegistry(
                parent_session_id=parent_session_id
            )
        
        return self._session_registries[parent_session_id]
    
    def clear_registry(self, parent_session_id: str) -> bool:
        """
        清理指定父 Session 的 Registry
        
        释放 Registry 及其所有子 Session，并清理 _agents 中对应的代理，防止内存泄漏。
        应在研究任务完成或取消后调用。
        
        Args:
            parent_session_id: 父 Session ID
            
        Returns:
            是否成功清理（False 表示 Registry 不存在）
        """
        if parent_session_id in self._session_registries:
            registry = self._session_registries[parent_session_id]
            agent_ids_to_remove = []
            for agent_id, agent in list(self._agents.items()):
                session = getattr(agent, '_session', None)
                if session and getattr(session, 'parent_session_id', None) == parent_session_id:
                    agent_ids_to_remove.append(agent_id)
            for aid in agent_ids_to_remove:
                del self._agents[aid]
            registry.clear()
            del self._session_registries[parent_session_id]
            if agent_ids_to_remove:
                logger.debug(f"清理 {len(agent_ids_to_remove)} 个 agent: {agent_ids_to_remove}")
            return True
        return False
    
    def clear_all_registries(self) -> int:
        """
        清理所有 Session Registry
        
        Returns:
            清理的 Registry 数量
        """
        count = len(self._session_registries)
        for registry in self._session_registries.values():
            registry.clear()
        self._session_registries.clear()
        return count
    
    def create_agents_for_requirement(
        self,
        requirement: Dict[str, Any]
    ) -> List[BaseAgent]:
        """
        根据需求自动创建所需的所有 Agents
        
        这是核心方法 - 主控 Agent 调用此方法，
        工厂根据需求分析自动创建专业 Agents。
        
        Args:
            requirement: 需求定义，包含:
                - topic: 研究主题
                - aspects: 研究维度 ["市场规模", "竞争格局", ...]
                - data_sources: 数据来源偏好
                - output_format: 输出格式
                - special_requirements: 特殊要求
                
        Returns:
            Agent 列表，每个负责一个子任务
        """
        agents = []
        topic = requirement.get("topic", "未知主题")
        aspects = requirement.get("aspects", [])
        output_format = requirement.get("output_format", "docx")
        
        # 1. 为每个研究维度创建专业 Agent
        for i, aspect in enumerate(aspects):
            capability = self._analyze_aspect_capability(aspect, topic)
            agent = self.create_agent(
                agent_id=f"{aspect.lower().replace(' ', '_')}_{i+1}",
                capability=capability,
                context={
                    "topic": topic,
                    "aspect": aspect,
                    "requirement": requirement
                }
            )
            agents.append(agent)
        
        # 2. 创建数据收集 Agent（如果需要）
        if requirement.get("needs_data_collection", True):
            data_agent = self.create_agent(
                agent_id="data_collector",
                capability=AgentCapability(
                    name="数据收集Agent",
                    description=f"收集'{topic}'相关数据",
                    required_skills=["search_skill", "file_skill"],
                    optional_skills=["news_search", "http_skill"]
                ),
                context={"topic": topic, "aspects": aspects}
            )
            agents.insert(0, data_agent)  # 数据收集放最前
        
        # 3. 创建报告生成 Agent
        report_capability = self._get_report_capability(output_format)
        report_agent = self.create_agent(
            agent_id="report_generator",
            capability=report_capability,
            context={
                "topic": topic,
                "output_format": output_format,
                "sections": aspects
            }
        )
        agents.append(report_agent)
        
        return agents
    
    def _analyze_aspect_capability(
        self,
        aspect: str,
        topic: str
    ) -> AgentCapability:
        """
        分析研究维度，确定所需能力
        
        根据 aspect 的关键词，自动推断需要的 Skills
        """
        aspect_lower = aspect.lower()
        
        # 分析关键词，匹配 Skills
        required_skills = ["search_skill", "file_skill"]
        optional_skills = []
        description = f"分析'{topic}'的'{aspect}'"
        
        # 根据维度类型调整 Skills
        if any(kw in aspect_lower for kw in ["政策", "法规", "policy", "regulation"]):
            optional_skills.extend(["news_search", "http_skill"])
            description += "（重点关注政策文件和法规）"
            
        elif any(kw in aspect_lower for kw in ["竞争", "竞争格局", "competitor", "market share"]):
            optional_skills.extend(["http_skill", "web_scraper"])
            description += "（重点关注企业信息和市场份额）"
            
        elif any(kw in aspect_lower for kw in ["技术", "technology", "技术趋势", "专利"]):
            optional_skills.extend(["http_skill"])
            description += "（重点关注技术发展和专利信息）"
            
        elif any(kw in aspect_lower for kw in ["财务", "financial", "营收", "利润"]):
            optional_skills.extend(["http_skill", "web_scraper"])
            description += "（重点关注财务数据和财报）"
        
        return AgentCapability(
            name=f"{aspect}分析Agent",
            description=description,
            required_skills=required_skills,
            optional_skills=optional_skills
        )
    
    def _get_report_capability(self, output_format: str) -> AgentCapability:
        """根据输出格式确定报告生成能力"""
        if output_format == "docx":
            return AgentCapability(
                name="报告生成Agent",
                description="生成Word格式研究报告",
                required_skills=["docx_skill", "file_skill"],
                optional_skills=["search_skill"]
            )
        elif output_format == "markdown":
            return AgentCapability(
                name="报告生成Agent",
                description="生成Markdown格式研究报告",
                required_skills=["file_skill"],
                optional_skills=["search_skill"]
            )
        else:
            return AgentCapability(
                name="报告生成Agent",
                description=f"生成{output_format}格式研究报告",
                required_skills=["file_skill"],
                optional_skills=["search_skill", "docx_skill"]
            )
    
    def create_custom_agent(
        self,
        agent_id: str,
        name: str,
        description: str,
        skills: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> BaseAgent:
        """
        创建完全自定义的 Agent
        
        用户可以直接指定任意 Skills，完全灵活
        """
        capability = AgentCapability(
            name=name,
            description=description,
            required_skills=skills,
            optional_skills=[]
        )
        return self.create_agent(agent_id, capability, context)
    
    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """获取已创建的 Agent"""
        return self._agents.get(agent_id)
    
    def list_agents(self) -> Dict[str, str]:
        """列出所有已创建的 Agent"""
        return {
            aid: agent.config.get("name", "Unknown")
            for aid, agent in self._agents.items()
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """获取工厂统计信息（扩展版）"""
        return {
            "created_count": self._created_count,
            "active_agents": len(self._agents),
            "agent_ids": list(self._agents.keys()),
            # Session 相关统计（Phase 3.9）
            "session_registries": len(self._session_registries),
            "registry_ids": list(self._session_registries.keys()),
            "has_message_bus": self._message_bus is not None,
            "has_shared_memory": self._shared_memory is not None,
            # 生命周期统计
            "hibernated_agents": sum(
                1 for a in self._agents.values()
                if hasattr(a, '_lifecycle_state') 
                and a._lifecycle_state == AgentLifecycleState.HIBERNATED
            ),
        }
    
    # === 批量管理方法（v2.2新增） ===
    
    async def create_batch(
        self,
        parent_session_id: str,
        batch_index: int,
        aspects: List[str],
        previous_batch_agents: Optional[List[str]] = None,
        skill_registry: Optional[SkillRegistry] = None,
    ) -> BatchCreationResult:
        """
        创建批次Agent
        
        核心设计：创建新批次时，先休眠上一批次
        
        Args:
            parent_session_id: 父Session ID（任务级）
            batch_index: 批次索引（从0开始）
            aspects: 研究维度列表
            previous_batch_agents: 上一批Agent ID列表（用于休眠）
            skill_registry: Skill注册表（可选，默认使用工厂的）
            
        Returns:
            BatchCreationResult: 包含Agent列表和Session列表
        """
        # 1. 先休眠上一批Agent（如果有）
        if previous_batch_agents:
            await self.hibernate_batch(previous_batch_agents)
            logger.info(f"Batch {batch_index-1}: 已休眠 {len(previous_batch_agents)} 个Agent")
        
        # 2. 创建这批Agent
        agents = []
        sessions = []
        
        registry = skill_registry or self._skill_registry
        
        for i, aspect in enumerate(aspects):
            agent_id = f"agent_{batch_index}_{i}"
            
            capability = AgentCapability(
                name=f"{aspect[:20]}数据收集Agent",
                description=f"收集'{aspect}'相关数据",
                required_skills=["search_skill", "lc_tavily_search"],
                optional_skills=["http_skill", "news_search"],
                role="data_collector",
                goal=f"收集{aspect}的完整原始数据",
            )
            
            agent, session = self.create_agent_with_session(
                agent_id=agent_id,
                capability=capability,
                parent_session_id=parent_session_id,
                context={"aspect": aspect, "batch_index": batch_index},
                category="data_collection",
            )
            
            # 设置生命周期状态为READY
            if hasattr(agent, '_lifecycle_state'):
                agent._lifecycle_state = AgentLifecycleState.READY
            
            agents.append(agent)
            sessions.append(session)
        
        logger.info(f"Batch {batch_index}: 创建 {len(agents)} 个Agent")
        
        return BatchCreationResult(
            batch_index=batch_index,
            agents=agents,
            sessions=sessions,
        )
    
    async def hibernate_batch(self, agent_ids: List[str]) -> None:
        """
        批量休眠Agent
        
        释放Agent实例，保留Session和数据。
        
        Args:
            agent_ids: Agent ID列表
        """
        hibernated_count = 0
        
        for agent_id in agent_ids:
            agent = self._agents.get(agent_id)
            if agent:
                try:
                    # 调用Agent内部休眠方法
                    if hasattr(agent, 'hibernate') and self._persistence:
                        await agent.hibernate(self._persistence)
                        hibernated_count += 1
                    
                    # 清理Agent实例引用（释放内存）
                    del self._agents[agent_id]
                    
                except Exception as e:
                    logger.warning(f"Failed to hibernate agent {agent_id}: {e}")
        
        logger.info(f"已休眠 {hibernated_count} 个Agent，内存已释放")
    
    async def restore_batch(
        self,
        parent_session_id: str,
        batch_index: int,
    ) -> List[GenericAgent]:
        """
        批量恢复Agent
        
        从Session恢复Agent，重新加载Skills。
        
        Args:
            parent_session_id: 父Session ID
            batch_index: 批次索引
            
        Returns:
            恢复后的Agent列表
            
        Raises:
            ValueError: 如果Registry不存在或没有匹配的Session
        """
        # 1. 加载这批的Session记录
        registry = self._session_registries.get(parent_session_id)
        if not registry:
            # 尝试从持久化加载
            if self._persistence:
                registry_data = self._persistence.load_registry(parent_session_id)
                if registry_data:
                    # 从持久化数据重建Registry
                    registry = AgentSessionRegistry(parent_session_id=parent_session_id)
                    # 重建sessions
                    for session_data in registry_data.get("sessions", []):
                        session = AgentSession(
                            session_id=session_data.get("session_id"),
                            agent_id=session_data.get("agent_id"),
                            parent_session_id=parent_session_id,
                            origin=SessionOrigin.SPAWNED,
                            task=session_data.get("task", {}),
                            context=session_data.get("context", {}),
                        )
                        session.status = session_data.get("status", "pending")
                        registry.register(session)
                    # 缓存到内存
                    self._session_registries[parent_session_id] = registry
                    logger.info(f"Loaded registry from persistence: {parent_session_id}")
            
            if not registry:
                raise ValueError(f"Registry not found: {parent_session_id}")
        
        # 2. 筛选这批的Session
        batch_sessions = [
            s for s in registry.sessions.values()
            if s.context.get("batch_index") == batch_index
            and s.status == AgentSessionStatus.HIBERNATED
        ]
        
        if not batch_sessions:
            logger.warning(f"No hibernated sessions found for batch {batch_index}")
            return []
        
        # 3. 批量恢复
        agents = []
        for session in batch_sessions:
            try:
                # 从模板创建Agent实例
                agent = self._create_agent_from_template(session)
                
                # 调用Agent内部恢复方法
                if hasattr(agent, 'restore'):
                    await agent.restore(session)
                
                # 注册到工厂
                self._agents[agent.agent_id] = agent
                
                agents.append(agent)
                
            except Exception as e:
                logger.warning(f"Failed to restore agent from session {session.session_id}: {e}")
        
        logger.info(f"Batch {batch_index}: 恢复 {len(agents)} 个Agent")
        
        return agents
    
    def _create_agent_from_template(self, session: AgentSession) -> GenericAgent:
        """
        从Session的agent_template创建Agent实例
        
        Args:
            session: AgentSession
            
        Returns:
            新创建的GenericAgent实例
            
        Raises:
            ValueError: 如果Session没有agent_template
        """
        agent_template = session.agent_template
        if agent_template is None:
            raise ValueError(f"Session {session.session_id} has no agent_template")
        
        capability = agent_template.get("capability", {})
        
        # 构建配置
        config = {
            "name": capability.get("name"),
            "description": capability.get("description"),
            "skills": capability.get("skills", capability.get("required_skills", [])),
            "required_skills": capability.get("required_skills", []),
            "optional_skills": capability.get("optional_skills", []),
            "skill_registry": self._skill_registry,
            "context": agent_template.get("context", {}),
            "role": capability.get("role", ""),
            "goal": capability.get("goal", ""),
        }
        
        # 创建Agent实例
        agent = GenericAgent(
            agent_id=session.agent_id,
            agent_type="dynamic",
            config=config
        )
        
        # 注入通信能力
        agent._session = session
        agent._message_bus = self._message_bus
        agent._shared_memory = self._shared_memory
        
        return agent


# 全局工厂实例
_factory_instance: Optional[DynamicAgentFactory] = None


def get_agent_factory() -> DynamicAgentFactory:
    """获取全局 Agent 工厂实例"""
    global _factory_instance
    if _factory_instance is None:
        _factory_instance = DynamicAgentFactory()
    return _factory_instance
