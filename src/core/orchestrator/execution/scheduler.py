# -*- coding: utf-8 -*-
"""
执行调度器 - 基于任务分解计划进行智能调度

设计理念：
1. 使用 DecompositionPlan 驱动执行顺序
2. 基于 AgentSpec.dependencies 进行拓扑排序
3. 支持并行执行无依赖的 Agent
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from enum import Enum
import logging
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class ExecutionState(Enum):
    """执行状态"""
    PENDING = "pending"
    READY = "ready"        # 依赖满足，可执行
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ScheduledAgent:
    """调度中的Agent"""
    agent_id: str
    agent: Any                          # 实际的Agent对象
    dependencies: List[str]             # 依赖的Agent ID列表
    state: ExecutionState = ExecutionState.PENDING
    priority: int = 0
    parallel_group: int = 0
    result: Optional[Dict[str, Any]] = None
    
    def is_ready(self, completed: Set[str]) -> bool:
        """检查是否可以执行（依赖都已满足）"""
        if self.state != ExecutionState.PENDING:
            return False
        return all(dep in completed for dep in self.dependencies)
    
    def can_retry(self, max_retries: int) -> bool:
        """是否可以重试"""
        return self.state == ExecutionState.FAILED


class ExecutionScheduler:
    """
    执行调度器
    
    基于任务分解计划进行智能调度：
    1. 解析 Agent 依赖关系
    2. 拓扑排序确定执行顺序
    3. 识别可并行执行的 Agent
    4. 动态调度执行
    """
    
    def __init__(
        self,
        max_parallel: int = 5,
        enable_dynamic_scheduling: bool = True,
    ):
        """
        初始化调度器
        
        Args:
            max_parallel: 最大并行数
            enable_dynamic_scheduling: 是否启用动态调度
        """
        self.max_parallel = max_parallel
        self.enable_dynamic_scheduling = enable_dynamic_scheduling
        
        # 调度状态
        self._scheduled_agents: Dict[str, ScheduledAgent] = {}
        self._completed: Set[str] = set()
        self._failed: Set[str] = set()
        self._execution_order: List[str] = []
    
    def _get_agent_category(self, agent: Any) -> str:
        """
        获取 Agent 的 category（兼容多种存储方式）
        
        Args:
            agent: Agent 实例
            
        Returns:
            category 字符串
        """
        # 1. 直接属性
        category = getattr(agent, 'category', None)
        if category:
            return category
        
        # 2. config 中
        config = getattr(agent, 'config', {}) or {}
        category = config.get('category')
        if category:
            return category
        
        # 3. context 中
        context = getattr(agent, '_context', None) or getattr(agent, 'context', {}) or {}
        category = context.get('category')
        if category:
            return category
        
        # 4. 根据 agent_id 推断
        agent_id = getattr(agent, 'agent_id', '').lower()
        if agent_id.startswith('synthesis_'):
            return 'synthesis'
        elif agent_id.startswith('analysis_'):
            return 'analysis'
        elif agent_id.startswith('research_'):
            return 'research'
        
        return 'research'  # 默认
    
    def schedule_from_decomposition(
        self,
        decomposition_plan: Any,  # DecompositionPlan
        agents: List[Any],
    ) -> List[List[str]]:
        """
        从分解计划生成执行调度
        
        Args:
            decomposition_plan: 任务分解计划
            agents: Agent列表
            
        Returns:
            执行批次列表，每批次内的Agent可并行执行
        """
        # 清理状态
        self._scheduled_agents.clear()
        self._completed.clear()
        self._failed.clear()
        self._execution_order.clear()
        
        # 1. 构建Agent ID到Agent的映射
        agent_map = {self._get_agent_id(agent): agent for agent in agents}
        logger.info(f"[Scheduler] agent_map 包含 {len(agent_map)} 个Agent: {list(agent_map.keys())}")
        
        # 2. 从分解计划提取Agent规格
        agent_specs = {}
        for phase, specs in decomposition_plan.phases.items():
            for spec in specs:
                agent_specs[spec.agent_id] = spec
        logger.info(f"[Scheduler] decomposition_plan 包含 {len(agent_specs)} 个AgentSpec: {list(agent_specs.keys())}")
        
        # 3. 构建调度Agent
        for agent in agents:
            agent_id = self._get_agent_id(agent)
            
            # 从AgentSpec获取依赖，如果没有则从context获取
            spec = agent_specs.get(agent_id)
            
            # **关键修复**：如果精确匹配失败，尝试模糊匹配
            # AgentSpec ID格式: synthesis_0_执行摘要, deep_analysis_1_市场规模
            # 实际Agent ID格式: synthesis_执行摘要_1, research_市场规模_2
            if not spec:
                # 提取关键部分进行匹配
                agent_id_lower = agent_id.lower()
                for spec_id, spec_obj in agent_specs.items():
                    spec_id_lower = spec_id.lower()
                    agent_parts = agent_id_lower.split('_')
                    spec_parts = spec_id_lower.split('_')
                    
                    # 检查是否包含相同的关键词
                    if len(agent_parts) >= 2 and len(spec_parts) >= 3:
                        # 提取章节名关键词
                        # agent: research_市场规模_2 -> 章节=市场规模
                        # spec: deep_analysis_1_市场规模 -> 章节=市场规模
                        agent_section = agent_parts[1] if len(agent_parts) >= 3 else agent_parts[-1]
                        spec_section = spec_parts[-1]
                        
                        # 如果章节名匹配
                        if agent_section == spec_section or agent_section in spec_section or spec_section in agent_section:
                            # 检查类型是否匹配
                            agent_type = agent_parts[0] if agent_parts else ''
                            
                            # spec类型可能是组合词: deep_analysis, data_collection
                            if spec_parts[0] in ['deep', 'data'] and len(spec_parts) >= 4:
                                spec_type = '_'.join(spec_parts[:2])  # deep_analysis
                            else:
                                spec_type = spec_parts[0]  # synthesis
                            
                            # 类型映射: research -> deep_analysis, synthesis -> synthesis
                            type_match = (
                                agent_type == spec_type or
                                (agent_type == 'research' and spec_type in ['deep_analysis', 'data_collection', 'data_validation']) or
                                (agent_type == 'synthesis' and spec_type == 'synthesis')
                            )
                            
                            if type_match:
                                spec = spec_obj
                                logger.info(f"[Scheduler] 模糊匹配: Agent {agent_id} -> AgentSpec {spec_id}")
                                break
            
            if spec:
                dependencies = spec.dependencies
                priority = spec.priority
                parallel_group = spec.parallel_group
                # **关键修复**：将AgentSpec格式的依赖ID转换为实际Agent ID
                dependencies = self._convert_dependency_ids(dependencies, agent_map)
                logger.info(f"[Scheduler] Agent {agent_id} 从AgentSpec获取依赖: {dependencies}")
            else:
                # 回退：从Agent的context获取（支持 _context 和 context 两种属性名）
                context = getattr(agent, '_context', {}) or getattr(agent, 'context', {}) or {}
                depends_on = context.get('depends_on', [])
                # 将章节名转换为Agent ID
                dependencies = self._resolve_dependencies(depends_on, agent_map)
                priority = 0
                parallel_group = 0
                logger.warning(f"[Scheduler] Agent {agent_id} 未找到AgentSpec，从context获取依赖: {dependencies}")
            
            self._scheduled_agents[agent_id] = ScheduledAgent(
                agent_id=agent_id,
                agent=agent,
                dependencies=dependencies,
                state=ExecutionState.PENDING,
                priority=priority,
                parallel_group=parallel_group,
            )
        
        # 4. 拓扑排序生成执行批次
        execution_batches = self._topological_sort()
        
        # 5. 记录执行顺序
        for batch in execution_batches:
            self._execution_order.extend(batch)
        
        logger.info(f"[Scheduler] 调度完成: {len(self._scheduled_agents)} 个Agent, "
                   f"{len(execution_batches)} 个批次")
        for i, batch in enumerate(execution_batches):
            logger.info(f"[Scheduler]   批次{i+1}: {batch}")
        
        return execution_batches
    
    def schedule_from_agents(
        self,
        agents: List[Any],
    ) -> List[List[str]]:
        """
        从Agent列表直接生成调度（无分解计划）
        
        Args:
            agents: Agent列表
            
        Returns:
            执行批次列表
        """
        # 清理状态
        self._scheduled_agents.clear()
        self._completed.clear()
        self._failed.clear()
        self._execution_order.clear()
        
        # 构建Agent映射
        agent_map = {self._get_agent_id(agent): agent for agent in agents}
        
        # 构建调度Agent
        for agent in agents:
            agent_id = self._get_agent_id(agent)
            
            # 从Agent获取依赖（兼容多种存储方式）
            depends_on = []
            
            # 1. 检查 _context 属性
            context = getattr(agent, '_context', None)
            if context and isinstance(context, dict):
                depends_on = context.get('depends_on', [])
            # 2. 检查 context 属性
            if not depends_on:
                context = getattr(agent, 'context', None)
                if context and isinstance(context, dict):
                    depends_on = context.get('depends_on', [])
            # 3. 检查 config.context
            if not depends_on:
                config = getattr(agent, 'config', None)
                if config and isinstance(config, dict):
                    context = config.get('context', {})
                    if isinstance(context, dict):
                        depends_on = context.get('depends_on', [])
            
            # 确保 depends_on 是列表
            if not isinstance(depends_on, (list, tuple)):
                depends_on = []
            dependencies = self._resolve_dependencies(depends_on, agent_map)
            
            # 从Agent获取category（兼容属性和config）
            category = getattr(agent, 'category', None)
            if not category:
                config = getattr(agent, 'config', {}) or {}
                category = config.get('category', 'research')
            
            # **关键修复**：只在未配置依赖时，才推断默认依赖
            # 如果 agent 已经通过 depends_on 配置了依赖，尊重配置
            if not dependencies:
                if category == 'synthesis':
                    # synthesis Agent 默认依赖所有 analysis Agent
                    analysis_agents = [
                        aid for aid in agent_map 
                        if self._get_agent_category(agent_map[aid]) == 'analysis'
                    ]
                    if analysis_agents:
                        dependencies = analysis_agents
                        logger.info(f"[Scheduler] {agent_id} 未配置依赖，使用默认: 所有 analysis agents")
                    else:
                        # 兜底：依赖所有 research agent
                        research_agents = [
                            aid for aid in agent_map 
                            if self._get_agent_category(agent_map[aid]) == 'research'
                        ]
                        dependencies = research_agents
                        logger.warning(f"[Scheduler] {agent_id} 未找到 analysis agents，使用 research agents")
            
            # 验证依赖配置
            if not dependencies:
                logger.warning(f"[Scheduler] {agent_id} 没有配置任何依赖，可能无法获取数据")
            elif len(dependencies) > 10:
                logger.info(f"[Scheduler] {agent_id} 配置了 {len(dependencies)} 个依赖（综合章节需要多源数据）")
            
            self._scheduled_agents[agent_id] = ScheduledAgent(
                agent_id=agent_id,
                agent=agent,
                dependencies=dependencies,
                state=ExecutionState.PENDING,
            )
        
        # 拓扑排序
        execution_batches = self._topological_sort()
        
        for batch in execution_batches:
            self._execution_order.extend(batch)
        
        logger.info(f"调度完成: {len(self._scheduled_agents)} 个Agent, "
                   f"{len(execution_batches)} 个批次")
        
        return execution_batches
    
    def get_ready_agents(self) -> List[ScheduledAgent]:
        """
        获取当前可执行的Agent
        
        Returns:
            可执行的Agent列表
        """
        ready = []
        for agent_id, scheduled in self._scheduled_agents.items():
            if scheduled.is_ready(self._completed):
                scheduled.state = ExecutionState.READY
                ready.append(scheduled)
        
        # 按优先级排序
        ready.sort(key=lambda x: x.priority, reverse=True)
        
        # 限制并行数
        return ready[:self.max_parallel]
    
    def mark_running(self, agent_id: str) -> None:
        """标记Agent为运行中"""
        if agent_id in self._scheduled_agents:
            self._scheduled_agents[agent_id].state = ExecutionState.RUNNING
            logger.debug(f"Agent {agent_id} 开始执行")
    
    def mark_completed(
        self, 
        agent_id: str, 
        result: Dict[str, Any]
    ) -> None:
        """标记Agent完成"""
        if agent_id in self._scheduled_agents:
            self._scheduled_agents[agent_id].state = ExecutionState.COMPLETED
            self._scheduled_agents[agent_id].result = result
            self._completed.add(agent_id)
            logger.debug(f"Agent {agent_id} 执行完成")
    
    def mark_failed(
        self, 
        agent_id: str, 
        error: str
    ) -> None:
        """标记Agent失败"""
        if agent_id in self._scheduled_agents:
            self._scheduled_agents[agent_id].state = ExecutionState.FAILED
            self._scheduled_agents[agent_id].result = {"error": error}
            self._failed.add(agent_id)
            logger.warning(f"Agent {agent_id} 执行失败: {error}")
    
    def is_all_completed(self) -> bool:
        """是否所有Agent都已完成"""
        return len(self._completed) == len(self._scheduled_agents)
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """获取执行统计"""
        return {
            "total": len(self._scheduled_agents),
            "completed": len(self._completed),
            "failed": len(self._failed),
            "pending": len([a for a in self._scheduled_agents.values() 
                          if a.state == ExecutionState.PENDING]),
            "running": len([a for a in self._scheduled_agents.values() 
                          if a.state == ExecutionState.RUNNING]),
            "execution_order": self._execution_order,
        }
    
    def _get_agent_id(self, agent: Any) -> str:
        """获取Agent ID"""
        if hasattr(agent, 'agent_id'):
            return agent.agent_id
        elif hasattr(agent, 'id'):
            return agent.id
        else:
            return str(id(agent))
    
    def _resolve_dependencies(
        self,
        depends_on: List[str],
        agent_map: Dict[str, Any],
    ) -> List[str]:
        """
        解析依赖关系
        
        Args:
            depends_on: 依赖的章节名或Agent ID列表
            agent_map: Agent ID到Agent的映射
            
        Returns:
            解析后的Agent ID列表
        """
        resolved = []
        for dep in depends_on:
            # 直接匹配Agent ID
            if dep in agent_map:
                resolved.append(dep)
                continue
            
            # 尝试匹配章节名
            for agent_id in agent_map:
                if dep.lower() in agent_id.lower():
                    resolved.append(agent_id)
                    break
        
        return list(set(resolved))  # 去重
    
    def _convert_dependency_ids(
        self,
        spec_dependency_ids: List[str],
        agent_map: Dict[str, Any],
    ) -> List[str]:
        """
        将AgentSpec格式的依赖ID转换为实际Agent ID
        
        AgentSpec ID格式: deep_analysis_1_市场规模, synthesis_0_执行摘要
        实际Agent ID格式: research_市场规模_2, synthesis_执行摘要_1
        
        Args:
            spec_dependency_ids: AgentSpec格式的依赖ID列表
            agent_map: Agent ID到Agent的映射
            
        Returns:
            转换后的实际Agent ID列表
        """
        converted = []
        
        for spec_dep_id in spec_dependency_ids:
            # 直接匹配
            if spec_dep_id in agent_map:
                converted.append(spec_dep_id)
                continue
            
            # 模糊匹配：提取章节名关键词
            spec_parts = spec_dep_id.lower().split('_')
            if len(spec_parts) < 3:  # 至少要有 type_index_section 格式
                continue
            
            # 提取章节名（最后一个部分）
            spec_section = spec_parts[-1]
            
            # 提取类型（可能是前两个部分组合，如 deep_analysis）
            # 格式: deep_analysis_1_市场规模 -> type='deep_analysis', index='1', section='市场规模'
            if spec_parts[0] in ['deep', 'data'] and len(spec_parts) >= 4:
                spec_type = '_'.join(spec_parts[:2])  # deep_analysis 或 data_collection
            else:
                spec_type = spec_parts[0]  # synthesis, report
            
            for actual_agent_id in agent_map:
                actual_parts = actual_agent_id.lower().split('_')
                if len(actual_parts) < 2:
                    continue
                
                # 实际Agent ID格式: research_市场规模_2 或 synthesis_执行摘要_1
                actual_type = actual_parts[0]  # research, synthesis
                
                # 章节名在中间或末尾
                if len(actual_parts) >= 3:
                    actual_section = actual_parts[1]  # research_市场规模_2 -> 市场规模
                else:
                    actual_section = actual_parts[-1] if len(actual_parts) >= 2 else ''
                
                # 类型映射
                type_match = (
                    (spec_type in ['deep_analysis', 'data_collection', 'data_validation'] and actual_type == 'research') or
                    (spec_type == 'synthesis' and actual_type == 'synthesis') or
                    (spec_type == 'report' and actual_type in ['report', 'document'])
                )
                
                # 章节名匹配
                section_match = (
                    spec_section == actual_section or
                    spec_section in actual_section or
                    actual_section in spec_section
                )
                
                if type_match and section_match:
                    converted.append(actual_agent_id)
                    logger.info(f"[Scheduler] 依赖ID转换: {spec_dep_id} -> {actual_agent_id}")
                    break
        
        return list(set(converted))  # 去重
    
    def _topological_sort(self) -> List[List[str]]:
        """
        拓扑排序生成执行批次
        
        Returns:
            执行批次列表，每批次内可并行执行
        """
        # 构建入度表
        in_degree = defaultdict(int)
        graph = defaultdict(list)
        
        for agent_id, scheduled in self._scheduled_agents.items():
            in_degree[agent_id] = len(scheduled.dependencies)
            for dep in scheduled.dependencies:
                if dep in self._scheduled_agents:
                    graph[dep].append(agent_id)
        
        # 批次处理
        batches = []
        remaining = set(self._scheduled_agents.keys())
        
        while remaining:
            # 找出当前批次（入度为0的节点）
            batch = [
                agent_id for agent_id in remaining 
                if in_degree[agent_id] == 0
            ]
            
            if not batch:
                # 存在循环依赖
                logger.error(f"检测到循环依赖，剩余Agent: {remaining}")
                # 强制将剩余Agent作为最后批次
                batch = list(remaining)
            
            # 按优先级排序
            batch.sort(
                key=lambda x: self._scheduled_agents[x].priority, 
                reverse=True
            )
            
            batches.append(batch)
            
            # 更新入度
            for agent_id in batch:
                remaining.remove(agent_id)
                for dependent in graph[agent_id]:
                    in_degree[dependent] -= 1
        
        return batches
    
    def merge_agents(self, new_agents: List[Any]) -> None:
        """动态合并新 Agent 到调度器（用于引擎注入检查点）"""
        for agent in new_agents:
            agent_id = self._get_agent_id(agent)
            if agent_id and agent_id not in self._scheduled_agents:
                # 从 agent 提取依赖信息
                context = (getattr(agent, '_context', None) or 
                          getattr(agent, 'context', {}) or {})
                if isinstance(context, dict):
                    depends_on = context.get('depends_on', [])
                    deps = self._resolve_dependencies(depends_on, 
                        {aid: sa.agent for aid, sa in self._scheduled_agents.items()})
                else:
                    deps = []
                self._scheduled_agents[agent_id] = ScheduledAgent(
                    agent=agent, dependencies=deps, priority=0
                )
                logger.info(f"[Scheduler] 合并新 Agent: {agent_id}")

    def reschedule_all(self) -> List[List[str]]:
        """合并新 Agent 后重新计算全部批次"""
        return self._topological_sort()

    def get_agent_by_id(self, agent_id: str) -> Optional[Any]:
        """根据ID获取Agent"""
        if agent_id in self._scheduled_agents:
            return self._scheduled_agents[agent_id].agent
        return None
    
    def get_scheduled_agent(self, agent_id: str) -> Optional[ScheduledAgent]:
        """获取调度Agent"""
        return self._scheduled_agents.get(agent_id)
