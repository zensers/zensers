"""
Dream Mode Integration - 做梦模式集成

将做梦模式集成到 Orchestrator 主任务流程中。

设计理念：
- 主任务优先：用户发起新需求时立即暂停知识提取
- 异步提取：利用闲置资源、空闲时间进行知识提取
- 渐进增强：系统越用越强，但不牺牲当前体验

使用方式：
```python
# 初始化
from src.core.memory.dream import DreamModeScheduler, RawResearchDataStore
from src.core.memory import UserKnowledgeBank

knowledge_bank = UserKnowledgeBank(user_id="user_001")
raw_data_store = RawResearchDataStore(user_id="user_001")
dream_scheduler = DreamModeScheduler(
    knowledge_bank=knowledge_bank,
    raw_data_store=raw_data_store
)

# 在 Orchestrator 中使用
orchestrator = OrchestratorWithDreamMode(
    dream_scheduler=dream_scheduler,
    knowledge_bank=knowledge_bank
)

# 主任务完成时自动存储研究资料
result = await orchestrator.run_research(...)

# 知识提取会在后台自动执行
```
"""

__all__ = ["OrchestratorWithDreamMode", "create_dream_mode_components"]

import logging
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def create_dream_mode_components(
    user_id: str,
    storage_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    创建做梦模式所需的所有组件
    
    Args:
        user_id: 用户ID
        storage_path: 存储路径（可选）
    
    Returns:
        包含所有组件的字典
    """
    # 相对导入
    from ..knowledge_bank import UserKnowledgeBank
    from . import (
        DreamModeScheduler,
        RawResearchDataStore,
        DreamMode,
        DreamModeConfig
    )
    from ..core import CoreMemory
    
    # 创建知识银行
    knowledge_bank = UserKnowledgeBank(
        user_id=user_id,
        db_path=f"{storage_path}/knowledge_bank_{user_id}.db" if storage_path else None
    )
    
    # 创建研究资料暂存区
    raw_data_store = RawResearchDataStore(
        user_id=user_id,
        storage_path=f"{storage_path}/raw_data.db" if storage_path else None
    )
    
    # 创建 DreamMode（用于 CoreMemory 整合）
    core_memory = CoreMemory(
        user_id=user_id,
        storage_path=storage_path
    )
    dream_mode = DreamMode(
        core_memory=core_memory,
        knowledge_bank=knowledge_bank
    )
    
    # 创建做梦模式调度器
    config = DreamModeConfig(
        trigger_after_task=True,
        trigger_on_idle_seconds=30,
        trigger_on_pending_threshold=10,
        batch_size=10
    )
    
    dream_scheduler = DreamModeScheduler(
        knowledge_bank=knowledge_bank,
        raw_data_store=raw_data_store,
        dream_mode=dream_mode,
        config=config
    )
    
    return {
        "knowledge_bank": knowledge_bank,
        "raw_data_store": raw_data_store,
        "core_memory": core_memory,
        "dream_mode": dream_mode,
        "dream_scheduler": dream_scheduler
    }


class OrchestratorWithDreamMode:
    """
    集成做梦模式的 Orchestrator 包装器
    
    职责：
    1. 包装原有 Orchestrator
    2. 在主任务完成时自动存储研究资料
    3. 在主任务开始时通知调度器暂停知识提取
    4. 支持手动触发知识提取
    
    使用方式：
    ```python
    # 创建组件
    components = create_dream_mode_components(user_id="user_001")
    
    # 创建包装器
    orchestrator = OrchestratorWithDreamMode(
        orchestrator=base_orchestrator,
        dream_scheduler=components["dream_scheduler"],
        knowledge_bank=components["knowledge_bank"]
    )
    
    # 执行研究
    result = await orchestrator.run_research_task(task_input)
    
    # 研究完成后，资料会自动存储到暂存区
    # 知识提取会在后台异步执行
    ```
    """
    
    def __init__(
        self,
        orchestrator: Any,
        dream_scheduler: Any,
        knowledge_bank: Any,
        auto_start_dream: bool = True
    ):
        """
        初始化带做梦模式的 Orchestrator
        
        Args:
            orchestrator: 原始 Orchestrator 实例
            dream_scheduler: 做梦模式调度器
            knowledge_bank: 知识银行
            auto_start_dream: 是否自动启动后台做梦循环
        """
        self.orchestrator = orchestrator
        self.dream_scheduler = dream_scheduler
        self.knowledge_bank = knowledge_bank
        
        # 启动后台循环
        if auto_start_dream:
            self.dream_scheduler.start_background()
            logger.info("Dream mode background loop started")
    
    async def run_research_task(
        self,
        task_input: Any,
        extract_knowledge: bool = True
    ) -> Dict[str, Any]:
        """
        执行研究任务（带做梦模式支持）
        
        Args:
            task_input: 任务输入
            extract_knowledge: 是否提取知识（默认 True）
        
        Returns:
            研究结果
        """
        # 初始化变量
        task = None
        result = None
        
        # 1. 通知调度器主任务开始
        await self.dream_scheduler.on_main_task_started()
        
        try:
            # 2. 解析任务
            task = self.orchestrator.parse_task(task_input)
            
            # 3. 创建工作流
            workflow = self.orchestrator.create_workflow(task)
            
            # 4. 执行工作流
            result = await self.orchestrator.execute_workflow(workflow.workflow_id)
            
            # 5. 如果成功且需要提取知识，存储研究资料
            if extract_knowledge and result.get("status") == "success":
                await self._store_research_data(
                    research_id=task.task_id,
                    result=result
                )
            
            return result
            
        finally:
            # 6. 通知调度器主任务完成
            await self.dream_scheduler.on_main_task_completed(
                research_id=task.task_id if task else "unknown",
                content=self._extract_content_from_result(result) if result else "",
                topic=task.description if task else "",
                domain=task.params.get("industry") if task else None
            )
    
    async def _store_research_data(
        self,
        research_id: str,
        result: Dict[str, Any]
    ):
        """
        存储研究资料到暂存区
        
        Args:
            research_id: 研究ID
            result: 研究结果
        """
        try:
            # 提取研究内容
            content = self._extract_content_from_result(result)
            
            if not content:
                logger.warning(f"No content to store for research {research_id}")
                return
            
            # 存储到知识银行（记录研究历史）
            await self.knowledge_bank.deposit_from_research(
                research_id=research_id,
                research_process={
                    "content": content,
                    "topic": result.get("task", {}).get("description", ""),
                    "result_summary": result.get("result", {}).get("summary", "")
                }
            )
            
            logger.info(f"Research data stored: {research_id}")
            
        except Exception as e:
            logger.error(f"Failed to store research data: {e}")
    
    def _extract_content_from_result(self, result: Dict[str, Any]) -> str:
        """
        从研究结果中提取文本内容
        
        Args:
            result: 研究结果
        
        Returns:
            文本内容
        """
        content_parts = []
        
        # 尝试从不同位置提取内容
        if "result" in result:
            result_data = result["result"]
            
            # 从 data 中提取
            if isinstance(result_data, dict):
                if "data" in result_data:
                    data = result_data["data"]
                    if isinstance(data, dict):
                        # 提取各字段
                        for key in ["summary", "content", "analysis", "report", "findings"]:
                            if key in data:
                                value = data[key]
                                if isinstance(value, str):
                                    content_parts.append(value)
                                elif isinstance(value, list):
                                    content_parts.extend(str(item) for item in value)
                
                # 从 all_data 中提取
                if "all_data" in result_data:
                    for item in result_data["all_data"]:
                        if isinstance(item, dict) and "data" in item:
                            item_data = item["data"]
                            if isinstance(item_data, dict):
                                for key in ["content", "text", "summary"]:
                                    if key in item_data:
                                        content_parts.append(str(item_data[key]))
        
        # 从 stages 中提取
        if "stages" in result:
            for stage in result["stages"]:
                if isinstance(stage, dict) and "output" in stage:
                    output = stage["output"]
                    if isinstance(output, dict):
                        for key in ["content", "text", "summary", "result"]:
                            if key in output:
                                content_parts.append(str(output[key]))
        
        return "\n\n".join(content_parts)
    
    # ========== 委托方法 ==========
    
    def register_agent(self, agent: Any) -> None:
        """注册 Agent（委托）"""
        return self.orchestrator.register_agent(agent)
    
    def unregister_agent(self, agent_id: str) -> bool:
        """注销 Agent（委托）"""
        return self.orchestrator.unregister_agent(agent_id)
    
    def get_agent(self, agent_id: str) -> Any:
        """获取 Agent（委托）"""
        return self.orchestrator.get_agent(agent_id)
    
    # ========== 做梦模式控制 ==========
    
    async def trigger_knowledge_extraction(
        self,
        batch_size: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        手动触发知识提取
        
        Args:
            batch_size: 批量处理大小
        
        Returns:
            提取结果
        """
        return await self.dream_scheduler.run_now(batch_size)
    
    def get_dream_stats(self) -> Dict[str, Any]:
        """获取做梦模式统计信息"""
        return self.dream_scheduler.get_stats()
    
    def stop_dream_background(self):
        """停止后台做梦循环"""
        self.dream_scheduler.stop_background()
    
    def start_dream_background(self):
        """启动后台做梦循环"""
        self.dream_scheduler.start_background()
    
    # ========== 属性委托 ==========
    
    @property
    def status(self) -> str:
        """获取状态"""
        return self.orchestrator.status
    
    @property
    def agents(self) -> Dict[str, Any]:
        """获取已注册的 Agent"""
        return self.orchestrator.agents