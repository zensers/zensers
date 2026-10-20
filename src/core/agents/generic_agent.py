"""
动态Agent实现
============

GenericAgent是动态创建的Agent，通过Skill路由执行任务。

特点:
1. 动态创建，根据需求生成
2. 通过Skill Registry路由任务
3. 灵活配置，可组合多个Skill
4. 无固定职责，适应性强

v2.1 修复：
- 使用asyncio.Lock替代threading.Lock
- update_state()改为异步方法

v2.2 新增：
- 生命周期状态管理（AgentLifecycleState）
- hibernate()/restore()方法支持休眠恢复

设计文档: docs/STATUS/AGENT_UNIFICATION_PLAN.md
设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/AGENT_LIFECYCLE_AND_DATA_MANAGEMENT.md
重构文档: .sisyphus/plans/agent_mixin_refactor_plan.md
"""

import asyncio
import hashlib
import inspect
import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, List, TYPE_CHECKING
from datetime import datetime
from urllib.parse import urlparse
import logging

# 导入Mixin
from src.core.agents.mixins import (
    StateManagementMixin,
    CommunicationMixin
)

from src.core.prompt_manager import PromptManager

# 导入生命周期状态
from src.core.agents.lifecycle_state import (
    AgentLifecycleState,
    InvalidStateError,
    validate_transition,
)

# 导入Session状态
from src.core.agents.agent_session import AgentSessionStatus

from src.core.data.canonical_registry import parse_entry_key

if TYPE_CHECKING:
    from src.core.agents.session_persistence import SessionPersistenceManager
    from src.core.agents.agent_session import AgentSession

from src.core.llm_client import call_llm
from src.core.evidence_scope import EvidenceScope
from src.core.search import (
    AnySearchProvider,
    GatewaySearchSkillAdapter,
    LocalSkillProvider,
    SearchGateway,
)

logger = logging.getLogger(__name__)

_AUTHORITY_DOMAINS = {
    "gov.cn": 0.95, "stats.gov.cn": 0.98, "miit.gov.cn": 0.95,
    "worldbank.org": 0.95, "imf.org": 0.95, "oecd.org": 0.93,
    "mckinsey.com": 0.88, "bcg.com": 0.87, "bain.com": 0.87,
    "deloitte.com": 0.85, "pwc.com": 0.85, "ey.com": 0.85,
    "goldmansachs.com": 0.88, "morganstanley.com": 0.87,
    "eastmoney.com": 0.75, "10jqka.com.cn": 0.72,
    "sina.com.cn": 0.70, "sohu.com": 0.65, "163.com": 0.65,
}

# 读取 quality_rubric.md 文件（模块级缓存，避免重复 IO）
_RUBRIC_CACHE: str = ""

def _load_quality_rubric() -> str:
    """读取 quality_rubric.md 文件内容"""
    global _RUBRIC_CACHE
    if not _RUBRIC_CACHE:
        rubric_path = Path(__file__).parent.parent.parent.parent / "prompts" / "_shared" / "quality_rubric.md"
        if rubric_path.exists():
            _RUBRIC_CACHE = rubric_path.read_text(encoding="utf-8")
        else:
            _RUBRIC_CACHE = ""
    return _RUBRIC_CACHE


COGNITIVE_STRATEGY = {
    "fact_driven": {
        "L1": {"dimension_ceiling": "inferential", "speculative_word_downgrade": "strict", "confidence_threshold": {"factual": "HIGH"}},
        "L2": {"caliber_floor_for_citation": "llm_inference_factual",  # _DEFERRED: not consumed by communication.py
             "same_caliber_resolution": "newer_timestamp",           # _DEFERRED: TODO in communication.py:204
             "speculative_write_policy": "never"},                    # _DEFERRED: TODO in communication.py:204
        "L3": {"speculative_policy": "reference_only", "reasoning_mode": "cross_validation",                  # _DEFERRED: not consumed by any code
             "inferential_instruction": "用数据验证推断，标注未经验证的主张", "falsification_requirement": "all_inferential",  # _DEFERRED: not enforced at runtime
             "evidence_chain_template": "数据 → 发现 → 确认", "cross_dimension_instruction": "与其他事实维度交叉验证", "insight_instruction": "寻找数据中隐含的反直觉模式"},
        "L4": {"hypothesis_type": "描述性", "hypothesis_count": (1, 2), "hypothesis_template": "【数据观察H1】 → 【支持证据】→ 【确认/否定】→ 【发现】", "counter_hypothesis_required": False, "agent_hypothesis_count": 0, "verification_focus": "Data accuracy", "output_suffix": "数据验证结果"},
        "L5": {"contradiction_resolution": "Data conflict resolution", "contradiction_instruction": "两项事实性主张冲突，请：(1)判断哪个数据源更可信并说明理由 (2)解释矛盾产生的可能原因（数据口径差异、统计时间窗口不同、样本偏差等）(3)说明该矛盾对本维度结论的影响程度", "auto_resolve_threshold": 0.8,    # _DEFERRED: spec v1.3 Section 4.6 Note 2
             "escalation_action": "Flag for human review"},  # _DEFERRED: spec v1.3 Section 4.6 Note 2
    },
    "inference_driven": {
        "L1": {"dimension_ceiling": "speculative", "speculative_word_downgrade": "moderate", "confidence_threshold": {"factual": "MEDIUM"}},
        "L2": {"caliber_floor_for_citation": "llm_inference_speculative",  # _DEFERRED: not consumed by communication.py
             "same_caliber_resolution": "higher_source_count",           # _DEFERRED: TODO in communication.py:204
             "speculative_write_policy": "with_uncertainty_tag"},        # _DEFERRED: TODO in communication.py:204
        "L3": {"speculative_policy": "cautious_use", "reasoning_mode": "causal_chain",                  # _DEFERRED: not consumed by any code
             "inferential_instruction": "Build causal chain; check premises", "falsification_requirement": "speculative_only",  # _DEFERRED: not enforced at runtime
             "evidence_chain_template": "前提 → 推理 → 结论", "cross_dimension_instruction": "Trace causal transmission from other dimensions", "insight_instruction": "在假设验证之外，关注假设之间的关联和涌现模式——多个假设的交叉验证可能揭示比单个假设更深层的关系"},
        "L4": {"hypothesis_type": "因果性", "hypothesis_count": (3, 5), "hypothesis_template": "【因果假设H1】 → 【支持证据】→ 【确认/修正/推翻】→ 【结论】", "counter_hypothesis_required": True, "agent_hypothesis_count": 2, "verification_focus": "Logic completeness", "output_suffix": "假设验证结果"},
        "L5": {"contradiction_resolution": "Premise re-examination", "contradiction_instruction": "两项结论冲突，请追溯哪个前提或推理步骤出现了分歧，并分析：(1)分歧前提的具体内容 (2)各前提的支撑证据强度 (3)修正前提后结论如何变化", "auto_resolve_threshold": 0.6,    # _DEFERRED: spec v1.3 Section 4.6 Note 2
             "escalation_action": "Inject as reasoning challenge"},  # _DEFERRED: spec v1.3 Section 4.6 Note 2
    },
    "forward_looking": {
        "L1": {"dimension_ceiling": None, "speculative_word_downgrade": "relaxed", "confidence_threshold": {"speculative": "LOW"}},
        "L2": {"caliber_floor_for_citation": "llm_inference_speculative",  # _DEFERRED: not consumed by communication.py
             "same_caliber_resolution": "wider_coverage",              # _DEFERRED: TODO in communication.py:204
             "speculative_write_policy": "with_falsification_condition"},  # _DEFERRED: TODO in communication.py:204
        "L3": {"speculative_policy": "open_use", "reasoning_mode": "scenario_analysis",                  # _DEFERRED: not consumed by any code
             "inferential_instruction": "Map to scenarios; assign probabilities", "falsification_requirement": "all_claims",  # _DEFERRED: not enforced at runtime
             "evidence_chain_template": "信号 → 情景 → 概率", "cross_dimension_instruction": "Check consistency with other forward-looking claims", "insight_instruction": "在情景推演之外，关注不同情景之间的转折信号——什么条件变化会导致从一种情景切换到另一种，这些转折点往往是最有价值的洞察"},
        "L4": {"hypothesis_type": "预测性", "hypothesis_count": (2, 3), "hypothesis_template": "【预测性假设H1】 → 【支持信号】→ 【概率评估】→ 【情景】", "counter_hypothesis_required": True, "agent_hypothesis_count": 1, "verification_focus": "Falsification conditions", "output_suffix": "前瞻验证结果"},
        "L5": {"contradiction_resolution": "Scenario reconciliation", "contradiction_instruction": "两项预测冲突，请分析在什么条件下各自成立，并给出情景分析：(1)各预测成立的条件集 (2)当前数据更支持哪个条件集 (3)两个预测是否可以在不同时间尺度上同时成立", "auto_resolve_threshold": 0.4,    # _DEFERRED: spec v1.3 Section 4.6 Note 2
             "escalation_action": "Present both scenarios"},  # _DEFERRED: spec v1.3 Section 4.6 Note 2
    },
    "assessment_driven": {
        "L1": {"dimension_ceiling": None, "speculative_word_downgrade": "relaxed", "confidence_threshold": {"factual": "HIGH", "inferential": "MEDIUM", "speculative": "LOW"}},
        "L2": {"caliber_floor_for_citation": "llm_inference_speculative",  # _DEFERRED: not consumed by communication.py
             "same_caliber_resolution": "wider_coverage",              # _DEFERRED: TODO in communication.py:204
             "speculative_write_policy": "with_falsification_condition"},  # _DEFERRED: TODO in communication.py:204
        "L3": {"speculative_policy": "open_use", "reasoning_mode": "risk_scenario",                    # _DEFERRED: not consumed by any code
             "inferential_instruction": "Build risk scenarios from cross-dimension signals", "falsification_requirement": "key_risks_only",  # _DEFERRED: not enforced at runtime
             "evidence_chain_template": "风险触发条件 → 传导路径 → 影响评估 → 应对策略", "cross_dimension_instruction": "Map cross-dimension claims to risk scenarios, must reference them explicitly", "insight_instruction": "深入分析每个风险的作用机制和传导路径，识别风险间的关联和级联效应"},
        "L4": {"hypothesis_type": "风险情景", "hypothesis_count": (1, 2), "hypothesis_template": "【风险情景H1】 → 【触发条件】→ 【传导路径】→ 【影响评估】", "counter_hypothesis_required": False, "agent_hypothesis_count": 0, "verification_focus": "Scenario plausibility", "output_suffix": "风险情景评估"},
        "L5": {"contradiction_resolution": "Risk scenario reconciliation", "contradiction_instruction": "两项评估冲突，请分析：(1)各评估隐含的风险情景 (2)当前数据更支持哪个情景 (3)是否可在不同条件下先后发生", "auto_resolve_threshold": 0.5,    # _DEFERRED: spec v1.3 Section 4.6 Note 2
             "escalation_action": "Present both risk scenarios with probability"},  # _DEFERRED: spec v1.3 Section 4.6 Note 2
    },
}


class GenericAgent(
    StateManagementMixin,
    CommunicationMixin
):
    """
    动态Agent（Mixin组合模式）
    
    GenericAgent通过配置决定能力，通过Skill Registry路由任务。
    与FixedAgent不同，GenericAgent是动态创建的，职责由配置定义。
    
    Mixin组合：
    - StateManagementMixin: 状态管理（异步安全）
    - CommunicationMixin: 通信能力（MessageBus/SharedMemory）
    
    注意：
    - 不使用InputValidationMixin（动态Agent不做输入验证）
    - execute()有默认实现，不需要子类覆盖
    
    Skill路由机制：
        action = task.get("action")
        skill_registry = self.config.get("skill_registry")
        available_skills = self.config.get("skills", [])
        
        if action == "search" and "search_skill" in available_skills:
            skill = self._get_search_skill(skill_registry)
            return await skill.execute(**parameters)
    
    构造函数兼容性：
        Factory调用: GenericAgent(agent_id="xxx", agent_type="dynamic", config={
            "skill_registry": registry,
            "skills": ["search_skill", "analysis_skill"],
            "name": "分析Agent"
        })
    """
    
    agent_type: str = "dynamic"

    @staticmethod
    def _build_claim_canonical_key(
        task_id: str, chapter_id: str, section_id: str, claim_id: str,
    ) -> str:
        """Build a collision-safe canonical key for a cross-dimension claim."""
        parts = [task_id, chapter_id, section_id, claim_id]
        normalized = [str(part or "unknown").strip().replace(":", "_") for part in parts]
        return "claim:" + ":".join(normalized)

    def __init__(
        self,
        agent_id: str,
        agent_type: Optional[str] = None,
        config: Optional[Dict] = None,
    ):
        """
        初始化动态Agent
        
        Args:
            agent_id: Agent唯一标识
            agent_type: Agent类型（默认"dynamic"）
            config: 配置字典，包含：
                - skill_registry: SkillRegistry实例
                - skills: 可用Skill名称列表
                - name: Agent名称
                - context: 上下文信息
        """
        # === 核心标识属性（IAgent Protocol必需） ===
        self.agent_id = agent_id
        self.agent_type = agent_type or "dynamic"
        
        # === 配置字典（主控依赖name和context键） ===
        self.config = config or {}
        
        # === 状态管理属性（StateManagementMixin依赖） ===
        self._status = "idle"
        self._data: Dict[str, Any] = {}
        self._lock = asyncio.Lock()  # 使用asyncio.Lock
        self._created_at = datetime.now().isoformat()
        self._updated_at = self._created_at
        
        # === 通信能力属性（CommunicationMixin依赖） ===
        self._message_bus = None
        self._shared_memory = None
        self._session = None
        
        # === GenericAgent特有属性（从config提取） ===
        self._skill_registry = self.config.get("skill_registry")
        self._available_skills = self.config.get("skills", [])
        self._action_to_skill_cache = None
        self._role = self.config.get("role", "")
        self._goal = self.config.get("goal", "")
        self._backstory = self.config.get("backstory", "")
        self._search_gateway = None
        self._search_gateway_skill = None
        
        # === 生命周期状态 ===
        self._lifecycle_state = AgentLifecycleState.CREATED
        self._context = self.config.get("context", {})
        
        # === P0-1修复: 从 context 中提取 section_id 并设置为属性 ===
        # 这样 ExecutionEngine._get_section_id_from_agent() 可以正确获取 section_id
        # 用于 ContentLockManager 的章节锁定机制
        self.section_id = self._context.get("section_id", "")

    def validate_input(self, task_input: Dict[str, Any]) -> tuple[bool, str]:
        """Validate the common task shape required by the IAgent contract."""
        if not isinstance(task_input, dict):
            return False, "task_input must be a dictionary"
        return True, ""

    def _report_progress(self, message: str, action: str = "analyzing"):
        _sid = getattr(self, '_current_session_id', None)
        if not _sid:
            return
        try:
            from src.core.session_streamer import SessionStreamer
            SessionStreamer.push_agent_message(_sid, {
                "agent_id": self.agent_id,
                "agent_name": self.config.get("context", {}).get("aspect", self.agent_type),
                "action": action,
                "content": message,
            })
        except Exception:
            pass

    # === 核心执行方法（有默认实现） ===
    
    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行任务（Skill路由）
        
        根据task中的action字段路由到对应的Skill执行。
        
        Args:
            task: 任务定义，包含：
                - action: 任务类型（如"search", "news_search"）
                - parameters: 任务参数
                
        Returns:
            执行结果
                
        路由映射：
            - "search" → "search_skill" (DuckDuckGo搜索)
            - "news_search" → "news_search" (新闻搜索)
            - "file_operation" → "file_skill" (文件操作)
            - "http_request" → "http_skill" (HTTP请求)
            - "generate_docx" → "docx_skill" (Word文档生成)
            - LangChain Skills: "lc_tavily_search", "lc_arxiv", "lc_wikipedia", "lc_python_repl"
        """
        action = task.get("action", "")
        parameters = task.get("parameters", {})
        
        # MCP protocol route (not a skill — handled before skill lookup)
        if action == "mcp":
            return await self._execute_mcp(parameters)
        
        skill_registry = self._skill_registry
        available_skills = self._available_skills
        
        if self._action_to_skill_cache is None:
            self._action_to_skill_cache = self._build_action_to_skill_map()
        ACTION_TO_SKILL = self._action_to_skill_cache
        
        # 查找对应的 Skill
        skill_name = ACTION_TO_SKILL.get(action)
        
        logger.info(f"GenericAgent {self.agent_id}: action='{action}' -> skill_name='{skill_name}', available_skills={available_skills[:5]}...")

        # A missing action is not an intrinsic LLM request.  Only actions
        # explicitly declared in the intrinsic map may enter the LLM path;
        # unknown actions must remain a cheap, deterministic compatibility
        # response instead of unexpectedly spending an LLM call.
        if action not in ACTION_TO_SKILL:
            return {
                "success": True,
                "message": f"GenericAgent {self.agent_id} executed action: {action}",
                "available_skills": available_skills,
            }
        
        if skill_name is not None and skill_name in available_skills and skill_registry:
            skill = skill_registry.get(skill_name)
            if skill:
                logger.info(f"GenericAgent {self.agent_id}: executing '{skill_name}' via-registry")
                result = await skill.execute(**parameters)
                return self._ensure_standard_result(result, action)
        
        # Intrinsic LLM capability (call_llm) — no registry lookup needed
        if skill_name is None or skill_name not in available_skills:
            _label = "LLM=intrinsic" if skill_name is None else "no-skill-found"
            logger.info(f"GenericAgent {self.agent_id}: executing intrinsic LLM path ({_label})")
            # 优先从 Agent context 获取 topic/aspect，再从 task 获取
            context = self._context or {}
            topic = context.get("topic") or task.get("topic", "")
            aspect = context.get("aspect") or task.get("aspect", "")
            aspects = task.get("aspects", [])
                    
            # 确保 topic 是字符串（可能是 ResearchRequirement 对象）
            if hasattr(topic, 'topic'):
                topic = topic.topic
            if not isinstance(topic, str):
                topic = str(topic) if topic else ""
                    
            # 确保 aspect 是字符串
            if not isinstance(aspect, str):
                aspect = str(aspect) if aspect else ""

            # 读取研究框架上下文
            core_question = context.get("core_question") or task.get("core_question", "")
            role_in_report = context.get("role_in_report") or task.get("role_in_report", "")
            sibling_aspects = context.get("sibling_aspects") or task.get("sibling_aspects", [])
                    
            logger.info(f"GenericAgent {self.agent_id}: topic='{topic}', aspect='{aspect}', aspects={aspects}")
                    
            quality_feedback = self._context.get("quality_feedback", {})
            if quality_feedback:
                logger.info(f"GenericAgent {self.agent_id}: 带质量反馈重试(第{quality_feedback.get('previous_attempt', 0)+1}次, 上次得分{quality_feedback.get('score', '?')})")
                self._quality_feedback = quality_feedback
            else:
                self._quality_feedback = None
                    
            # === Knowledge enrichment (before any LLM analysis path) ===
            knowledge_enrichment = {}
            if "knowledge_query" in self._available_skills and skill_registry:
                kq_skill = skill_registry.get("knowledge_query")
                if kq_skill:
                    try:
                        enrichment = await kq_skill.execute(
                            action="enrich", topic=topic, aspect=aspect
                        )
                        if enrichment.get("success"):
                            knowledge_enrichment = enrichment.get("data", {})
                    except Exception:
                        logger.warning("Knowledge enrichment failed", exc_info=True)
            self._knowledge_enrichment = knowledge_enrichment
                    
            # Initialize search results for data passing
            search_results = None
                    
            # Phase-aware execution: check agent category from config.
            # Set via factory.create_agent_with_session() -> context["category"] -> config["category"].
            # Decomposition path categories:
            #   "research"       -> DATA_COLLECTION phase (search only)
            #   "quality-check"  -> DATA_VALIDATION phase (validate existing data)
            #   "market-analysis"-> DEEP_ANALYSIS phase (analyze with frameworks, no search)
            #   "synthesis"      -> SYNTHESIS phase (cross-section integration)
            # Fallback path uses "data-collection" (search + analyze, unchanged).
            agent_category = self.config.get("category", "")
                    
            # Phase 1: DATA_COLLECTION - priority-driven execution
            # structured_db skills first, web_search as supplement, llm last
            if agent_category == "research":
                # [P0-5] Preloaded annual report data delivery
                if self._context.get("preloaded"):
                    annual_report_data = {}
                    if self._shared_memory and hasattr(self._shared_memory, 'get'):
                        annual_report_data = self._shared_memory.get("annual_report_data") or {}
                            
                    if annual_report_data:
                        # C11: Forensic mode — precise extraction by hypothesis data needs
                        if self._context.get("forensic_mode") and self._context.get("hypothesis_data_needs"):
                            result = await self._handle_preloaded_forensic(annual_report_data, action)
                            if result is not None:
                                return result

                        all_sections = annual_report_data.get("sections", [])

                        # [P0-5c] Filter sections by agent's section_type if available
                        own_section_types = set()
                        from src.core.decomposition.section_type_map import resolve_section_types as _resolve_st
                        section_id = self._context.get("section_id", "")
                        if section_id:
                            own_section_types.update(_resolve_st(section_id))

                        if own_section_types:
                            filtered_sections = [
                                s for s in all_sections
                                if s.get("section_type", "") in own_section_types
                            ]
                        else:
                            filtered_sections = all_sections

                        data_points = []
                        for section in filtered_sections:
                            content = section.get("content", "")
                            if content:
                                data_points.append({
                                    "title": section.get("title", ""),
                                    "content": content[:4000],
                                    "source": "annual_report_pdf",
                                    "type": section.get("section_type", "document"),
                                })
                        for table_type, rows in annual_report_data.get("financial_tables", {}).items():
                            for row in rows[:10]:
                                data_points.append({
                                    "title": f"{table_type} - {row.get('科目', '')}",
                                    "content": str(row),
                                    "source": "annual_report_pdf_table",
                                    "type": "structured_data",
                                })
                                
                        self._report_progress(f"Delivered {len(data_points)} preloaded data points (filtered={bool(own_section_types)}, types={own_section_types or 'all'})", "data_delivery")
                        return self._ensure_standard_result({
                            "success": True,
                            "content": json.dumps(data_points, ensure_ascii=False),
                            "data_points": data_points,
                            "sources": [{"title": "Annual Report PDF", "url": "", "type": "document"}],
                            "agent_id": self.agent_id,
                        }, action)
                    else:
                        return self._ensure_standard_result({
                            "success": False,
                            "error": "No annual report data available in SharedMemory",
                            "content": "",
                            "agent_id": self.agent_id,
                        }, action)
                        
                self._report_progress("Starting data collection...", "searching")
                data_points = []
                sources = []
                _structured_data_fetched = False
                _structured_data_sufficient = False

                from src.core.decomposition.strategies import SKILL_PRIORITY_MAP, DATA_SOURCE_PRIORITY

                def _skill_tier(name: str) -> str:
                    return SKILL_PRIORITY_MAP.get(name, "web_search")

                tiered_skills = {}
                for s in available_skills:
                    tiered_skills.setdefault(_skill_tier(s), []).append(s)
                execution_order = (
                    tiered_skills.get("structured_db", [])
                    + tiered_skills.get("web_search", [])
                    + tiered_skills.get("llm", [])
                )

                # Tier 1: structured_db (stock_data, wind, bloomberg, etc.)
                for db_skill_name in tiered_skills.get("structured_db", []):
                    if not skill_registry:
                        continue
                    if db_skill_name == "llm":
                        continue
                    db_skill = skill_registry.get(db_skill_name)
                    if not db_skill:
                        logger.warning(f"GenericAgent {self.agent_id}: {db_skill_name} not available in registry, skipping")
                        continue
                    try:
                        structured = await self._process_skill_output(
                            db_skill, db_skill_name, topic, aspect, skill_registry,
                            structured_data_sufficient=_structured_data_sufficient,
                        )
                        dp_count = len(structured.get("data_points", []))
                        if dp_count > 0:
                            _structured_data_fetched = True
                            if dp_count >= 3:
                                _structured_data_sufficient = True
                        data_points.extend(structured.get("data_points", []))
                        sources.extend(structured.get("sources", []))
                        if self._shared_memory and hasattr(self._shared_memory, 'write_canonical'):
                            for metric, value in structured.get("canonical_metrics", {}).items():
                                await self._shared_memory.write_canonical(
                                    metric=metric, value=value,
                                    caliber="structured_source",
                                    source=db_skill_name,
                                    publisher=self.agent_id,
                                )
                        logger.info(
                            f"GenericAgent {self.agent_id}: {db_skill_name} fetched "
                            f"{dp_count} data_points, sufficient={_structured_data_sufficient}"
                        )
                    except Exception as struct_err:
                        logger.warning(f"GenericAgent {self.agent_id}: {db_skill_name} failed: {struct_err}")
                self._report_progress(f"结构化数据库查询完成，获取 {len(data_points)} 条数据", "searching")

                # Tier 2: web_search (search_skill, news_search) — supplement for structured gaps
                # Skip web search if annual report document_context is preloaded
                _has_doc_data_t2 = bool(self._context.get("document_context") or self._context.get("has_preloaded_data") or task.get("document_context"))
                search_results = None
                if topic and tiered_skills.get("web_search") and not _has_doc_data_t2:
                    self._report_progress(f"Searching web sources for '{aspect or topic}'...", "searching")
                    web_skills = tiered_skills.get("web_search", [])
                    preloaded = task.get("preloaded_search_results")

                    if not _structured_data_fetched and topic:
                        fallback_queries = self._generate_structured_fallback_queries(topic, aspect or "")
                        if fallback_queries:
                            logger.info(f"GenericAgent {self.agent_id}: structured_db unavailable, injecting {len(fallback_queries)} fallback queries")
                            if not preloaded:
                                preloaded = []
                            preloaded.extend([{"query": q, "results": []} for q in fallback_queries])

                    search_depth = "basic" if _structured_data_sufficient else "deep"

                    if "search_skill" in web_skills and skill_registry:
                        search_skill = self._get_search_skill(skill_registry)
                        if search_skill:
                            search_result = await self._process_skill_output(
                                search_skill, "search_skill", topic, aspect, skill_registry,
                                structured_data_sufficient=_structured_data_sufficient,
                                preloaded_search_results=preloaded,
                                search_depth=search_depth,
                            )
                            data_points.extend(search_result.get("data_points", []))
                            sources.extend(search_result.get("sources", []))
                            search_results = search_result
                    self._report_progress(f"网络搜索完成，共 {len(data_points)} 条数据", "searching")

                    if "news_search" in web_skills and skill_registry and topic and not _has_doc_data_t2:
                        news_skill = skill_registry.get("news_search")
                        if news_skill:
                            try:
                                news_result = await self._process_skill_output(
                                    news_skill, "news_search", topic, aspect, skill_registry,
                                    structured_data_sufficient=_structured_data_sufficient,
                                )
                                data_points.extend(news_result.get("data_points", []))
                                sources.extend(news_result.get("sources", []))
                                logger.info(f"GenericAgent {self.agent_id}: news_search 补充 {len(news_result.get('data_points', []))} 条新闻")
                                self._report_progress(f"新闻搜索补充 {len(news_result.get('data_points', []))} 条", "searching")
                            except Exception as news_err:
                                logger.warning(f"GenericAgent {self.agent_id}: news_search failed: {news_err}")

                    # B-FIX-3: write key metrics to SharedMemory
                    if self._shared_memory and hasattr(self._shared_memory, 'write_canonical'):
                        import re as _re
                        _section_id = self.section_id
                        for _dp in data_points[:10]:
                            _c = _dp.get("content", "")
                            _u = _dp.get("url", "")
                            for _p, _mn in [
                                (r'(?:净利润|归母|扣非)[^\d]*?(\d+\.?\d*)\s*亿元', "净利润"),
                                (r'(?:(?:营业)?收入|营收)[^\d]*?(\d+\.?\d*)\s*亿元', "营收"),
                                (r'销量[^\d]*?(\d+\.?\d*)\s*万辆', "销量"),
                                (r'研发[^\d]*?(\d+\.?\d*)\s*亿元', "研发投入"),
                                (r'毛利率[^\d]*?(\d+\.?\d*)\s*%', "毛利率"),
                            ]:
                                _m = _re.search(_p, _c)
                                if _m:
                                    _metric_key = _mn if not _section_id else f"{_section_id}/{_mn}"
                                    _conflict = await self._shared_memory.write_canonical(
                                        metric=_metric_key,
                                        value=float(_m.group(1)),
                                        caliber="search_result",
                                        source=_u,
                                        publisher=self.agent_id,
                                    )
                                    if _conflict and self._message_bus:
                                        from src.core.communication import Event
                                        await self._message_bus.publish(
                                            "data.conflict.detected",
                                            Event(type="data.conflict.detected", data={
                                                "metric": _conflict.key,
                                                "values": _conflict.values,
                                                "sources": _conflict.sources,
                                            })
                                        )
                    return self._ensure_standard_result({
                        # A configured search tier is not evidence that data
                        # was collected. Do not report success when every
                        # provider/skill returned no usable data.
                        "success": bool(data_points),
                        "data_points": data_points,
                        "sources": sources,
                        "total_sources": search_results.get("total_sources", 0) if search_results else len(sources),
                        "quality_stats": search_results.get("quality_stats", {}) if search_results else {},
                        "agent_id": self.agent_id,
                    }, action)
                if data_points:
                    return self._ensure_standard_result({
                        "success": True,
                        "data_points": data_points,
                        "sources": sources,
                        "total_sources": len(sources),
                        "quality_stats": {},
                        "agent_id": self.agent_id,
                    }, action)
                return self._ensure_standard_result({
                    "success": False,
                    "error": "Data collection agent: no data source available",
                    "agent_id": self.agent_id,
                }, action)
                    
            # Phase 2: DATA_VALIDATION - cross-validate collected data for quality
            if agent_category == "quality-check":
                self._report_progress("Validating collected data...", "analyzing")
                data_points = task.get("aggregated_data_points", [])
                sources = task.get("aggregated_sources", [])
                if data_points:
                    validation_result = self._validate_collected_data(data_points, sources)
                    logger.info(
                        f"GenericAgent {self.agent_id}: validation complete - "
                        f"{validation_result['total_validated']}/{validation_result['total_input']} points, "
                        f"quality={validation_result['average_quality_score']}, "
                        f"conflicts={len(validation_result['conflicts'])}"
                    )
                    self._report_progress(f"数据验证完成，{validation_result['total_validated']}/{validation_result['total_input']} 个数据点，质量评分 {validation_result['average_quality_score']}", "analyzing")
                    # IMP-4: auto-resolve numerical conflicts
                    resolved_conflicts = []
                    if validation_result.get("has_conflicts"):
                        resolved_conflicts = self._resolve_numerical_conflicts(
                            validation_result.get("conflicts", [])
                        )
                        if resolved_conflicts:
                            logger.info(
                                f"GenericAgent {self.agent_id}: resolved {len(resolved_conflicts)} conflicts"
                            )
                    self._report_progress(f"冲突解决完成，{len(resolved_conflicts)} 个冲突已处理", "analyzing")
                    # IMP-3: targeted re-collection on low quality (max 1 round)
                    recollection_attempted = False
                    if validation_result.get("quality_rating") == "low" and skill_registry:
                        recollection_queries = self._generate_recollection_queries(
                            topic, aspect or "", validation_result.get("warnings", [])
                        )
                        if recollection_queries:
                            search_skill = self._get_search_skill(skill_registry)
                            if search_skill:
                                try:
                                    for rq in recollection_queries[:3]:
                                        sr = await search_skill.execute(query=rq, max_results=5)
                                        if sr and sr.get("success") and sr.get("results"):
                                            for item in sr["results"]:
                                                evidence = self._evidence_metadata(item)
                                                data_points.append({
                                                    "title": item.get("title", ""),
                                                    "content": item.get("body", "") or item.get("snippet", ""),
                                                    "url": item.get("href", "") or item.get("url", ""),
                                                    "quality_score": 40,
                                                    "source_type": "recollection",
                                                    "credibility": "recollection_search",
                                                    **evidence,
                                                })
                                                sources.append({
                                                    "title": item.get("title", ""),
                                                    "url": item.get("href", "") or item.get("url", ""),
                                                    "type": "web",
                                                    **evidence,
                                                })
                                    recollection_attempted = True
                                    logger.info(
                                        f"GenericAgent {self.agent_id}: re-collection added data, "
                                        f"re-validating {len(data_points)} total points"
                                    )
                                    validation_result = self._validate_collected_data(data_points, sources)
                                    self._report_progress(f"补充收集后重新验证，{validation_result['total_validated']} 个有效数据点", "analyzing")
                                except Exception as rc_err:
                                    logger.warning(f"GenericAgent {self.agent_id}: re-collection failed: {rc_err}")
                    validation_result["resolved_conflicts"] = resolved_conflicts
                    validation_result["recollection_attempted"] = recollection_attempted
                    return self._ensure_standard_result({
                        "success": True,
                        "data_points": validation_result.get("validated_data_points", data_points),
                        "sources": sources,
                        "validation": validation_result,
                        "agent_id": self.agent_id,
                    }, action)
                return self._ensure_standard_result({
                    "success": True,
                    "data_points": [],
                    "sources": [],
                    "validation": {"status": "completed", "note": "no data to validate", "quality_rating": "none"},
                    "agent_id": self.agent_id,
                }, action)
                    
            # Phase 3: DEEP_ANALYSIS - use pre-collected data, apply analytical frameworks
            # These agents receive dependency-filtered data_points/sources from upstream phases.
            # search_skill is available (via ASPECT_SKILL_MAP) for on-demand model/data lookup.
            if agent_category in ("market-analysis", "analysis", "financial-analysis"):
                self._report_progress(f"Analyzing {aspect or topic}...", "analyzing")
                aggregated_data_points = task.get("aggregated_data_points", [])
                aggregated_sources = task.get("aggregated_sources", [])
                _analysis_scope_config = task.get("evidence_scope", {}) or {}
                _scope_is_explicit = bool(
                    _analysis_scope_config
                    or task.get("dependency_agent_ids")
                    or task.get("required_metrics")
                    or task.get("section_id")
                )
                _direct_source_agents = {
                    str(item.get("source_agent_id") or item.get("agent_id") or "").strip()
                    for item in aggregated_data_points
                    if isinstance(item, dict)
                    and str(item.get("source_agent_id") or item.get("agent_id") or "").strip()
                }
                _analysis_scope = EvidenceScope(
                    section_id=str(_analysis_scope_config.get("section_id") or getattr(self, "section_id", "") or task.get("section_id", "")),
                    allowed_source_agents=set(_analysis_scope_config.get("allowed_source_agents") or task.get("dependency_agent_ids", []) or _direct_source_agents),
                    required_metrics=set(task.get("required_metrics") or _analysis_scope_config.get("required_metrics") or task.get("data_needs", []) or self._context.get("data_needs", [])),
                )
                # P-FIX-DEEP: search fallback when no upstream data available
                # Skip search if annual report document_context is preloaded
                _has_doc_data = bool(self._context.get("document_context") or self._context.get("has_preloaded_data") or task.get("document_context"))
                if not aggregated_data_points and not _has_doc_data and "search_skill" in self._available_skills and self._skill_registry:
                    logger.info(f"GenericAgent {self.agent_id}: 无上游数据，降级执行搜索")
                    _sr = await self._do_deep_research(
                        topic=topic, aspect=aspect, aspects=aspects, skill_registry=self._skill_registry,
                        preloaded_search_results=task.get("preloaded_search_results"),
                    )
                    if _sr and _sr.get("searches"):
                        for _search in _sr["searches"]:
                            for _item in (_search.get("results") or []):
                                _url = _item.get("href", "") or _item.get("url", "")
                                _evidence = self._evidence_metadata(_item)
                                aggregated_data_points.append({
                                    "title": _item.get("title", ""),
                                    "content": _item.get("body", "") or _item.get("snippet", ""),
                                    "url": _url,
                                    "quality_score": _item.get("quality_score", 0),
                                    "source_agent_id": f"analysis_fallback:{self.agent_id}",
                                    "section_id": _analysis_scope.section_id,
                                    **_evidence,
                                })
                                aggregated_sources.append({
                                    "title": _item.get("title", ""),
                                    "url": _url,
                                    "type": "web",
                                    **_evidence,
                                })
                        logger.info(f"GenericAgent {self.agent_id}: 降级搜索收集 {len(aggregated_data_points)} 数据点")
                        self._report_progress(f"降级搜索完成，获取 {len(aggregated_data_points)} 条数据", "searching")
                canonical_data = task.get("canonical_data", {}) or {}
                # Apply the same scope to both upstream evidence and any
                # targeted fallback search results.  Fallback evidence is
                # explicitly scoped to this agent/chapter above.
                _analysis_scope.allowed_source_agents.add(f"analysis_fallback:{self.agent_id}")
                aggregated_data_points, _evidence_audit = _analysis_scope.select(aggregated_data_points)
                # Filter to target currency only: zh report→CNY, en report→USD
                _target_cur = task.get("target_currency", "CNY")
                if _target_cur and canonical_data:
                    _filtered = {}
                    _any_with_currency = False
                    for _k, _v in canonical_data.items():
                        _pk = parse_entry_key(_k)
                        _key_currency = _pk["currency"]
                        _has_currency = _key_currency != ""
                        if _has_currency:
                            _any_with_currency = True
                        _matches_cur = _key_currency == _target_cur
                        _has_no_currency = not _key_currency
                        if _matches_cur or _has_no_currency:
                            _filtered[_k] = _v
                    if _any_with_currency and not _filtered:
                        canonical_data = {}
                    elif _filtered:
                        canonical_data = _filtered
                canonical_data = (
                    _analysis_scope.select_canonical(canonical_data)
                    if _scope_is_explicit else {}
                )
                # Supplement from SharedMemory for real-time updates across batches
                if self._shared_memory and hasattr(self._shared_memory, 'get'):
                    _sm_reg = self._shared_memory.get("_canonical_registry", {})
                    if _sm_reg:
                        _merged_canonical = dict(canonical_data)
                        for _k, _v in _sm_reg.items():
                            _spk = parse_entry_key(_k)
                            _skey_cur = _spk["currency"]
                            if _skey_cur == _target_cur or not _skey_cur:
                                _merged_canonical[_k] = _v
                        # Re-apply the same chapter scope after merging the
                        # live registry; otherwise SharedMemory would bypass
                        # the filtered task canonical_data view.
                        canonical_data = (
                            _analysis_scope.select_canonical(_merged_canonical)
                            if _scope_is_explicit else {}
                        )
                # B2.3: Read cross-dimension claims from SharedMemory
                cross_dimension_claims = []
                if self._shared_memory and hasattr(self._shared_memory, 'get_all_canonical'):
                    _all_canon = self._shared_memory.get_all_canonical()
                    _claim_records = []
                    for _ck, _cv in _all_canon.items():
                        if _ck.startswith("claim:") and _cv.get("publisher") != aspect:
                            _claim_val = _cv.get("value", {})
                            if isinstance(_claim_val, dict) and _claim_val.get("statement"):
                                _claim_records.append(_claim_val)
                    cross_dimension_claims = (
                        _analysis_scope.select_claims(_claim_records)
                        if _scope_is_explicit else []
                    )
                    _conflict_entries = {
                        k: v for k, v in _all_canon.items()
                        if k.startswith("conflict:claim:")
                        and _scope_is_explicit
                        and _analysis_scope.select_claims([v.get("value", {})])
                    }
                # A2.1: Generate causal hypotheses before analysis
                _cog_type = await self.infer_cognitive_type(aspect, topic)
                _cog_strategy = COGNITIVE_STRATEGY.get(_cog_type, COGNITIVE_STRATEGY["fact_driven"])
                self._context[f"cog_strategy:{aspect}"] = _cog_strategy
                causal_hypotheses = []
                if aggregated_data_points and len(aggregated_data_points) >= 5:
                    try:
                        _hyp_data = "\n".join([f"- {dp.get('title','')}: {(dp.get('content','') or '')[:200]}" for dp in aggregated_data_points[:5]])
                        _hyp_claims = "\n".join([f"- [{c.get('source_aspect','?')}] {c.get('statement','')}" for c in (cross_dimension_claims or [])]) if cross_dimension_claims else '暂无'
                        _l4_gen = _cog_strategy["L4"]
                        _hcount = _l4_gen["hypothesis_count"]
                        _hcount_str = f"{_hcount[0]}-{_hcount[1]}" if isinstance(_hcount, tuple) else str(_hcount)
                        hypothesis_prompt = f"""基于以下数据，生成{_hcount_str}个关于「{aspect}」的{_l4_gen['hypothesis_type']}假设。
每个假设必须：1) 可被数据验证或反驳 2) 涉及跨维度因果传导 3) 不与已知事实矛盾{'' if not _l4_gen['counter_hypothesis_required'] else ' 4) 包含反面假设'}

数据摘要（前5条）：
{_hyp_data}

其他维度已有发现：
{_hyp_claims}

输出格式（每行一个假设）：
假设：[因果陈述] | 验证数据：[需要什么数据] | 传导：[影响哪些维度] | 反面假设：[对立因果陈述]"""

                        hypothesis_result = await call_llm(
                            prompt=hypothesis_prompt,
                            system_prompt="你是一位因果推断专家。只输出假设，不要分析。"
                        )
                        if hypothesis_result.get("success") and hypothesis_result.get("content"):
                            causal_hypotheses = self._parse_causal_hypotheses(hypothesis_result["content"])
                            self._context["causal_hypotheses"] = causal_hypotheses
                    except Exception as _hyp_err:
                        logger.warning(f"GenericAgent {self.agent_id}: causal hypothesis generation failed: {_hyp_err}")
                system_prompt = self._get_professional_role_prompt(aspect)
                if aggregated_data_points:
                    prompt = self._build_analysis_prompt_with_data(
                        topic=topic, aspect=aspect, aspects=aspects,
                        data_points=aggregated_data_points, sources=aggregated_sources,
                        core_question=core_question,
                        role_in_report=role_in_report,
                        sibling_aspects=sibling_aspects,
                        sub_aspects=self._context.get("sub_aspects"),
                        cross_dimension_claims=cross_dimension_claims,
                        causal_hypotheses=causal_hypotheses,
                        conflict_entries=_conflict_entries if self._shared_memory and hasattr(self._shared_memory, 'get_all_canonical') else {},
                        deep_mode_tables=task.get("deep_mode_tables", ""),
                    )
                else:
                    prompt = self._build_basic_research_prompt(
                        topic, aspect, aspects,
                        core_question=core_question,
                        role_in_report=role_in_report,
                        sibling_aspects=sibling_aspects,
                    )
                # [P0-5] Inject annual report document context
                document_context = task.get("document_context", "") or self._context.get("document_context", "")
                document_tables = task.get("document_tables", []) or self._context.get("document_tables", [])
                if document_context or document_tables:
                    doc_injection = "\n\n## 年报原始数据（来自企业年报PDF解析）\n"
                    if document_context:
                        truncated = self._truncate_by_tokens(document_context, max_tokens=6000, preserve_tables=bool(document_tables))
                        doc_injection += f"\n### 年报章节原文\n{truncated}\n"
                    if document_tables:
                        doc_injection += "\n### 结构化财务数据\n"
                        if isinstance(document_tables, dict):
                            for table_type, rows in document_tables.items():
                                if rows:
                                    doc_injection += f"\n#### {table_type}\n"
                                    for row in rows:
                                        doc_injection += f"- {row}\n"
                        elif isinstance(document_tables, list):
                            for table in document_tables[:5]:
                                doc_injection += f"\n{table}\n"
                    doc_injection += "\n**重要**: 以上数据来自企业年报原文，优先使用这些数据进行分析，无需重新搜索。\n"
                    prompt = doc_injection + prompt
                # S-FIX-3: inject canonical authority data into prompt
                if canonical_data:
                    _canonical_section = "\n".join([
                        f"- {k}: {v.get('value','')}{v.get('unit','')} "
                        f"(口径: {v.get('caliber','不详')}, 来源: {v.get('source','不详')})"
                        for k, v in canonical_data.items()
                    ])
                    prompt += f"\n\n## 已确认的规范数据（必须优先引用）\n{_canonical_section}\n"
                    prompt += "\n**重要**: 以上数据已经过口径校准和权威性验证。引用时优先使用这些值，"
                    prompt += "除非你有更新的权威数据来源。"
                # Final SharedMemory check before LLM call: pick up last-millisecond resolution
                if self._shared_memory and hasattr(self._shared_memory, 'get'):
                    _sm_latest = self._shared_memory.get("_canonical_registry", {})
                    if _sm_latest:
                        _tmp = {}
                        for k, v in _sm_latest.items():
                            _pk = parse_entry_key(k)
                            if not _pk["currency"] or _pk["currency"] == _target_cur:
                                _tmp[k] = v
                        _sm_latest = _tmp
                    if _sm_latest and _sm_latest != canonical_data:
                        _diff = {k: v for k, v in _sm_latest.items() if k not in canonical_data or canonical_data[k] != v}
                        if _diff:
                            _ds = "\n".join([f"- {k}: {v.get('value','')}{v.get('unit','')} (口径: {v.get('caliber','不详')})" for k, v in _diff.items()])
                            prompt += f"\n\n## 实时更新规范数据（其他agent已完成）\n{_ds}\n"
                            prompt += "**注意**: 这些数据来自刚刚完成的其他agent，优先级高于前面列出的规范数据。"
                result = await call_llm(prompt=prompt, system_prompt=system_prompt)

                # M3: canonical enforcement after LLM output
                if result.get("success") and result.get("content") and canonical_data:
                    result["content"] = self._enforce_canonical_values(
                        result["content"], canonical_data
                    )

                # 日期验证
                if result.get("success") and result.get("content"):
                    validated = self._validate_output_dates(result["content"], self.agent_id)
                    if validated != result["content"]:
                        logger.warning(f"GenericAgent {self.agent_id}: 分析路径日期验证修正了年份")
                        result["content"] = validated

                # L4: Parse hypothesis verification results from analysis output
                if result.get("success") and result.get("content") and causal_hypotheses:
                    try:
                        _verified = self._parse_hypothesis_verification(result["content"], causal_hypotheses)
                        for _vh in _verified:
                            await self._shared_memory.write_canonical(
                                metric=f"hypothesis:{aspect}:{_vh.get('id', '')}",
                                value=_vh,
                                caliber="llm_inference",
                                source=self.agent_id,
                                publisher=aspect,
                            )
                    except Exception as _hyp_err:
                        logger.warning(f"GenericAgent {self.agent_id}: hypothesis verification parse failed: {_hyp_err}")

                # B2.1: Write cross-dimension claims to SharedMemory
                if result.get("success") and result.get("content") and self._shared_memory:
                    try:
                        _claims = await self._extract_claims_from_analysis(result["content"], aspect)
                        _caliber_map = {
                            "factual": "llm_inference_factual",
                            "inferential": "llm_inference",
                            "speculative": "llm_inference_speculative",
                        }
                        for _claim in _claims:
                            _caliber = _caliber_map.get(_claim.get("epistemic_level", "inferential"), "llm_inference")
                            # L5: Pre-write contradiction detection (agent layer)
                            if hasattr(self._shared_memory, 'get_all_canonical'):
                                _existing_claims = self._shared_memory.get_all_canonical()
                                for _ek, _ev in _existing_claims.items():
                                    if _ek.startswith("claim:") and isinstance(_ev.get("value"), dict):
                                        _contradiction = await self._detect_claim_contradiction(_ev["value"], _claim)
                                        if _contradiction:
                                            logger.warning(
                                                f"GenericAgent {self.agent_id}: CLAIM CONTRADICTION for "
                                                f"'{_ek}': {_contradiction}"
                                            )
                                            from src.core.orchestrator.aggregation.result_aggregator import ConflictRecord, ConflictResolution
                                            await self._shared_memory.write_canonical(
                                                metric=f"conflict:{_ek}",
                                                value={"contradiction": _contradiction, "claims": [_ev["value"].get("statement",""), _claim.get("statement","")]},
                                                caliber="llm_inference",
                                                source=self.agent_id,
                                                publisher=aspect,
                                            )
                            _claim_task_id = str(
                                self._context.get("task_id")
                                or self._context.get("session_id")
                                or "task_unknown"
                            )
                            _claim_chapter_id = str(
                                self._context.get("chapter_id")
                                or self.section_id
                                or "chapter_unknown"
                            )
                            _claim_section_id = str(
                                self._context.get("section_id") or aspect or "section_unknown"
                            )
                            await self._shared_memory.write_canonical(
                                metric=self._build_claim_canonical_key(
                                    _claim_task_id,
                                    _claim_chapter_id,
                                    _claim_section_id,
                                    str(_claim.get("id", "claim_unknown")),
                                ),
                                value=_claim,
                                caliber=_caliber,
                                source=self.agent_id,
                                publisher=aspect,
                            )
                    except Exception as _claim_err:
                        logger.warning(f"GenericAgent {self.agent_id}: claim extraction failed: {_claim_err}")

                # Iterative deepening: detect knowledge gaps and supplement
                if result.get("success") and result.get("content") and skill_registry:
                    gaps = self._detect_knowledge_gaps(result["content"])

                    # 语义级缺口检测（仅在启发式触发后运行）
                    if gaps:
                        semantic_gaps = await self._detect_semantic_gaps(result["content"])
                        gaps.extend(semantic_gaps)

                    if gaps:
                        logger.info(f"GenericAgent {self.agent_id}: detected {len(gaps)} knowledge gaps, performing supplementary search")
                        self._report_progress(f"分析内容知识检测完成{', 发现 '+str(len(gaps))+' 个缺口' if gaps else ', 无需补充'}", "analyzing")
                        supp_result = await self._supplementary_search_for_gaps(
                            topic=topic, aspect=aspect, gaps=gaps,
                            skill_registry=skill_registry,
                        )
                        if supp_result and supp_result.get("data_points"):
                            supplemental_points = []
                            for raw_point in supp_result["data_points"]:
                                if not isinstance(raw_point, dict):
                                    continue
                                point = dict(raw_point)
                                point.setdefault("source_agent_id", f"analysis_supplement:{self.agent_id}")
                                point.setdefault("section_id", _analysis_scope.section_id)
                                supplemental_points.append(point)
                            supplemental_points, _supplement_audit = _analysis_scope.select(supplemental_points)
                            new_data_points = list(aggregated_data_points) + supplemental_points
                            selected_urls = {
                                str(point.get("url") or point.get("source_url") or "").strip()
                                for point in supplemental_points
                                if isinstance(point, dict)
                            }
                            new_sources = list(aggregated_sources) + [
                                source for source in (supp_result.get("sources") or [])
                                if isinstance(source, dict)
                                and selected_urls
                                and str(source.get("url") or source.get("source_url") or "").strip() in selected_urls
                            ]
                            prompt2 = self._build_analysis_prompt_with_data(
                                topic=topic, aspect=aspect, aspects=aspects,
                                data_points=new_data_points, sources=new_sources,
                                core_question=core_question,
                                role_in_report=role_in_report,
                                sibling_aspects=sibling_aspects,
                                sub_aspects=self._context.get("sub_aspects"),
                                cross_dimension_claims=cross_dimension_claims,
                                causal_hypotheses=causal_hypotheses,
                                conflict_entries=_conflict_entries if self._shared_memory and hasattr(self._shared_memory, 'get_all_canonical') else {},
                                deep_mode_tables=task.get("deep_mode_tables", ""),
                            )
                            revised = await call_llm(prompt=prompt2, system_prompt=system_prompt)

                            # M3: canonical enforcement on revised content
                            if revised.get("success") and revised.get("content") and canonical_data:
                                revised["content"] = self._enforce_canonical_values(
                                    revised["content"], canonical_data
                                )

                            if revised.get("success") and revised.get("content"):
                                validated = self._validate_output_dates(revised["content"], self.agent_id)
                                if validated != revised["content"]:
                                    logger.warning(f"GenericAgent {self.agent_id}: 修订路径日期验证修正了年份")
                                    revised["content"] = validated
                                result = revised
                                aggregated_data_points = new_data_points
                                aggregated_sources = new_sources
                                logger.info(f"GenericAgent {self.agent_id}: analysis revised with supplementary data")
                                self._report_progress(f"补充搜索后修订完成，新增 {len(new_data_points)} 数据点", "analyzing")

                # 自评: 对生成内容进行质量评估
                max_self_eval = self.config.get("max_self_eval_iterations", 0)
                if max_self_eval > 0 and result.get("success") and result.get("content"):
                    content_text = result.get("content", "")
                    eval_result = await self._self_evaluate(content_text)
                    result["self_evaluation"] = eval_result
                    self._report_progress(f"分析内容自评完成，评分 {eval_result.get('score', 'N/A')}", "analyzing")

                if result.get("success"):
                    result["data_points"] = aggregated_data_points
                    result["sources"] = aggregated_sources
                    if task.get("evidence_scope"):
                        result["evidence_scope"] = task["evidence_scope"]
                return self._ensure_standard_result(result, action)
                    
            # M5-b: CALIBRATION - cross-agent numeric consistency check
            if agent_category == "calibration":
                self._report_progress("校准跨章节数值一致性...", "analyzing")
                all_results = task.get("parameters", {}).get("all_results", context.get("all_results", []))
                canonical_data = task.get("parameters", {}).get("canonical_data", context.get("canonical_data", {}))
                from src.core.prompts.calibration_prompt import (
                    CALIBRATION_SYSTEM_PROMPT,
                    CALIBRATION_USER_PROMPT_TEMPLATE,
                )
                all_sections = []
                for r in all_results:
                    agent_id = r.get("agent_id", "unknown")
                    section_content = r.get("content", "") or r.get("result", "")
                    status = "✓" if r.get("success") else "✗"
                    all_sections.append(f"[{status}] Agent {agent_id}:\n{section_content}")
                canonical_summary = "\n".join([
                    f"- {k}: {v.get('value','')}{v.get('unit','')}"
                    for k, v in canonical_data.items()
                ]) if canonical_data else "(no canonical data provided)"
                prompt = CALIBRATION_USER_PROMPT_TEMPLATE.format(
                    canonical_summary=canonical_summary,
                    all_sections_report="\n\n".join(all_sections) if all_sections else "(no sections to calibrate)",
                    target_currency=task.get("target_currency", "CNY"),
                )
                result = await call_llm(
                    prompt=prompt,
                    system_prompt=CALIBRATION_SYSTEM_PROMPT,
                )
                if result.get("success") and result.get("content"):
                    _cal_content = result["content"]
                    result["calibration_report"] = {"summary": _cal_content[:5000], "full_text": _cal_content}
                    _ref = {}
                    import re as _re
                    _json_block = _re.search(
                        r'```(?:json)\s*(\{.*?\})\s*```', _cal_content, _re.DOTALL
                    )
                    if _json_block:
                        import json as _json
                        try:
                            _parsed = _json.loads(_json_block.group(1))
                            if isinstance(_parsed, dict):
                                _ref = _parsed
                        except _json.JSONDecodeError:
                            pass
                    result["unified_data_reference"] = _ref
                return self._ensure_standard_result(result, action)
                    
            # Check if there is aggregated content from previous phases (synthesis agent path)
            aggregated_data_points = task.get("aggregated_data_points", [])
            aggregated_sources = task.get("aggregated_sources", [])
            aggregated_content = task.get("aggregated_content", [])
                    
            # 如果有前序数据，使用前序数据构建prompt
            if aggregated_data_points or aggregated_content:
                logger.info(f"GenericAgent {self.agent_id}: 接收到前序数据 - "
                           f"data_points={len(aggregated_data_points)}, "
                           f"sources={len(aggregated_sources)}, "
                           f"content={len(aggregated_content)}")
                        
                # 污染修复：从 task 获取 target_aspect
                target_aspect = task.get("target_aspect", "")
                        
                # 使用前序数据构建prompt
                prompt = self._build_synthesis_prompt_with_data(
                    topic=topic,
                    aspect=aspect,
                    aspects=aspects,
                    data_points=aggregated_data_points,
                    sources=aggregated_sources,
                    previous_content=aggregated_content,
                    target_aspect=target_aspect,
                    core_question=core_question,
                    role_in_report=role_in_report,
                    sibling_aspects=sibling_aspects,
                )
                        
                # S-FIX-3: inject canonical authority data into synthesis prompt
                _canonical_data_syn = task.get("canonical_data", {}) or {}
                # Filter to target currency
                _target_cur_syn = task.get("target_currency", "CNY")
                if _target_cur_syn and _canonical_data_syn:
                    _canonical_data_syn = {}
                    for _k, _v in dict(task.get("canonical_data", {})).items():
                        _sp = _k.split("_")
                        _sk_cur = _sp[2] if len(_sp) >= 3 else ""
                        if _sk_cur == _target_cur_syn or len(_sp) <= 2:
                            _canonical_data_syn[_k] = _v
                if _canonical_data_syn:
                    _cs = "\n".join([
                        f"- {k}: {v.get('value','')}{v.get('unit','')} "
                        f"(口径: {v.get('caliber','不详')})"
                        for k, v in _canonical_data_syn.items()
                    ])
                    prompt += f"\n\n## 全报告规范数据（跨章节一致性要求）\n{_cs}\n"
                    prompt += "\n**重要**: 所有章节中同一指标必须使用相同的值。如有差异，以上述规范数据为准。"
                # Final SharedMemory check before LLM call (same pattern as analysis path)
                if self._shared_memory and hasattr(self._shared_memory, 'get'):
                    _sm_latest = self._shared_memory.get("_canonical_registry", {})
                    if _sm_latest:
                        _tmp = {}
                        for k, v in _sm_latest.items():
                            _pk = parse_entry_key(k)
                            if not _pk["currency"] or _pk["currency"] == _target_cur_syn:
                                _tmp[k] = v
                        _sm_latest = _tmp
                    if _sm_latest and _sm_latest != _canonical_data_syn:
                        _diff = {k: v for k, v in _sm_latest.items() if k not in _canonical_data_syn or _canonical_data_syn[k] != v}
                        if _diff:
                            _ds = "\n".join([f"- {k}: {v.get('value','')}{v.get('unit','')}" for k, v in _diff.items()])
                            prompt += f"\n\n## 实时更新规范数据\n{_ds}\n"
                        
                # 执行LLM分析（知识富集存在时注入system_prompt）
                enrichment = getattr(self, '_knowledge_enrichment', {})
                if enrichment.get("entities") or enrichment.get("methodologies"):
                    system_prompt = self._get_professional_role_prompt(aspect)
                    self._report_progress(f"Generating analysis for {aspect or topic}...", "writing")
                    result = await call_llm(prompt=prompt, system_prompt=system_prompt)
                else:
                    self._report_progress(f"Generating analysis for {aspect or topic}...", "writing")
                    result = await call_llm(prompt=prompt)

                # M3: canonical enforcement on synthesis output
                if result.get("success") and result.get("content") and _canonical_data_syn:
                    result["content"] = self._enforce_canonical_values(
                        result["content"], _canonical_data_syn
                    )

                # 日期验证
                if result.get("success") and result.get("content"):
                    validated = self._validate_output_dates(result["content"], self.agent_id)
                    if validated != result["content"]:
                        logger.warning(f"GenericAgent {self.agent_id}: 合成路径日期验证修正了年份")
                        result["content"] = validated
                        
                # 将前序数据传递到结果中
                if result.get("success"):
                    result["data_points"] = aggregated_data_points
                    result["sources"] = aggregated_sources
                    result["previous_content"] = aggregated_content
                    logger.info(f"GenericAgent {self.agent_id}: 传递前序数据到结果")
                            
                    # **输出过滤**：检测并清理污染内容
                    output_content = result.get("content", "")
                    if output_content:
                        # 构建输入内容列表（用于污染检测）
                        input_texts = []
                        for pc in aggregated_content:
                            if pc.get("content"):
                                input_texts.append(pc["content"])
                        for dp in aggregated_data_points:
                            if dp.get("content"):
                                input_texts.append(dp["content"])
                                
                        # 执行过滤
                        filtered_content = self._filter_output_contamination(
                            output_content=output_content,
                            input_contents=input_texts,
                            similarity_threshold=0.7,
                            min_contamination_length=50,
                        )
                                
                        # 如果过滤后内容有变化，记录日志
                        if filtered_content != output_content:
                            original_len = len(output_content)
                            filtered_len = len(filtered_content)
                            logger.info(
                                f"GenericAgent {self.agent_id}: 输出污染过滤完成，"
                                f"原始长度={original_len}，过滤后长度={filtered_len}，"
                                f"移除={original_len - filtered_len}字符"
                            )
                            result["content"] = filtered_content
                                    
                            # 提取污染来源（用于调试）
                            contamination_sources = self._extract_contamination_sources(
                                output_content=output_content,
                                input_contents=aggregated_content,
                                key_field="content",
                                similarity_threshold=0.6,
                            )
                            if contamination_sources:
                                logger.warning(
                                    f"GenericAgent {self.agent_id}: 检测到污染来源: {contamination_sources}"
                                )
                        
                return self._ensure_standard_result(result, action)
                    
            # synthesis类型agent（执行摘要、研究结论）无前序数据时拒绝生成
            if aspect in aspects and (aspect.lower() in {"summary", "结论", "摘要", "执行摘要", "研究结论"}):
                logger.warning(f"GenericAgent {self.agent_id}: 综合分析agent无前序数据，拒绝生成虚假内容")
                return self._ensure_standard_result({
                    "success": False,
                    "error": f"无法生成{aspect}：核心研究章节未产出有效数据",
                    "content": "",
                    "agent_id": self.agent_id,
                }, action)
                    
            # 深度研究：先搜索再分析
            _has_doc_data_dp = bool(self._context.get("document_context") or self._context.get("has_preloaded_data") or task.get("document_context"))
            if topic and "search_skill" in available_skills and not _has_doc_data_dp:
                search_results = await self._do_deep_research(
                    topic=topic,
                    aspect=aspect,
                    aspects=aspects,
                    skill_registry=skill_registry,
                )
                if search_results:
                    _n = sum(len(s.get('results', [])) for s in search_results.get('searches', []))
                    self._report_progress(f"搜索完成，获取 {_n} 条结果", "searching")
                        
                # 构建包含搜索结果的 prompt
                if search_results:
                    prompt = self._build_research_prompt_with_data(
                        topic=topic,
                        aspect=aspect,
                        aspects=aspects,
                        search_results=search_results,
                    )
                else:
                    # 搜索失败，回退到纯 LLM
                    prompt = self._build_basic_research_prompt(topic, aspect, aspects)
            else:
                prompt = self._build_basic_research_prompt(topic, aspect, aspects)
                    
            # 防御性检查：确保prompt不为空
            if not prompt or not prompt.strip():
                logger.error(f"GenericAgent {self.agent_id}: prompt为空，无法执行LLM任务")
                return {
                    "success": False,
                    "error": "prompt 不能为空",
                    "agent_id": self.agent_id,
                    "action": action,
                    "topic": topic,
                    "aspect": aspect,
                }
                    
            # 根据章节类型选择专业角色
            system_prompt = self._get_professional_role_prompt(aspect)
                    
            result = await call_llm(prompt=prompt, system_prompt=system_prompt)
                    
            # 修复1: 清理LLM输出中的prompt残留文字
            if result.get("success") and result.get("content"):
                cleaned = self._clean_llm_output(result["content"])
                if cleaned != result["content"]:
                    logger.info(f"GenericAgent {self.agent_id}: 清理prompt残留，减少{len(result['content'])-len(cleaned)}字符")
                    result["content"] = cleaned
                        
                # 日期验证：强制校验LLM输出中的年份引用
                validated = self._validate_output_dates(result["content"], self.agent_id)
                if validated != result["content"]:
                    logger.warning(f"GenericAgent {self.agent_id}: 日期验证修正了输出中的年份")
                    result["content"] = validated
                    result["date_corrections_applied"] = True
                        
                # **输出过滤**：检测并清理与搜索结果的重复内容
                # 只有当有搜索结果时才执行过滤
                if search_results:
                    # 提取搜索结果内容作为输入参考
                    input_texts = []
                    for search in search_results.get("searches", []):
                        for item in search.get("results", []):
                            body = item.get("body", "") or item.get("snippet", "")
                            if body:
                                input_texts.append(body)
                            
                    if input_texts:
                        filtered_content = self._filter_output_contamination(
                            output_content=result["content"],
                            input_contents=input_texts,
                            similarity_threshold=0.7,
                            min_contamination_length=50,
                        )
                                
                        if filtered_content != result["content"]:
                            original_len = len(result["content"])
                            filtered_len = len(filtered_content)
                            logger.info(
                                f"GenericAgent {self.agent_id}: 输出污染过滤完成，"
                                f"原始长度={original_len}，过滤后长度={filtered_len}，"
                                f"移除={original_len - filtered_len}字符"
                            )
                            result["content"] = filtered_content
                    
            # 调试日志：记录 LLM 返回结果
            logger.info(f"GenericAgent {self.agent_id}: LLM 返回成功={result.get('success')}")
            if result.get("success"):
                content_len = len(result.get("content", ""))
                logger.info(f"GenericAgent {self.agent_id}: 内容长度={content_len} 字符")
                        
                # P0-3修复：生成数据图表（ChartPlannerAgent）
                charts = await self._generate_charts_from_content(
                    content=result.get("content", ""),
                    topic=topic,
                    aspect=aspect,
                )
                if charts:
                    result["charts"] = charts
                    logger.info(f"GenericAgent {self.agent_id}: 生成了 {len(charts)} 张图表")
                    
            # **关键修复**：将搜索数据添加到返回结果中
            # 这是数据传递链路断裂的根本原因！
            if search_results:
                # 提取data_points（搜索结果列表）
                data_points = []
                sources = []
                for search in search_results.get("searches", []):
                    for item in search.get("results", []):
                        evidence = self._evidence_metadata(item)
                        data_points.append({
                            "title": item.get("title", ""),
                            "content": item.get("body", "") or item.get("snippet", ""),
                            "url": item.get("href", "") or item.get("url", ""),
                            "quality_score": item.get("quality_score", 0),
                            "credibility": item.get("credibility", "unknown"),
                            **evidence,
                        })
                        sources.append({
                            "title": item.get("title", ""),
                            "url": item.get("href", "") or item.get("url", ""),
                            "type": "web",
                            "quality_score": item.get("quality_score", 0),
                            **evidence,
                        })
                        
                result["data_points"] = data_points
                result["sources"] = sources
                result["total_sources"] = search_results.get("total_sources", 0)
                result["quality_stats"] = search_results.get("quality_stats", {})
                        
                logger.info(f"GenericAgent {self.agent_id}: 添加搜索数据到结果 - "
                           f"data_points={len(data_points)}, sources={len(sources)}")
                    
            # 确保返回标准格式
            return self._ensure_standard_result(result, action)
        
        # 回退：尝试直接用 action 作为 skill_name
        if action in available_skills and skill_registry:
            skill = skill_registry.get(action)
            if skill:
                result = await skill.execute(**parameters)
                return self._ensure_standard_result(result, action)
        
        # 动态发现：尝试智能匹配 Skills（含分析 skill）
        if skill_registry and action not in ["", "default"]:
            discovered = skill_registry.discover_skills(action, auto_load=True)
            for skill_name in discovered:
                skill = skill_registry.get(skill_name)
                if skill:
                    self.add_skill(skill_name)
                    result = await skill.execute(**parameters)
                    return self._ensure_standard_result(result, action)
        
        # LLM fallback: call_llm() for unhandled actions (no longer a skill).
        # P0-3: Before generating, attempt a search so we have real data,
        # not just LLM training-cutoff knowledge.
        if True:  # always available as intrinsic capability
            logger.info(f"GenericAgent {self.agent_id}: LLM fallback for action '{action}'")
            # Extract topic/aspect from Agent context or task
            context = self._context or {}
            topic = context.get("topic") or task.get("topic", "")
            aspect = context.get("aspect") or task.get("aspect", "")
            aspects = task.get("aspects", [])

            # Normalise topic to string
            if hasattr(topic, 'topic'):
                topic = topic.topic
            if not isinstance(topic, str):
                topic = str(topic) if topic else ""
            if not isinstance(aspect, str):
                aspect = str(aspect) if aspect else ""

            # P0-3: Attempt search before pure LLM generation.
            # Even though we reached the fallback path, the registry may
            # still have search_skill available — use it to get real data.
            search_results = None
            _has_doc_data_fb = bool(self._context.get("document_context") or self._context.get("has_preloaded_data") or task.get("document_context"))
            if topic and skill_registry and not _has_doc_data_fb:
                search_skill = self._get_search_skill(skill_registry)
                if search_skill:
                    try:
                        logger.info(
                            f"GenericAgent {self.agent_id}: fallback attempting "
                            f"search for topic='{topic[:50]}...'"
                        )
                        search_results = await self._do_deep_research(
                            topic=topic,
                            aspect=aspect,
                            aspects=aspects,
                            skill_registry=skill_registry,
                        )
                    except Exception as search_err:
                        logger.warning(
                            f"GenericAgent {self.agent_id}: fallback search failed: {search_err}"
                        )
                        search_results = None

            # Build prompt — enriched with search results if available
            if search_results and search_results.get("searches"):
                prompt = self._build_research_prompt_with_data(
                    topic=topic,
                    aspect=aspect,
                    aspects=aspects,
                    search_results=search_results,
                )
                logger.info(
                    f"GenericAgent {self.agent_id}: fallback prompt built "
                    f"from {search_results.get('total_sources', 0)} search results"
                )
            elif topic:
                _fb_date = datetime.now().strftime("%Y-%m-%d")
                if aspect:
                    prompt = (
                        f"[SYSTEM DATE: {_fb_date}]\n\n"
                        f"请基于以下搜索数据进行深度研究分析。\n\n"
                        f"研究主题：{topic}\n"
                        f"重点关注维度：{aspect}\n\n"
                        f"请提供详细的分析结果，包括关键发现、数据支持和结论。\n"
                        f"注意：如果未提供搜索数据，请明确说明数据来源于模型知识而非实时搜索。\n"
                        f"重要：当前真实日期为 {_fb_date}，所有年份引用必须与此一致。"
                    )
                elif aspects:
                    aspects_str = "、".join([a for a in aspects if a])
                    prompt = (
                        f"[SYSTEM DATE: {_fb_date}]\n\n"
                        f"请基于以下搜索数据进行深度研究分析。\n\n"
                        f"研究主题：{topic}\n"
                        f"需要分析的维度：{aspects_str}\n\n"
                        f"请逐一分析每个维度，提供详细的研究发现和结论。\n"
                        f"注意：如果未提供搜索数据，请明确说明数据来源于模型知识而非实时搜索。\n"
                        f"重要：当前真实日期为 {_fb_date}，所有年份引用必须与此一致。"
                    )
                else:
                    prompt = (
                        f"[SYSTEM DATE: {_fb_date}]\n\n"
                        f"请研究并分析以下主题：{topic}\n\n"
                        f"请提供全面的分析，包括背景、现状、关键因素和未来趋势。\n"
                        f"注意：如果未提供搜索数据，请明确说明数据来源于模型知识而非实时搜索。\n"
                        f"重要：当前真实日期为 {_fb_date}，所有年份引用必须与此一致。"
                    )
            else:
                prompt = parameters.get(
                    "prompt",
                    f"执行任务: {action}\n参数: {parameters}"
                )

            result = await call_llm(prompt=prompt)

            # 日期验证
            if result.get("success") and result.get("content"):
                validated = self._validate_output_dates(result["content"], self.agent_id)
                if validated != result["content"]:
                    logger.warning(f"GenericAgent {self.agent_id}: fallback路径日期验证修正了年份")
                    result["content"] = validated

            # P0-3: Attach search data to result so downstream
            # quality checks and synthesis agents can access sources.
            if search_results:
                data_points = []
                sources = []
                for search in search_results.get("searches", []):
                    for item in search.get("results", []):
                        evidence = self._evidence_metadata(item)
                        data_points.append({
                            "title": item.get("title", ""),
                            "content": item.get("body", "") or item.get("snippet", ""),
                            "url": item.get("href", "") or item.get("url", ""),
                            "quality_score": item.get("quality_score", 0),
                            "credibility": item.get("credibility", "unknown"),
                            **evidence,
                        })
                        sources.append({
                            "title": item.get("title", ""),
                            "url": item.get("href", "") or item.get("url", ""),
                            "type": "web",
                            "quality_score": item.get("quality_score", 0),
                            **evidence,
                        })
                result["data_points"] = data_points
                result["sources"] = sources
                result["total_sources"] = search_results.get("total_sources", 0)
                result["quality_stats"] = search_results.get("quality_stats", {})
                logger.info(
                    f"GenericAgent {self.agent_id}: fallback enriched with "
                    f"{len(data_points)} data_points, {len(sources)} sources"
                )

                return self._ensure_standard_result(result, action)
        
        # 没有匹配的Skill
        logger.warning(f"GenericAgent {self.agent_id}: 无匹配Skill, action={action}, available={available_skills}")
        
        return {
            "success": False,
            "error": f"Agent {self.agent_id} 无法处理任务: {action}, 可用技能: {available_skills}",
            "message": f"Agent {self.agent_id} 无法处理任务: {action}",
            "agent_id": self.agent_id,
            "agent_name": self.config.get("name", self.agent_id),
            "action": action,
            "available_skills": available_skills,
        }
    
    async def _execute_mcp(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute an MCP tool call.
        
        MCP is a protocol layer, not a skill. This method routes the request
        to the MCPProtocolHandler, which discovers the right server and returns
        raw data. No format conversion is performed — the LLM downstream handles
        interpretation.
        
        Args:
            parameters: Must contain:
                - tool: fully qualified tool name (e.g., "wind.get_stock_data")
                - params: tool parameters dict
        
        Returns:
            Dict with raw MCP result or error information
        """
        mcp_handler = self.config.get("mcp_handler")
        if not mcp_handler:
            return {
                "success": False,
                "error": "MCP handler not available",
                "error_code": "mcp_handler_unavailable",
            }
        
        tool = parameters.get("tool", "")
        params = parameters.get("params", {})
        
        if not tool:
            return {
                "success": False,
                "error": "MCP tool name is required",
                "error_code": "missing_tool",
            }
        
        result = await mcp_handler.execute(tool, params)
        
        if result.get("success"):
            # Inject raw MCP data into parameters for LLM consumption
            # The LLM downstream handles format transformation naturally
            parameters["mcp_data"] = result.get("result")
            parameters["mcp_source"] = tool
        else:
            parameters["mcp_error"] = result.get("error")
            parameters["mcp_error_code"] = result.get("error_code")
            parameters["mcp_fallback"] = True
        
        # Continue to LLM processing with enriched context
        return await self.execute({
            "action": "llm",
            "parameters": parameters,
            "topic": self._context.get("topic", ""),
            "aspect": self._context.get("aspect", ""),
        })
    
    def add_skill(self, skill_name: str) -> bool:
        """Dynamically add a skill to _available_skills with registry validation and session sync."""
        if skill_name not in self._available_skills:
            if self._skill_registry and self._skill_registry.get(skill_name) is None:
                logger.warning(
                    f"GenericAgent {self.agent_id}: cannot add skill '{skill_name}', "
                    f"not found in registry"
                )
                return False
            self._available_skills.append(skill_name)
            if self._session and hasattr(self._session, 'agent_template') and self._session.agent_template:
                template = self._session.agent_template
                if "skill_names" in template:
                    if skill_name not in template["skill_names"]:
                        template["skill_names"].append(skill_name)
            logger.info(f"GenericAgent {self.agent_id}: dynamically added skill '{skill_name}'")
            return True
        return False

    async def _handle_preloaded_forensic(self, annual_report_data: dict, action: str):
        """C11: Forensic mode preloaded path — precise extraction by hypothesis data needs."""
        try:
            from src.skills.analysis.annual_report_parser import AnnualReportParserSkill
            parser = AnnualReportParserSkill()
            data_needs = self._context.get("hypothesis_data_needs", [])
            hypothesis = self._context.get("core_question", "")
            extracted = parser.extract_for_hypothesis(annual_report_data, hypothesis, data_needs)
            data_points = []
            for sec in extracted.get("relevant_sections", []):
                data_points.append({
                    "title": sec.get("title", ""),
                    "content": sec.get("content", "")[:4000],
                    "source": "annual_report_pdf",
                    "type": sec.get("section_type", "document"),
                    "relevance": "hypothesis_match",
                })
            for item in extracted.get("relevant_line_items", []):
                data_points.append({
                    "title": f"{item['table_type']} - {item['row'].get('科目', '')}",
                    "content": str(item["row"]),
                    "source": "annual_report_pdf_table",
                    "type": "structured_data",
                    "relevance": "hypothesis_match",
                })
            self._report_progress(f"Delivered {len(data_points)} forensic data points for hypothesis: {hypothesis[:50]}", "data_delivery")
            return self._ensure_standard_result({
                "success": True,
                "content": json.dumps(data_points, ensure_ascii=False),
                "data_points": data_points,
                "sources": [{"title": "Annual Report PDF", "url": "", "type": "document"}],
                "agent_id": self.agent_id,
            }, action)
        except Exception as e:
            logger.warning(f"GenericAgent {self.agent_id}: forensic preloaded extraction failed, falling back to standard preloaded: {e}")
            return None

    def _ensure_standard_result(self, result: Dict[str, Any], action: str) -> Dict[str, Any]:
        """
        确保返回标准格式结果
        
        支持多种Skill返回格式的统一化：
        - Intrinsic LLM: {content, model, usage}
        - Search Skill: {results, query, total}
        - HTTP Skill: {status_code, body}
        - Web Scraper: {text, title, url}
        - File Skill: {content, filepath}
        
        Args:
            result: Skill返回的原始结果
            action: 执行的动作
            
        Returns:
            标准格式的结果字典，包含 success, result, agent_id 等字段
        """
        if result is None:
            return {
                "success": False,
                "error": "Skill returned None",
                "agent_id": self.agent_id,
                "action": action,
            }
        
        # 确保是字典
        if not isinstance(result, dict):
            return {
                "success": True,
                "result": result,
                "agent_id": self.agent_id,
                "action": action,
            }
        
        # 确保包含success字段
        if "success" not in result:
            result["success"] = True
        
        # 定义结果字段映射（按优先级）
        RESULT_FIELDS = [
            # 标准字段
            ("result", "result"),
            ("content", "result"),
            ("output", "result"),
            ("data", "result"),
            # Skill特定字段
            ("results", "result"),      # SearchSkill
            ("body", "result"),         # HTTPSkill
            ("text", "result"),         # WebScraperSkill
            ("analysis", "result"),     # 分析结果
            ("findings", "result"),     # 研究发现
            ("summary", "result"),      # 摘要
        ]
        
        # 确保成功结果包含result字段（验证器可能要求）
        if result.get("success") and "result" not in result:
            # 按优先级尝试各种字段
            for source_field, target_field in RESULT_FIELDS:
                if source_field in result and result[source_field]:
                    value = result[source_field]
                    
                    # 处理列表类型（如SearchSkill的results）
                    if isinstance(value, list):
                        # 将列表转换为文本格式
                        if source_field == "results":
                            # 搜索结果格式化
                            formatted = []
                            sources = []  # P0-3修复：收集来源信息
                            for item in value:
                                if isinstance(item, dict):
                                    title = item.get("title", "")
                                    snippet = item.get("body", "") or item.get("snippet", "") or item.get("content", "")
                                    url = item.get("href", "") or item.get("url", "")
                                    if title:
                                        formatted.append(f"### {title}")
                                    if snippet:
                                        formatted.append(snippet[:300])
                                    if url:
                                        formatted.append(f"来源: {url}")
                                        # P0-3修复：收集来源
                                        sources.append({
                                            "title": title,
                                            "url": url,
                                            "type": "web",
                                            **self._evidence_metadata(item),
                                        })
                                    formatted.append("")
                            result[target_field] = "\n".join(formatted)
                            # P0-3修复：保留来源信息作为结构化数据
                            if sources:
                                result["sources"] = sources
                        else:
                            # 其他列表直接存储
                            result[target_field] = value
                    elif isinstance(value, dict):
                        # 字典类型，存储原值
                        result[target_field] = value
                    elif isinstance(value, str):
                        result[target_field] = value
                    else:
                        result[target_field] = str(value)
                    
                    break  # 找到第一个有效字段后停止
            
            # 如果仍未找到，将整个结果作为result（排除元数据和charts）
            # Note: charts保留在顶层，不放入result子字典
            if "result" not in result:
                result["result"] = {
                    k: v for k, v in result.items() 
                    if k not in ["success", "message", "error", "agent_id", "action", "charts", "data_points", "sources"]
                }
        
        # 确保包含agent_id
        if "agent_id" not in result:
            result["agent_id"] = self.agent_id
        
        # 添加action信息
        if "action" not in result:
            result["action"] = action
        
        # 将 agent 的 category 写入结果，供 _build_report_task 识别章节类型
        if "category" not in result:
            _cat = self.config.get("category", "")
            if _cat:
                result["category"] = _cat
            
        return result

    async def _extract_claims_from_analysis(
        self, analysis_content: str, aspect: str
    ) -> List[Dict]:
        """Extract structured claims from analysis output for cross-dimension sharing.
        
        L1: Each claim is annotated with epistemic_level (factual/inferential/speculative)
        and falsification condition. Rule-based validation enforces consistency.
        L1-C: Paragraph-level sliding window preserves key middle conclusions.
        L1-D: Dimension-level epistemic ceiling prevents misclassification.
        """
        if len(analysis_content) > 3000:
            _paragraphs = [p for p in analysis_content.split("\n\n") if p.strip()]
            if len(_paragraphs) <= 5:
                _truncated = analysis_content[:2500] + "\n\n...[中间省略]...\n\n" + analysis_content[-500:]
            else:
                _head = "\n\n".join(_paragraphs[:2])
                _tail = "\n\n".join(_paragraphs[-2:])
                _key_patterns = ["结论", "发现", "验证", "结果", "综上", "因此", "表明", "证明"]
                _mid_candidates = []
                for p in _paragraphs[2:-2]:
                    if any(kw in p for kw in _key_patterns):
                        _mid_candidates.append(p)
                _mid = "\n\n".join(_mid_candidates[:2]) if _mid_candidates else ""
                _parts = [_head]
                if _mid:
                    _parts.append("...[关键中间段落]...")
                    _parts.append(_mid)
                _parts.append("...[中间省略]...")
                _parts.append(_tail)
                _truncated = "\n\n".join(_parts)
                if len(_truncated) > 3000:
                    _truncated = analysis_content[:2500] + "\n\n...[中间省略]...\n\n" + analysis_content[-500:]
        else:
            _truncated = analysis_content

        claim_prompt = f"""从以下「{aspect}」分析中提取核心结论（claim）。
每个 claim 必须包含：
1. statement：一句话结论
2. confidence：HIGH/MEDIUM/LOW
3. 前提条件：什么条件下此结论成立
4. 跨维度影响：此结论会影响哪些其他维度
5. epistemic_level：事实性(factual)/推断性(inferential)/推测性(speculative)
   - factual：有直接数据支撑的事实陈述，如"2025年Q1市场份额为32%"
   - inferential：基于事实的逻辑推断，有间接支撑，如"份额下降趋势暗示竞争加剧"
   - speculative：推测性判断，缺乏直接数据支撑，如"企业可能通过并购寻求突破"
6. falsification：什么条件下此结论会被推翻

示例：
[{{"statement":"2025年Q1市场份额为32%", "confidence":"HIGH", "前提条件":"数据来源可靠", "cross_impact":["竞争格局"], "epistemic_level":"factual", "falsification":"数据源修正时"}}]
[{{"statement":"份额下降趋势暗示竞争加剧", "confidence":"MEDIUM", "前提条件":"份额数据准确", "cross_impact":["战略意图"], "epistemic_level":"inferential", "falsification":"若份额下降由行业整体萎缩导致而非竞争加剧"}}]
[{{"statement":"企业可能通过并购寻求突破", "confidence":"LOW", "前提条件":"行业整合趋势持续", "cross_impact":["投资建议"], "epistemic_level":"speculative", "falsification":"若未来6个月无并购公告则推断不成立"}}]

分析内容：
{_truncated}

输出JSON数组，最多5个claim。格式：
[{{"statement":"...", "confidence":"HIGH/MEDIUM/LOW", "前提条件":"...", "cross_impact":["维度1"], "epistemic_level":"factual/inferential/speculative", "falsification":"..."}}]"""

        result = await call_llm(
            prompt=claim_prompt,
            system_prompt="你只输出JSON数组，不要其他文字。"
        )
        if result.get("success") and result.get("content"):
            try:
                import json as _json
                content = result["content"]
                match = re.search(r'\[.*\]', content, re.DOTALL)
                if match:
                    claims = _json.loads(match.group())
                    ASPECT_EPISTEMIC_CEILING = {
                        "strategic_intent": "speculative",
                        "战略意图": "speculative",
                        "战略意图推断": "speculative",
                        "Strategic Intent": "speculative",
                    }
                    _epistemic_order = {"factual": 0, "inferential": 1, "speculative": 2}
                    _ceiling = ASPECT_EPISTEMIC_CEILING.get(aspect, None)
                    _speculative_words = {"可能", "预计", "或许", "也许", "大概", "猜测", "推测", "预期"}
                    for i, c in enumerate(claims):
                        c["id"] = str(i)
                        c["source_aspect"] = aspect
                        if "epistemic_level" not in c:
                            c["epistemic_level"] = "inferential"
                        _level = c.get("epistemic_level", "inferential")
                        if _level not in _epistemic_order:
                            c["epistemic_level"] = "inferential"
                            _level = "inferential"
                        if c.get("confidence") == "LOW" and c.get("前提条件") and _level == "factual":
                            c["epistemic_level"] = "inferential"
                            _level = "inferential"
                        _stmt = c.get("statement", "")
                        if _level == "factual" and any(w in _stmt for w in _speculative_words):
                            c["epistemic_level"] = "inferential"
                            _level = "inferential"
                        if _ceiling and _epistemic_order.get(_level, 1) < _epistemic_order.get(_ceiling, 1):
                            c["epistemic_level"] = _ceiling
                        c.setdefault("falsification", "未指定证伪条件")
                    return claims[:5]
            except Exception:
                pass
        return []

    def _parse_causal_hypotheses(self, content: str) -> List[Dict]:
        """Parse causal hypotheses from LLM output.

        Expected format per line: 假设：[因果陈述] | 验证数据：[需要什么数据] | 传导：[影响哪些维度] | 反面假设：[对立因果陈述]
        """
        hypotheses = []
        for line in content.strip().split("\n"):
            line = line.strip()
            if not line or "|" not in line:
                continue
            parts = line.split("|")
            h = {}
            for part in parts:
                part = part.strip()
                if part.startswith("假设：") or part.startswith("假设:"):
                    h["statement"] = part.split("：", 1)[-1].split(":", 1)[-1].strip()
                elif part.startswith("验证数据：") or part.startswith("验证数据:"):
                    h["verification_data"] = part.split("：", 1)[-1].split(":", 1)[-1].strip()
                elif part.startswith("传导：") or part.startswith("传导:"):
                    h["transmission"] = part.split("：", 1)[-1].split(":", 1)[-1].strip()
                elif part.startswith("反面假设：") or part.startswith("反面假设:"):
                    h["counter_hypothesis"] = part.split("：", 1)[-1].split(":", 1)[-1].strip()
            if h.get("statement"):
                h["status"] = "unverified"
                hypotheses.append(h)
        return hypotheses[:5]

    def _parse_hypothesis_verification(self, content: str, hypotheses: List[Dict]) -> List[Dict]:
        """L4: Parse hypothesis verification results from analysis output.
        
        Expected format (pipe-delimited):
        假设验证结果：
        假设1：验证 | 依据：数据支撑... | 反面假设可能性：低
        假设2：修正 | 依据：部分成立 | 修正内容：... | 反面假设可能性：中
        假设3(新)：[陈述] | 验证|修正|推翻 | 依据：... | 反面假设可能性：高
        """
        import hashlib as _hashlib
        import re as _re
        verified = []
        verification_section = ""
        
        markers = ["假设验证结果", "假设验证结果：", "数据验证结果", "数据验证结果：", "前瞻验证结果", "前瞻验证结果：", "假设敏感性检验", "假设敏感性检验：", "验证结果"]
        for marker in markers:
            if marker in content:
                idx = content.index(marker)
                verification_section = content[idx:]
                break
        
        if not verification_section:
            for h in hypotheses:
                h_copy = dict(h)
                h_copy["status"] = "unverified"
                h_copy["id"] = _hashlib.md5(h.get("statement", "").encode()).hexdigest()[:8]
                verified.append(h_copy)
            return verified
        
        for i, h in enumerate(hypotheses):
            h_copy = dict(h)
            h_copy["id"] = _hashlib.md5(h.get("statement", "").encode()).hexdigest()[:8]
            
            pattern = f"假设{i+1}"
            if pattern in verification_section:
                matching_lines = [line for line in verification_section.split("\n")
                                  if pattern in line and "|" in line and "(新)" not in line]
                if matching_lines:
                    line = matching_lines[-1]
                    line_parts = line.split("|")
                    judgment_part = line_parts[0].strip()
                    
                    if any(kw in judgment_part for kw in ["验证", "证实", "verified", "confirmed"]):
                        h_copy["status"] = "verified"
                    elif any(kw in judgment_part for kw in ["修正", "修订", "revised", "modified", "部分"]):
                        h_copy["status"] = "revised"
                        if len(line_parts) > 2:
                            h_copy["revision_note"] = line_parts[-1].strip().replace("修正内容：", "").replace("修正内容:", "")
                    elif any(kw in judgment_part for kw in ["推翻", "否定", "refuted", "rejected", "不成立"]):
                        h_copy["status"] = "refuted"
                    else:
                        h_copy["status"] = "unverified"
                    
                    for lp in line_parts:
                        lp = lp.strip()
                        if lp.startswith("反面假设可能性：") or lp.startswith("反面假设可能性:"):
                            h_copy["counter_possibility"] = lp.split("：", 1)[-1].split(":", 1)[-1].strip()
                else:
                    h_copy["status"] = "unverified"
            else:
                h_copy["status"] = "unverified"
            
            verified.append(h_copy)
        
        new_hyp_pattern = _re.compile(r'假设(\d+)\s*\(新\)\s*[：:]\s*(.+?)(?:\s*\||$)')
        for line in verification_section.split("\n"):
            m = new_hyp_pattern.search(line)
            if m and "|" in line:
                line_parts = line.split("|")
                new_h = {"id": f"new_{m.group(1)}", "source": "agent_generated", "statement": m.group(2).strip()}
                for lp in line_parts:
                    lp = lp.strip()
                    if lp.startswith("依据：") or lp.startswith("依据:"):
                        new_h["evidence"] = lp.split("：", 1)[-1].split(":", 1)[-1].strip()
                    elif lp.startswith("反面假设可能性：") or lp.startswith("反面假设可能性:"):
                        new_h["counter_possibility"] = lp.split("：", 1)[-1].split(":", 1)[-1].strip()
                
                full_line = line
                if any(kw in full_line for kw in ["修正", "修订", "部分"]):
                    new_h["status"] = "revised"
                elif any(kw in full_line for kw in ["推翻", "否定", "不成立"]):
                    new_h["status"] = "refuted"
                elif any(kw in full_line for kw in ["验证", "证实"]):
                    new_h["status"] = "verified"
                else:
                    new_h["status"] = "unverified"
                
                if new_h.get("statement"):
                    verified.append(new_h)
        
        return verified

    def _heuristic_cognitive_type(self, aspect: str):
        _SIGNALS = {
            "inference_driven": [
                "投资", "战略", "建议", "策略", "研判", "意图", "决策", "配置",
                "invest", "strateg", "advice", "recommend", "intent", "decision", "allocat",
            ],
            "forward_looking": [
                "趋势", "前景", "技术", "政策", "法规", "展望", "预测", "路线", "演进",
                "trend", "outlook", "forecast", "predict", "policy", "regulat", "roadmap", "evolution",
            ],
            "assessment_driven": [
                "估值", "风险", "财务", "评分", "评级", "敏感性", "压力测试",
                "valuat", "risk", "financ", "scor", "rat", "sensitiv", "stress",
            ],
        }
        aspect_lower = aspect.lower()
        scores = {}
        for ctype, keywords in _SIGNALS.items():
            scores[ctype] = sum(1 for kw in keywords if kw in aspect or kw in aspect_lower)
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else None

    async def infer_cognitive_type(self, aspect: str, topic: str = "") -> str:
        cache_key = f"cog_type:{aspect}:{topic}"
        cached = self._context.get(cache_key)
        if cached:
            return cached

        valid_types = {"fact_driven", "inference_driven", "forward_looking", "assessment_driven"}
        inferred = None
        method_used = "none"

        try:
            result = await call_llm(
                prompt=f"""Classify the following research aspect into a cognitive type. Output ONLY the type name.

Research Topic: {topic}
Research Aspect: {aspect}

Cognitive type definitions:
- fact_driven: Describe current state, quantify facts (e.g., Market Size, Competitive Landscape, Industry Chain, 市场规模, 竞争格局, 产业链)
- inference_driven: Derive conclusions, guide action (e.g., Investment Advice, Strategic Judgment, 投资建议, 战略研判)
- forward_looking: Predict future, prospective analysis (e.g., Technology Trends, Policy & Regulation, 技术趋势, 政策法规)
- assessment_driven: Quantify & evaluate under conditions (e.g., Valuation, Risk Analysis, 估值分析, 风险分析)

Output ONE type name only: fact_driven / inference_driven / forward_looking / assessment_driven""",
                system_prompt="You are a research methodology expert.",
                max_tokens=50,
                temperature=0.0,
            )
            content = result.get("content", "").strip().lower()
            _matches = [(content.rfind(vt), vt) for vt in valid_types if vt in content]
            if _matches:
                inferred = max(_matches, key=lambda x: x[0])[1]
                method_used = "llm_full"
        except Exception as e:
            logger.warning(f"GenericAgent {self.agent_id}: cognitive type LLM full attempt failed: {e}")

        if inferred is None:
            try:
                result = await call_llm(
                    prompt=f"Which cognitive type is '{aspect}'? Output only: fact_driven / inference_driven / forward_looking / assessment_driven",
                    system_prompt="Output type name only.",
                    max_tokens=30,
                    temperature=0.0,
                )
                content = result.get("content", "").strip().lower()
                _matches = [(content.rfind(vt), vt) for vt in valid_types if vt in content]
                if _matches:
                    inferred = max(_matches, key=lambda x: x[0])[1]
                    method_used = "llm_retry"
            except Exception as e:
                logger.warning(f"GenericAgent {self.agent_id}: cognitive type LLM retry failed: {e}")

        if inferred is None:
            inferred = self._heuristic_cognitive_type(aspect)
            if inferred:
                method_used = "heuristic"

        if inferred is None:
            inferred = "fact_driven"
            method_used = "fallback"

        logger.info(f"GenericAgent {self.agent_id}: cognitive type for '{aspect}' = {inferred} (method: {method_used})")
        self._context[cache_key] = inferred
        return inferred

    def _detect_claim_contradiction_precheck(self, claim_a: Dict, claim_b: Dict) -> bool:
        """L5 pre-check: Fast heuristic to identify candidate contradiction pairs.
        
        Returns True if the pair MIGHT be contradictory (needs LLM confirmation).
        Intentionally over-sensitive (high recall, low precision) to avoid missing
        real contradictions. The LLM stage will filter false positives.
        """
        stmt_a = claim_a.get("statement", "")
        stmt_b = claim_b.get("statement", "")
        if not stmt_a or not stmt_b:
            return False
        
        positive = {"增长", "上升", "扩张", "改善", "提升", "增加", "上涨", "回暖",
                    "普及", "加速", "领先", "突破", "恢复", "繁荣", "强劲", "乐观",
                    "收紧", "趋严", "升级", "扩张", "扩张", "强化", "推进", "普及"}
        negative = {"下降", "萎缩", "收缩", "恶化", "下滑", "减少", "下跌", "承压",
                    "渗透率下滑", "放缓", "滞后", "受阻", "衰退", "疲软", "悲观",
                    "放松", "趋缓", "降级", "收缩", "弱化", "停滞", "萎缩", "低迷"}
        a_pos = any(w in stmt_a for w in positive)
        a_neg = any(w in stmt_a for w in negative)
        b_pos = any(w in stmt_b for w in positive)
        b_neg = any(w in stmt_b for w in negative)
        
        if (a_pos and b_neg) or (a_neg and b_pos):
            def _bigrams(text):
                return {text[i:i+2] for i in range(len(text)-1)}
            bigrams_a = _bigrams(stmt_a)
            bigrams_b = _bigrams(stmt_b)
            dir_bigrams = set()
            for w in positive | negative:
                for i in range(len(w)-1):
                    dir_bigrams.add(w[i:i+2])
            content_a = bigrams_a - dir_bigrams
            content_b = bigrams_b - dir_bigrams
            if content_a and content_b:
                overlap = len(content_a & content_b) / max(len(content_a), 1)
                if overlap > 0.25:
                    return True
        
        return False

    async def _detect_claim_contradiction(self, claim_a: Dict, claim_b: Dict) -> Optional[str]:
        """L5: Detect semantic contradiction between two claims using LLM.
        
        Two-stage approach:
        1. Fast heuristic pre-check (_detect_claim_contradiction_precheck) filters
           obviously unrelated pairs with zero latency.
        2. LLM semantic analysis confirms/rejects candidate pairs with high accuracy.
        
        Falls back to heuristic-only result on LLM failure.
        """
        stmt_a = claim_a.get("statement", "")
        stmt_b = claim_b.get("statement", "")
        if not stmt_a or not stmt_b:
            return None
        
        if not self._detect_claim_contradiction_precheck(claim_a, claim_b):
            return None
        
        prompt = (
            "判断以下两条声明是否存在逻辑矛盾。两条声明讨论的是同一主体但方向相反才算矛盾；"
            "讨论不同主体或不同方面不算矛盾。\n\n"
            f"声明A: {stmt_a}\n"
            f"声明B: {stmt_b}\n\n"
            "请严格按以下JSON格式回答，不要添加任何其他内容:\n"
            '{"contradiction": true/false, "type": "方向矛盾/因果矛盾/事实矛盾/无矛盾", '
            '"confidence": 0.0-1.0, "explanation": "简短说明"}'
        )
        
        try:
            # Keep an injectable client seam for quality checks and tests.  The
            # production fallback remains the shared LLM gateway.
            injected_client = getattr(self, "_llm_client", None)
            injected_generate = getattr(injected_client, "generate", None)
            if callable(injected_generate):
                result = await injected_generate(prompt)
                content = result.get("content", "") if isinstance(result, dict) else str(result or "")
            else:
                result = await call_llm(
                    prompt=prompt,
                    system_prompt="你是一个逻辑矛盾检测专家。只输出JSON，不输出任何其他内容。",
                    max_tokens=200,
                    temperature=0.0,
                )
                content = result.get("content", "")
            content = content.strip()
            
            import json as _json
            json_match = re.search(r'\{[^}]+\}', content)
            if json_match:
                parsed = _json.loads(json_match.group())
                # Accept both historical response keys while the prompt uses
                # the canonical ``contradiction`` name.
                is_contradiction = parsed.get(
                    "contradiction", parsed.get("is_contradiction", False)
                )
                conf = parsed.get("confidence", 0.0)
                ctype = parsed.get("type", "方向矛盾")
                explanation = parsed.get("explanation", "")
                
                if is_contradiction and conf >= 0.6:
                    return f"{ctype}: '{stmt_a[:50]}' vs '{stmt_b[:50]}' ({explanation})"
                else:
                    return None
            
            logger.debug(f"GenericAgent L5: LLM output not valid JSON, skipping contradiction report: {content[:100]}")
        except Exception as e:
            logger.debug(f"GenericAgent L5: LLM call failed, skipping contradiction report: {e}")
        
        return None

    def _enforce_canonical_values(self, content: str, canonical_data: Dict) -> str:
        """
        M3: Post-processing to enforce canonical values in generated content.
        Extracts metrics via MetricExtractor, compares with canonical_data,
        and replaces values differing by more than 5% (skipping table lines).
        Supports both Chinese and English metric names via ENGLISH_ALIASES.
        """
        import re as _re
        if not content or not canonical_data:
            return content

        from src.core.data.metric_extractor import MetricExtractor
        extractor = MetricExtractor()
        en_aliases = getattr(MetricExtractor, 'ENGLISH_ALIASES', {})

        data_points = [{"content": content, "url": ""}]
        found_metrics = extractor.extract(data_points)

        for fm in found_metrics:
            metric_name = fm["metric"]
            text_value = fm["value"]
            text_unit = fm["unit"]

            for key, entry in canonical_data.items():
                if not isinstance(entry, dict):
                    continue
                canonical_value = entry.get("value")
                if canonical_value is None:
                    continue

                entry_metric = key.split("_")[0] if "_" in key else key
                if entry_metric != metric_name:
                    continue

                diff = abs(text_value - float(canonical_value)) / max(abs(float(canonical_value)), 0.01)
                if diff <= 0.05:
                    continue

                new_str = str(canonical_value)
                old_str = str(text_value)
                if old_str.endswith(".0"):
                    old_pattern = _re.escape(old_str[:-2]) + r'(?:\.0)?'
                else:
                    old_pattern = _re.escape(old_str)

                names = [metric_name] + en_aliases.get(metric_name, [])
                name_part = "(?:" + "|".join(_re.escape(n) for n in names) + ")"
                pattern = (
                    rf'({name_part}'
                    rf'[^\d]*?)'
                    rf'({old_pattern})'
                    rf'(\s*{_re.escape(text_unit)})'
                )

                def _skip_table_line(match, _new=new_str):
                    last_newline = content.rfind('\n', 0, match.start())
                    if last_newline >= 0:
                        line_start = content[last_newline + 1:]
                        if line_start.startswith('|'):
                            return match.group(0)
                    return match.group(1) + _new + match.group(3)

                content = _re.sub(pattern, _skip_table_line, content)

        return content

    async def run(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        运行Agent（带状态管理和错误处理）
        
        注意：GenericAgent不做输入验证（与FixedAgent不同）。
        
        Args:
            task: 任务定义
            
        Returns:
            执行结果
        """
        import json as _json
        task_str = str(task)
        if len(task_str) > 500:
            task_summary = _json.dumps({
                "action": task.get("action", ""),
                "aspect": task.get("aspect", ""),
                "aspects": task.get("aspects", []),
                "topic": task.get("topic", ""),
                "data_count": len(task.get("data", [])),
                "data_keys": list(task.get("data", {}).keys()) if isinstance(task.get("data"), dict) else f"{len(task.get('data', []))} items",
                "data_size_kb": len(task_str) // 1024,
            }, ensure_ascii=False)[:300]
            logger.info(f"GenericAgent.run [{self.agent_id}]: 开始执行, task_summary={task_summary}")
        else:
            logger.info(f"GenericAgent.run [{self.agent_id}]: 开始执行, task={task}")
        
        try:
            # 发布开始事件
            await self.publish_event("task_started", {"task_keys": list(task.keys())})
            
            # 更新状态
            await self.update_state(status="running", data={"task": task})
            
            logger.info(f"GenericAgent.run [{self.agent_id}]: 调用execute()")
            
            # 执行
            result = await self.execute(task)
            
            logger.info(f"GenericAgent.run [{self.agent_id}]: execute()返回, success={result.get('success') if result else 'None'}")
            
            # 更新状态
            await self.update_state(status="completed", data={"result": result})
            
            # 确保结果包含标准字段
            if result is None:
                result = {"success": False, "error": "execute() returned None"}
            elif not isinstance(result, dict):
                result = {"success": True, "result": result}
            
            if "success" not in result:
                result["success"] = True
            result["agent_id"] = self.agent_id
            result["agent_type"] = self.agent_type
            
            # 发布完成事件
            await self.publish_event("task_completed", {"success": result["success"]})
            
            logger.info(f"GenericAgent.run [{self.agent_id}]: 完成, success={result.get('success')}")
            
            return result
            
        except Exception as e:
            logger.error(f"GenericAgent.run [{self.agent_id}]: 异常 - {e}")
            
            # 更新状态
            await self.update_state(status="error", data={"error": str(e)})
            
            # 发布错误事件
            await self.publish_event("task_error", {"error": str(e)})
            
            # 返回error字典
            return {
                "success": False,
                "error": str(e),
                "agent_id": self.agent_id,
                "agent_type": self.agent_type,
            }
    
    # === 通用数据管道 (Phase 3) ===

    async def _process_skill_output(
        self,
        skill,
        skill_name: str,
        topic: str,
        aspect: str,
        skill_registry: Any = None,
        structured_data_sufficient: bool = False,
        preloaded_search_results: Optional[List] = None,
        search_depth: str = "deep",
    ) -> Dict[str, Any]:
        """通用 Skill 输出处理器。

        不假设 Skill 返回什么数据结构，用三层策略将任意数据
        转为下游可消费的 content + canonical_metrics。

        这是所有 Skill 数据进入系统的唯一入口。

        Args:
            structured_data_sufficient: 跨 Tier 状态，控制 news_search 数量和 search_depth
            preloaded_search_results: 跨 Tier 状态，search_skill 的预加载结果
            search_depth: 跨 Tier 状态，"basic" 或 "deep"
        """
        result = {"data_points": [], "sources": [], "canonical_metrics": {}}

        try:
            # Skill execution belongs to the Agent task lifecycle.  Do not
            # truncate it with a hidden fixed timeout; cancellation is owned
            # by the coordinator/task controller.
            processed = await self._process_skill_output_inner(
                skill, skill_name, topic, aspect, skill_registry,
                structured_data_sufficient, preloaded_search_results, search_depth,
            )
            return processed
        except Exception as e:
            logger.error(f"GenericAgent {self.agent_id}: {skill_name} unexpected error: {e}")
            return result

    async def _process_skill_output_inner(
        self,
        skill,
        skill_name: str,
        topic: str,
        aspect: str,
        skill_registry: Any = None,
        structured_data_sufficient: bool = False,
        preloaded_search_results: Optional[List] = None,
        search_depth: str = "deep",
    ) -> Dict[str, Any]:
        result = {"data_points": [], "sources": [], "canonical_metrics": {}}

        if skill_name == "search_skill":
            return await self._process_search_skill(
                skill, topic, aspect, skill_registry,
                preloaded_search_results=preloaded_search_results,
                search_depth=search_depth,
            )

        if skill_name == "news_search":
            return await self._process_news_skill(
                skill, topic, aspect,
                max_results=5 if structured_data_sufficient else 10,
            )

        identifiers = self._resolve_identifiers(
            skill_name, topic, aspect, skill_registry
        )
        if not identifiers:
            identifiers = [topic]

        manifest = skill_registry.get_manifest(skill_name) if skill_registry else None
        actions = self._infer_actions_from_manifest(manifest, skill, aspect, identifiers[0])

        if len(identifiers) > 10:
            logger.info(f"GenericAgent {self.agent_id}: truncating identifiers "
                        f"from {len(identifiers)} to 10 for {skill_name}")
        for identifier in identifiers[:10]:
            for action in actions:
                try:
                    kwargs = self._build_execute_kwargs(
                        manifest, action, identifier, topic
                    )
                    try:
                        skill_result = await skill.execute(**kwargs)
                    except TypeError as te:
                        logger.warning(f"GenericAgent {self.agent_id}: {skill_name}.execute() "
                                       f"rejected kwargs {kwargs}: {te}")
                        continue

                    if skill_result is None:
                        continue
                    if not isinstance(skill_result, dict):
                        logger.warning(f"GenericAgent {self.agent_id}: {skill_name} returned "
                                       f"{type(skill_result).__name__}, expected dict")
                        skill_result = {"success": True, "data": {},
                                        "content": str(skill_result)}

                    if not skill_result.get("success"):
                        continue

                    data = skill_result.get("data")
                    if data is None:
                        data = {}
                    elif isinstance(data, list):
                        data = {"records": data}
                    elif not isinstance(data, dict):
                        data = {"value": data}

                    content = await self._to_readable_content(
                        skill_result, skill, data, action, identifier, skill_name, topic
                    )

                    metrics = self._extract_numeric_metrics(data)

                    _manifest_priority = (manifest.priority if manifest else "web_search")
                    if _manifest_priority == "structured_db":
                        _dp_quality = 95
                        _dp_credibility = "structured_source"
                        _src_type = "structured"
                        _src_quality = 95
                    else:
                        _dp_quality = 50
                        _dp_credibility = "search_result"
                        _src_type = "web"
                        _src_quality = 50
                    dp = {
                        "title": f"{identifier} {action}",
                        "content": content,
                        "url": f"{skill_name}://{identifier}/{action}",
                        "quality_score": _dp_quality,
                        "credibility": _dp_credibility,
                    }
                    if isinstance(data, dict) and data:
                        dp["data"] = data
                    result["data_points"].append(dp)
                    result["sources"].append({
                        "title": f"{skill_name} {identifier} {action}",
                        "url": f"{skill_name}://{identifier}/{action}",
                        "type": _src_type,
                        "quality_score": _src_quality,
                    })
                    result["canonical_metrics"].update(metrics)

                except Exception as action_err:
                    logger.warning(
                        f"GenericAgent {self.agent_id}: {skill_name} "
                        f"action '{action}' failed: {action_err}"
                    )

        return result

    async def _process_search_skill(
        self, skill, topic, aspect, skill_registry,
        preloaded_search_results=None, search_depth="deep",
    ) -> Dict[str, Any]:
        result = {"data_points": [], "sources": [], "canonical_metrics": {}}
        aspects = [aspect] if aspect else []
        search_results = await self._do_deep_research(
            topic=topic, aspect=aspect, aspects=aspects, skill_registry=skill_registry,
            preloaded_search_results=preloaded_search_results,
            depth=search_depth,
        )
        for search in search_results.get("searches", []):
            for item in search.get("results", []):
                evidence = self._evidence_metadata(item)
                result["data_points"].append({
                    "title": item.get("title", ""),
                    "content": item.get("body", "") or item.get("snippet", ""),
                    "url": item.get("href", "") or item.get("url", ""),
                    "quality_score": item.get("quality_score", 0),
                    "credibility": item.get("credibility", "unknown"),
                    **evidence,
                })
                result["sources"].append({
                    "title": item.get("title", ""),
                    "url": item.get("href", "") or item.get("url", ""),
                    "type": "web",
                    "quality_score": item.get("quality_score", 0),
                    **evidence,
                })
        result["total_sources"] = search_results.get("total_sources", 0)
        result["quality_stats"] = search_results.get("quality_stats", {})
        return result

    async def _process_news_skill(
        self, skill, topic: str, aspect: str, max_results: int = 10,
    ) -> Dict[str, Any]:
        result = {"data_points": [], "sources": [], "canonical_metrics": {}}
        news_query = f"{topic} {aspect} 最新 动态" if aspect else f"{topic} 最新 动态"
        try:
            news_result = await skill.execute(
                query=news_query, max_results=max_results, time_range="w",
            )
            if news_result and isinstance(news_result, dict) and news_result.get("success"):
                results_data = news_result.get("results", [])
                if not results_data:
                    results_data = news_result.get("data", {}).get("results", [])
                if not isinstance(results_data, list):
                    logger.warning(f"GenericAgent {self.agent_id}: news_search results is "
                                   f"{type(results_data).__name__}, skipping")
                    return result
                for nr in results_data[:20]:
                    if not isinstance(nr, dict):
                        continue
                    news_body = nr.get("body", "") or nr.get("snippet", "")
                    news_url = nr.get("href", "") or nr.get("url", "")
                    evidence = self._evidence_metadata(nr)
                    result["data_points"].append({
                        "title": nr.get("title", ""),
                        "content": news_body,
                        "url": news_url,
                        "quality_score": 70,
                        "credibility": "news_source",
                        "source_type": "news",
                        "source_name": nr.get("source", ""),
                        "date": nr.get("date", ""),
                        **evidence,
                    })
                    result["sources"].append({
                        "title": nr.get("title", ""),
                        "url": news_url,
                        "type": "news",
                        "quality_score": 70,
                        **evidence,
                    })
        except Exception as e:
            logger.warning(f"GenericAgent {self.agent_id}: news_search failed: {e}")
        return result

    async def _to_readable_content(
        self,
        skill_result: Dict,
        skill: Any,
        data: dict,
        action: str,
        identifier: str,
        skill_name: str,
        topic: str,
    ) -> str:
        """三层内容转换 — 适用于任意 Skill，不依赖 Skill 配合。

        L1: Skill 自带的 content 字段
        L2: Skill 实现了 format_data()（structured_db 类必需）
        L3: LLM 总结（通用兜底，structured_db 类跳过以控制成本）
        兜底: JSON dump
        """
        content = skill_result.get("content", "")
        if content and not isinstance(content, str):
            content = str(content)

        formatted = ""
        if hasattr(skill, 'format_data') and callable(skill.format_data):
            try:
                formatted = skill.format_data(data, action, identifier)
                if inspect.isawaitable(formatted):
                    formatted = await formatted
                formatted = formatted or ""
                if not isinstance(formatted, str):
                    formatted = str(formatted)
            except Exception:
                pass

        if formatted and (not content or len(formatted) > len(content)):
            content = formatted
        if content:
            return content

        manifest = None
        if hasattr(self, '_skill_registry') and self._skill_registry:
            manifest = self._skill_registry.get_manifest(skill_name)

        data_preview = str(data)
        if len(data_preview) > 2000:
            data_preview = data_preview[:2000] + "...(truncated)"

        if data and len(data_preview) > 100 and (not manifest or manifest.priority != "structured_db"):
            try:
                llm_summary = await self._llm_summarize_data(
                    data, skill_name, action, topic
                )
                if llm_summary:
                    return llm_summary
            except Exception:
                pass

        if isinstance(data, dict) and data:
            try:
                return json.dumps(data, ensure_ascii=False, indent=2, default=str)
            except (ValueError, TypeError, OverflowError) as e:
                logger.warning(f"GenericAgent {self.agent_id}: JSON dump failed for "
                               f"{skill_name}: {e}")
                return str(data)[:2000]
        return content or ""

    async def _llm_summarize_data(
        self,
        data: dict,
        skill_name: str,
        action: str,
        topic: str,
    ) -> str:
        data_str = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        if len(data_str) > 6000:
            data_str = data_str[:6000] + "\n... (truncated)"

        max_chars = 500 if len(data_str) > 2000 else 200

        try:
            from src.config.llm_profiles import RoutingHint
            from src.core.llm_client import call_llm
            llm_result = await call_llm(
                prompt=(
                    f"将以下来自 {skill_name} 的 {action} 数据整理为结构化摘要。\n"
                    f"研究主题：{topic}\n\n"
                    f"原始数据：\n{data_str}\n\n"
                    f"要求：\n"
                    f"1. 提取关键数值并标注含义（如'市值22600亿'而非'market_capital: 22600'）\n"
                    f"2. 用中文表述\n"
                    f"3. 不超过{max_chars}字"
                ),
                system_prompt="你是数据摘要引擎，只输出摘要，不分析。",
                routing_hint=RoutingHint(action="data_summarization"),
            )
            if llm_result.get("success") and llm_result.get("content"):
                return llm_result["content"]
        except Exception as e:
            logger.warning(f"GenericAgent {self.agent_id}: LLM summarize failed: {e}")
        return ""

    def _resolve_identifiers(
        self,
        skill_name: str,
        topic: str,
        aspect: str,
        skill_registry: Any = None,
    ) -> List[str]:
        identifiers = []

        raw_entities = getattr(self, '_context', {}).get("entities", [])
        if raw_entities:
            from src.core.entity_resolver import EntityInfo
            entities = [
                EntityInfo.from_dict(e) if isinstance(e, dict) else e
                for e in raw_entities
            ]
            listed = [e for e in entities if e.is_listed and e.resolved_code]
            if listed:
                return [e.resolved_code for e in listed]

        symbol = self._extract_stock_symbol(topic)
        if symbol:
            return [symbol]

        chinese_m = re.search(r'[\u4e00-\u9fff]+', topic)
        if chinese_m:
            embedded_codes = self._resolve_embedded_companies(topic)
            if embedded_codes:
                return embedded_codes
            if self._is_likely_company_name(chinese_m.group(0), topic):
                resolved = self._resolve_company_to_code(chinese_m.group(0))
                if resolved:
                    return [resolved]

        if skill_registry:
            manifest = skill_registry.get_manifest(skill_name)
            if manifest and manifest.supports_topic_fallback and topic:
                skill = skill_registry.get(skill_name)
                if skill:
                    old_manifest = getattr(skill, '_manifest', None)
                    try:
                        skill._manifest = manifest
                        identifier = skill.resolve_identifier(topic, aspect)
                        if identifier:
                            return [identifier]
                    finally:
                        skill._manifest = old_manifest

        return identifiers

    def _infer_actions_from_manifest(
        self,
        manifest: Any,
        skill: Any,
        aspect: str,
        identifier: str,
    ) -> List[str]:
        if manifest and manifest.action_rules:
            if skill:
                old_manifest = getattr(skill, '_manifest', None)
                try:
                    skill._manifest = manifest
                    return skill.infer_actions(aspect, identifier)
                finally:
                    skill._manifest = old_manifest
            all_actions = []
            matched = False
            for rule in manifest.action_rules:
                if not re.match(rule.pattern, identifier):
                    continue
                if rule.aspect_keywords:
                    aspect_lower = (aspect or "").lower()
                    if any(kw.lower() in aspect_lower for kw in rule.aspect_keywords):
                        all_actions.extend(rule.actions)
                        matched = True
                    continue
                if not matched:
                    return rule.actions
            if matched:
                return list(dict.fromkeys(all_actions))

        return ["default"]

    def _build_execute_kwargs(
        self,
        manifest: Any,
        action: str,
        identifier: str,
        topic: str,
    ) -> Dict[str, Any]:
        kwargs = {"action": action}

        if manifest and manifest.action_param_map and action in manifest.action_param_map:
            param_map = manifest.action_param_map[action]
            for param_name, source in param_map.items():
                if source == "symbol":
                    kwargs[param_name] = identifier
                elif source == "query":
                    kwargs[param_name] = identifier
                elif source == "topic":
                    kwargs[param_name] = topic
                else:
                    kwargs[param_name] = identifier
        else:
            kwargs["symbol"] = identifier

        return kwargs

    # === 深度研究方法 ===
    


    _STOCK_CODE_CACHE: Dict[str, str] = {}

    _UNIT_MULTIPLIERS = {
        "亿": 1e8, "万": 1e4, "千": 1e3, "百": 1e2,
    }

    @staticmethod
    def _parse_chinese_number(val: str):
        if not isinstance(val, str):
            return None
        val = val.strip()
        if val.endswith("%"):
            try:
                return float(val[:-1]) / 100.0
            except ValueError:
                return None
        for unit, mult in GenericAgent._UNIT_MULTIPLIERS.items():
            if val.endswith(unit):
                try:
                    return float(val[:-len(unit)]) * mult
                except ValueError:
                    return None
        return None

    def _extract_numeric_metrics(self, data: Any, prefix: str = "") -> Dict[str, float]:
        metrics: Dict[str, float] = {}
        if isinstance(data, dict):
            for key, val in data.items():
                full_key = f"{prefix}.{key}" if prefix else key
                if isinstance(val, (int, float)) and not isinstance(val, bool):
                    if isinstance(val, float) and val != val:
                        continue
                    metrics[full_key] = float(val)
                elif isinstance(val, str):
                    parsed = self._parse_chinese_number(val)
                    if parsed is not None:
                        metrics[full_key] = parsed
                    else:
                        try:
                            v = float(val)
                            if v == v:
                                metrics[full_key] = v
                        except (ValueError, TypeError):
                            pass
                elif isinstance(val, list) and val and isinstance(val[0], dict):
                    for i, item in enumerate(val[:4]):
                        item_prefix = f"{full_key}[{i}]"
                        for ik, iv in item.items():
                            full_ik = f"{item_prefix}.{ik}"
                            if isinstance(iv, (int, float)) and not isinstance(iv, bool):
                                if isinstance(iv, float) and iv != iv:
                                    continue
                                metrics[full_ik] = float(iv)
                            elif isinstance(iv, str):
                                parsed = self._parse_chinese_number(iv)
                                if parsed is not None:
                                    metrics[full_ik] = parsed
                                else:
                                    try:
                                        v = float(iv)
                                        if v == v:
                                            metrics[full_ik] = v
                                    except (ValueError, TypeError):
                                        pass
        return metrics















    def _extract_stock_symbol(self, topic: str) -> str:
        if not topic:
            return ""
        import re
        if re.match(r'^\d{6}$', topic.strip()):
            return topic.strip()
        m = re.search(r'\d{6}', topic)
        if m:
            return m.group(0)
        chinese_m = re.search(r'[\u4e00-\u9fff]+', topic)
        if not chinese_m:
            return ""
        company_name = chinese_m.group(0)
        if not self._is_likely_company_name(company_name, topic):
            return ""
        cached = self._STOCK_CODE_CACHE.get(company_name)
        if cached:
            return cached
        code = self._resolve_company_to_code(company_name)
        if code:
            self._STOCK_CODE_CACHE[company_name] = code
            return code
        return ""

    def _is_likely_company_name(self, chinese_text: str, full_topic: str) -> bool:
        from src.core.decomposition.strategies import _is_listed_company_topic
        if _is_listed_company_topic(chinese_text):
            return True
        return _is_listed_company_topic(full_topic)

    _AKSHARE_RESOLVE_CACHE: Dict[str, str] = {}

    def _resolve_company_to_code(self, company_name: str) -> str:
        cached = self._AKSHARE_RESOLVE_CACHE.get(company_name)
        if cached is not None:
            return cached

        code = self._resolve_via_entity_resolver(company_name)
        if code:
            self._AKSHARE_RESOLVE_CACHE[company_name] = code
            return code

        code = self._resolve_via_akshare(company_name)
        if code:
            self._AKSHARE_RESOLVE_CACHE[company_name] = code
            return code

        self._AKSHARE_RESOLVE_CACHE[company_name] = ""
        return ""

    _EMBEDDED_COMPANY_CACHE: Dict[str, List[str]] = {}

    def _resolve_embedded_companies(self, topic: str) -> List[str]:
        cached = self._EMBEDDED_COMPANY_CACHE.get(topic)
        if cached is not None:
            return cached

        codes = []

        code_map = self._get_stock_name_table()
        if code_map:
            seen = set()
            for company_name, code in code_map.items():
                if len(company_name) < 3:
                    continue
                if company_name in topic and code not in seen:
                    codes.append(code)
                    seen.add(code)

        industry_codes = self._resolve_industry_constituents(topic)
        if industry_codes:
            seen = set(codes)
            for c in industry_codes:
                if c not in seen:
                    codes.append(c)
                    seen.add(c)

        if codes:
            logger.info(
                f"GenericAgent {self.agent_id}: found {len(codes)} listed companies "
                f"in topic '{topic[:40]}'"
            )
        self._EMBEDDED_COMPANY_CACHE[topic] = codes
        return codes

    _STOCK_TABLE_CACHE: Optional[Dict[str, str]] = None

    @classmethod
    def _get_stock_name_table(cls) -> Dict[str, str]:
        if cls._STOCK_TABLE_CACHE is not None:
            return cls._STOCK_TABLE_CACHE
        try:
            from src.core.entity_resolver import get_entity_resolver
            resolver = get_entity_resolver()
            if not resolver._table_loaded:
                resolver._try_load_disk_cache()
            cls._STOCK_TABLE_CACHE = dict(resolver._stock_name_table) if resolver._stock_name_table else {}
        except Exception:
            cls._STOCK_TABLE_CACHE = {}
        return cls._STOCK_TABLE_CACHE

    _INDUSTRY_BOARD_CACHE: Optional[Dict[str, str]] = None
    _INDUSTRY_CONSTITUENT_CACHE: Dict[str, List[str]] = {}

    def _resolve_industry_constituents(self, topic: str) -> List[str]:
        try:
            import akshare as ak
        except ImportError:
            return []

        board_map = self._get_industry_board_map()
        if not board_map:
            return []

        matched_boards = []
        for board_name in board_map:
            if board_name in topic or any(kw in topic for kw in board_name.split()):
                matched_boards.append(board_name)
        if not matched_boards:
            return []

        all_codes = []
        seen = set()
        code_map = self._get_stock_name_table()

        for board_name in matched_boards[:3]:
            cached = self._INDUSTRY_CONSTITUENT_CACHE.get(board_name)
            if cached is not None:
                for c in cached:
                    if c not in seen:
                        all_codes.append(c)
                        seen.add(c)
                continue

            try:
                cons_df = ak.stock_board_industry_cons_em(symbol=board_name)
                if cons_df is None or cons_df.empty:
                    self._INDUSTRY_CONSTITUENT_CACHE[board_name] = []
                    continue
                code_col = None
                for col in cons_df.columns:
                    if "代码" in str(col) or "code" in str(col).lower() or "symbol" in str(col).lower():
                        code_col = col
                        break
                if not code_col:
                    self._INDUSTRY_CONSTITUENT_CACHE[board_name] = []
                    continue
                board_codes = []
                for _, row in cons_df.iterrows():
                    c = str(row[code_col]).strip()
                    if c and len(c) == 6 and c not in seen:
                        board_codes.append(c)
                        all_codes.append(c)
                        seen.add(c)
                self._INDUSTRY_CONSTITUENT_CACHE[board_name] = board_codes
                logger.info(
                    f"GenericAgent {self.agent_id}: industry board '{board_name}' "
                    f"→ {len(board_codes)} constituent stock codes"
                )
            except Exception as e:
                logger.debug(f"GenericAgent {self.agent_id}: industry constituents failed for '{board_name}': {e}")
                self._INDUSTRY_CONSTITUENT_CACHE[board_name] = []

        return all_codes

    @classmethod
    def _get_industry_board_map(cls) -> Dict[str, str]:
        if cls._INDUSTRY_BOARD_CACHE is not None:
            return cls._INDUSTRY_BOARD_CACHE
        try:
            import akshare as ak
            df = ak.stock_board_industry_name_em()
            name_col = None
            code_col = None
            for col in df.columns:
                col_str = str(col)
                if "名称" in col_str or "板块" in col_str:
                    name_col = col
                if "代码" in col_str:
                    code_col = col
            if name_col and code_col:
                cls._INDUSTRY_BOARD_CACHE = {
                    str(row[name_col]): str(row[code_col])
                    for _, row in df.iterrows()
                }
                logger.info(f"GenericAgent: loaded {len(cls._INDUSTRY_BOARD_CACHE)} industry boards from akshare")
                return cls._INDUSTRY_BOARD_CACHE
        except Exception as e:
            logger.debug(f"GenericAgent: failed to load industry board map: {e}")
        cls._INDUSTRY_BOARD_CACHE = {}
        return cls._INDUSTRY_BOARD_CACHE

    def _resolve_via_entity_resolver(self, company_name: str) -> str:
        try:
            from src.core.entity_resolver import get_entity_resolver
            resolver = get_entity_resolver()
            if not resolver._table_loaded:
                resolver._try_load_disk_cache()
            if resolver._stock_name_table:
                code = resolver._stock_name_table.get(company_name)
                if code:
                    logger.info(
                        f"GenericAgent {self.agent_id}: resolved '{company_name}' "
                        f"via EntityResolver disk cache → '{code}'"
                    )
                    return code
        except Exception as e:
            logger.debug(f"GenericAgent {self.agent_id}: EntityResolver fallback failed: {e}")
        return ""

    def _resolve_via_akshare(self, company_name: str) -> str:
        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                name_col = None
                code_col = None
                for col in df.columns:
                    col_lower = str(col).lower()
                    if "名称" in str(col) or "name" in col_lower:
                        name_col = col
                    if "代码" in str(col) or "code" in col_lower or "symbol" in col_lower:
                        code_col = col
                if name_col and code_col:
                    search_names = [company_name]
                    try:
                        from src.core.intent.keyword_registry import get_registry
                        for name in get_registry()._listed_company_names:
                            if name in company_name and name != company_name:
                                search_names.append(name)
                    except Exception:
                        pass
                    for search_name in search_names:
                        matches = df[df[name_col].astype(str).str.contains(
                            search_name, na=False
                        )]
                        if not matches.empty:
                            code = str(matches.iloc[0][code_col])
                            logger.info(
                                f"GenericAgent {self.agent_id}: resolved company "
                                f"'{company_name}' (matched '{search_name}') → stock code '{code}'"
                            )
                            return code
        except ImportError:
            logger.warning(f"GenericAgent {self.agent_id}: akshare not installed, cannot resolve company name")
        except Exception as e:
            logger.warning(
                f"GenericAgent {self.agent_id}: failed to resolve company "
                f"'{company_name}' to stock code: {e}"
            )
        return ""

    def _build_action_to_skill_map(self) -> Dict[str, Optional[str]]:
        """从 manifest.capabilities 反向构建 action→skill 映射。

        ⚠️ web_search 双重语义：作为 action 时映射到 lc_tavily_search（LangChain 搜索），
        但作为 skill name 时 web_search 是 search_skill 的 alias（MultiSearchSkill）。
        Task 4.3 将统一此不一致。"""
        intrinsic = {
            "llm": None, "analyze": None, "analysis": None,
            "reasoning": None, "summarize": None, "translate": None,
            "research": None, "data_collection": None,
            "calibration": None, "execute": None,
        }
        result = dict(intrinsic)
        if self._skill_registry:
            all_manifests = getattr(self._skill_registry, "all_manifests", None)
            manifests = all_manifests() if callable(all_manifests) else {}
            for name, manifest in manifests.items():
                for cap in manifest.capabilities:
                    if cap not in result:
                        result[cap] = name
        result["search"] = "search_skill"
        result["news_search"] = "news_search"
        result["file_operation"] = "file_skill"
        result["http_request"] = "http_skill"
        result["generate_docx"] = "docx_skill"
        result["generate_pptx"] = "pptx_skill"
        result["web_search"] = "lc_tavily_search"
        result["tavily_search"] = "lc_tavily_search"
        result["academic_search"] = "lc_arxiv"
        result["arxiv_search"] = "lc_arxiv"
        result["wiki_search"] = "lc_wikipedia"
        result["wikipedia_search"] = "lc_wikipedia"
        result["data_analysis"] = "lc_python_repl"
        result["python_repl"] = "lc_python_repl"
        return result



    def _generate_structured_fallback_queries(self, topic: str, aspect: str) -> List[str]:
        """Generate targeted search queries when structured data (stock_data) is unavailable."""
        from datetime import date
        current_year = str(date.today().year)
        aspect_prefix = f"{aspect} " if aspect else ""
        queries = []

        raw_entities = getattr(self, '_context', {}).get("entities", [])
        if raw_entities:
            from src.core.entity_resolver import EntityInfo
            entities = [
                EntityInfo.from_dict(e) if isinstance(e, dict) else e
                for e in raw_entities
            ]
            for entity in entities:
                if entity.is_listed:
                    queries.append(f"{entity.name} 年度报告 年报")
                    queries.append(f"{entity.name} 研究报告 券商")
                else:
                    queries.append(f"{entity.name} 最新动态 行业分析")
                    queries.append(f"{entity.name} 深度分析")

        queries.append(f"{topic} {aspect_prefix}财务数据 年报")
        aspect_lower = (aspect or "").lower()
        if any(kw in aspect_lower for kw in ["financial", "财务", "盈利", "利润", "营收"]):
            queries.append(f"{topic} 营收 净利润 最新")
            queries.append(f"{topic} 年报 财务报表")
        if any(kw in aspect_lower for kw in ["valuation", "估值", "价值", "pe", "pb"]):
            queries.append(f"{topic} 估值 PE PB 最新")
            queries.append(f"{topic} 市值 投资价值 分析")
        if any(kw in aspect_lower for kw in ["risk", "风险", "杠杆", "负债"]):
            queries.append(f"{topic} 风险 负债率 财务健康")
        if len(queries) == 1:
            queries.append(f"{topic} 财报 数据")
        result = []
        for q in queries:
            if current_year not in q:
                q = f"{q} {current_year}"
            result.append(q)
        return list(dict.fromkeys(result))

    def _generate_recollection_queries(
        self,
        topic: str,
        aspect: str,
        warnings: List[Dict[str, Any]],
    ) -> List[str]:
        """Generate targeted re-collection queries from validation warnings.
        
        IMP-3: When quality_rating is 'low', use timeliness warnings to generate
        fresh search queries for one round of targeted re-collection.
        """
        from datetime import date
        current_year = str(date.today().year)
        queries = []
        for w in warnings:
            wtype = w.get("type", "")
            if wtype == "timeliness":
                queries.append(f"{topic} {aspect} 最新 {current_year}")
                queries.append(f"{topic} {aspect} 数据 {current_year} 年")
            else:
                queries.append(f"{topic} {aspect} 补充数据 {current_year}")
        queries = list(dict.fromkeys(queries))
        return queries

    def _resolve_numerical_conflicts(
        self,
        conflicts: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Auto-resolve numerical conflicts by authority + timeliness rules.
        
        IMP-4: Resolution priority:
        1. Authority: source from higher-authority domain wins
        2. Timeliness: URL containing newer year wins (when authority equal)
        3. Tiebreaker: first source listed wins
        """
        authority_domains = _AUTHORITY_DOMAINS
        current_year = datetime.now().year
        resolved = []
        for conflict in conflicts:
            if conflict.get("type") != "numerical_conflict":
                continue
            sources = conflict.get("sources", [])
            if len(sources) < 2:
                continue
            src_scores = []
            for i, src in enumerate(sources):
                url = src.get("url", "")
                domain = ""
                try:
                    domain = urlparse(url).netloc.lower() if url else ""
                    if domain.startswith("www."):
                        domain = domain[4:]
                except Exception:
                    pass
                auth_score = 0.5
                if domain:
                    if domain in authority_domains:
                        auth_score = authority_domains[domain]
                    else:
                        for auth_domain, score in authority_domains.items():
                            if domain.endswith("." + auth_domain) or domain == auth_domain:
                                auth_score = max(auth_score, score)
                                break
                src_year = 0
                for y in range(current_year - 5, current_year + 2):
                    if str(y) in url:
                        src_year = max(src_year, y)
                    if str(y) in src.get("source", ""):
                        src_year = max(src_year, y)
                src_scores.append((i, auth_score, src_year))
            max_auth = max(s[1] for s in src_scores)
            top_by_auth = [s for s in src_scores if s[1] == max_auth]
            if len(top_by_auth) == 1:
                best_idx = top_by_auth[0][0]
                reason = "authority"
            else:
                max_year = max(s[2] for s in top_by_auth)
                top_by_year = [s for s in top_by_auth if s[2] == max_year]
                if max_year > 0 and len(top_by_year) < len(top_by_auth):
                    best_idx = top_by_year[0][0]
                    reason = "timeliness"
                else:
                    best_idx = top_by_auth[0][0]
                    reason = "authority" if max_auth > 0.6 else "tiebreaker"
            resolved.append({
                "claim": conflict.get("claim", ""),
                "resolved_value": sources[best_idx]["value"],
                "resolution_reason": reason,
                "winning_source": sources[best_idx].get("source", ""),
                "original_conflict": conflict,
            })
        return resolved

    def _get_search_skill(self, skill_registry: Any):
        """Return the task's routed search skill when factory routing is enabled.

        Direct ``GenericAgent`` construction remains compatible with existing
        tests and callers; agents created by ``AgentFactory`` opt in through
        ``use_search_gateway``.
        """
        injected_gateway = self.config.get("search_gateway")
        if injected_gateway is not None:
            if self._search_gateway_skill is None:
                self._search_gateway = injected_gateway
                self._search_gateway_skill = GatewaySearchSkillAdapter(
                    injected_gateway,
                    scope="generic_agent",
                )
            return self._search_gateway_skill
        if not skill_registry:
            return None
        legacy_skill = skill_registry.get("search_skill")
        if not legacy_skill or not self.config.get("use_search_gateway", False):
            return legacy_skill
        if self._search_gateway_skill is None:
            self._search_gateway = SearchGateway(
                task_id=self.agent_id,
                providers={
                    "anysearch": AnySearchProvider(),
                    "local_skill": LocalSkillProvider(legacy_skill, name="local_skill"),
                },
                primary_provider="anysearch",
                fallback_providers=["local_skill"],
                min_quality_score=40,
                max_provider_retries=1,
                max_provider_switches=1,
            )
            self._search_gateway_skill = GatewaySearchSkillAdapter(self._search_gateway)
        return self._search_gateway_skill

    @staticmethod
    def _evidence_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
        """Copy auditable evidence identity across legacy result projections."""
        return {
            "evidence_id": item.get("evidence_id", ""),
            "provenance_id": item.get("provenance_id", ""),
            "evidence_excerpt": item.get("evidence_excerpt", "")
            or item.get("excerpt", "")
            or item.get("snippet", ""),
            "locator": item.get("locator", "")
            or item.get("url", "")
            or item.get("href", ""),
            "task_id": item.get("task_id", ""),
            "request_id": item.get("request_id", ""),
            "retrieved_at": item.get("retrieved_at"),
        }

    async def _do_deep_research(
        self,
        topic: str,
        aspect: str,
        aspects: List[str],
        skill_registry: Any,
        preloaded_search_results: Optional[List[Dict]] = None,
        depth: str = "deep",
    ) -> Dict[str, Any]:
        """
        执行深度研究：两阶段搜索策略 + 多轮搜索获取实时数据，带质量评估循环
        
        v3.0 改进（两阶段搜索策略）：
        1. 第一阶段：搜索获取URL列表
        2. 第二阶段：爬取URL获取完整内容
        3. 质量过滤基于完整内容而非简短摘要
        4. 使用框架配置的搜索次数（而非硬编码2次）
        5. 增加质量评估循环，质量不足时继续搜索
        6. 动态生成更多查询词
        
        Args:
            topic: 研究主题
            aspect: 单个维度
            aspects: 多个维度
            skill_registry: Skill 注册表
            
        Returns:
            搜索结果汇总（包含质量评分和完整内容）
        """
        import asyncio

        # Compact large-report routing still needs evidence, but repeating the
        # full deep-search loop for every section creates an avoidable long
        # tail.  Keep the default deep behavior for normal and primary-data
        # tasks; only the explicit compact route uses the bounded basic mode.
        if self._context.get("compact_route"):
            depth = "basic"
        
        search_skill = self._get_search_skill(skill_registry)
        if not search_skill:
            logger.warning(f"GenericAgent {self.agent_id}: no search skill available")
            return {}
        
        # P-FIX-ENGINE: quick connectivity probe before deep search
        if hasattr(search_skill, 'ping_engines'):
            try:
                _available = await search_skill.ping_engines(timeout=2.0)
                if not _available:
                    logger.warning(f"GenericAgent {self.agent_id}: 无可用的搜索引擎，跳过搜索")
                    return {}
            except Exception:
                logger.warning(f"GenericAgent {self.agent_id}: 搜索引擎探测异常，继续尝试搜索")
        
        # 获取网页爬取技能（用于获取详细内容）- 两阶段搜索的核心
        web_scraper = skill_registry.get("web_scraper")
        if web_scraper:
            logger.info(f"GenericAgent {self.agent_id}: 启用两阶段搜索策略（搜索+爬取）")
        else:
            logger.warning(f"GenericAgent {self.agent_id}: web_scraper不可用，仅使用搜索摘要")
        
        all_results = {"searches": [], "total_sources": 0, "quality_stats": {}}
        
        if preloaded_search_results:
            for pr in preloaded_search_results:
                if isinstance(pr, dict) and "results" in pr:
                    all_results["searches"].append(pr)
                elif isinstance(pr, dict) and "searches" in pr:
                    all_results["searches"].extend(pr.get("searches", []))
            logger.info(f"GenericAgent {self.agent_id}: injected {len(preloaded_search_results)} preloaded search results")
        
        # 构建质量过滤上下文
        quality_context = {
            "topic": topic,
            "aspect": aspect,
            "focus_areas": [aspect] if aspect else (aspects or []),
        }
        
        # 从Agent配置获取搜索参数（使用框架配置）
        skill_params = self.config.get("skill_params", {})
        search_params = skill_params.get("search_skill", {})
        if depth == "basic":
            min_queries = max(search_params.get("max_queries", 10) // 3, 2)
            max_results_per_query = max(search_params.get("max_results", 20) // 2, 5)
            MIN_QUALITY_SCORE = 55.0
            MIN_SOURCES = 2
            STAGNATION_LIMIT = 2
            MAX_QUERIES = 5
            MAX_ITERATIONS = 5
            MAX_LLM_CALLS = 1
        else:
            min_queries = min(max(int(search_params.get("max_queries", 5)), 3), 5)
            max_results_per_query = search_params.get("max_results", 20)
            MIN_QUALITY_SCORE = 45.0
            MIN_SOURCES = 5
            STAGNATION_LIMIT = 6
            MAX_QUERIES = 5
            MAX_ITERATIONS = 5
            MAX_LLM_CALLS = 3

        if self._context.get("compact_route"):
            # Large reports trade per-section search depth for breadth.  Do
            # not let framework-level max_queries values silently expand the
            # compact route back into a full deep-search workload.
            min_queries = 2
            MAX_QUERIES = 3
            MAX_ITERATIONS = 2
            MAX_LLM_CALLS = 0
        
        logger.info(f"GenericAgent {self.agent_id}: 搜索配置 depth={depth}, min_queries={min_queries}, max_results={max_results_per_query}")
        
        # 新增：获取领域角色信息
        
        MIN_CALL_INTERVAL = 5.0
        
        # 新增：获取领域角色信息
        from src.core.search import DomainRoleInferrer
        research_type = self._context.get("research_type", "market_research")
        language = self._context.get("language", "zh")
        role_inferrer = DomainRoleInferrer()
        role_info = role_inferrer.infer(research_type, topic, language)
        
        logger.info(f"GenericAgent {self.agent_id}: 领域角色={role_info['role']}, 研究类型={research_type}")
        
        # v3.4 R2 fix: construct intent_result namespace from context
        from types import SimpleNamespace
        _ctx_intent = SimpleNamespace(
            confidence=self._context.get("intent_confidence", 1.0),
            intent_confidence=self._context.get("intent_confidence", 1.0),
            domain_context=self._context.get("domain_context", {}),
            hidden_requirements=self._context.get("hidden_requirements", []),
        )
        
        try:
            # 构建搜索查询词列表
            queries = self._generate_search_queries(topic, aspect, aspects, role_info=role_info, intent_result=_ctx_intent)
            
            # v3.4 R3: Conditional initial LLM expansion based on research_type
            has_explicit_research_type = "research_type" in self._context
            total_count = len(queries)
            needs_llm_expansion = (
                total_count < 8
                or (not has_explicit_research_type and total_count < 15)
                or (has_explicit_research_type and total_count < 12)
            )
            
            llm_call_count = 0
            last_llm_call_time = 0.0
            
            if needs_llm_expansion:
                logger.info(f"GenericAgent {self.agent_id}: 初始查询不足({total_count}个), 触发 LLM 扩展 (has_explicit_research_type={has_explicit_research_type})")
                llm_queries = await self._generate_smart_queries_with_llm(
                    topic=topic,
                    aspect=aspect,
                    existing_queries=list(queries),
                    role_info=role_info,
                    min_queries=max(15, total_count + 5),
                )
                if llm_queries:
                    queries.extend(llm_queries)
                    llm_call_count += 1
                    import time
                    last_llm_call_time = time.time()
                    logger.info(f"GenericAgent {self.agent_id}: LLM 扩展了 {len(llm_queries)} 个新查询, 总计 {len(queries)} 个")
            
            executed_queries = set()
            if preloaded_search_results:
                for pr in preloaded_search_results:
                    if isinstance(pr, dict):
                        executed_queries.add(pr.get("query", ""))
            iteration = 0
            best_quality_score = 0.0
            stagnation_count = 0
            seen_urls = set()
            
            # 持续搜索直到满足条件
            while True:
                iteration += 1
                logger.info(f"GenericAgent {self.agent_id}: 搜索迭代 {iteration}")
                
                # 选择未执行的查询
                pending_queries = [q for q in queries if q not in executed_queries]
                
                # 每轮执行2-3个查询
                queries_to_execute = pending_queries[:3] if pending_queries else []
                
                if not queries_to_execute:
                    # 没有更多查询，生成新的补充查询
                    new_queries = self._generate_supplementary_queries(
                        topic, aspect, all_results, executed_queries
                    )
                    if not new_queries:
                        logger.info(f"GenericAgent {self.agent_id}: 无法生成更多查询，停止搜索")
                        break
                    queries.extend(new_queries)
                    queries_to_execute = new_queries[:3]
                    logger.info(f"GenericAgent {self.agent_id}: 生成{len(new_queries)}个新查询")
                
                # 执行搜索
                for query in queries_to_execute:
                    if query in executed_queries:
                        continue
                    
                    executed_queries.add(query)
                    logger.info(f"GenericAgent {self.agent_id}: 搜索 '{query}' (已执行{len(executed_queries)}次)")
                    
                    try:
                        # 深度搜索模式：启用翻页和关键词扩展
                        # 动态翻页策略：根据迭代次数调整
                        # 第1轮：翻1页快速获取（避免超时）
                        # 第2轮+：翻2页深度补充
                        dynamic_max_pages = 1 if iteration <= 1 else 2
                        
                        # 动态关键词扩展：第1轮不扩展，后续扩展
                        enable_kw_expansion = iteration > 1
                        
                        # Route query to appropriate search engine region based on language.
                        # Chinese queries -> domestic engines (Baidu, 360, Sogou) for local relevance.
                        # English queries -> global engines (Google, DDGS, Bing Intl) for authoritative intl data.
                        query_region = "global" if self._is_english_query(query) else "cn-cn"
                        
                        search_result = await search_skill.execute(
                                query=query,
                                max_results=max_results_per_query,
                                region=query_region,
                                
                                # 动态翻页策略
                                enable_pagination=True,
                                max_pages=dynamic_max_pages,
                                
                                # 动态关键词扩展
                                enable_keyword_expansion=enable_kw_expansion,
                                keyword_expansion_strategies=["time", "industry"],
                                max_keyword_variations=1,  # 减少变体数
                                
                                # 质量过滤 - 标准阈值
                                enable_quality_filter=True,
                                min_quality_score=35.0,
                                context=quality_context,
                            )
                        
                        if search_result.get("success") and search_result.get("results"):
                            quality_stats = search_result.get("quality_stats", {})
                            if quality_stats:
                                logger.info(f"GenericAgent {self.agent_id}: 质量过滤统计 - "
                                           f"过滤掉 {quality_stats.get('filtered_count', 0)} 条低质量结果, "
                                           f"来源分布: {quality_stats.get('tier_distribution', {})}")
                                all_results["quality_stats"][query] = quality_stats
                            
                            # 两阶段搜索策略：爬取URL获取完整内容
                            results_to_store = search_result["results"]
                            if web_scraper:
                                enriched_results = await self._enrich_results_with_content(
                                    search_result["results"][:10],  # 只爬取前10个URL，避免超时
                                    web_scraper,
                                    query,
                                )
                                if enriched_results:
                                    results_to_store = enriched_results
                                    logger.info(f"GenericAgent {self.agent_id}: 爬取了 {len(enriched_results)} 个URL的完整内容")
                            
                            unique_results = []
                            for r in results_to_store:
                                url = r.get("href", "") or r.get("url", "")
                                if url and url in seen_urls:
                                    continue
                                if url:
                                    seen_urls.add(url)
                                unique_results.append(r)

                            all_results["searches"].append({
                                "query": query,
                                "results": unique_results,
                                "quality_stats": quality_stats,
                            })
                            all_results["total_sources"] = len(seen_urls)
                            
                    except asyncio.TimeoutError:
                        logger.warning(f"GenericAgent {self.agent_id}: 搜索 '{query}' 超时")
                    except Exception as e:
                        logger.warning(f"GenericAgent {self.agent_id}: 搜索 '{query}' 失败: {e}")
                
                # 质量评估
                quality_score = self._evaluate_data_quality(all_results)
                high_quality_count = self._count_high_quality_sources(all_results, MIN_QUALITY_SCORE)
                
                # 质量停滞检测
                if quality_score > best_quality_score:
                    best_quality_score = quality_score
                    stagnation_count = 0
                else:
                    stagnation_count += 1
                
                logger.info(f"GenericAgent {self.agent_id}: 迭代{iteration}完成 - "
                           f"已搜索{len(executed_queries)}次(最低{min_queries}次), "
                           f"总来源={all_results['total_sources']}, "
                           f"高质量来源={high_quality_count}, "
                           f"质量分={quality_score:.1f}")
                
                # 实时持久化：每次搜索迭代后保存已收集数据到 ResearchResultStore
                try:
                    task_id = (self._context or {}).get("task_id", "")
                    if task_id and all_results.get("total_sources", 0) > 0:
                        from src.core.storage import ResearchResultStore, ResearchStatus
                        store = ResearchResultStore(storage_path="data")
                        # 提取已收集的 data_points 和 sources
                        saved_data_points = []
                        saved_sources = []
                        for search in all_results.get("searches", []):
                            for item in search.get("results", []):
                                evidence = self._evidence_metadata(item)
                                saved_data_points.append({
                                    "title": item.get("title", ""),
                                    "content": item.get("body", "") or item.get("snippet", ""),
                                    "url": item.get("href", "") or item.get("url", ""),
                                    **evidence,
                                })
                                saved_sources.append({
                                    "title": item.get("title", ""),
                                    "url": item.get("href", "") or item.get("url", ""),
                                    **evidence,
                                })
                        store.save_result(
                            task_id=task_id,
                            result={
                                "topic": self._context.get("topic", ""),
                                "sections": [],
                                "data_points": saved_data_points,
                                "sources": saved_sources,
                            },
                            status=ResearchStatus.COLLECTING,
                        )
                except Exception as e:
                    logger.warning(f"GenericAgent {self.agent_id}: ResearchResultStore持久化失败: {e}")
                
                # 只有在达到最低搜索次数后才检查质量
                if len(executed_queries) >= min_queries:
                    # 质量达标检查：必须同时满足最少搜索次数+质量评分达标
                    if high_quality_count >= MIN_SOURCES and quality_score >= MIN_QUALITY_SCORE:
                        logger.info(f"GenericAgent {self.agent_id}: 已达最低搜索次数({min_queries})且质量达标，停止搜索")
                        break
                    elif stagnation_count >= STAGNATION_LIMIT:
                        # 质量停滞：连续多轮质量未提升，使用当前最佳数据
                        logger.info(f"GenericAgent {self.agent_id}: 搜索质量连续{STAGNATION_LIMIT}轮未提升"
                                   f"(最佳质量分={best_quality_score:.1f})，接受当前数据({all_results['total_sources']}个数据源)")
                        break
                    else:
                        logger.info(f"GenericAgent {self.agent_id}: 已达最低搜索次数({min_queries})但质量未达标"
                                   f"(高质量源={high_quality_count}/{MIN_SOURCES}, 质量分={quality_score:.1f}/{MIN_QUALITY_SCORE})，继续搜索")
                else:
                    logger.info(f"GenericAgent {self.agent_id}: 未达最低搜索次数({len(executed_queries)}/{min_queries})，继续搜索")
                
                # 新增：硬限制检查（防止无限循环）
                # Source diversity check: if >80% sources are from Chinese domains,
                # trigger English-only supplementary searches for international data diversity.
                cn_domain_count = 0
                total_source_count = 0
                for search in all_results.get("searches", []):
                    for item in search.get("results", []):
                        url = item.get("href", "") or item.get("url", "")
                        total_source_count += 1
                        if url and (".cn" in url.lower() or "baidu" in url.lower()):
                            cn_domain_count += 1
                
                if total_source_count > 5 and cn_domain_count / total_source_count > 0.8:
                    logger.info(f"GenericAgent {self.agent_id}: source diversity low ({cn_domain_count}/{total_source_count} CN domains), triggering English supplementary search")
                    from datetime import datetime
                    eng_queries = self._get_english_queries(
                        topic, aspect or "", datetime.now().year, datetime.now().year - 1,
                        role_info=role_info,
                    )
                    new_eng = [q for q in eng_queries if q not in executed_queries]
                    if new_eng:
                        queries.extend(new_eng[:3])
                
                if len(executed_queries) >= MAX_QUERIES:
                    logger.warning(f"GenericAgent {self.agent_id}: reached max queries {MAX_QUERIES}, stopping")
                    break
                
                if iteration >= MAX_ITERATIONS:
                    logger.warning(f"GenericAgent {self.agent_id}: 达到最大迭代轮数 {MAX_ITERATIONS}，强制停止")
                    break
                
                # 新增：质量停滞时触发 LLM 扩展（优先于硬编码回退）
                if stagnation_count >= 2 and llm_call_count < MAX_LLM_CALLS:
                    import time
                    elapsed = time.time() - last_llm_call_time
                    if elapsed < MIN_CALL_INTERVAL:
                        await asyncio.sleep(MIN_CALL_INTERVAL - elapsed)
                    
                    logger.info(f"GenericAgent {self.agent_id}: 质量停滞，触发 LLM 关键词扩展 (第{llm_call_count + 1}次)")
                    
                    llm_queries = await self._generate_smart_queries_with_llm(
                        topic=topic,
                        aspect=aspect,
                        existing_queries=list(executed_queries),
                        role_info=role_info,
                        min_queries=min_queries,
                    )
                    
                    if llm_queries:
                        queries.extend(llm_queries)
                        llm_call_count += 1
                        last_llm_call_time = time.time()
                        logger.info(f"GenericAgent {self.agent_id}: LLM 扩展了 {len(llm_queries)} 个新查询")
                        continue  # 立即使用新查询
                
                # 生成补充查询（硬编码回退）
                supplementary_queries = self._generate_supplementary_queries(
                    topic, aspect, all_results, executed_queries
                )
                
                # 新增：如果硬编码也无法生成新查询，接受当前数据
                if not supplementary_queries:
                    logger.info(f"GenericAgent {self.agent_id}: 无法生成更多查询，接受当前数据")
                    break
                    
                queries.extend(supplementary_queries)
            
            logger.info(f"GenericAgent {self.agent_id}: 深度研究完成，获取 {all_results['total_sources']} 个数据源，"
                       f"执行了 {len(executed_queries)} 次搜索")
            
        except Exception as e:
            logger.warning(f"GenericAgent {self.agent_id}: 深度研究失败: {e}")
        
        return all_results
    
    @staticmethod
    def _is_english_query(query: str) -> bool:
        """Detect whether a search query is primarily English or Chinese.
        
        English queries should be routed to international search engines (Google, DDGS, Bing Intl)
        for higher quality results. Chinese queries work better on domestic engines (Baidu, 360, Sogou)
        for local market data.
        
        Args:
            query: Search query string
            
        Returns:
            True if the query contains mostly ASCII/English characters, False if mostly Chinese
        """
        if not query:
            return False
        # Count Chinese characters
        chinese_chars = sum(1 for c in query if '\u4e00' <= c <= '\u9fff')
        total_chars = len(query.strip())
        if total_chars == 0:
            return False
        # If more than 30% of non-space characters are Chinese, treat as Chinese query
        non_space = sum(1 for c in query if not c.isspace())
        return (chinese_chars / non_space) < 0.3
    
    @staticmethod
    def _extract_keywords(topic: str) -> str:
        """
        从研究主题中提取核心关键词（去除研究类通用词）
        
        "中国新能源汽车市场深度研究" → "新能源汽车"
        "全球AI芯片行业分析报告" → "AI芯片"
        """
        import re
        # 去除常见的研究类后缀
        keywords = re.sub(
            r'(深度研究|市场研究|研究报告|分析报告|行业分析|行业研究|发展研究|'
            r'发展分析|前景分析|市场分析|调查报告|调研报告|白皮书|蓝皮书)',
            '', topic
        )
        # 去除 "的"、"与"、"和" 等连词前后不重要的部分
        keywords = re.sub(r'^(中国|全球|国内|国外|亚太|欧美)\s*', '', keywords)
        # 去空格
        keywords = keywords.strip()
        # 如果提取后为空，返回原主题
        return keywords if keywords else topic

    # Map Chinese aspect keywords to English topic keywords for bilingual search.
    # English queries are routed to international search engines (Google, DDGS, Bing Intl)
    # and return higher-quality data for quantitative analysis.
    _ENGLISH_ASPECT_MAP = {
        "规模": "market size sales volume shipment",
        "市场": "market size sales volume shipment",
        "销量": "sales volume shipment units sold",
        "产量": "production output manufacturing volume",
        "竞争": "competition competitive landscape market share",
        "企业": "company enterprise corporation top players",
        "公司": "company enterprise corporation",
        "格局": "competitive landscape market structure",
        "趋势": "trend forecast outlook development",
        "发展": "development growth trend outlook",
        "未来": "future outlook forecast projection",
        "预测": "forecast projection prediction outlook",
        "政策": "policy regulation regulatory government",
        "法规": "regulation compliance legal regulatory",
        "投资": "investment capital funding financing",
        "融资": "funding financing capital raising",
        "资本": "capital investment funding financing",
        "技术": "technology R&D innovation patent",
        "研发": "R&D research development innovation",
        "创新": "innovation technology breakthrough R&D",
        "产业链": "supply chain value chain industry chain",
        "风险": "risk analysis downside uncertainty",
        "估值": "valuation PE PB EV EBITDA DCF",
        "财务": "financial revenue profit margin earnings",
        "用户": "user customer consumer demographic",
        "区域": "regional geographic distribution market penetration",
    }

    def _get_english_search_topic(self, topic: str) -> str:
        """Extract clean English search topic from Chinese research topic.
        
        Strips all Chinese characters and builds a pure English query string
        using the term mapping dictionary. This ensures English queries contain
        NO Chinese text, so they route to global engines (Google, DDGS, Bing Intl).
        
        Examples:
          "中国新能源汽车市场深度研究" -> "China new energy vehicle NEV electric vehicle auto market"
          "全球AI芯片行业分析报告" -> "global AI chip semiconductor industry"
          "中国医药生物行业投资策略" -> "China pharmaceutical biotech industry"
        """
        import re
        # Remove research suffixes
        kw = re.sub(
            r'(深度研究|市场研究|研究报告|分析报告|行业分析|行业研究|发展研究|'
            r'发展分析|前景分析|市场分析|调查报告|调研报告|白皮书|蓝皮书)',
            '', topic
        )
        
        # Extract region prefix
        region_prefix = ""
        region_map = {
            "中国": "China", "全球": "global", "国内": "China domestic",
            "国外": "international", "亚太": "Asia Pacific", "欧美": "Europe US",
        }
        m = re.match(r'^(中国|全球|国内|国外|亚太|欧美)', kw)
        if m:
            region_prefix = region_map.get(m.group(1), m.group(1)) + " "
            kw = kw[m.end():]
        
        # Remove any remaining Chinese characters not covered by term_map
        # Keep only ASCII, digits, and spaces for clean English output
        kw_ascii = re.sub(r'[^\x00-\x7F]+', ' ', kw).strip()
        
        # Common Chinese industry terms to English mapping
        term_map = {
            "新能源": "new energy",
            "汽车": "vehicle automotive",
            "新能源车": "new energy vehicle NEV",
            "新能源汽车": "new energy vehicle NEV electric vehicle",
            "电动": "electric EV",
            "半导体": "semiconductor chip",
            "芯片": "chip semiconductor",
            "人工智能": "artificial intelligence AI",
            "AI": "AI artificial intelligence",
            "大数据": "big data",
            "云计算": "cloud computing",
            "互联网": "internet",
            "数字化": "digital transformation",
            "医药": "pharmaceutical biotech",
            "医疗": "healthcare medical",
            "生物": "biotech biological",
            "消费": "consumer consumption retail",
            "零售": "retail e-commerce",
            "金融": "financial finance banking",
            "保险": "insurance",
            "地产": "real estate property",
            "制造": "manufacturing industrial",
            "工业": "industrial manufacturing",
            "通信": "telecommunications 5G",
            "软件": "software SaaS enterprise",
            "能源": "energy solar wind power",
            "市场": "market industry",
            "行业": "industry sector",
            "产业": "industry sector",
            "深度": "in-depth analysis",
            "研究": "research analysis",
        }
        
        # Build English-only search topic: only use ASCII remnants + term map translations
        eng_parts = [kw_ascii] if kw_ascii else []
        for ch_term, en_term in term_map.items():
            if ch_term in kw:
                eng_parts.append(en_term)
        
        # Ensure at least one meaningful term exists
        eng_parts = [p for p in eng_parts if p and not all(c in ' \t\n\r' for c in p)]
        if not eng_parts:
            eng_parts = ["market research"]
        
        return region_prefix + " ".join(set(eng_parts))
    
    def _get_english_queries(
        self,
        topic: str,
        aspect: str,
        current_year: int,
        prev_year: int,
        role_info: Optional[Dict] = None,
    ) -> List[str]:
        """Generate English search queries for better international results.
        
        These queries are routed to global search engines (Google, DDGS, Bing Intl)
        instead of Chinese engines (Baidu, 360, Sogou) to avoid low-quality SEO spam.
        
        Args:
            topic: Research topic
            aspect: Research dimension (Chinese)
            current_year: Current year
            prev_year: Previous year
            
        Returns:
            List of English query strings
        """
        eng_topic = self._get_english_search_topic(topic)
        aspect_lower = aspect.lower()
        queries = []
        
        # Map Chinese aspect keywords to English query templates
        if any(kw in aspect_lower for kw in ["规模", "市场", "销量", "产量"]):
            queries = [
                f"{eng_topic} sales volume {current_year} statistics",
                f"{eng_topic} market size {current_year} report",
                f"{eng_topic} market share {current_year}",
                f"{eng_topic} industry data {current_year} forecast",
                f"{eng_topic} production output {prev_year} annual report",
            ]
        elif any(kw in aspect_lower for kw in ["竞争", "企业", "公司", "格局"]):
            queries = [
                f"{eng_topic} top companies market share {current_year}",
                f"{eng_topic} competitive landscape {current_year}",
                f"{eng_topic} leading players ranking {current_year}",
                f"{eng_topic} industry concentration CR{current_year}",
                f"{eng_topic} market competition analysis",
            ]
        elif any(kw in aspect_lower for kw in ["趋势", "发展", "未来", "预测"]):
            queries = [
                f"{eng_topic} market trend forecast {current_year}",
                f"{eng_topic} industry outlook {current_year}",
                f"{eng_topic} technology trend {current_year}",
                f"{eng_topic} growth drivers {current_year}",
                f"{eng_topic} emerging trends {prev_year} {current_year}",
            ]
        elif any(kw in aspect_lower for kw in ["政策", "法规"]):
            queries = [
                f"{eng_topic} regulation policy {current_year}",
                f"{eng_topic} government policy impact {current_year}",
                f"{eng_topic} regulatory framework compliance",
                f"{eng_topic} subsidy incentive program",
                f"{eng_topic} trade policy tariff {current_year}",
            ]
        elif any(kw in aspect_lower for kw in ["技术", "研发", "创新"]):
            queries = [
                f"{eng_topic} technology innovation patent {current_year}",
                f"{eng_topic} R&D investment breakthrough {current_year}",
                f"{eng_topic} emerging technology roadmap",
                f"{eng_topic} patent filing trend analysis",
            ]
        elif any(kw in aspect_lower for kw in ["投资", "融资", "资本"]):
            queries = [
                f"{eng_topic} investment funding {current_year}",
                f"{eng_topic} M&A deal {current_year}",
                f"{eng_topic} IPO valuation {current_year}",
                f"{eng_topic} venture capital funding",
            ]
        elif any(kw in aspect_lower for kw in ["产业链", "供应链"]):
            queries = [
                f"{eng_topic} supply chain value chain analysis",
                f"{eng_topic} upstream downstream margin profit pool",
                f"{eng_topic} vertical integration supply {current_year}",
            ]
        elif any(kw in aspect_lower for kw in ["风险"]):
            queries = [
                f"{eng_topic} risk analysis downside {current_year}",
                f"{eng_topic} industry risk factor assessment",
            ]
        else:
            # Generic English queries
            queries = [
                f"{eng_topic} {current_year} industry report",
                f"{eng_topic} market data {current_year}",
                f"{eng_topic} {aspect} analysis {current_year}",
            ]
        
        # Add topic-specific common queries
        queries.append(f"{eng_topic} {current_year} annual report")
        queries.append(f"{eng_topic} latest news {current_year}")
        
        # v3.4 R8: Add English queries from role_info.data_focus (en)
        if role_info:
            from src.core.search.domain_role_inferrer import DomainRoleInferrer
            en_inferrer = DomainRoleInferrer()
            en_role_info = en_inferrer.infer(
                role_info.get("research_type", "market_research"),
                topic,
                language="en",
            )
            en_data_focus = en_role_info.get("data_focus", [])
            for focus in en_data_focus[:3]:
                queries.append(f"{eng_topic} {focus} {current_year}")
        
        return queries

    def _detect_knowledge_gaps(self, content: str) -> List[str]:
        """Detect knowledge gaps in generated analysis content.
        
        Analyzes the generated analysis for missing quantitative data,
        insufficient coverage, and other indicators of shallow analysis.
        Returns a list of gap descriptions to target in supplementary search.
        
        Args:
            content: Generated analysis text
            
        Returns:
            List of gap descriptions, empty if content appears sufficient
        """
        if not content or len(content) < 500:
            return ["content too short, need more comprehensive data"]
        
        gaps = []
        
        # Gap 1: Missing quantitative data (numbers, percentages)
        number_count = len(re.findall(r'\d+[\.\d]*%|\d+[\.\d]*\s*亿|\d+[\.\d]*\s*万', content))
        if number_count < 5:
            gaps.append("insufficient quantitative data: need more statistics with specific numbers, percentages, and growth rates")
        
        # Gap 2: Missing year references (staleness indicator)
        from datetime import datetime
        current_year = datetime.now().year
        year_refs = len(re.findall(rf'{current_year}|\d{{4}}', content))
        if year_refs < 3:
            gaps.append("insufficient time-contextualized data: need more recent figures with year references")
        
        # Gap 3: Content too short (shallow analysis)
        if len(content) < 1500:
            gaps.append("analysis too brief: need deeper coverage with more supporting evidence")
        
        # Gap 4: Missing comparison/trend language
        trend_keywords = ["增长", "下降", "同比", "环比", "趋势", "增长", "decline", "growth", "trend", "increase", "decrease"]
        trend_count = sum(1 for kw in trend_keywords if kw in content)
        if trend_count < 3:
            gaps.append("missing trend analysis: need year-over-year comparisons and growth trajectory discussion")
        
        logger.info(f"Knowledge gap detection: {len(gaps)} gaps found (numbers={number_count}, years={year_refs}, length={len(content)})")
        return gaps

    async def _detect_semantic_gaps(self, content: str) -> List[str]:
        """
        使用 LLM 检测语义级别的知识缺口。

        仅在启发式检查已触发缺口后由 execute() 调用（成本控制）。

        检查维度:
            1. 结构要素完整性: 核心结论/论证分析/数据支撑/风险提示
            2. 风险提示: 不确定性/假设前提/数据缺口/替代情景

        Returns:
            List[str]: 语义缺口描述（最多 2 项）
        """
        summary = content[:400]

        prompt = (
            "分析以下研究内容，检测知识缺口。以 JSON 格式输出。\n\n"
            "## 检查维度\n"
            "1. 结构完整性：是否包含核心结论、论证分析、"
            "数据支撑、风险提示四个要素？\n"
            "2. 反证覆盖：是否讨论了不确定性、假设前提、数据缺口，以及可能推翻当前结论的替代情景？\n\n"
            "## 内容\n"
            f"{summary}\n\n"
            "## 输出格式\n"
            '{"gaps": ["缺口描述1", "缺口描述2"], '
            '"has_structure": true/false, '
            '"has_counter_evidence": true/false}'
        )

        resp = await self._call_llm_directly(
            prompt=prompt,
            temperature=0.2,
        )

        if not resp.get("success"):
            return []

        result_text = resp.get("content", "")

        import json
        try:
            parsed = json.loads(result_text)
            if isinstance(parsed, dict):
                gaps = parsed.get("gaps", [])
                return gaps[:2]
        except (json.JSONDecodeError, ValueError):
            pass

        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', result_text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
                if isinstance(parsed, dict):
                    return parsed.get("gaps", [])[:2]
            except (json.JSONDecodeError, ValueError):
                pass

        return []

    async def _supplementary_search_for_gaps(
        self,
        topic: str,
        aspect: str,
        gaps: List[str],
        skill_registry: Any,
    ) -> Dict[str, Any]:
        """Perform targeted supplementary search to fill knowledge gaps.
        
        Uses English queries on global search engines for higher quality data.
        
        Args:
            topic: Research topic
            aspect: Research dimension
            gaps: List of gap descriptions from _detect_knowledge_gaps()
            skill_registry: Skill registry for accessing search skill
            
        Returns:
            Dict with 'data_points' and 'sources' lists, or empty dict on failure
        """
        # Get search skill from registry (not from available_skills, since analysis agents don't have it)
        search_skill = self._get_search_skill(skill_registry)
        if not search_skill:
            logger.info(f"GenericAgent {self.agent_id}: no search skill available for gap filling")
            return {}
        
        # Generate targeted queries based on gaps
        from datetime import datetime
        current_year = datetime.now().year
        eng_topic = self._get_english_search_topic(topic)
        
        # Build gap-specific queries
        gap_queries = []
        for gap in gaps:
            if "quantitative" in gap or "statistics" in gap:
                gap_queries.append(f"{eng_topic} {aspect} statistics {current_year} data")
                gap_queries.append(f"{eng_topic} {aspect} market size growth rate {current_year}")
            elif "trend" in gap or "year" in gap:
                gap_queries.append(f"{eng_topic} {aspect} trend forecast {current_year}")
                gap_queries.append(f"{eng_topic} {aspect} year over year comparison")
            elif "brief" in gap or "shallow" in gap:
                gap_queries.append(f"{eng_topic} {aspect} in-depth analysis report {current_year}")
        
        # Also add general supplementary queries
        standard = self._get_english_queries(topic, aspect, current_year, current_year - 1, role_info=None)
        gap_queries.extend(standard[:3])
        
        # Execute searches
        all_data_points = []
        all_sources = []
        seen_urls = set()
        
        for query in gap_queries[:4]:  # Max 4 gap-filling queries
            try:
                search_result = await search_skill.execute(
                        query=query,
                        max_results=10,
                        region="global",
                        enable_quality_filter=True,
                        min_quality_score=35.0,
                    )
                if search_result.get("success") and search_result.get("results"):
                    for item in search_result["results"]:
                        url = item.get("href", "") or item.get("url", "")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            evidence = self._evidence_metadata(item)
                            all_data_points.append({
                                "title": item.get("title", ""),
                                "content": item.get("body", "") or item.get("snippet", ""),
                                "url": url,
                                "quality_score": item.get("quality_score", 0),
                                **evidence,
                            })
                            all_sources.append({
                                "title": item.get("title", ""),
                                "url": url,
                                "type": "web",
                                **evidence,
                            })
            except Exception as e:
                logger.warning(f"GenericAgent {self.agent_id}: gap-fill search failed for '{query}': {e}")
        
        if all_data_points:
            logger.info(f"GenericAgent {self.agent_id}: gap-fill collected {len(all_data_points)} supplementary data points")
            return {"data_points": all_data_points, "sources": all_sources}
        return {}

    def _validate_collected_data(
        self,
        data_points: List[Dict[str, Any]],
        sources: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Validate and cross-reference collected data points.
        
        DATA_VALIDATION phase: checks data quality by:
        1. Deduplication: remove duplicate URLs
        2. Source credibility scoring: classify by domain authority
        3. Conflict detection: identify contradictory data points
        4. Timeliness check: flag data without recent year references
        5. Completeness: identify gaps in coverage
        
        Args:
            data_points: Raw data points from DATA_COLLECTION phase
            sources: Source metadata from DATA_COLLECTION phase
            
        Returns:
            Dict with validated_data_points, warnings, conflicts, and quality_score
        """
        validated = []
        seen_urls = set()
        warnings = []
        conflicts = []
        total_score = 0.0
        
        # Domain authority scoring
        authority_domains = _AUTHORITY_DOMAINS
        
        # Track numerical claims for conflict detection
        # e.g. "market reached 12.8 million units" -> extract "12.8 million"
        numerical_claims: Dict[str, List[Dict]] = {}
        
        current_year = datetime.now().year
        
        for dp in data_points:
            url = dp.get("url", "")
            title = dp.get("title", "")
            content = dp.get("content", "") or ""
            source_text = title + " " + content
            
            # Step 1: Deduplication
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            
            # Step 1.5: Structured data sources get maximum credibility
            is_structured = (
                dp.get("credibility") == "structured_source"
                or any(url.startswith(f"{s}://") for s in ("stock_data", "wind_data", "bloomberg_data"))
            )
            if is_structured:
                year_refs = set()
                for y in range(current_year - 5, current_year + 2):
                    if str(y) in source_text:
                        year_refs.add(y)
                validated.append({
                    "title": title,
                    "content": content,
                    "url": url,
                    "domain": "",
                    "credibility_score": 1.0,
                    "credibility_source": "structured_database",
                    "quality_score": max(dp.get("quality_score", 0), 90),
                    "year_refs": sorted(year_refs) if year_refs else [],
                    "is_recent": True,
                })
                total_score += max(dp.get("quality_score", 0), 90)
                continue
            
            # Step 2: Source credibility scoring via domain authority
            domain = ""
            try:
                domain = urlparse(url).netloc.lower() if url else ""
                if domain.startswith("www."):
                    domain = domain[4:]
            except Exception:
                pass
            
            # Check domain against authority list (exact + suffix match)
            credibility_score = 0.5  # Default medium credibility
            matched_rule = "general website"
            if domain:
                if domain in authority_domains:
                    credibility_score = authority_domains[domain]
                    matched_rule = f"known authority: {domain}"
                else:
                    for auth_domain, score in authority_domains.items():
                        if domain.endswith("." + auth_domain) or domain == auth_domain:
                            credibility_score = max(credibility_score, score)
                            matched_rule = f"subdomain of: {auth_domain}"
                            break
            
            # Step 3: Timeliness - check for year references in content
            year_refs = set()
            for y in range(current_year - 5, current_year + 2):
                if str(y) in source_text:
                    year_refs.add(y)
            
            is_recent = any(y >= current_year - 1 for y in year_refs)
            if not is_recent:
                warnings.append({
                    "type": "timeliness",
                    "message": f"No recent data found in: {title[:60]}",
                    "url": url,
                })
            
            # Step 4: Extract numerical claims for cross-referencing
            # Look for patterns like "XX%", "XX billion", "XX million"
            number_patterns = re.findall(r'(\d+[\.\d]*\s*%|\d+[\.\d]*\s*(?:亿|万|billion|million|thousand))', source_text)
            for match in number_patterns[:3]:  # Limit per source
                # Normalize the claim key (e.g. "35.6%" -> "percent_35.6")
                claim_key = f"num_{match.strip()}"
                if claim_key not in numerical_claims:
                    numerical_claims[claim_key] = []
                numerical_claims[claim_key].append({
                    "source": title[:50],
                    "url": url,
                    "value": match.strip(),
                })
            
            # Step 5: Quality score per data point
            q_score = 0.0
            q_score += credibility_score * 40.0  # 0-40 points from authority
            q_score += 20.0 if is_recent else 0.0  # 0-20 for recency
            q_score += 10.0 if len(content) > 100 else 5.0 if content else 0.0  # 0-10 for content depth
            q_score += 10.0 if number_patterns else 0.0  # 0-10 for containing data
            q_score += 10.0 if len(title) > 15 else 5.0  # 0-10 for meaningful title
            q_score += 10.0 if url else 0.0  # 0-10 for having URL
            
            validated.append({
                "title": title,
                "content": content,
                "url": url,
                "domain": domain,
                "credibility_score": round(credibility_score, 2),
                "credibility_source": matched_rule,
                "quality_score": round(min(q_score, 100.0), 1),
                "year_refs": sorted(year_refs) if year_refs else [],
                "is_recent": is_recent,
            })
            total_score += q_score
        
        # Step 6: Conflict detection
        for claim_key, claim_sources in numerical_claims.items():
            if len(claim_sources) >= 2:
                # Check if same value appears across sources (consistency)
                values = set(s["value"] for s in claim_sources)
                if len(values) > 1:
                    conflicts.append({
                        "type": "numerical_conflict",
                        "claim": claim_key,
                        "sources": claim_sources,
                        "message": f"Conflicting values: {', '.join(sorted(values))}",
                    })
        
        # Step 7: Overall quality assessment
        n = len(validated)
        avg_score = round(total_score / n, 1) if n > 0 else 0.0
        
        quality_rating = "high"
        if avg_score < 50:
            quality_rating = "low"
        elif avg_score < 70:
            quality_rating = "medium"
        
        return {
            "status": "completed",
            "validated_data_points": validated,
            "total_input": len(data_points),
            "total_validated": len(validated),
            "deduplicated": len(data_points) - len(validated),
            "average_quality_score": avg_score,
            "quality_rating": quality_rating,
            "warnings": warnings[:10],
            "conflicts": conflicts[:5],
            "has_conflicts": len(conflicts) > 0,
            "sources": sources,
        }

    def _generate_search_queries(
        self,
        topic: str,
        aspect: str,
        aspects: List[str],
        intent_result: Optional[Any] = None,
        role_info: Optional[Dict] = None,
    ) -> List[str]:
        """
        Generate search queries (bilingual: Chinese + English).
        
        v3.4 enhancements:
        - Accept role_info and intent_result for domain-aware query generation
        - Detect is_generic_data_focus and is_data_focus_irrelevant_to_aspect
        - Merge hardcoded queries with intent-driven queries when data_focus is generic or irrelevant
        
        Args:
            topic: Research topic
            aspect: Single research dimension
            aspects: Multiple research dimensions
            intent_result: Intent analysis result (IntentAnalysisResult or DeepIntentResult)
            role_info: Domain role information from DomainRoleInferrer
            
        Returns:
            List of query strings (mix of Chinese and English)
        """
        queries = []

        # 使用 KeywordDeriver 结构化派生关键词
        try:
            from src.core.search.keyword_deriver import KeywordDeriver
            deriver = KeywordDeriver()
            kw = deriver.derive(topic, aspect or "")
            search_topic = kw["core"][0] if kw["core"] else self._extract_keywords(topic)
        except Exception:
            search_topic = self._extract_keywords(topic)

        from datetime import datetime
        current_year = datetime.now().year
        prev_year = current_year - 1
        
        # v3.4 R2: Confidence-aware domain context usage
        confidence = 1.0
        if intent_result:
            confidence = getattr(intent_result, 'intent_confidence', None) or getattr(intent_result, 'confidence', 1.0)
        use_domain_context = confidence >= 0.5
        
        # v3.4 R2: Data source - role_info.data_focus first
        data_focus = []
        is_generic_data_focus = False
        is_data_focus_irrelevant_to_aspect = False
        
        context_data_needs = self._context.get("data_needs", []) if self._context else []
        if context_data_needs:
            for need in context_data_needs:
                queries.append(f"{search_topic} {need} {current_year}")
                queries.append(f"{search_topic} {need} 数据")
            queries.append(f"{search_topic} {aspect} {current_year}")
            logger.info(f"GenericAgent {self.agent_id}: using data_needs ({len(context_data_needs)} needs) for queries, skipping data_focus")
        elif role_info:
            data_focus = role_info.get('data_focus', [])
            from src.core.search.domain_role_inferrer import DomainRoleInferrer
            default_focus = DomainRoleInferrer.DEFAULT_TEMPLATE.get("data_focus", {}).get("zh", [])
            if data_focus and set(data_focus) == set(default_focus):
                is_generic_data_focus = True
        
        domain_context = {}
        hidden_requirements = []
        if intent_result and use_domain_context:
            domain_context = getattr(intent_result, 'domain_context', {}) or {}
            hidden_requirements = getattr(intent_result, 'hidden_requirements', []) or []
            if not data_focus:
                data_focus = domain_context.get('data_focus', [])
        
        # v3.4 R2: Generate intent-driven queries from data_focus
        if data_focus:
            for focus in data_focus[:4]:
                queries.append(f"{search_topic} {focus} {current_year}")
                queries.append(f"{search_topic} {focus} 数据")
                if aspect:
                    queries.append(f"{search_topic} {aspect} {focus} {current_year}")
        
        # v3.4 R2: Check data_focus relevance to aspect
        if aspect and data_focus and not is_generic_data_focus:
            aspect_lower = aspect.lower()
            relevant_to_aspect = any(
                focus in aspect_lower or aspect_lower in focus
                for focus in data_focus
            )
            if not relevant_to_aspect:
                is_data_focus_irrelevant_to_aspect = True
        
        # v3.4 R2: Hidden requirements-driven queries
        if use_domain_context:
            for req in hidden_requirements[:4]:
                queries.append(f"{search_topic} {req} {current_year}")
                queries.append(f"{search_topic} {req}")
        
        # v3.4 R2: Expertise-driven queries (skip when data_needs present)
        if not context_data_needs and role_info:
            expertise = role_info.get('expertise', [])
            if expertise:
                expertise_str = expertise[0] if isinstance(expertise, list) else expertise
                queries.append(f"{search_topic} {expertise_str} {current_year}")
        
        # v3.4 R2: Hardcoded logic - only fallback when no queries generated
        if not queries:
            if aspect:
                aspect_lower = aspect.lower()
                
                if any(kw in aspect_lower for kw in ["规模", "市场", "销量", "产量"]):
                    queries.extend([
                        f"{search_topic} 销量 {current_year} 统计",
                        f"{search_topic} 产量 {current_year} 数据",
                        f"{search_topic} 市场份额 {current_year}",
                        f"{search_topic} 销量 {prev_year} 年度",
                        f"{search_topic} 行业数据 {current_year}",
                    ])
                elif any(kw in aspect_lower for kw in ["竞争", "企业", "公司", "格局"]):
                    queries.extend([
                        f"{search_topic} 企业销量排名 {current_year}",
                        f"{search_topic} 主要企业 名单",
                        f"{search_topic} 厂商 市场份额 {current_year}",
                        f"{search_topic} 龙头企业 动态",
                        f"{search_topic} 新进入企业 {current_year}",
                    ])
                elif any(kw in aspect_lower for kw in ["趋势", "发展", "未来", "预测"]):
                    queries.extend([
                        f"{search_topic} 政策 {current_year}",
                        f"{search_topic} 新技术 {current_year}",
                        f"{search_topic} 行业动态 {current_year}",
                        f"{search_topic} 重要事件 {current_year}",
                        f"{search_topic} 技术路线",
                    ])
                elif any(kw in aspect_lower for kw in ["投资", "融资", "资本"]):
                    queries.extend([
                        f"{search_topic} 融资 {current_year}",
                        f"{search_topic} 投资 项目 {current_year}",
                        f"{search_topic} IPO {current_year}",
                        f"{search_topic} 并购 {current_year}",
                        f"{search_topic} 资本动态",
                    ])
                elif any(kw in aspect_lower for kw in ["政策", "法规", "监管"]):
                    queries.extend([
                        f"{search_topic} 政策文件 {current_year}",
                        f"{search_topic} 法规 {current_year}",
                        f"{search_topic} 补贴政策 {current_year}",
                        f"{search_topic} 监管通知 {current_year}",
                        f"{search_topic} 标准 规范",
                    ])
                elif any(kw in aspect_lower for kw in ["技术", "研发", "创新"]):
                    queries.extend([
                        f"{search_topic} 技术突破 {current_year}",
                        f"{search_topic} 专利 {current_year}",
                        f"{search_topic} 研发投入 {current_year}",
                        f"{search_topic} 新产品 {current_year}",
                        f"{search_topic} 技术路线图",
                    ])
                else:
                    queries.extend([
                        f"{search_topic} {aspect} 新闻 {current_year}",
                        f"{search_topic} {aspect} 数据 {current_year}",
                        f"{search_topic} {aspect} 动态",
                        f"{search_topic} {aspect} 公告",
                    ])
                
                queries.extend([
                    f"{search_topic} 最新消息 {current_year}",
                    f"{search_topic} 官方数据 {current_year}",
                ])
                
            elif aspects:
                for a in aspects[:4]:
                    a_lower = a.lower()
                    if any(kw in a_lower for kw in ["规模", "市场"]):
                        queries.append(f"{search_topic} 销量数据 {current_year}")
                    elif any(kw in a_lower for kw in ["竞争", "企业"]):
                        queries.append(f"{search_topic} 企业排名 {current_year}")
                    elif any(kw in a_lower for kw in ["趋势", "发展"]):
                        queries.append(f"{search_topic} 政策动态 {current_year}")
                    else:
                        queries.append(f"{search_topic} {a} 新闻 {current_year}")
                
                queries.append(f"{search_topic} 行业动态 {current_year}")
            else:
                queries.extend([
                    f"{search_topic} 新闻 {current_year}",
                    f"{search_topic} 数据统计 {current_year}",
                    f"{search_topic} 企业动态 {current_year}",
                    f"{search_topic} 政策 {current_year}",
                    f"{search_topic} 最新消息",
                ])
        
        # v3.4 R2: Multi-aspect processing
        if aspects and len(aspects) > 1:
            for extra_aspect in aspects[1:3]:
                queries.append(f"{search_topic} {extra_aspect} {current_year}")
                queries.append(f"{search_topic} {extra_aspect} 分析")
        
# Phase 2: English queries for international search engines
        eng_queries = self._get_english_queries(
            topic, aspect or "", current_year, prev_year,
            role_info=role_info,
        )
        queries.extend(eng_queries)
        
        # Deduplicate and return
        return list(dict.fromkeys(queries))
    
    def _generate_supplementary_queries(
        self,
        topic: str,
        aspect: str,
        current_results: Dict[str, Any],
        executed_queries: set,
    ) -> List[str]:
        """
        根据当前结果生成补充查询词
        
        **核心原则**：继续搜索原始数据，而非搜索报告或分析结论！
        
        Args:
            topic: 研究主题
            aspect: 研究维度（可能为None）
            current_results: 当前搜索结果
            executed_queries: 已执行的查询
            
        Returns:
            补充查询词列表（搜索原始数据）
        """
        from datetime import datetime
        current_year = datetime.now().year
        
        # 从主题中提取核心关键词
        search_topic = self._extract_keywords(topic)
        
        supplementary = []
        
        # 确保 aspect 不为 None
        aspect_str = aspect or ""
        
        # 分析当前结果缺失的数据类型
        has_numbers = False
        has_companies = False
        has_policies = False
        has_news = False
        has_technology = False
        has_investment = False
        
        for search in current_results.get("searches", []):
            for result in search.get("results", []):
                text = (result.get("title", "") + " " + result.get("body", "")).lower()
                if any(kw in text for kw in ["亿", "万", "%", "增长", "销量", "产量"]):
                    has_numbers = True
                if any(kw in text for kw in ["公司", "企业", "集团", "厂商", "品牌"]):
                    has_companies = True
                if any(kw in text for kw in ["政策", "法规", "补贴", "监管", "通知"]):
                    has_policies = True
                if any(kw in text for kw in ["新闻", "公告", "发布", "宣布"]):
                    has_news = True
                if any(kw in text for kw in ["技术", "研发", "专利", "创新", "突破"]):
                    has_technology = True
                if any(kw in text for kw in ["融资", "投资", "并购", "ipo", "资本"]):
                    has_investment = True
        
        # 生成补充查询 - 搜索原始数据源
        if aspect_str:
            if not has_numbers:
                supplementary.extend([
                    f"{search_topic} {aspect_str} 销量 {current_year}",
                    f"{search_topic} {aspect_str} 统计数据 {current_year}",
                    f"{search_topic} {aspect_str} 年度数据",
                ])
            if not has_companies:
                supplementary.extend([
                    f"{search_topic} {aspect_str} 企业名单",
                    f"{search_topic} {aspect_str} 主要厂商 {current_year}",
                    f"{search_topic} {aspect_str} 龙头企业",
                ])
            if not has_policies:
                supplementary.extend([
                    f"{search_topic} {aspect_str} 政策文件",
                    f"{search_topic} {aspect_str} 通知 {current_year}",
                    f"{search_topic} {aspect_str} 规划",
                ])
            if not has_technology:
                supplementary.extend([
                    f"{search_topic} {aspect_str} 技术进展 {current_year}",
                    f"{search_topic} {aspect_str} 研发动态",
                ])
            if not has_investment:
                supplementary.extend([
                    f"{search_topic} {aspect_str} 融资 {current_year}",
                    f"{search_topic} {aspect_str} 投资动态",
                ])
            
            # 添加更多原始数据搜索
            supplementary.extend([
                f"{search_topic} {aspect_str} 最新动态 {current_year}",
                f"{search_topic} {aspect_str} 公告",
            ])
        else:
            # aspect为空时的补充查询
            if not has_numbers:
                supplementary.append(f"{search_topic} 数据统计 {current_year}")
            if not has_companies:
                supplementary.append(f"{search_topic} 主要企业名单")
            if not has_policies:
                supplementary.append(f"{search_topic} 政策文件 {current_year}")
            
            supplementary.extend([
                f"{search_topic} 最新消息 {current_year}",
                f"{search_topic} 行业动态",
            ])
        
        # 过滤已执行的查询
        return [q for q in supplementary if q not in executed_queries]
    
    async def _enrich_results_with_content(
        self,
        search_results: List[Dict[str, Any]],
        web_scraper: Any,
        query: str,
    ) -> List[Dict[str, Any]]:
        """
        两阶段搜索策略：爬取搜索结果的URL获取完整内容
        
        这解决了搜索结果只有简短摘要的问题：
        - 搜索结果的 body 字段只是搜索引擎显示的简短摘要（几十个字）
        - 质量过滤器无法基于简短摘要准确评估内容质量
        - 通过爬取URL获取完整网页内容，可以：
          1. 更准确地评估内容质量
          2. 提供更丰富的数据给LLM分析
          3. 减少因摘要过短而被错误过滤的情况
        
        Args:
            search_results: 搜索结果列表（包含title, href, body等字段）
            web_scraper: WebScraperSkill实例
            query: 当前搜索查询词（用于日志）
            
        Returns:
            增强后的搜索结果列表（body字段替换为完整内容）
        """
        import asyncio
        
        enriched_results = []
        max_concurrent = 3  # 并发爬取数（避免被封）
        
        async def crawl_single_result(result: Dict[str, Any]) -> Dict[str, Any]:
            """爬取单个URL"""
            url = result.get("href", "")
            if not url or not url.startswith("http"):
                return result
            
            try:
                # 调用web_scraper爬取完整内容
                scraper_result = await web_scraper.execute(
                    url=url, action="extract_text"
                )
                
                if scraper_result.get("success"):
                    full_text = scraper_result.get("text", "") or scraper_result.get("result", "")
                    if full_text and len(full_text) > len(result.get("body", "")):
                        enriched = result.copy()
                        enriched["body"] = full_text[:3000]
                        enriched["full_content_fetched"] = True
                        enriched["content_length"] = len(full_text)
                        # 用完整内容重新计算 quality_score（原分基于 snippet 偏低）
                        _old_score = enriched.get("quality_score", 30)
                        if len(full_text) > 1000:
                            enriched["quality_score"] = max(_old_score, 55)
                        elif len(full_text) > 300:
                            enriched["quality_score"] = max(_old_score, 45)
                        logger.debug(f"GenericAgent: 爬取成功 {url[:50]}... "
                                     f"内容长度={len(full_text)}, 质量分={_old_score}->{enriched['quality_score']}")
                        return enriched
            except asyncio.TimeoutError:
                logger.debug(f"GenericAgent: 爬取超时 {url[:50]}...")
            except Exception as e:
                logger.debug(f"GenericAgent: 爬取失败 {url[:50]}... 错误={e}")
            
            # 爬取失败，保留原始结果
            return result
        
        # 使用信号量控制并发
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def crawl_with_semaphore(result: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                return await crawl_single_result(result)
        
        try:
            # 并发爬取所有URL
            tasks = [crawl_with_semaphore(r) for r in search_results]
            enriched_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            final_results = []
            for i, result in enumerate(enriched_results):
                if isinstance(result, Exception):
                    # 爬取异常，使用原始结果
                    final_results.append(search_results[i])
                else:
                    final_results.append(result)
            
            # 统计爬取成功数
            success_count = sum(1 for r in final_results if r.get("full_content_fetched"))
            logger.info(f"GenericAgent: 两阶段搜索 - 爬取 {len(search_results)} 个URL，成功 {success_count} 个")
            
            return final_results
            
        except Exception as e:
            logger.warning(f"GenericAgent: 两阶段搜索失败: {e}")
            return search_results
    
    # ============================================================
    # LLM 关键词扩展能力（Agent 内部 LLM 调用）
    # ============================================================
    
    async def _call_llm_directly(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 500,
        temperature: float = 0.7,
        action: str = "keyword_expand",
    ) -> Dict[str, Any]:
        """
        Agent 直接调用 LLM（通过统一 call_llm 接口）

        用于关键词扩展、决策辅助等 Agent 内部能力。

        Args:
            prompt: 用户提示
            system_prompt: 系统提示（可选）
            max_tokens: 最大输出 token 数
            temperature: 温度参数
            action: 路由动作标识（默认 "keyword_expand"）

        Returns:
            {"success": True, "content": "..."} 或 {"success": False, "error": "..."}
        """
        try:
            from src.core.llm_client import call_llm
            from src.config.llm_profiles import RoutingHint

            result = await call_llm(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                routing_hint=RoutingHint(agent_type="generic", action=action),
            )
            return result

        except Exception as e:
            logger.warning(f"GenericAgent {self.agent_id}: LLM 直接调用失败: {e}")
            return {"success": False, "content": "", "error": str(e)}
    
    def _validate_query(
        self,
        query: str,
        existing_queries: Optional[List[str]] = None,
    ) -> bool:
        """
        校验查询词是否有效
        
        Args:
            query: 待校验的查询词
            existing_queries: 已存在的查询词列表（避免重复）
            
        Returns:
            True 表示有效，False 表示无效
        """
        # 长度检查
        if len(query) < 5 or len(query) > 100:
            return False
        
        # 纯数字或纯符号检查
        if query.isdigit() or all(not c.isalnum() for c in query):
            return False

        # Reject generic report-generation prompts.  They produce broad,
        # low-signal search results instead of a factual research query.
        forbidden_phrases = (
            "市场分析报告",
            "研究报告",
            "预测分析",
            "market research report",
            "market analysis report",
            "industry research forecast",
        )
        query_lower = query.casefold()
        if any(phrase.casefold() in query_lower for phrase in forbidden_phrases):
            return False
        
        # 重复检查
        if existing_queries and query in existing_queries:
            return False
        
        return True
    
    def _parse_llm_queries(
        self,
        content: str,
        existing_queries: Optional[List[str]] = None,
    ) -> List[str]:
        """
        解析 LLM 返回的查询词，带校验
        
        Args:
            content: LLM 返回的原始内容
            existing_queries: 已存在的查询词列表
            
        Returns:
            有效的查询词列表（最多 8 个）
        """
        queries = []
        
        for line in content.strip().split('\n'):
            line = line.strip()
            
            # 跳过空行和注释
            if not line or line.startswith('#') or len(line) < 5:
                continue
            
            # 清理序号（如 "1. xxx" → "xxx"）
            if line[0].isdigit():
                line = re.sub(r'^\d+[.、\s]*', '', line)
            
            # 校验并添加
            if self._validate_query(line, existing_queries):
                queries.append(line)
        
        return queries[:8]  # 最多返回 8 个
    
    async def _generate_smart_queries_with_llm(
        self,
        topic: str,
        aspect: str,
        existing_queries: Optional[List[str]] = None,
        role_info: Optional[Dict] = None,
        min_queries: int = 10,
    ) -> List[str]:
        """
        使用 LLM 智能生成搜索关键词（Agent 内部能力）
        
        **核心原则**：搜索原始数据，而非现成报告或分析结论！
        
        **变更说明**：
        - 移除旧 LLM Skill 依赖，改用 call_llm()
        - 新增 role_info 参数，接收 DomainRoleInferrer 推断的角色信息
        - 新增 min_queries 参数，确保生成足够的关键词
        
        Args:
            topic: 研究主题
            aspect: 研究维度
            existing_queries: 已有的查询（避免重复）
            role_info: 领域角色信息（来自 DomainRoleInferrer）
            min_queries: 最少搜索次数（用于计算需要生成的关键词数量）
            
        Returns:
            LLM 生成的搜索关键词列表
        """
        # 默认角色信息
        if not role_info:
            role_info = {
                "role": "资深研究分析师",
                "expertise": ["数据分析", "信息收集"],
                "data_focus": ["核心数据", "关键指标"],
            }
        
        from datetime import datetime
        current_year = datetime.now().year
        
        # 计算需要生成的关键词数量（确保大于 min_queries）
        target_count = max(10, int(min_queries * 1.5))
        
        # 提取角色信息
        role = role_info.get("role", "资深研究分析师")
        expertise = role_info.get("expertise", [])
        data_focus = role_info.get("data_focus", [])
        
        # 构建系统提示
        system_prompt = f"""你是一位{role}，擅长：{', '.join(expertise)}。
你的任务是生成精准的搜索查询词，用于收集：{', '.join(data_focus)}。

**查询设计原则**：
1. 精准优于泛泛：
   - 差：新能源汽车 数据
   - 好：新能源汽车 渗透率 2025 乘联会
2. 指定来源类型提高精度：
   - 新能源汽车 销量 中汽协 2025
   - 比亚迪 年报 营收 2024
   - 新能源汽车 券商研报 市场份额 2025
3. 优先搜索原始数据源（新闻、公告、统计），也搜索高质量报告（券商研报、咨询报告、行业协会报告）
4. 中英文分别设计查询

**输出格式**：每行一个查询词，不要编号，不要说明文字。"""

        # 构建用户提示
        prompt = f"""研究主题: {topic}
研究维度: {aspect or "综合分析"}
当前年份: {current_year}

请生成 {target_count} 个搜索查询词，格式：主题 + 数据类型 + 时间

示例：
{topic} 销量 {current_year}
{topic} 企业排名
{topic} 政策文件
{topic} 融资动态
{topic} 最新消息

查询词列表："""

        try:
            # 使用 Agent 内部的 LLM 调用能力
            result = await self._call_llm_directly(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=800,
                temperature=0.7,
            )
            
            if result.get("success"):
                content = result.get("content", "")
                # 使用统一的解析方法
                queries = self._parse_llm_queries(content, existing_queries)
                
                logger.info(f"GenericAgent {self.agent_id}: LLM 生成了 {len(queries)} 个关键词")
                return queries
            else:
                logger.warning(f"GenericAgent {self.agent_id}: LLM 调用失败: {result.get('error')}")
                return []
                
        except Exception as e:
            logger.warning(f"GenericAgent {self.agent_id}: LLM 关键词生成失败: {e}")
            return []
    
    def _evaluate_data_quality(self, results: Dict[str, Any]) -> float:
        """
        评估数据质量分数（权威度加权平均）
        
        Args:
            results: 搜索结果
            
        Returns:
            质量分数 (0-100)
        """
        CREDIBILITY_WEIGHT = {
            "tier1_authority": 4.0,
            "tier2_professional": 3.0,
            "tier3_reputable": 2.0,
            "tier4_general": 1.0,
            "tier5_low_quality": 0.2,
        }
        weighted_sum = 0.0
        weight_sum = 0.0
        for search in results.get("searches", []):
            for result in search.get("results", []):
                quality_score = result.get("quality_score", 30)
                credibility = result.get("credibility", "tier4_general")
                weight = CREDIBILITY_WEIGHT.get(credibility, 1.0)
                weighted_sum += quality_score * weight
                weight_sum += weight
        return weighted_sum / weight_sum if weight_sum > 0 else 0.0
    
    def _count_high_quality_sources(
        self,
        results: Dict[str, Any],
        min_score: float,
    ) -> int:
        """
        统计高质量来源数量
        
        Args:
            results: 搜索结果
            min_score: 最低质量分数
            
        Returns:
            高质量来源数量
        """
        count = 0
        
        for search in results.get("searches", []):
            for result in search.get("results", []):
                quality_score = result.get("quality_score", 0)
                credibility = result.get("credibility", "")
                
                # 权威来源或高质量来源
                if quality_score >= min_score or credibility in ["tier1_authority", "tier2_professional"]:
                    count += 1
        
        return count
    
    @staticmethod
    def _count_tokens(text: str) -> int:
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            pass
        import re as _re
        cjk = len(_re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]", text))
        ascii_chars = len(_re.findall(r"[a-zA-Z0-9\s]", text))
        other = max(0, len(text) - cjk - ascii_chars)
        return max(1, int(cjk * 1.5 + ascii_chars * 0.25 + other * 0.5))

    def _truncate_by_tokens(self, text: str, max_tokens: int = 2000, preserve_tables: bool = False) -> str:
        if not text:
            return text
        if self._count_tokens(text) <= max_tokens:
            return text
        if preserve_tables:
            table_parts = []
            text_parts = []
            current = []
            in_table = False
            for line in text.split('\n'):
                is_table_line = bool(line.strip()) and (
                    line.strip().startswith('|') or line.strip().startswith('+') or
                    line.strip().startswith('-') or set(line.strip()) <= {'|', '-', '+', ' ', ':'}
                )
                if is_table_line and not in_table:
                    if current:
                        text_parts.append('\n'.join(current))
                        current = []
                    in_table = True
                    current.append(line)
                elif not is_table_line and in_table:
                    table_parts.append('\n'.join(current))
                    current = []
                    in_table = False
                    current.append(line)
                else:
                    current.append(line)
            if current:
                if in_table:
                    table_parts.append('\n'.join(current))
                else:
                    text_parts.append('\n'.join(current))
            budget = max_tokens
            for tp in table_parts:
                budget -= self._count_tokens(tp)
            budget = max(budget, max_tokens // 4)
            truncated_text = self._truncate_text_to_tokens('\n\n'.join(text_parts), budget)
            result_parts = []
            for tp in table_parts:
                result_parts.append(tp)
            if truncated_text.strip():
                result_parts.append(truncated_text)
            return '\n\n'.join(result_parts) + "\n\n[... 内容因Token限制已截断，完整数据见结构化财务数据部分 ...]"
        return self._truncate_text_to_tokens(text, max_tokens)

    def _truncate_text_to_tokens(self, text: str, max_tokens: int) -> str:
        if self._count_tokens(text) <= max_tokens:
            return text
        paragraphs = text.split('\n\n')
        result = []
        current_tokens = 0
        for para in paragraphs:
            para_tokens = self._count_tokens(para)
            if current_tokens + para_tokens + 2 > max_tokens:
                break
            result.append(para)
            current_tokens += para_tokens + 2
        if not result:
            lines = text.split('\n')
            for line in lines:
                line_tokens = self._count_tokens(line)
                if current_tokens + line_tokens + 1 > max_tokens:
                    break
                result.append(line)
                current_tokens += line_tokens + 1
        truncated = '\n\n'.join(result) if '\n\n' in text[:500] else '\n'.join(result)
        if len(truncated) < len(text):
            truncated += "\n\n[... 内容因Token限制已截断，完整数据见结构化财务数据部分 ...]"
        return truncated

    def _truncate_by_paragraph(self, text: str, max_chars: int = 8000) -> str:
        if len(text) <= max_chars:
            return text
        paragraphs = text.split('\n\n')
        result = []
        current_len = 0
        for para in paragraphs:
            if current_len + len(para) + 2 > max_chars:
                break
            result.append(para)
            current_len += len(para) + 2
        if not result:
            lines = text.split('\n')
            for line in lines:
                if current_len + len(line) + 1 > max_chars:
                    break
                result.append(line)
                current_len += len(line) + 1
        truncated = '\n\n'.join(result) if '\n\n' in text[:max_chars] else '\n'.join(result)
        if len(truncated) < len(text):
            truncated += "\n\n[... 内容因长度限制已截断，完整数据见结构化财务数据部分 ...]"
        return truncated

    def _get_professional_role_prompt(self, aspect: str) -> str:
        from src.core.prompt_manager import get_profile_name_for_aspect
        from src.core.i18n import get_language_instruction
        from datetime import datetime
        
        _now = datetime.now()
        _current_date = _now.strftime("%Y-%m-%d")
        _current_year = str(_now.year)
        _prev_year = str(_now.year - 1)
        
        pm = PromptManager()
        profile_name = get_profile_name_for_aspect(aspect)
        try:
            profile = pm.load_profile(profile_name)
        except FileNotFoundError:
            profile = pm.load_profile('general')
        spec = pm.render('_shared', 'output_spec',
                         current_date=_current_date,
                         current_year=_current_year,
                         prev_year=_prev_year)
        lang_instruction = get_language_instruction()
        base = profile.system_prompt + '\n\n' + spec + '\n' + lang_instruction

        base += (
            "\n\n## 跨章节因果链分析要求\n"
            "在分析本维度时，必须思考你的结论如何与其他维度关联。"
            "例如：如果你分析'研发投入'，需要说明研发投入如何影响'财务预测'的营收增长假设；"
            "如果你分析'供应链成本'，需要解释降本如何传导至'核心财务指标'的利润率。"
            "在每个分析段落结尾，用1-2句话说明与其他章节的因果联系。\n"
            "\n## 日期约束\n"
            "当前日期为 {current_date}。不得编造超过当前日期的确定数据。"
            "当需要预测未来时，使用'预计'、'有望'等措辞，"
            "不要编造具体未来年份的确定数据（如'2028年营收将达到XX'是禁止的，"
            "应写为'预计未来2-3年营收有望达到XX'）。"
        ).format(current_date=_current_date)

        enrichment = getattr(self, '_knowledge_enrichment', {})

        entities = enrichment.get("entities", [])
        if entities:
            base += "\n\n## 已有知识参考\n"
            budget = 300
            for e in entities:
                line = f"- {e['name']}: {e.get('description', '')[:80]}\n"
                if budget - len(line) < 0:
                    break
                base += line
                budget -= len(line)

        patterns = enrichment.get("patterns", [])
        if patterns:
            base += "\n\n## 历史经验提醒\n"
            budget = 150
            for p in patterns:
                line = f"- {p['content'][:100]}\n"
                if budget - len(line) < 0:
                    break
                base += line
                budget -= len(line)

        methodologies = enrichment.get("methodologies", [])
        if methodologies:
            methodology_summaries = []
            for i, m in enumerate(methodologies[:3]):
                content = m.get('content', '')
                if content:
                    name = m.get('name') or m.get('methodology_name') or m.get('title') or f'框架{i+1}'
                    truncated = content[:300]
                    methodology_summaries.append(f"{i+1}. {name}: {truncated}")

            if methodology_summaries:
                base += "\n\n## 分析框架\n" + "\n\n".join(methodology_summaries) + "\n"

        quality_feedback = getattr(self, '_quality_feedback', {})
        if quality_feedback:
            fb_score = quality_feedback.get("score", "?")
            fb_issues = quality_feedback.get("issues", [])
            fb_attempt = quality_feedback.get("previous_attempt", 0)
            issues_text = "\n".join(
                f"  - {issue}" if isinstance(issue, str) else f"  - {issue.get('message', str(issue))}"
                for issue in fb_issues[:3]
            )
            base += (
                f"\n\n## 质量反馈（重试第{fb_attempt + 1}次）\n"
                f"上次得分: {fb_score}\n"
                f"需改进的问题:\n{issues_text}\n"
                f"请针对以上问题改进分析质量。\n"
            )

        return base

    def _build_research_prompt_with_data(
        self,
        topic: str,
        aspect: str,
        aspects: List[str],
        search_results: Dict[str, Any],
    ) -> str:
        """
        构建包含搜索数据的研究 prompt
        
        Args:
            topic: 研究主题
            aspect: 单个维度
            aspects: 多个维度
            search_results: 搜索结果
            
        Returns:
            完整的研究 prompt
        """
        # 格式化搜索结果（包含质量评分）
        data_context = []
        sources_with_quality = []  # 收集高质量来源
        
        for search in search_results.get("searches", []):
            data_context.append(f"\n【搜索: {search['query']}】")
            
            for i, r in enumerate(search.get("results", [])[:5], 1):
                title = r.get("title", "N/A")
                url = r.get("href", "") or r.get("url", "")
                body = r.get("body", "") or r.get("snippet", "")
                
                # 质量评分
                quality_score = r.get("quality_score", 0)
                credibility = r.get("credibility", "unknown")
                
                # 可信度标签
                credibility_labels = {
                    "tier1_authority": "【权威】",
                    "tier2_professional": "【专业】",
                    "tier3_reputable": "【可信】",
                    "tier4_general": "【一般】",
                    "tier5_low_quality": "【低质】",
                }
                cred_label = credibility_labels.get(credibility, "")
                
                data_context.append(f"• {title}")
                data_context.append(f"  来源: {url}")
                if body:
                    data_context.append(f"  内容: {body[:200]}...")
                data_context.append("")
                
                # 收集高质量来源
                if quality_score >= 50:
                    sources_with_quality.append({
                        "title": title,
                        "url": url,
                        "quality_score": quality_score,
                        "credibility": credibility,
                    })
        
        data_str = "\n".join(data_context)
        
        # 质量统计摘要
        quality_summary = ""
        if search_results.get("quality_stats"):
            quality_summary = "\n## 数据质量统计\n"
            for query, stats in search_results["quality_stats"].items():
                filtered = stats.get("filtered_count", 0)
                tiers = stats.get("tier_distribution", {})
                quality_summary += f"- 查询 '{query}': 过滤 {filtered} 条低质量结果\n"
                if tiers:
                    tier_str = ", ".join([f"{k}: {v}" for k, v in tiers.items()])
                    quality_summary += f"  来源分布: {tier_str}\n"
        
        from src.core.i18n import get_language_instruction
        from datetime import datetime
        
        _now = datetime.now()
        _current_date = _now.strftime("%Y-%m-%d")
        _current_year = str(_now.year)
        
        pm = PromptManager()
        lang_inst = get_language_instruction()
        if aspect:
            return pm.render(
                'tasks', 'research_with_data',
                current_date=_current_date,
                current_year=_current_year,
                topic=topic,
                aspect=aspect,
                data=data_str,
                quality_summary=quality_summary,
            ) + '\n' + lang_inst
        else:
            aspects_str = "、".join(aspects) if aspects else "综合分析"
            return pm.render(
                'tasks', 'research_with_data',
                current_date=_current_date,
                current_year=_current_year,
                topic=topic,
                aspect=aspects_str,
                data=data_str,
                quality_summary=quality_summary,
            ) + '\n' + lang_inst
    
    def _build_analysis_prompt_with_data(
        self,
        topic: str,
        aspect: str,
        aspects: List[str],
        data_points: List[Dict[str, Any]],
        sources: List[Dict[str, Any]],
        core_question: str = "",
        role_in_report: str = "",
        sibling_aspects: Optional[List[str]] = None,
        sub_aspects: Optional[List[str]] = None,
        cross_dimension_claims: Optional[List[Dict]] = None,
        causal_hypotheses: Optional[List[Dict]] = None,
        conflict_entries: Optional[Dict[str, Dict]] = None,
        deep_mode_tables: str = "",
    ) -> str:
        """Build analysis prompt using pre-collected data points.
        
        Used by DEEP_ANALYSIS phase agents (category="market-analysis")
        that receive dependency-filtered data from DATA_COLLECTION phase.
        
        Args:
            topic: Research topic
            aspect: Single research dimension
            aspects: Multiple research dimensions
            data_points: Pre-collected data from upstream phases
            sources: Source metadata from upstream phases
            core_question: Central research question for the report
            role_in_report: This dimension's role in answering the core question
            sibling_aspects: Other dimensions being analyzed in parallel
            
        Returns:
            Rendered prompt string
        """
        # Analysis results carry inherited evidence forward.  Deduplicate it
        # before rendering, otherwise each dependent agent multiplies the same
        # source in the next batch.
        unique_data_points = []
        seen_data_keys = set()
        for dp in data_points or []:
            if not isinstance(dp, dict):
                continue
            identity = next(
                (str(dp.get(field)).strip() for field in ("evidence_id", "provenance_id", "data_id")
                 if str(dp.get(field) or "").strip()),
                "",
            )
            if identity:
                raw_key = f"identity:{identity}"
            else:
                try:
                    raw_key = json.dumps(
                        [dp.get("url"), dp.get("title"), dp.get("content"), dp.get("data")],
                        ensure_ascii=False, sort_keys=True, default=str,
                    )
                except (TypeError, ValueError):
                    raw_key = str(dp)
            key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
            if key not in seen_data_keys:
                seen_data_keys.add(key)
                unique_data_points.append(dp)

        data_context = []
        for i, dp in enumerate(unique_data_points, 1):
            title = dp.get("title", "")
            raw_content = dp.get("content", "") or ""
            raw_data = dp.get("data")
            url = dp.get("url", "")
            is_structured = any(url.startswith(f"{s}://") for s in ("stock_data", "wind_data", "bloomberg_data", "xueqiu"))
            quality = dp.get("quality_score", 0)
            credibility = dp.get("credibility", "unknown")

            if raw_data and isinstance(raw_data, dict) and raw_data:
                content = json.dumps(raw_data, ensure_ascii=False, indent=2, default=str)
            else:
                content = raw_content
            
            cred_labels = {
                "tier1_authority": " [AUTHORITY]",
                "tier2_professional": " [PROFESSIONAL]",
                "tier3_reputable": " [REPUTABLE]",
                "tier4_general": " [GENERAL]",
                "tier5_low_quality": " [LOW QUALITY]",
                "structured_source": " [STRUCTURED DB]",
            }
            cred_label = cred_labels.get(credibility, "")
            
            item_lines = [f"{i}. **{title}**{cred_label}"]
            if content:
                item_lines.append(f"   Content: {content}")
            if url:
                item_lines.append(f"   Source: {url}")
            item_lines.append("")
            data_context.append("\n".join(item_lines))
        
        data_str = "\n".join(data_context)
        
        from src.core.i18n import get_language_instruction
        from datetime import datetime
        
        _now = datetime.now()
        _current_date = _now.strftime("%Y-%m-%d")
        _current_year = str(_now.year)
        
        pm = PromptManager()
        lang_inst = get_language_instruction()
        sibling_str = "、".join(sibling_aspects) if sibling_aspects else ""
        framework_context = ""
        if core_question or role_in_report or sibling_str or sub_aspects or causal_hypotheses or cross_dimension_claims:
            parts = ["\n\n## 研究框架"]
            if core_question:
                parts.append(f"核心问题：{core_question}")
            if role_in_report:
                parts.append(f"你在报告中的角色：{role_in_report}")
            if sibling_str:
                parts.append(f"协作维度：{sibling_str}")
            # B2.4: Inject cross-dimension claims (L3+: reasoning-driven injection)
            _cog_strategy = self._context.get(f"cog_strategy:{aspect}", COGNITIVE_STRATEGY["fact_driven"])
            _aspect_policy = _cog_strategy["L3"]["speculative_policy"]
            if sub_aspects:
                parts.append("子主题（必须按此结构输出分析）：")
                for idx, sa in enumerate(sub_aspects, 1):
                    parts.append(f"  {idx}. {sa}")
            # B2.4: Inject cross-dimension claims (L3+: reasoning-driven injection)
            if cross_dimension_claims:
                _factual_claims = [c for c in cross_dimension_claims if c.get("epistemic_level") == "factual"]
                _inferential_claims = [c for c in cross_dimension_claims if c.get("epistemic_level") == "inferential"]
                _speculative_claims = [c for c in cross_dimension_claims if c.get("epistemic_level") == "speculative"]
                _no_level_claims = [c for c in cross_dimension_claims if c.get("epistemic_level") not in ("factual", "inferential", "speculative")]
                if _no_level_claims:
                    _inferential_claims.extend(_no_level_claims)
                if _factual_claims:
                    parts.append("\n### 其他维度已确认发现（可直接引用）")
                    for claim in _factual_claims:
                        parts.append(
                            f"  - [{claim.get('source_aspect','?')}] {claim.get('statement','')}"
                            f" (置信度: {claim.get('confidence','?')})"
                        )
                if _inferential_claims:
                    parts.append("\n### 其他维度推断结论（需验证后引用）")
                    for claim in _inferential_claims:
                        parts.append(
                            f"  - [{claim.get('source_aspect','?')}] {claim.get('statement','')}"
                            f" (置信度: {claim.get('confidence','?')},"
                            f" 前提: {claim.get('前提条件','未指定')})"
                        )
                    parts.append("\n**推理要求**:")
                    _infer_inst = _cog_strategy["L3"].get("inferential_instruction", "")
                    _cross_inst = _cog_strategy["L3"].get("cross_dimension_instruction", "")
                    if _infer_inst:
                        parts.append(f"  - {_infer_inst}")
                    if _cross_inst:
                        parts.append(f"  - {_cross_inst}")
                    parts.append("  - 若推断前提在你掌握的数据中不成立，需指出并修正结论")
                if _speculative_claims:
                    if _aspect_policy == "open_use":
                        parts.append("\n### 其他维度前瞻性判断（本维度核心输出，需系统化处理）")
                        for claim in _speculative_claims:
                            parts.append(
                                f"  - [{claim.get('source_aspect','?')}] {claim.get('statement','')}"
                                f" (置信度: {claim.get('confidence','?')},"
                                f" 证伪条件: {claim.get('falsification','未指定')})"
                            )
                        parts.append("\n**推理要求**:")
                        parts.append("  - 前瞻性判断是本维度的核心输出，可直接作为结论基础；每个判断须含证伪条件和概率评估")
                        parts.append("  - 必须引用上述其他维度的信息来支撑或修正你的风险情景分析")
                    elif _aspect_policy == "cautious_use":
                        parts.append("\n### 其他维度前瞻性判断（可作为方向性参考，但需明确标注不确定性）")
                        for claim in _speculative_claims:
                            parts.append(
                                f"  - [{claim.get('source_aspect','?')}] {claim.get('statement','')}"
                                f" (置信度: {claim.get('confidence','?')},"
                                f" 证伪条件: {claim.get('falsification','未指定')})"
                            )
                        parts.append("\n**推理要求**:")
                        parts.append("  - 引用前瞻性判断时用自然语言表达其推测性质与前提（如「预计…，前提是…」），严禁输出「置信度」「证伪条件」等标注字样或括号标签")
                        parts.append("  - 若你掌握的数据可以证伪某前瞻性判断，必须明确指出")
                        parts.append("  - 可基于前瞻性判断推导情景分析（乐观/中性/悲观），但需说明各情景的概率依据")
                    else:
                        parts.append("\n### 其他维度推测性观点（仅供参考，不得作为结论依据）")
                        for claim in _speculative_claims:
                            parts.append(
                                f"  - [{claim.get('source_aspect','?')}] {claim.get('statement','')}"
                                f" (置信度: {claim.get('confidence','?')},"
                                f" 证伪条件: {claim.get('falsification','未指定')})"
                            )
                        parts.append("\n**推理要求**:")
                        parts.append("  - 推测性观点仅供参考，不得作为结论依据；若数据可证伪某观点须指出，若启发分析方向须说明")
            # L3-D: Inject detected contradictions (before hypotheses — priority)
            if conflict_entries:
                parts.append("\n### 已检测到跨维度矛盾（优先处理）")
                for _ck, _cv in conflict_entries.items():
                    _conf_val = _cv.get("value", {})
                    parts.append(
                        f"  - 矛盾类型: {_conf_val.get('contradiction', '未知')}"
                        f" | 涉及结论: {_conf_val.get('claims', [])}"
                    )
                _l5 = _cog_strategy["L5"]
                parts.append(f"\n**要求**: {_l5['contradiction_instruction']}")
            # A2.2: Inject causal hypotheses into analysis prompt
            if causal_hypotheses:
                _l4 = _cog_strategy["L4"]
                _is_fact_driven = (_cog_strategy is COGNITIVE_STRATEGY.get("fact_driven"))
                _hypo_title = "建议探索" if _is_fact_driven else "必须验证或修正"
                parts.append(f"\n### {_l4['hypothesis_type']}假设（{_hypo_title}）")
                for i, h in enumerate(causal_hypotheses, 1):
                    parts.append(f"  {i}. {h.get('statement','')}")
                    parts.append(f"     验证数据需求：{h.get('verification_data','')}")
                    parts.append(f"     跨维度传导：{h.get('transmission','')}")
                    if h.get('counter_hypothesis'):
                        parts.append(f"     反面假设：{h['counter_hypothesis']}")
                if _is_fact_driven:
                    parts.append("\n**引导**：尝试用数据验证上述观察，确认或否定后得出发现")
                else:
                    parts.append("\n**假设驱动分析要求**：")
                    parts.append("  1. 对每个给定假设进行验证，给出支持/反对证据和验证结果（确认/修正/推翻）")
                    if _l4['agent_hypothesis_count'] > 0:
                        parts.append(f"  2. 基于你掌握的数据，额外提出至少{_l4['agent_hypothesis_count']}个新的{_l4['hypothesis_type']}假设并验证")
                    if _l4['counter_hypothesis_required']:
                        parts.append("  3. 对关键假设评估其反面假设成立的可能性")
                    parts.append("  4. 最终结论必须基于假设验证结果推导，而非直接下判断")
                parts.append(f"\n**输出格式**：在分析末尾标注「{_l4['output_suffix']}」，列出每个假设的验证结论")
            # L3-E: Evidence chain requirement (type-adaptive)
            _is_fact_driven = (_cog_strategy is COGNITIVE_STRATEGY.get("fact_driven"))
            parts.append("\n### 分析输出规范")
            _ect = _cog_strategy["L3"]["evidence_chain_template"]
            parts.append(f"  - 每个关键结论附带：{_ect}")
            parts.append("  - 输出红线：正文与表格中严禁出现置信度、factual、inferential、speculative、认知层级等内部标注字样——证据等级仅用于内部推理，不确定性一律用自然语言表达")
            if not _is_fact_driven:
                parts.append("  - 推理时内部区分事实/推断/前瞻层级，正文中用自然语言体现确定性差异，不得出现层级标注字样")
                parts.append("  - 若存在反对证据，列出并解释为何仍得出该结论")
            # Insight discovery section (type-adaptive)
            _insight_inst = _cog_strategy["L3"].get("insight_instruction")
            if _insight_inst:
                if _is_fact_driven:
                    parts.append(f"\n**洞察要求**：{_insight_inst}，在分析中自然呈现，标注「核心洞察」")
                else:
                    parts.append("\n### 洞察发现（独立于上述结构化要求）")
                    parts.append(f"  {_insight_inst}")
                    parts.append("  在报告末尾单独列出你发现的最重要的非常规洞察，标注为「核心洞察」")
            framework_context = "\n".join(parts)

        if deep_mode_tables:
            framework_context += (
                "\n\n## 深度模式结构化证据\n"
                "以下表格已通过校验。写作时必须优先使用这些记录，"
                "不得引入未提供的公司名或数字。估算值带 *，并保留脚注。\n\n"
                f"{deep_mode_tables}\n"
            )

        if aspect:
            return pm.render(
                'tasks', 'deep_analysis',
                current_date=_current_date,
                current_year=_current_year,
                topic=topic,
                aspect=aspect,
                data=data_str,
            ) + framework_context + '\n' + lang_inst
        else:
            aspects_str = "、".join(aspects) if aspects else "comprehensive analysis"
            return pm.render(
                'tasks', 'deep_analysis',
                current_date=_current_date,
                current_year=_current_year,
                topic=topic,
                aspect=aspects_str,
                data=data_str,
            ) + framework_context + '\n' + lang_inst
    
    def _build_basic_research_prompt(
        self,
        topic: str,
        aspect: str,
        aspects: List[str],
        core_question: str = "",
        role_in_report: str = "",
        sibling_aspects: Optional[List[str]] = None,
    ) -> str:
        """构建基础研究 prompt（无搜索数据时使用）
        
        防御性处理：确保即使topic为空也能返回有效的prompt
        """
        # 防御性处理：确保topic不为空
        if not topic or not topic.strip():
            topic = "指定研究主题"
            logger.warning(f"GenericAgent {self.agent_id}: topic为空，使用默认值")
        
        from src.core.i18n import get_language_instruction
        from datetime import datetime
        
        _now = datetime.now()
        _current_date = _now.strftime("%Y-%m-%d")
        _current_year = str(_now.year)
        
        lang_inst = get_language_instruction()

        sibling_str = "、".join(sibling_aspects) if sibling_aspects else ""
        framework_parts = []
        if core_question or role_in_report or sibling_str:
            framework_parts.append("\n## 研究框架")
            if core_question:
                framework_parts.append(f"核心问题：{core_question}")
            if role_in_report:
                framework_parts.append(f"你在报告中的角色：{role_in_report}")
            if sibling_str:
                framework_parts.append(f"协作维度：{sibling_str}")
        framework_context = "\n".join(framework_parts)

        pm = PromptManager()
        if aspect:
            return pm.render('tasks', 'basic_research', current_date=_current_date, current_year=_current_year, topic=topic, aspect=aspect, aspects='') + framework_context + '\n' + lang_inst
        elif aspects:
            aspects_str = "、".join([a for a in aspects if a])
            if aspects_str:
                return pm.render('tasks', 'basic_research', current_date=_current_date, current_year=_current_year, topic=topic, aspect='', aspects=aspects_str) + framework_context + '\n' + lang_inst
            else:
                return pm.render('tasks', 'basic_research', current_date=_current_date, current_year=_current_year, topic=topic, aspect='', aspects='') + framework_context + '\n' + lang_inst
        else:
            return pm.render('tasks', 'basic_research', current_date=_current_date, current_year=_current_year, topic=topic, aspect='', aspects='') + framework_context + '\n' + lang_inst

    @staticmethod
    def _clean_llm_output(content: str) -> str:
        """
        清理LLM输出中的prompt残留文字
        
        有些LLM会在回复中包含系统prompt或用户指令的部分内容，
        此方法去除这些残留，只保留真正的分析内容。
        
        v2.3 增强：
        - 更全面的标题匹配（包括无空格的情况）
        - 支持更多 prompt 指令模式
        """
        if not content:
            return content
        
        import re
        
        lines = content.split('\n')
        cleaned = []
        skip_section = False
        
        for line in lines:
            stripped = line.strip()
            
            # 跳过以prompt指令开头的整段文字
            # 增强匹配：支持 ##分析要求 和 ## 分析要求 两种格式
            if re.match(r'^#{1,6}\s*(分析要求|执行步骤|输出要求|禁止行为|质量标准|数据处理原则|分析框架|内容结构|主题|维度|数据)', stripped, re.IGNORECASE):
                skip_section = True
                continue
            if re.match(r'^#{1,6}(分析要求|执行步骤|输出要求|禁止行为|质量标准|数据处理原则|分析框架|内容结构|主题|维度|数据)', stripped, re.IGNORECASE):
                skip_section = True
                continue
            if re.match(r'^#{1,6}\s*(重要|注意|请确保|请严格|约束)', stripped):
                skip_section = True
                continue
            if stripped.startswith('**重要') or stripped.startswith('**禁止'):
                skip_section = True
                continue
            if stripped.startswith('如果原始数据不足') or stripped.startswith('不得复制') or stripped.startswith('不得抄袭'):
                skip_section = True
                continue
            
            # 遇到下一个标题或内容行时结束跳过模式
            # 增强判断：只有遇到真正的内容标题才结束跳过
            if skip_section and re.match(r'^#{1,6}\s+\S', stripped):
                # 检查是否是 prompt 指令标题
                prompt_keywords = ['分析要求', '执行步骤', '输出要求', '禁止行为', '质量标准', 
                                   '数据处理原则', '分析框架', '内容结构', '主题', '维度', 
                                   '数据', '重要', '注意', '请确保', '请严格', '约束']
                is_prompt_title = any(kw in stripped for kw in prompt_keywords)
                if not is_prompt_title:
                    skip_section = False
                    # 这个标题可能是真内容，保留
                    cleaned.append(line)
                continue
            
            if skip_section:
                continue
            
            # 跳过纯指令行
            if re.match(r'^\d+\.\s*(进行充分的信息搜索|从多个来源验证|进行深度分析|撰写专业)', stripped):
                continue
            if re.match(r'^[-•]\s*(数据准确|每个关键数据点|分析深入|结论明确|章节内容)', stripped):
                continue
            if '请提供详细的分析结果，包括关键发现、数据支持和结论' in stripped:
                # 这种行是prompt中的指令，如果单独出现则跳过
                if len(stripped) < 80:  # 短行
                    continue
            
            cleaned.append(line)
        
        result = '\n'.join(cleaned).strip()
        
        # 如果全部被清理了，返回原文
        return result if result else content
    
    @staticmethod
    def _validate_output_dates(content: str, agent_id: str = "") -> str:
        """
        Validate and correct year references in LLM output against the real current date.
        
        Scans for 4-digit year patterns, checks them against the system clock,
        and logs warnings for any mismatches that indicate date hallucination.
        
        Future years are valid in forecasts, targets, plans, and scenarios.
        This validator therefore never rewrites a year in model output.  It
        only logs future years for the L4 semantic quality audit, which can
        distinguish a labelled forecast from an unlabeled factual claim.
        
        Implementation note: processes matches right-to-left so that
        string position shifts don't affect earlier match positions.
        
        Args:
            content: LLM output content to validate
            agent_id: Agent identifier for logging
            
        Returns:
            Corrected content (with auto-fixed years where certain)
        """
        from datetime import datetime
        import re
        
        current_year = datetime.now().year
        # Find all 4-digit year patterns (1900-2099 range), standalone (not part of larger number)
        year_pattern = re.compile(r'(?<!\d)(19[0-9]{2}|20[0-9]{2})(?!\d)')

        matches = list(year_pattern.finditer(content))
        for match in matches:
            year = int(match.group())
            start, end = match.start(), match.end()
            
            ctx_start = max(0, start - 30)
            ctx_end = min(len(content), end + 30)
            context = content[ctx_start:ctx_end].replace('\n', ' ')
            
            if year > current_year:
                logger.info(
                    f"GenericAgent {agent_id}: DATE CHECK — future year "
                    f"'{year}' preserved for semantic L4 validation. Context: {context}"
                )
            elif year < 2020:
                logger.warning(f"GenericAgent {agent_id}: DATE CHECK — year '{year}' is before 2020. Verify this is intentionally historical data: {context}")
            elif year < current_year - 2:
                logger.info(f"GenericAgent {agent_id}: DATE CHECK — year '{year}' is >= 2 years old. Verify data freshness: {context}")
        
        return content

    async def _self_evaluate(self, content: str) -> Dict[str, Any]:
        """
        对生成的分析内容进行自我质量评估。

        仅在以下条件全部满足时执行:
            1. quality_rubric.md 文件存在
            2. 内容长度 > 500 字符

        Returns:
            {"score": int, "weak_dimensions": List[str], "suggestions": List[str]}
            或 rubric 不存在/短内容时返回 {"pass": True, "score": 100}
        """
        if len(content) < 500:
            return {"pass": True, "score": 100}

        rubric = _load_quality_rubric()
        if not rubric:
            return {"pass": True, "score": 100}

        eval_prompt = (
            f"请根据以下评分标准对分析内容进行质量评估（0-100 分）。\n\n"
            f"## 评分标准\n{rubric}\n\n"
            f"## 分析内容（前 3000 字符）\n{content[:3000]}\n\n"
            f"请以 JSON 格式输出：\n"
            f'{{"score": <0-100>, '
            f'"weak_dimensions": ["维度1", "维度2"], '
            f'"suggestions": ["改进建议1", "改进建议2"]}}'
        )

        resp = await self._call_llm_directly(
            prompt=eval_prompt,
            temperature=0.2,
            max_tokens=1000,
        )

        if not resp.get("success"):
            return {"pass": True, "score": 100, "llm_error": resp.get("error")}

        result_text = resp.get("content", "")

        import json
        try:
            parsed = json.loads(result_text)
            if isinstance(parsed, dict) and "score" in parsed:
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', result_text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
                if isinstance(parsed, dict) and "score" in parsed:
                    return parsed
            except (json.JSONDecodeError, ValueError):
                pass

        return {"pass": True, "score": 100, "parse_error": True}

    @staticmethod
    def _filter_output_contamination(
        output_content: str,
        input_contents: List[str],
        similarity_threshold: float = 0.7,
        min_contamination_length: int = 50,
    ) -> str:
        """
        过滤输出内容中的污染（与输入重复的部分）
        
        核心机制：
        1. 将输出内容按段落分割
        2. 对每个段落，计算与所有输入内容的相似度
        3. 如果相似度超过阈值，标记为污染并移除
        4. 保留原创内容
        
        Args:
            output_content: LLM 输出的内容
            input_contents: 输入内容列表（前序内容、数据点等）
            similarity_threshold: 相似度阈值，超过此值视为污染（默认 0.7）
            min_contamination_length: 最小污染段落长度（默认 50 字符）
            
        Returns:
            清理后的内容
            
        Example:
            >>> output = "市场规模达到500亿。竞争格局方面，主要玩家包括..."
            >>> inputs = ["竞争格局方面，主要玩家包括A公司、B公司..."]
            >>> filtered = _filter_output_contamination(output, inputs)
            >>> # 输出: "市场规模达到500亿。"
        """
        if not output_content or not input_contents:
            return output_content
        
        import re
        from difflib import SequenceMatcher
        
        # 预处理：合并所有输入内容为一个参考文本
        reference_text = "\n".join([c for c in input_contents if c])
        
        # 按段落分割输出内容
        # 段落定义：双换行或单换行分隔的连续非空行
        # 先尝试双换行分割，如果没有双换行则按单换行分割
        if '\n\n' in output_content:
            paragraphs = re.split(r'\n\s*\n', output_content)
        else:
            paragraphs = [p.strip() for p in output_content.split('\n') if p.strip()]
        
        filtered_paragraphs = []
        total_contaminated = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            # 短段落直接保留（可能是标题、分隔符等）
            if len(para) < min_contamination_length:
                filtered_paragraphs.append(para)
                continue
            
            # 计算与参考文本的相似度
            # 使用 SequenceMatcher 的 quick_ratio() 方法（快速但近似）
            similarity = SequenceMatcher(None, para, reference_text).quick_ratio()
            
            # 更精确的检查：查找最长公共子序列占比
            # 如果输出段落与输入内容有大段重复，视为污染
            max_overlap_ratio = 0.0
            for input_content in input_contents:
                if not input_content:
                    continue
                # 计算段落与每个输入内容的重叠比例
                matcher = SequenceMatcher(None, para, input_content)
                # 找到最长匹配块
                matches = matcher.get_matching_blocks()
                for match in matches:
                    if match.size > 0:
                        overlap_ratio = match.size / len(para)
                        max_overlap_ratio = max(max_overlap_ratio, overlap_ratio)
            
            # 判断是否为污染
            is_contaminated = (
                similarity > similarity_threshold or 
                max_overlap_ratio > similarity_threshold
            )
            
            if is_contaminated:
                total_contaminated += 1
                logger.debug(f"检测到污染段落（相似度={similarity:.2f}, 重叠率={max_overlap_ratio:.2f}）: {para[:50]}...")
            else:
                filtered_paragraphs.append(para)
        
        if total_contaminated > 0:
            logger.info(f"输出过滤：检测到 {total_contaminated} 个污染段落，已移除")
        
        # 重新组合过滤后的段落
        result = "\n\n".join(filtered_paragraphs)
        
        # 如果全部被过滤，返回原文（避免空输出）
        return result if result.strip() else output_content
    
    @staticmethod
    def _extract_contamination_sources(
        output_content: str,
        input_contents: List[Dict[str, Any]],
        key_field: str = "content",
        similarity_threshold: float = 0.6,
    ) -> List[str]:
        """
        提取污染来源（用于调试和日志）
        
        识别输出内容中哪些输入源被复制了。
        
        Args:
            output_content: LLM 输出内容
            input_contents: 输入内容列表（包含 content 字段的 dict）
            key_field: 内容字段名（默认 "content"）
            similarity_threshold: 相似度阈值
            
        Returns:
            污染来源标识列表（如 agent_id 或 title）
        """
        if not output_content or not input_contents:
            return []
        
        from difflib import SequenceMatcher
        
        contamination_sources = []
        
        for item in input_contents:
            input_text = item.get(key_field, "")
            if not input_text:
                continue
            
            # 计算相似度
            similarity = SequenceMatcher(None, output_content, input_text).quick_ratio()
            
            if similarity > similarity_threshold:
                # 提取来源标识
                source_id = (
                    item.get("agent_id") or 
                    item.get("title") or 
                    item.get("section_name") or
                    f"未知来源_{input_contents.index(item)}"
                )
                contamination_sources.append(f"{source_id}（相似度={similarity:.2f}）")
        
        return contamination_sources

    def _build_synthesis_prompt_with_data(
        self,
        topic: str,
        aspect: str,
        aspects: List[str],
        data_points: List[Dict[str, Any]],
        sources: List[Dict[str, Any]],
        previous_content: List[Dict[str, Any]],
        target_aspect: str = "",
        core_question: str = "",
        role_in_report: str = "",
        sibling_aspects: Optional[List[str]] = None,
    ) -> str:
        """
        构建综合分析prompt（使用前序Agent的数据）
        
        **污染修复**: 支持 target_aspect 参数，明确约束只输出目标章节
        
        Args:
            topic: 研究主题
            aspect: 单个维度
            aspects: 多个维度
            data_points: 前序Agent收集的数据点
            sources: 前序Agent收集的数据来源
            previous_content: 前序Agent的分析结果
            target_aspect: 目标章节名称
            core_question: 报告核心研究问题
            role_in_report: 该维度在报告中的角色
            sibling_aspects: 其他协作维度
            
        Returns:
            综合分析prompt
        """
        # 构建数据点摘要
        data_context = []
        if data_points:
            data_context.append("## 收集的数据点\n")
            for i, dp in enumerate(data_points[:20], 1):
                title = dp.get("title", "")
                raw_content = dp.get("content", "") or ""
                url = dp.get("url", "")
                is_structured = any(url.startswith(f"{s}://") for s in ("stock_data", "wind_data", "bloomberg_data"))
                max_len = 500 if is_structured else 200
                content = raw_content[:max_len]
                quality = dp.get("quality_score", 0)
                
                data_context.append(f"{i}. **{title}**")
                if content:
                    clean_content = re.sub(r'[（(]来源[：:][^）)]+[）)]', '', content)
                    clean_content = re.sub(r'[（(]数据来源[：:][^）)]+[）)]', '', clean_content)
                    clean_content = re.sub(r'，质量分\d+\.?\d*', '', clean_content)
                    clean_content = re.sub(r'，可信度[：:][^，）)]+', '', clean_content)
                    data_context.append(f"   {clean_content[:max_len]}...")
                data_context.append("")
        
        # 构建前序分析摘要
        # **污染修复**: 只传入与 target_aspect 相关的前序内容
        # 避免其他章节的内容污染 synthesis agent 的输出
        analysis_context = []
        if previous_content:
            analysis_context.append("## 前序分析结果（仅供参考，不得复制）\n")
            
            # **关键修复**: 过滤前序内容，只保留与目标章节相关的
            relevant_content = []
            for pc in previous_content[:20]:  # Y-FIX-2: increased from 10
                agent_id = pc.get("agent_id", "未知Agent")
                content = pc.get("content", "")
                
                # 提取章节名
                section_name = self._extract_aspect_from_agent_id(agent_id)
                
                # **核心修复**: 只保留与 target_aspect 相关的内容
                # 如果 target_aspect 为空，则保留所有内容（兼容旧逻辑）
                if target_aspect:
                    # 检查是否与目标章节相关
                    if self._is_content_relevant_to_aspect(section_name, target_aspect, content):
                        relevant_content.append((agent_id, section_name, content[:2000]))  # Y-FIX-2: was 500
                else:
                    # 无 target_aspect 时保留所有
                    relevant_content.append((agent_id, section_name, content[:2000]))  # Y-FIX-2: was 500
            
            # 输出过滤后的内容
            # Y-FIX-2: increased from 5; token budget protection: 20×2000≈40K chars, system prompt + user prompt may exceed 8K context
            _max_content = min(len(relevant_content), 20)  # S6: cap at 20 blocks
            for i, (agent_id, section_name, content) in enumerate(relevant_content[:_max_content], 1):
                # 明确标注章节归属
                analysis_context.append(f"### [{section_name} 章节]（相关参考）")
                analysis_context.append(content)
                analysis_context.append("")
            
            # 如果没有相关内容，添加提示
            if not relevant_content:
                analysis_context.append("（无直接相关的前序分析，请基于数据点原创撰写）")
        
        # 构建来源列表
        sources_context = []
        if sources:
            sources_context.append("## 数据来源\n")
            unique_urls = set()
            for s in sources[:30]:  # 限制数量
                url = s.get("url", "")
                if url and url not in unique_urls:
                    unique_urls.add(url)
                    title = s.get("title", "")
                    sources_context.append(f"- [{title}]({url})")
        
        # 组装完整prompt
        data_str = "\n".join(data_context) if data_context else ""
        analysis_str = "\n".join(analysis_context) if analysis_context else ""
        sources_str = "\n".join(sources_context) if sources_context else ""
        
        # 污染修复：如果指定了 target_aspect，优先使用它作为维度
        # 避免显示所有章节名称混淆 LLM
        if target_aspect:
            aspect_str = target_aspect
        else:
            aspect_str = aspect or ("、".join(aspects) if aspects else "综合分析")
        
        # 污染修复：统一强约束 - 无论是否有 target_aspect，都只输出目标章节
        if target_aspect:
            # synthesis agent：只输出目标章节
            constraint_text = f"""
**重要约束（必须严格遵守）**：
1. 只输出【{target_aspect}】章节的正文内容，不输出其他任何章节
2. 禁止输出"执行摘要"、"市场规模"、"竞争格局"、"发展趋势"、"研究结论"等标题，除非它就是【{target_aspect}】
3. 基于参考材料原创总结，不得大段复制原文
4. 可使用加粗、列表等 Markdown 格式，但禁止使用 #/##/### 标题
5. 输出建议 500-800 字，根据内容复杂度适当调整
6. 你收到的材料来自多个研究维度。请识别各维度结论中的**共同点**和**矛盾点**，如发现同一指标出现不同值（口径冲突），请标记并判断哪个更权威。最终输出基于已确认一致的数据。
7. **禁止在正文中添加数据来源标注**，如"（来源：XXX，质量分XX）"或"（数据来源：XXX）"等，来源信息仅供你参考
8. **采用传统行业研报结构**：核心结论（加粗1-2句）→ 论证与分析（2-4个子论点+数据）→ 数据表格（如有必要）→ 风险提示（章节末尾，集中列出不确定性、假设前提、数据缺口）。不要使用"反证与边界条件"等学术讨论段落，不确定性统一放在风险提示中

请撰写【{target_aspect}】章节内容："""
        elif aspect:
            # analysis agent：只输出指定章节的深度分析
            constraint_text = f"""
**重要约束（必须严格遵守）**：
1. 只输出【{aspect}】章节的深度分析内容，不输出其他任何章节
2. 禁止输出"执行摘要"、"市场规模"、"竞争格局"、"发展趋势"、"研究结论"等标题，除非它就是【{aspect}】
3. 基于数据原创分析，不得复制原文或前序分析结果
4. 可使用加粗、列表等 Markdown 格式，但禁止使用 #/##/### 标题
5. 输出建议 800-1200 字，根据内容复杂度适当调整
6. **禁止在正文中添加数据来源标注**，如"（来源：XXX，质量分XX）"或"（数据来源：XXX）"等，来源信息仅供你参考
7. **采用传统行业研报结构**：核心结论（加粗1-2句）→ 论证与分析（2-4个子论点+数据）→ 风险提示（章节末尾，集中列出不确定性、假设前提、数据缺口）。不要使用"反证与边界条件"等学术讨论段落

请撰写【{aspect}】章节的深度分析内容："""
        else:
            # research/default：综合分析
            constraint_text = f"""
请基于以上数据，撰写{aspect_str}的综合分析内容。要求：整合发现、原创洞察、专业结论。采用传统行业研报结构（核心结论→论证分析→风险提示），不确定性放在章节末尾风险提示中。直接输出分析正文，使用Markdown格式。注意：**禁止在正文中添加数据来源标注**，如"（来源：XXX）"等格式。"""
        
        from src.core.i18n import get_language_instruction
        lang_inst = get_language_instruction()

        sibling_str = "、".join(sibling_aspects) if sibling_aspects else ""
        framework_parts = []
        if core_question or role_in_report or sibling_str:
            framework_parts.append("\n## 研究框架")
            if core_question:
                framework_parts.append(f"核心问题：{core_question}")
            if role_in_report:
                framework_parts.append(f"你在报告中的角色：{role_in_report}")
            if sibling_str:
                framework_parts.append(f"协作维度：{sibling_str}")
        framework_context = "\n".join(framework_parts)

        return f"""# 综合分析任务

## 主题
{topic}

## 维度
{aspect_str}

{data_str}
{analysis_str}
{sources_str}
---
{constraint_text}
{framework_context}
{lang_inst}"""

    @staticmethod
    def _extract_aspect_from_agent_id(agent_id: str) -> str:
        """
        从 agent_id 中提取章节名
        
        支持的格式：
        - synthesis_0_执行摘要 -> 执行摘要
        - analysis_市场概况 -> 市场概况
        - research_1_竞争格局 -> 竞争格局
        
        Args:
            agent_id: Agent ID
            
        Returns:
            章节名
        """
        if "_" not in agent_id:
            return agent_id
        
        parts = agent_id.split("_")
        
        # 格式: type_index_aspect 或 type_aspect
        # 去掉前缀（type）和可能的索引，取最后一部分作为章节名
        if len(parts) >= 4 and parts[0] == "phase" and parts[-2] == "agent":
            return agent_id  # phase_N_agent_M 格式，无意义章节名
        if len(parts) >= 3:
            # synthesis_0_执行摘要 -> 执行摘要
            return parts[-1]
        elif len(parts) == 2:
            # analysis_市场概况 -> 市场概况
            return parts[1]
        else:
            return agent_id
    
    @staticmethod
    def _is_content_relevant_to_aspect(
        section_name: str, 
        target_aspect: str, 
        content: str
    ) -> bool:
        """
        判断内容是否与目标章节相关
        
        **污染修复**: 用于过滤前序内容，避免不相关章节的内容污染 synthesis 输出
        
        Args:
            section_name: 内容所属章节名
            target_aspect: 目标章节名
            content: 内容文本
            
        Returns:
            是否相关
        """
        # 1. 精确匹配
        if section_name == target_aspect:
            return True
        
        # 2. 章节别名映射
        aspect_aliases = {
            "执行摘要": ["摘要", "概要", "summary", "executive_summary"],
            "研究结论": ["结论", "总结", "conclusion", "建议"],
            "市场规模": ["规模", "市场", "market_size", "销量"],
            "竞争格局": ["竞争", "品牌", "competition", "格局"],
            "发展趋势": ["趋势", "发展", "trend", "未来"],
            "政策环境": ["政策", "policy", "法规"],
            "技术发展": ["技术", "technology", "创新"],
            "产业链": ["产业链", "供应链", "chain"],
            "风险分析": ["风险", "risk", "挑战"],
            "投资建议": ["投资", "investment", "机会"],
        }
        
        # 获取目标章节的别名
        target_aliases = aspect_aliases.get(target_aspect, [])
        target_aliases.append(target_aspect)
        
        # 检查 section_name 是否在目标章节的别名中
        for alias in target_aliases:
            if alias.lower() in section_name.lower() or section_name.lower() in alias.lower():
                return True
        
        # 3. 内容关键词匹配（用于处理模糊情况）
        # 统计内容中与目标章节相关的关键词出现次数
        keywords = aspect_aliases.get(target_aspect, [])
        if keywords:
            match_count = sum(1 for kw in keywords if kw.lower() in content.lower())
            # 如果超过一半的关键词出现，认为相关
            if match_count >= len(keywords) / 2:
                return True
        
        # 4. 特殊情况：执行摘要和研究结论可以引用所有章节
        if target_aspect in ["执行摘要", "研究结论", "摘要", "结论"]:
            return True
        
        return False

    # === GenericAgent特有方法 ===
    
    def get_available_skills(self) -> List[str]:
        """获取可用的Skill列表"""
        return self._available_skills.copy()
    
    def get_role_info(self) -> Dict[str, str]:
        """获取角色信息"""
        return {
            "role": self._role,
            "goal": self._goal,
            "backstory": self._backstory,
        }
    
    # === 生命周期管理方法 ===
    
    def get_lifecycle_state(self) -> AgentLifecycleState:
        """获取当前生命周期状态"""
        return self._lifecycle_state
    
    def set_lifecycle_state(self, state: AgentLifecycleState) -> None:
        """
        设置生命周期状态（带验证）
        
        Args:
            state: 目标状态
            
        Raises:
            InvalidStateError: 如果状态转换不合法
        """
        if not validate_transition(self._lifecycle_state, state):
            raise InvalidStateError(self._lifecycle_state, state)
        
        self._lifecycle_state = state
        logger.debug(f"Agent {self.agent_id}: state changed to {state.value}")
    
    async def hibernate(self, persistence: "SessionPersistenceManager") -> None:
        """
        Agent内部休眠方法
        
        保存状态到Session，释放内部资源。
        由Factory.hibernate_batch()调用。
        
        Args:
            persistence: Session持久化管理器
            
        Raises:
            InvalidStateError: 如果当前状态不允许休眠
        """
        # 1. 验证状态
        if self._lifecycle_state not in [
            AgentLifecycleState.READY,
            AgentLifecycleState.RUNNING,
            AgentLifecycleState.PAUSED,
            AgentLifecycleState.COMPLETED,
            AgentLifecycleState.FAILED,
        ]:
            raise InvalidStateError(
                self._lifecycle_state,
                AgentLifecycleState.HIBERNATING,
                f"Cannot hibernate agent in state {self._lifecycle_state.value}"
            )
        
        # 2. 更新生命周期状态
        self._lifecycle_state = AgentLifecycleState.HIBERNATING
        
        # 3. 保存Skill状态
        skill_states = {}
        for skill_name in self._available_skills:
            if self._skill_registry:
                skill = self._skill_registry._skills.get(skill_name)
                if skill and hasattr(skill, 'save_state'):
                    try:
                        skill_states[skill_name] = await skill.save_state()
                    except Exception as e:
                        logger.warning(f"Failed to save skill {skill_name}: {e}")
                        skill_states[skill_name] = {"error": str(e)}
        
        # 4. 保存Agent模板到Session
        if self._session:
            self._session.agent_template = {
                "capability": {
                    "name": self.config.get("name"),
                    "description": self.config.get("description"),
                    "required_skills": self.config.get("required_skills", []),
                    "optional_skills": self.config.get("optional_skills", []),
                    "role": self._role,
                    "goal": self._goal,
                    "skills": self._available_skills,
                },
                "skill_names": self._available_skills.copy(),
                "context": self._context.copy(),
            }
            
            # 5. 创建checkpoint
            checkpoint = {
                "skill_states": skill_states,
                "agent_data": self._data.copy(),
                "lifecycle_state": self._lifecycle_state.value,
                "hibernated_at": datetime.now().isoformat(),
            }
            self._session.create_checkpoint(checkpoint)
            
            # 6. 更新Session状态
            self._session.status = AgentSessionStatus.HIBERNATED
            self._session.updated_at = datetime.now()
            
            # 7. 持久化Session
            persistence.save_session(self._session)
            
            # 8. 更新Registry（需要从工厂获取）
            # 注意：Registry更新由Factory负责，这里只保存Session
            pass
        
        # 9. 清理Agent内部资源
        self._available_skills = []
        self._data.clear()
        self._context = {}
        self._lifecycle_state = AgentLifecycleState.HIBERNATED
        
        logger.info(f"Agent {self.agent_id}: 已休眠")
    
    async def restore(self, session: "AgentSession") -> None:
        """
        Agent内部恢复方法
        
        从Session恢复状态，重新加载Skills。
        由Factory.restore_batch()调用。
        
        Args:
            session: Agent Session
            
        Raises:
            ValueError: 如果Session没有agent_template
        """
        # 1. 设置生命周期状态
        self._lifecycle_state = AgentLifecycleState.RESUMING
        
        # 2. 获取Agent模板
        agent_template = session.agent_template
        if agent_template is None:
            raise ValueError(f"Session {session.session_id} has no agent_template")
        
        # 3. 恢复Skills
        skill_names = agent_template.get("skill_names", [])
        capability = agent_template.get("capability", {})
        
        self._available_skills = skill_names.copy()
        self._role = capability.get("role", "")
        self._goal = capability.get("goal", "")
        
        # 恢复Skill状态
        for skill_name in skill_names:
            if self._skill_registry:
                try:
                    skill = self._skill_registry.get(skill_name)
                    if skill and hasattr(skill, 'load_state'):
                        checkpoint = session.get_latest_checkpoint()
                        if checkpoint and "skill_states" in checkpoint:
                            skill_state = checkpoint["skill_states"].get(skill_name)
                            if skill_state and not skill_state.get("error"):
                                await skill.load_state(skill_state)
                except Exception as e:
                    logger.warning(f"Failed to restore skill {skill_name}: {e}")
        
        # 4. 恢复Agent数据
        checkpoint = session.get_latest_checkpoint()
        if checkpoint and "agent_data" in checkpoint:
            self._data = checkpoint["agent_data"].copy()
        
        # 5. 恢复上下文
        self._context = agent_template.get("context", {}).copy()
        
        # 6. 设置Session
        self._session = session
        
        # 7. 更新生命周期状态
        self._lifecycle_state = AgentLifecycleState.READY
        
        # 8. 更新Session状态
        session.status = AgentSessionStatus.RUNNING
        session.updated_at = datetime.now()
        
        logger.info(f"Agent {self.agent_id}: 已恢复，状态={self._lifecycle_state.value}")
    
    # ==================== P0-3修复：图表生成能力 ====================
    
    async def _generate_charts_from_content(
        self,
        content: str,
        topic: str,
        aspect: str,
    ) -> List[Dict[str, Any]]:
        """
        从LLM生成的内容中提取数据并生成图表
        
        使用ChartPlannerAgent进行语义分析，替代正则提取。
        当CHART_PLANNER_ENABLED=False时降级回原有正则逻辑。
        
        Args:
            content: LLM生成的内容
            topic: 研究主题
            aspect: 研究维度
            
        Returns:
            图表信息列表（含insertion_anchor/anchor_type）
        """
        from src.config import settings
        planner_enabled = getattr(settings, 'chart_planner', None)
        if planner_enabled is not None:
            planner_enabled = getattr(planner_enabled, 'enabled', True)
        else:
            planner_enabled = True
        
        if planner_enabled:
            return await self._generate_charts_with_planner(content, topic, aspect)
        else:
            return await self._generate_charts_legacy(content, topic, aspect)

    async def _generate_charts_with_planner(
        self,
        content: str,
        topic: str,
        aspect: str,
    ) -> List[Dict[str, Any]]:
        """使用ChartPlannerAgent生成图表"""
        charts = []
        
        try:
            from src.services.chart_planner import ChartPlannerAgent
            from src.services.chart_generator import ChartGenerator, ChartConfig
            
            output_dir = Path("output/charts")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            chart_planner = ChartPlannerAgent(output_dir=str(output_dir))
            chart_plans = await chart_planner.plan(
                content=content,
                topic=topic,
                section_title=aspect,
            )
            
            if chart_plans:
                chart_generator = ChartGenerator(output_dir=str(output_dir))
                for plan in chart_plans:
                    try:
                        config = ChartConfig(
                            chart_type=plan.chart_type,
                            title=plan.title,
                            data=plan.data,
                            xlabel=plan.xlabel,
                            ylabel=plan.ylabel,
                            caption=plan.caption,
                            source=getattr(plan, "source", "") or "公开资料整理",
                        )
                        render_result = chart_generator.generate(config)
                        if render_result.success and render_result.image_path:
                            charts.append({
                                "chart_type": plan.chart_type.value,
                                "title": plan.title,
                                "path": render_result.image_path,
                                "caption": plan.caption,
                                "aspect": aspect,
                                "insertion_anchor": plan.insertion_anchor,
                                "anchor_type": plan.anchor_type,
                            })
                            logger.info(f"ChartPlanner: generated chart for '{aspect}': {render_result.image_path}")
                    except Exception:
                        logger.exception(f"Chart rendering failed for plan: {plan.title}")
            
        except ImportError:
            logger.warning("ChartPlannerAgent not available, falling back to legacy")
            return await self._generate_charts_legacy(content, topic, aspect)
        except Exception:
            logger.exception("ChartPlanner failed, falling back to legacy")
            return await self._generate_charts_legacy(content, topic, aspect)
        
        return charts

    async def _generate_charts_legacy(
        self,
        content: str,
        topic: str,
        aspect: str,
    ) -> List[Dict[str, Any]]:
        """原有正则提取图表生成逻辑（降级用）"""
        charts = []
        
        try:
            from src.services.chart_generator import ChartGenerator, ChartConfig, ChartType
            
            output_dir = Path("output/charts")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            chart_generator = ChartGenerator(output_dir=str(output_dir))
            
            content_normalized = content.replace('\r\n', '\n').replace('\r', '\n')
            
            table_pattern = r'\|(.+)\|\n\|[-\s|:]+\|\n((?:\|.+\|\n?)+)'
            tables = re.findall(table_pattern, content_normalized)
            
            logger.info(f"Chart generation (legacy) for '{aspect}': content_len={len(content)}, tables_found={len(tables)}")
            if not tables:
                pipe_count = content.count('|')
                logger.debug(f"Chart generation: pipe_count={pipe_count}, content_preview={content[:200]}")

            for i, (header_row, data_rows) in enumerate(tables[:3]):
                try:
                    headers = [h.strip() for h in header_row.split('|') if h.strip()]
                    
                    rows = []
                    for row in data_rows.strip().split('\n'):
                        cells = [c.strip() for c in row.split('|') if c.strip()]
                        if cells and not all(c.replace('-', '').replace(':', '') == '' for c in cells):
                            rows.append(cells)
                    
                    if len(headers) >= 2 and len(rows) >= 2:
                        logger.info(f"Chart generation: table {i+1} - headers={headers[:3]}, rows={len(rows)}")
                        categories = [row[0] for row in rows if len(row) > 0]
                        
                        for col_idx in range(1, min(len(headers), 3)):
                            values = []
                            for row in rows:
                                if len(row) > col_idx:
                                    try:
                                        val_str = re.sub(r'[^\d.]', '', row[col_idx])
                                        val = float(val_str) if val_str else 0
                                        values.append(val)
                                    except (ValueError, IndexError):
                                        values.append(0)
                            
                            if values and sum(values) > 0:
                                config = ChartConfig(
                                    chart_type=ChartType.BAR,
                                    title=f"{aspect} - {headers[col_idx]}"[:50],
                                    data={
                                        "categories": categories[:10],
                                        "values": values[:10],
                                    },
                                    xlabel=headers[0],
                                    ylabel=headers[col_idx],
                                    source=f"{topic}研究数据",
                                )
                                
                                result = chart_generator.generate(config)
                                
                                if result.success and result.image_path:
                                    charts.append({
                                        "chart_type": "bar",
                                        "title": f"{headers[col_idx]}分析",
                                        "path": result.image_path,
                                        "aspect": aspect,
                                        "insertion_anchor": "",
                                        "anchor_type": "section_end",
                                    })
                                    logger.info(f"Generated chart for {aspect}: {result.image_path}")
                                    break
                                    
                except Exception:
                    logger.exception("Failed to generate chart from table")
                    continue
            
            market_share_pattern = r'(\w+(?:\s+\w+)?)\s*[：:]\s*(\d+(?:\.\d+)?)\s*[%％]'
            market_data = re.findall(market_share_pattern, content)
            
            if len(market_data) >= 3 and not charts:
                try:
                    categories = [m[0].strip()[:15] for m in market_data[:8]]
                    values = [float(m[1]) for m in market_data[:8]]
                    
                    config = ChartConfig(
                        chart_type=ChartType.BAR,
                        title=f"{aspect} - 市场份额分析",
                        data={
                            "categories": categories,
                            "values": values,
                        },
                        ylabel="占比 (%)",
                        source=f"{topic}研究数据",
                    )
                    
                    result = chart_generator.generate(config)
                    
                    if result.success and result.image_path:
                        charts.append({
                            "chart_type": "bar",
                            "title": "市场份额分析",
                            "path": result.image_path,
                            "aspect": aspect,
                            "insertion_anchor": "",
                            "anchor_type": "section_end",
                        })
                        logger.info(f"Generated market share chart: {result.image_path}")
                        
                except Exception:
                    logger.exception("Failed to generate market share chart")
            
        except ImportError:
            logger.warning("ChartGenerator not available, skipping chart generation")
        except Exception:
            logger.exception("Chart generation failed")
        
        return charts
