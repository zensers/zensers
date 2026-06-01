"""
Fixed Agent Base Class
======================

Characteristics of Fixed Agents:
1. Long-lived, not destroyed with tasks
2. Can be repeatedly optimized, continuously improving quality
3. Single responsibility, clear boundaries
4. Clear input/output contract
5. Asynchronous execution, supports concurrent scheduling
6. Has communication capabilities, can participate in coordination

v2.1 Fixes:
- Use asyncio.Lock instead of threading.Lock
- update_state() changed to async method
- Constructor parameter order adjusted, fixing subclass call misalignment

Design doc: docs/STATUS/AGENT_UNIFICATION_PLAN.md
Refactor doc: .sisyphus/plans/agent_mixin_refactor_plan.md
"""

import asyncio
from abc import abstractmethod
from typing import Any, Dict, Optional
from datetime import datetime
import logging

# Import Mixins
from src.core.agents.mixins import (
    StateManagementMixin,
    CommunicationMixin,
    InputValidationMixin
)

logger = logging.getLogger(__name__)


class FixedAgent(
    StateManagementMixin,
    CommunicationMixin,
    InputValidationMixin
):
    """
    Fixed Agent Base Class (Mixin Composition Pattern)
    
    Fixed Agents are core capability components of the system, responsible for 
    executing standardized professional tasks. Unlike dynamic agents, fixed agents 
    are long-lived and can be continuously optimized and accumulate capabilities.
    
    Mixin Composition:
    - StateManagementMixin: State management (async-safe)
    - CommunicationMixin: Communication capabilities (MessageBus/SharedMemory)
    - InputValidationMixin: Input validation
    
    Execution Mode:
    - All agents must implement the async execute() method
    - Orchestrator schedules multiple agents concurrently via asyncio.gather()
    - Synchronous blocking would break the entire system's concurrency
    
    Special Attributes:
    - version: Agent version number, for tracking optimization iterations
    - capabilities: Agent capability list
    - name: Agent name
    - description: Agent description
    
    Constructor Compatibility:
        Factory call: FixedAgent(agent_id="xxx", config={"name": "Data Agent", ...})
        Direct call: FixedAgent(agent_id="xxx", name="Analysis Agent", description="...")
    """
    
    # Class attributes (FixedAgent specific)
    agent_type: str = "fixed"
    version: str = "1.0.0"
    capabilities: list = []
    
    def __init__(
        self,
        agent_id: str,
        name: str = "",
        description: str = "",
        config: Optional[Dict] = None,
        *,
        agent_type: Optional[str] = None,  # Keyword argument, avoid position misalignment
        storage_path: Optional[str] = None,  # Deprecated, kept for compatibility
    ):
        """
        Initialize Fixed Agent
        
        Args:
            agent_id: Agent unique identifier
            name: Agent name
            description: Agent description
            config: Configuration dictionary
            agent_type: Agent type (keyword argument, Factory compatible)
            storage_path: Storage path (deprecated, kept for compatibility)
            
        Constructor Compatibility:
            Factory call: FixedAgent(agent_id="xxx", config={...})
            Direct call: FixedAgent(agent_id="xxx", name="Analysis Agent", description="...")
            Subclass call: super().__init__(agent_id, name=name, description=description, config=config)
        """
        # === Core identity attributes (IAgent Protocol required) ===
        self.agent_id = agent_id
        self.agent_type = agent_type or self.__class__.agent_type
        
        # === Configuration dictionary (orchestrator depends on name and context keys) ===
        # Merge name/description into config, ensuring orchestrator can access
        self.config = config or {}
        if name:
            self.config["name"] = name
        if description:
            self.config["description"] = description
        
        # === State management attributes (StateManagementMixin depends on) ===
        self._status = "idle"
        self._data: Dict[str, Any] = {}
        self._lock = asyncio.Lock()  # Use asyncio.Lock
        self._created_at = datetime.now().isoformat()
        self._updated_at = self._created_at
        
        # === Communication attributes (CommunicationMixin depends on) ===
        self._message_bus = None
        self._shared_memory = None
        self._session = None
        
        # === FixedAgent specific attributes ===
        self.name = name or self.config.get("name", agent_id)
        self.description = description or self.config.get("description", "")
        self.storage_path = storage_path
        self._capability_cache: Dict[str, Any] = {}
        
        # === P0-1 Fix: Extract section_id from config.context ===
        # Used for ContentLockManager's chapter locking mechanism
        # Consistent with GenericAgent and BaseAgent
        context = self.config.get("context", {}) if self.config else {}
        self.section_id = context.get("section_id", "")
    
    # === Core execution methods ===
    
    @abstractmethod
    async def execute(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute Agent's core task (async)
        
        This is the only entry method for fixed agents, all subclasses must implement it.
        
        ⚠️ Important: Must be an async method, otherwise it will block the event loop 
        and break concurrent scheduling.
        
        Args:
            task_input: Task input parameters, specific format defined by subclass
            
        Returns:
            Task execution result, specific format defined by subclass
            
        Example:
            >>> agent = RequirementAnalysisAgent("req_001")
            >>> result = await agent.execute({
            ...     "user_input": "Analyze energy storage industry",
            ...     "context": {"industry": "energy storage"}
            ... })
        """
        pass
    
    async def run(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run Agent (async, with state management and error handling)
        
        This is the standard run interface provided externally, internally calls execute().
        Automatically handles state transitions, event publishing, and exception catching.
        
        Args:
            task_input: Task input parameters
            
        Returns:
            Task execution result, containing status information
            
        Error Handling Strategy:
            - Input validation failure: Return error dict, don't raise exception
            - Execution exception: Return error dict, don't raise exception
            - Unlike BaseAgent, FixedAgent doesn't re-raise exceptions
        """
        # Validate input
        valid, error_msg = self.validate_input(task_input)
        if not valid:
            return {
                "success": False,
                "error": f"Input validation failed: {error_msg}",
                "agent_id": self.agent_id,
                "agent_name": self.name,
            }
        
        try:
            # Publish start event
            await self.publish_event("task_started", {"input_keys": list(task_input.keys())})
            
            # Execute core task
            result = await self.execute(task_input)
            
            # Ensure result contains standard fields
            if "success" not in result:
                result["success"] = True
            result["agent_id"] = self.agent_id
            result["agent_name"] = self.name
            result["agent_version"] = self.version
            
            # Publish completion event
            await self.publish_event("task_completed", {"success": result["success"]})
            
            return result
            
        except Exception as e:
            # Publish error event
            await self.publish_event("task_error", {"error": str(e)})
            
            # Return error dict (don't raise exception)
            return {
                "success": False,
                "error": str(e),
                "agent_id": self.agent_id,
                "agent_name": self.name,
            }
    
    # === FixedAgent specific methods ===
    
    def get_capabilities(self) -> list:
        """
        Get Agent capability list
        
        Returns:
            List of capability descriptions
            
        Note:
            This method has no calls in the entire codebase, kept only for compatibility.
            Recommend using capabilities class attribute directly.
        """
        return self.capabilities.copy()
