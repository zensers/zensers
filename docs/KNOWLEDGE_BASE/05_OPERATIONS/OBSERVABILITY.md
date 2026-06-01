# Observability System Design

**Version**: v1.0  
**Status**: Design Phase  
**Updated**: 2026-04-05

---

## 1. Three Pillars of Observability

### 1.1 Logs

```python
class StructuredLogging:
    """Structured logging system"""
    
    def __init__(self):
        self.logger = logging.getLogger("Zensers")
        self.handler = JSONLogHandler()
        self.logger.addHandler(self.handler)
    
    def log_agent_execution(self, agent: Agent, event: ExecutionEvent):
        """Log agent execution"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": event.level,
            "service": "agent",
            "agent_id": agent.id,
            "agent_type": agent.type,
            "task_id": agent.current_task_id,
            "trace_id": event.trace_id,
            "span_id": event.span_id,
            "event_type": event.type,
            "message": event.message,
            "context": {
                "input_tokens": event.input_tokens,
                "output_tokens": event.output_tokens,
                "duration_ms": event.duration_ms,
                "llm_model": event.model,
            },
            "metadata": {
                "version": "1.0",
                "environment": os.getenv("ENV", "production"),
                "host": socket.gethostname(),
            }
        }
        
        self.logger.log(event.level, json.dumps(log_entry))
```

### 1.2 Metrics

```python
class MetricsCollector:
    """Metrics collector"""
    
    def __init__(self):
        self.registry = CollectorRegistry()
        self._setup_default_metrics()
    
    def _setup_default_metrics(self):
        # Task metrics
        self.tasks_total = Counter('Zensers_tasks_total', 'Total tasks', ['status', 'type'])
        self.task_duration = Histogram('Zensers_task_duration_seconds', 'Task duration', ['type'])
        self.tasks_in_progress = Gauge('Zensers_tasks_in_progress', 'Tasks in progress')
        
        # Agent metrics
        self.agent_executions = Counter('Zensers_agent_executions_total', 'Agent executions', ['agent_type', 'status'])
        self.agent_execution_duration = Histogram('Zensers_agent_execution_duration_seconds', 'Agent duration', ['agent_type'])
        self.active_agents = Gauge('Zensers_active_agents', 'Active agents', ['type'])
        
        # LLM metrics
        self.llm_requests = Counter('Zensers_llm_requests_total', 'LLM requests', ['model', 'status'])
        self.llm_tokens = Counter('Zensers_llm_tokens_total', 'LLM tokens', ['model', 'type'])
        self.llm_latency = Histogram('Zensers_llm_latency_seconds', 'LLM latency', ['model'])
        self.llm_cost = Counter('Zensers_llm_cost_usd', 'LLM cost USD', ['model'])
        
        # Data metrics
        self.data_collected_bytes = Counter('Zensers_data_collected_bytes', 'Data collected', ['source'])
        self.cache_hit_rate = Gauge('Zensers_cache_hit_rate', 'Cache hit rate')
```
