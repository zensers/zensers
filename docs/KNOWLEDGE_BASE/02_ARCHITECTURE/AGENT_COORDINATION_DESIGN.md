# Agent Coordination Mechanism Design

## Part 1: Current Problem Diagnosis

### 1.1 Coordination Issue List

| Issue | Current State | Impact |
|-------|---------------|--------|
| **Task Assignment** | Directly calls `agent.execute(task)` | No standardized assignment flow |
| **Status Tracking** | AgentSession exists but not fully integrated | Cannot know Agent status in real time |
| **Progress Reporting** | No mechanism | Master doesn't know Agent progress |
| **Result Collection** | ResultCollector's setup() not called | Event subscription doesn't work |
| **Heartbeat Detection** | None | Cannot determine if Agent is alive |
| **Timeout Handling** | None | Agent may block indefinitely |
| **Retry Mechanism** | None | Failure returns error directly |
| **Cancel Mechanism** | None | Cannot cancel executing Agent |
| **Concurrency Control** | Global Semaphore | Doesn't distinguish Agent type/priority |

### 1.2 Comparison with oh-my-openagent

| Feature | oh-my-openagent | Current Project | Gap |
|---------|-----------------|-----------------|-----|
| **Session Hierarchy** | Master -> Sub-Agent -> Sub-Sub-Agent | Already exists | Usable |
| **Event Notification** | session.idle/error/deleted | Not fully integrated | Needs improvement |
| **Progress Tracking** | TaskProgress + toolCallWindow | Not present | Needs implementation |
| **Heartbeat Detection** | Polling + stability detection | Not present | Needs implementation |
| **Cancel Mechanism** | abortSession + cleanup | Not present | Needs implementation |
| **Retry Mechanism** | FallbackChain | Not present | Integrate existing |

---

## Part 2: Architecture Design

### 2.1 Agent Coordination Model

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Coordination Model                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Master Agent (Orchestrator)                                 │
│  ├── AgentSessionRegistry        ← Tracks sub-Agent sessions │
│  ├── ResultCollector              ← Collects results         │
│  ├── HeartbeatMonitor            ← Monitors Agent health     │
│  └── TaskScheduler               ← Schedules task execution  │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Agent Coordination Layer                │    │
│  │                                                      │    │
│  │  1. Task Assignment          Standardized interface  │    │
│  │  2. Status Tracking          Real-time status sync   │    │
│  │  3. Progress Reporting       Periodic progress push  │    │
│  │  4. Heartbeat Detection      Timeout detection       │    │
│  │  5. Result Collection        Event-driven collection │    │
│  │  6. Error Handling           Retry + degradation     │    │
│  │  7. Cancel Mechanism         Graceful cancellation   │    │
│  │                                                      │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Task Assignment Design

```python
@dataclass
class TaskAssignment:
    """Task assignment information"""
    task_id: str
    agent_id: str
    task_type: str
    priority: int = 0
    dependencies: List[str] = field(default_factory=list)
    timeout_seconds: float = 300.0
    max_retries: int = 3
    created_at: datetime = field(default_factory=datetime.now)

class TaskScheduler:
    """Task scheduler"""
    
    def __init__(self):
        self._pending: List[TaskAssignment] = []
        self._running: Dict[str, TaskAssignment] = {}
        self._completed: Dict[str, TaskAssignment] = {}
    
    async def assign(self, agent: BaseAgent, task: Dict) -> str:
        """Assign task to agent"""
        task_id = str(uuid.uuid4())
        assignment = TaskAssignment(
            task_id=task_id,
            agent_id=agent.agent_id,
            task_type=task.get("type", "unknown"),
        )
        
        # Dispatch based on dependencies
        if assignment.dependencies:
            self._pending.append(assignment)  # Wait for dependencies
        else:
            self._running[task_id] = assignment
            await self._execute(agent, task, assignment)
        
        return task_id
    
    async def _execute(self, agent, task, assignment):
        """Execute task with timeout and retry"""
        try:
            result = await asyncio.wait_for(
                agent.execute(task),
                timeout=assignment.timeout_seconds
            )
            self._mark_completed(assignment.task_id, result)
        except asyncio.TimeoutError:
            await self._handle_timeout(agent, task, assignment)
        except Exception as e:
            await self._handle_error(agent, task, assignment, e)
```

[Content continues with detailed design for status tracking, progress reporting, heartbeat detection, result collection, error handling, and cancel mechanisms]
