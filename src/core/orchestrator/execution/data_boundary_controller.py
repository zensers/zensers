"""
数据边界控制器 - 精确控制每个 Agent 可以访问的数据范围

核心原则：
1. 精确匹配：基于 agent_id 精确匹配，不得过度提取
2. 最小必要：只提取完成任务所需的最小数据集
3. 明确边界：每个 agent 的数据边界必须明确定义
4. 可追溯：所有数据访问都有日志记录
"""
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import logging

logger = logging.getLogger(__name__)


@dataclass
class DataBoundary:
    """
    数据边界定义
    
    定义一个 agent 可以访问的数据范围：
    - allowed_agents: 允许访问的 agent ID 列表（精确匹配）
    - allowed_fields: 允许访问的数据字段
    - max_items: 最大数据项数量（防止数据过载）
    - max_length: 单项最大长度（防止 token 消耗过大）
    """
    agent_id: str
    allowed_agents: Set[str] = field(default_factory=set)
    allowed_fields: Set[str] = field(default_factory=lambda: {"content", "data_points", "sources"})
    max_items: int = 5  # 最大数据项数量
    max_length: int = 1000  # 单项最大长度（字符）
    
    def is_allowed_agent(self, source_agent_id: str) -> bool:
        """检查是否允许访问指定 agent 的数据"""
        return source_agent_id in self.allowed_agents
    
    def filter_data(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        过滤数据，只保留允许访问的数据
        
        Args:
            data: 原始数据列表
            
        Returns:
            过滤后的数据列表
        """
        filtered = []
        
        for item in data:
            source_agent_id = item.get("agent_id", "")
            
            # 精确匹配检查
            if not self.is_allowed_agent(source_agent_id):
                logger.debug(f"[DataBoundary] {self.agent_id} 不允许访问 {source_agent_id} 的数据")
                continue
            
            # 字段过滤
            filtered_item = {
                "agent_id": source_agent_id,
            }
            
            for field_name in self.allowed_fields:
                if field_name in item:
                    value = item[field_name]
                    
                    # 长度限制
                    if isinstance(value, str) and len(value) > self.max_length:
                        value = value[:self.max_length] + "...[截断]"
                        logger.debug(f"[DataBoundary] {self.agent_id} 截断 {source_agent_id} 的 {field_name} 字段")
                    
                    filtered_item[field_name] = value
            
            filtered.append(filtered_item)
            
            # 数量限制
            if len(filtered) >= self.max_items:
                logger.info(f"[DataBoundary] {self.agent_id} 达到最大数据项数量 {self.max_items}")
                break
        
        logger.info(f"[DataBoundary] {self.agent_id} 从 {len(data)} 项数据中提取 {len(filtered)} 项")
        return filtered


class DataBoundaryController:
    """
    数据边界控制器
    
    管理所有 agent 的数据边界，提供统一的数据访问接口。
    """
    
    def __init__(self):
        self._boundaries: Dict[str, DataBoundary] = {}
        self._access_log: List[Dict[str, Any]] = []  # 数据访问日志
        self._lock = asyncio.Lock()  # 线程安全锁
        
    async def register_boundary(self, boundary: DataBoundary) -> None:
        """注册 agent 的数据边界（线程安全）"""
        async with self._lock:
            self._boundaries[boundary.agent_id] = boundary
            logger.info(f"[DataBoundaryController] 注册边界: {boundary.agent_id} -> {boundary.allowed_agents}")
    
    async def get_allowed_data(
        self,
        agent_id: str,
        all_data: List[Dict[str, Any]],
        data_type: str = "content"
    ) -> List[Dict[str, Any]]:
        """
        获取 agent 允许访问的数据（线程安全）
        
        Args:
            agent_id: 目标 agent ID
            all_data: 所有数据
            data_type: 数据类型（content, data_points, sources）
            
        Returns:
            过滤后的数据
        """
        async with self._lock:
            boundary = self._boundaries.get(agent_id)
            
            if not boundary:
                logger.warning(f"[DataBoundaryController] {agent_id} 未注册数据边界，拒绝访问")
                return []
            
            # 记录访问日志（使用正确的时间戳方式）
            self._access_log.append({
                "agent_id": agent_id,
                "data_type": data_type,
                "requested_items": len(all_data),
                "allowed_agents": list(boundary.allowed_agents),
                "timestamp": datetime.now().isoformat(),
            })
            
            # 过滤数据
            filtered_data = boundary.filter_data(all_data)
            
            return filtered_data
    
    def get_access_log(self) -> List[Dict[str, Any]]:
        """获取数据访问日志"""
        return self._access_log.copy()
    
    def clear_access_log(self) -> None:
        """清空访问日志"""
        self._access_log.clear()
    
    def validate_boundary_config(self, agent_id: str, dependencies: List[str]) -> bool:
        """
        验证边界配置是否合理
        
        检查：
        1. 依赖的 agent 是否存在
        2. 是否过度提取（依赖过多）
        3. 是否遗漏必要依赖
        
        Args:
            agent_id: 目标 agent ID
            dependencies: 配置的依赖列表
            
        Returns:
            是否合理
        """
        if not dependencies:
            logger.warning(f"[DataBoundaryController] {agent_id} 没有配置任何依赖")
            return False
        
        # 检查过度提取
        if len(dependencies) > 10:
            logger.warning(f"[DataBoundaryController] {agent_id} 配置了 {len(dependencies)} 个依赖，可能过度提取")
            return False
        
        # 检查依赖格式
        for dep in dependencies:
            if not dep or not isinstance(dep, str):
                logger.warning(f"[DataBoundaryController] {agent_id} 的依赖格式错误: {dep}")
                return False
        
        return True


def create_boundary_for_synthesis(
    synthesis_agent_id: str,
    target_aspect: str,
    all_agent_ids: List[str],
    configured_dependencies: Optional[List[str]] = None
) -> DataBoundary:
    """
    为 synthesis agent 创建数据边界
    
    规则：
    1. 如果配置了 dependencies，使用配置的依赖
    2. 否则，默认依赖所有 analysis agent
    3. 不允许访问其他 synthesis agent
    
    Args:
        synthesis_agent_id: synthesis agent ID（如 "synthesis_0_执行摘要"）
        target_aspect: 目标章节（如 "执行摘要"）
        all_agent_ids: 所有 agent ID 列表
        configured_dependencies: 配置的依赖列表（从任务分解获取）
        
    Returns:
        DataBoundary 实例
    """
    # 优先使用配置的依赖
    if configured_dependencies:
        allowed_agents = set(configured_dependencies)
        logger.info(f"[create_boundary] {synthesis_agent_id} 使用配置的依赖: {configured_dependencies}")
    else:
        # 默认：允许访问所有 analysis agent
        allowed_agents = {
            aid for aid in all_agent_ids 
            if aid.startswith("analysis_")
        }
        logger.info(f"[create_boundary] {synthesis_agent_id} 使用默认依赖: 所有 analysis agents")
    
    return DataBoundary(
        agent_id=synthesis_agent_id,
        allowed_agents=allowed_agents,
        allowed_fields={"content"},  # synthesis 只需要 content
        max_items=10,  # synthesis 可能需要参考多个章节
        max_length=2000,  # synthesis 可以看更长的内容
    )


def create_boundary_for_analysis(
    analysis_agent_id: str,
    target_aspect: str,
    all_agent_ids: List[str],
    agent_section_map: Optional[Dict[str, str]] = None,
) -> DataBoundary:
    """
    为 analysis agent 创建数据边界
    
    规则：
    1. 只允许访问对应章节的 research agent
    2. 允许访问 data_points 和 sources
    3. 不允许访问其他章节的数据
    
    Args:
        analysis_agent_id: analysis agent ID
        target_aspect: 目标章节
        all_agent_ids: 所有 agent ID 列表
        
    Returns:
        DataBoundary 实例
    """
    aspect_to_match = target_aspect
    
    allowed_agents = set()
    
    for agent_id in all_agent_ids:
        if not agent_id.startswith("research_") and not agent_id.startswith("phase_"):
            continue
        # R-FIX-11: 优先使用 agent_section_map
        if agent_section_map and agent_id in agent_section_map:
            agent_aspect = agent_section_map[agent_id]
        else:
            agent_aspect = _extract_aspect_from_agent_id(agent_id)
        
        # DB-FIX-2: use substring matching (was exact match, failed for 424+ cases)
        if agent_aspect == aspect_to_match:
            allowed_agents.add(agent_id)
        elif aspect_to_match and agent_aspect and (aspect_to_match in agent_aspect or agent_aspect in aspect_to_match):
            allowed_agents.add(agent_id)
            logger.debug(f"[create_boundary] Fuzzy matched '{aspect_to_match}' -> '{agent_aspect}' for {agent_id}")
    
    if not allowed_agents:
        logger.warning(f"[create_boundary] {analysis_agent_id} 未找到对应章节 '{aspect_to_match}' 的 research agent")
    
    return DataBoundary(
        agent_id=analysis_agent_id,
        allowed_agents=allowed_agents,
        allowed_fields={"content", "data_points", "sources"},
        max_items=5,
        max_length=1000,
    )


def _extract_aspect_from_agent_id(agent_id: str) -> str:
    """
    从 agent_id 中提取章节名
    
    支持的格式：
    - synthesis_0_执行摘要 -> 执行摘要
    - analysis_市场概况 -> 市场概况
    - research_1_竞争格局 -> 竞争格局
    - phase_1_agent_0 -> phase_1_agent_0（不变，无意义章节名时不提取）
    
    如果无法提取有意义的章节名，返回原始 agent_id。
    """
    if "_" not in agent_id:
        return agent_id
    
    parts = agent_id.split("_")
    
    # phase_N_agent_M 格式：无意义章节名，返回原始值
    if len(parts) >= 4 and parts[0] == "phase" and parts[-2] == "agent":
        return agent_id
    
    # 格式: type_aspect_index 或 type_index_aspect 或 type_aspect
    if len(parts) >= 3:
        last = parts[-1]
        # 检查最后一段是否为数字索引
        # research_季度业绩波动分析_7 → 中间部分为章节名
        if last.isdigit():
            return "_".join(parts[1:-1])
        # synthesis_0_执行摘要 | research_1_竞争格局 → 最后一段为章节名
        return last
    elif len(parts) == 2:
        # analysis_市场概况 -> 市场概况
        return parts[1]
    else:
        return agent_id
    
    parts = agent_id.split("_")
    
    # 格式: type_aspect_index 或 type_index_aspect 或 type_aspect
    if len(parts) >= 3:
        last = parts[-1]
        # 检查最后一段是否为数字索引
        # research_季度业绩波动分析_7 → 中间部分为章节名
        if last.isdigit():
            return "_".join(parts[1:-1])
        # synthesis_0_执行摘要 | research_1_竞争格局 → 最后一段为章节名
        return last
    elif len(parts) == 2:
        # analysis_市场概况 -> 市场概况
        return parts[1]
    else:
        return agent_id