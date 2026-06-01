# MCP Integration Architecture

> Status: **Ready for Implementation**
> Date: 2026-05-03
> Version: 1.2

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.2 | 2026-05-03 | Fixed: async/await in MCPToolMatcher, TransportType.HTTP→STREAMABLE_HTTP, credential duplicate prevention, layer diagram clarification; Added: dependencies, simplified v1 observability scope |
| 1.1 | 2026-05-03 | Added: error handling strategy, observability, security, testing strategy |
| 1.0 | 2026-05-03 | Initial draft |

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [MCP Protocol Layer](#2-mcp-protocol-layer)
3. [Credential Manager](#3-credential-manager)
4. [Intelligent Routing Integration](#4-intelligent-routing-integration)
5. [Error Handling Strategy](#5-error-handling-strategy)
6. [Data Flow](#6-data-flow)
7. [Configuration](#7-configuration)
8. [Observability & Monitoring](#8-observability--monitoring)
9. [Security Considerations](#9-security-considerations)
10. [Testing Strategy](#10-testing-strategy)
11. [Implementation Plan](#11-implementation-plan)

---

## 1. Architecture Overview

### 1.1 Role of MCP in the System

MCP (Model Context Protocol) is a **protocol layer**, not a skill wrapper. It standardizes how external tools are discovered, invoked, and authenticated. The system has two parallel execution paths:

```
GenericAgent.execute({action, parameters})
    │
    ├── action="search" ─────→ SkillRegistry ───→ search_skill, llm_skill, ...
    │
    └── action="mcp" ────────→ MCP Protocol Layer ──→ MCP Servers
                                    │
                                    ├── wind.get_stock_data
                                    ├── slack.send_message
                                    └── github.create_pr
```

Key distinction:
- **Skills** are system-internal capabilities (search, LLM, file ops). Tightly coupled to the system.
- **MCP tools** are external capabilities (Wind data, Slack messaging, GitHub ops). Loosely coupled via standard protocol.

### 1.2 Layer Diagram

```
┌──────────────────────────────────────────────────┐
│                 ResearchOrchestrator              │
│          (decomposes task, creates agents)        │
└──────────────────────┬───────────────────────────┘
                        │
┌──────────────────────▼───────────────────────────┐
│            IntelligentRoutingAdapter              │
│  (intent analysis → task structure → exec plan)  │
│                                                   │
│  For each section/aspect:                         │
│    - resolve required skills (ASPECT_SKILL_MAP)   │
│    - resolve required MCP tools (semantic match)  │
└──────────────────────┬───────────────────────────┘
                        │
┌──────────────────────▼───────────────────────────┐
│              GenericAgent.execute()               │
│                                                   │
│  action="search" → SkillRegistry                  │
│  action="mcp"    → MCPProtocolHandler              │
└──────────────────────┬───────────────────────────┘
                        │
┌──────────────────────▼───────────────────────────┐
│            MCP Protocol Layer                     │
│                                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────┐ │
│  │ MCPClient   │  │ Credential  │  │ Rate      │ │
│  │ (transport) │──│ Manager    │──│ Limiter   │ │
│  │             │  │ (auth)      │  │ (cost)    │ │
│  └──────┬──────┘  └─────────────┘  └───────────┘ │
│         │                                          │
└─────────┼──────────────────────────────────────────┘
          │
          ▼
   ┌──────────┐  ┌──────────┐  ┌──────────┐
   │Wind MCP  │  │Slack MCP │  │GitHub MCP│
   │Server    │  │Server    │  │Server    │
   └──────────┘  └──────────┘  └──────────┘
```

> **Note**: There is no "Format Adapter" layer. MCP returns raw data, and the LLM naturally handles format interpretation. This is intentional—closed-source MCP tools cannot be modified, and a fixed schema would lose data.

---

## 2. MCP Protocol Layer

### 2.1 Current State

| Component | Status | Lines |
|-----------|--------|-------|
| `config.py` - MCPConfig, AuthConfig, ConfigLoader | ✅ Complete | 1068 |
| `server.py` - MCPServer, Request handling | ✅ Complete | 325 |
| `client.py` - MCPClient, tool invocation | ⚠️ Local mode only | 279 |
| `tool_registry.py` - Tool ABC, ToolRegistry | ✅ Complete | 583 |

**Gap**: `MCPClient` only supports local mode (direct server instance). Remote mode (SSE/HTTP) is not implemented. Auth headers are defined in config but never injected into transport.

### 2.2 Transport Types

| Transport | Description | Use Case |
|-----------|-------------|----------|
| `stdio` | Standard input/output | Local MCP servers, subprocesses |
| `sse` | Server-Sent Events | Remote servers, real-time updates |
| `streamable_http` | Standard HTTP request/response | Remote servers, simple request-response |

> **Note**: `TransportType` enum in `config.py` uses `STREAMABLE_HTTP`. The code examples use this value.

### 2.3 MCPClient Enhancement

```python
class MCPClient:
    def __init__(self, config, credential_manager=None, rate_limiter=None):
        self.config = config
        self._credential_manager = credential_manager
        self._rate_limiter = rate_limiter
        self._http_session = None  # aiohttp or httpx
        self._tool_cache: Dict[str, ToolMeta] = {}
    
    async def connect(self):
        """Connect to MCP server via configured transport"""
        if self.config.transport == TransportType.STDIO:
            # Existing: spawn subprocess
            await self._connect_stdio()
        elif self.config.transport in (TransportType.SSE, TransportType.STREAMABLE_HTTP):
            # New: establish SSE/HTTP connection with auth
            auth = self._credential_manager.get_auth(self.config.name)
            headers = auth.build_headers() if auth else {}
            self._http_session = await self._create_session(self.config.url, headers)
    
    async def discover_tools(self) -> List[ToolMeta]:
        """Query MCP server for available tools"""
        if self._tool_cache:
            return list(self._tool_cache.values())
        
        # MCP protocol: tools/list endpoint
        response = await self._request("tools/list", {})
        tools = []
        for tool_data in response.get("tools", []):
            tool = ToolMeta(
                name=tool_data["name"],
                description=tool_data.get("description", ""),
                parameters=tool_data.get("parameters", {}),
                permissions=tool_data.get("permissions", [])
            )
            tools.append(tool)
            self._tool_cache[tool.name] = tool
        return tools
    
    async def call_tool(self, tool_name, params):
        """Invoke MCP tool with auth handling and rate limiting"""
        
        # Rate limiting check
        if self._rate_limiter and not await self._rate_limiter.acquire():
            return {
                "success": False, 
                "error": "rate_limit_exceeded",
                "retry_after": await self._rate_limiter.retry_after()
            }
        
        if self._http_session:
            response = await self._http_session.request(
                method="POST",
                json={"tool": tool_name, "params": params}
            )
            
            # Auth error handling
            if response.status == 401:
                # Token expired, refresh and retry
                refreshed = await self._credential_manager.refresh(self.config.name)
                if not refreshed:
                    return {"success": False, "error": "auth_refresh_failed"}
                
                auth = self._credential_manager.get_auth(self.config.name)
                headers = auth.build_headers()
                response = await self._http_session.request(..., headers=headers)
            
            if response.status == 429:
                # Rate limited by server
                retry_after = response.headers.get("Retry-After", "60")
                return {
                    "success": False, 
                    "error": "server_rate_limit",
                    "retry_after": int(retry_after)
                }
            
            return await response.json()
```

### 2.4 MCPProtocolHandler (New Component)

This is **not a Skill**. It is a routing layer within `GenericAgent.execute()` that handles `action="mcp"`.

```python
# Location: src/core/agents/mcp_handler.py

@dataclass
class ToolMeta:
    """Metadata for an MCP tool"""
    name: str
    description: str
    parameters: Dict
    permissions: List[str] = field(default_factory=list)


class MCPProtocolHandler:
    """
    MCP protocol handler. Routes tool calls to the correct MCP server,
    returns raw data for LLM consumption.
    
    This is NOT a Skill wrapper. It is a protocol adapter that:
    1. Resolves tool name to MCP server
    2. Obtains credentials from CredentialManager
    3. Calls the tool via MCPClient
    4. Returns raw data (no format conversion)
    """
    
    def __init__(self, credential_manager=None, rate_limiter=None):
        self._credential_manager = credential_manager
        self._rate_limiter = rate_limiter
        self._clients: Dict[str, MCPClient] = {}  # server_name → client
        self._tool_index: Dict[str, str] = {}      # tool_name → server_name
        self._tool_meta: Dict[str, ToolMeta] = {}  # tool_name → metadata
    
    @classmethod
    async def create(cls, config: MCPConfig, credential_manager=None, rate_limiter=None):
        """Factory method for async initialization"""
        handler = cls(credential_manager, rate_limiter)
        await handler.initialize(config)
        return handler
    
    async def initialize(self, config: MCPConfig):
        """Initialize connections to all configured MCP servers"""
        for server_config in config.get_enabled_servers():
            try:
                client = MCPClient(server_config, self._credential_manager, self._rate_limiter)
                await client.connect()
                self._clients[server_config.name] = client
                
                # Discover and index tools
                tools = await client.discover_tools()
                for tool in tools:
                    self._tool_index[tool.name] = server_config.name
                    self._tool_meta[tool.name] = tool
                    
            except Exception as e:
                # Log error but continue with other servers
                logger.error(f"Failed to connect to MCP server {server_config.name}: {e}")
    
    async def execute(self, tool: str, params: Dict) -> Dict:
        """
        Execute an MCP tool.
        
        Args:
            tool: fully qualified tool name (e.g., "wind.get_stock_data")
            params: tool parameters
        
        Returns:
            Dict with keys:
            - success: bool
            - result: raw MCP tool response (if success)
            - error: error message (if failure)
            - error_code: error type (if failure)
            - retry_after: seconds to wait before retry (if rate limited)
        """
        server_name = self._tool_index.get(tool)
        if not server_name:
            return {"success": False, "error": f"Unknown MCP tool: {tool}", "error_code": "unknown_tool"}
        
        client = self._clients.get(server_name)
        if not client:
            return {"success": False, "error": f"MCP server not connected: {server_name}", "error_code": "server_disconnected"}
        
        return await client.call_tool(tool, params)
    
    def list_available_tools(self) -> List[Dict]:
        """List all available MCP tools for routing"""
        return [
            {
                "name": name, 
                "server": server,
                "description": self._tool_meta[name].description,
                "parameters": self._tool_meta[name].parameters
            }
            for name, server in self._tool_index.items()
        ]
    
    def get_tool_meta(self, tool_name: str) -> Optional[ToolMeta]:
        """Get metadata for a specific tool"""
        return self._tool_meta.get(tool_name)
```

### 2.5 Integration into GenericAgent

```python
# In GenericAgent.execute(), add a new action route:

def __init__(self, ...):
    ...
    self._mcp_handler = config.get("mcp_handler")  # injected by factory

async def execute(self, task):
    action = task.get("action", "")
    parameters = task.get("parameters", {})
    
    if action == "mcp":
        # Route to MCP protocol handler
        if not self._mcp_handler:
            return {"success": False, "error": "MCP handler not available"}
        
        tool = parameters.get("tool", "")
        params = parameters.get("params", {})
        
        # Step 1: Call MCP tool, get raw data
        mcp_result = await self._mcp_handler.execute(tool, params)
        
        if not mcp_result.get("success"):
            # Inject error context for graceful degradation
            parameters["mcp_error"] = mcp_result.get("error")
            parameters["mcp_error_code"] = mcp_result.get("error_code")
            parameters["mcp_fallback"] = True
        else:
            # Step 2: Inject raw data into LLM context
            parameters["mcp_data"] = mcp_result.get("result")
        
        # Fall through to llm_skill with enriched parameters
        action = "llm"  # Continue with LLM processing
    
    if action == "search":
        # Route to SkillRegistry (existing)
        ...
```

> **Why no format conversion**: MCP returns raw, heterogeneous data. Converting it to a fixed schema would either lose data (for complex tools) or be impossible (for closed-source MCPs). The LLM is the natural format adapter—it understands any JSON structure.

---

## 3. Credential Manager

### 3.1 Why It Exists

MCP servers require authentication. Credentials vary by:
- **Scope**: system-level (DB passwords) vs user-level (personal API keys)
- **Lifetime**: static (API key) vs refreshable (OAuth token)
- **Source**: env vars, config file, user session input

### 3.2 CredentialManager Interface

```python
# Location: src/core/mcp/credentials.py

@dataclass
class Credential:
    server_name: str
    auth: AuthConfig
    source: str  # "system" | "user" | "session"
    expires_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)


class CredentialManager:
    """
    Manages credentials for all MCP servers.
    
    Resolution priority: session > user > system
    """
    
    def __init__(self, encryption_key: Optional[str] = None):
        self._credentials: Dict[str, List[Credential]] = {}
        self._effective_cache: Dict[str, Optional[AuthConfig]] = {}
        self._encryption_key = encryption_key
        self._audit_log: List[Dict] = []
    
    def register_system(self, server_name: str, auth: AuthConfig):
        """Register system-level credentials (from config/env)"""
        self._add_credential(server_name, auth, "system")
    
    def register_user(self, server_name: str, auth: AuthConfig):
        """Register user-level credentials (from login)"""
        self._add_credential(server_name, auth, "user")
    
    def register_session(self, server_name: str, auth: AuthConfig):
        """Register session-level credentials (runtime injection)"""
        self._add_credential(server_name, auth, "session")
    
    def _add_credential(self, server_name: str, auth: AuthConfig, source: str):
        """Add credential and invalidate cache"""
        if server_name not in self._credentials:
            self._credentials[server_name] = []
        
        # Remove existing credential with same source to prevent duplicates
        self._credentials[server_name] = [
            c for c in self._credentials[server_name] 
            if c.source != source
        ]
        
        cred = Credential(server_name=server_name, auth=auth, source=source)
        self._credentials[server_name].append(cred)
        
        # Invalidate cache
        self._effective_cache.pop(server_name, None)
        
        # Audit log
        self._log_access(server_name, "register", source)
    
    def get_auth(self, server_name: str) -> Optional[AuthConfig]:
        """
        Get effective credentials for a server.
        Priority: session > user > system
        """
        # Check cache first
        if server_name in self._effective_cache:
            self._log_access(server_name, "get", "cache")
            return self._effective_cache[server_name]
        
        creds = self._credentials.get(server_name, [])
        if not creds:
            return None
        
        # Sort by priority: session > user > system
        priority_order = {"session": 0, "user": 1, "system": 2}
        
        for cred in sorted(creds, key=lambda c: priority_order.get(c.source, 99)):
            # Check expiration
            if cred.expires_at and cred.expires_at <= datetime.now():
                continue
            
            # Cache and return
            self._effective_cache[server_name] = cred.auth
            self._log_access(server_name, "get", cred.source)
            return cred.auth
        
        return None
    
    async def refresh(self, server_name: str) -> bool:
        """Refresh OAuth token for a server"""
        auth = self.get_auth(server_name)
        if not auth or auth.type != AuthType.OAUTH:
            return False
        
        try:
            # OAuth refresh flow
            new_token = await self._oauth_refresh(auth)
            if new_token:
                # Update the credential
                auth.token = new_token["access_token"]
                auth.expires_at = datetime.now() + timedelta(seconds=new_token.get("expires_in", 3600))
                self._log_access(server_name, "refresh", "oauth")
                return True
        except Exception as e:
            logger.error(f"OAuth refresh failed for {server_name}: {e}")
        
        return False
    
    def _log_access(self, server_name: str, action: str, source: str):
        """Log credential access for audit"""
        self._audit_log.append({
            "timestamp": datetime.now().isoformat(),
            "server": server_name,
            "action": action,
            "source": source
        })
    
    def get_audit_log(self, server_name: Optional[str] = None) -> List[Dict]:
        """Get audit log, optionally filtered by server"""
        if server_name:
            return [e for e in self._audit_log if e["server"] == server_name]
        return self._audit_log.copy()
```

### 3.3 Configuration Integration

```yaml
# config/mcp.yaml
servers:
  - name: wind
    transport: sse
    url: "https://mcp.wind.com/sse"
    auth:
      type: api_key
      api_key: "${WIND_API_KEY}"        # System-level, from env
      api_key_header: "X-Wind-Token"
    security:
      encryption: true                   # Encrypt when persisting
      audit: true                        # Log all credential access
      rotation_days: 90                  # Suggest rotation interval
  
  - name: slack
    transport: sse
    url: "https://mcp.slack.com/sse"
    auth:
      type: bearer
      token: "${SLACK_BOT_TOKEN}"       # System-level, from env
```

### 3.4 Auth Error Handling

```
MCPClient.call_tool()
    │
    ├── 200 OK → return result
    ├── 401 Unauthorized → CredentialManager.refresh() → retry
    │       └── refresh failed → return auth_error
    ├── 403 Forbidden → return permission_error
    ├── 429 Rate Limited → return rate_limit_error with retry_after
    └── 5xx → retry with backoff → return server_error
```

---

## 4. Intelligent Routing Integration

### 4.1 Semantic Tool Matching (Primary Approach)

Instead of static mapping, use semantic matching to find relevant MCP tools for each aspect:

```python
# Location: src/core/decomposition/mcp_matcher.py

class MCPToolMatcher:
    """
    Match MCP tool descriptions to aspects using semantic similarity.
    """
    
    def __init__(self, mcp_handler: MCPProtocolHandler, llm_client=None):
        self._mcp_handler = mcp_handler
        self._llm_client = llm_client
        self._cache: Dict[str, List[str]] = {}
    
    async def match(self, aspect: str, top_k: int = 3) -> List[str]:
        """
        Find relevant MCP tools for an aspect.
        
        Args:
            aspect: Research aspect (e.g., "财务分析", "技术趋势")
            top_k: Maximum number of tools to return
        
        Returns:
            List of fully qualified tool names (e.g., ["wind.get_stock_data"])
        """
        # Check cache
        if aspect in self._cache:
            return self._cache[aspect][:top_k]
        
        # Get all available tools
        all_tools = self._mcp_handler.list_available_tools()
        if not all_tools:
            return []
        
        # Keyword-based matching (fast path)
        matched = self._keyword_match(aspect, all_tools)
        
        # LLM-based matching (accurate path, if available)
        if self._llm_client and len(matched) < top_k:
            semantic_matches = await self._semantic_match(aspect, all_tools, top_k)
            matched.extend(semantic_matches)
        
        # Deduplicate and cache
        matched = list(dict.fromkeys(matched))[:top_k]
        self._cache[aspect] = matched
        
        return matched
    
    def _keyword_match(self, aspect: str, tools: List[Dict]) -> List[str]:
        """Keyword-based matching for common patterns"""
        ASPECT_KEYWORDS = {
            "财务分析": ["stock", "financial", "财报", "股价", "业绩"],
            "估值分析": ["valuation", "估值", "pe", "pb", "市值"],
            "技术趋势": ["github", "arxiv", "repo", "paper", "research"],
            "竞争格局": ["industry", "competitor", "market", "竞争"],
            "市场规模": ["market", "size", "规模", "industry"],
        }
        
        keywords = ASPECT_KEYWORDS.get(aspect, [])
        matched = []
        
        for tool in tools:
            desc_lower = tool["description"].lower()
            name_lower = tool["name"].lower()
            
            for kw in keywords:
                if kw.lower() in desc_lower or kw.lower() in name_lower:
                    matched.append(tool["name"])
                    break
        
        return matched
    
    async def _semantic_match(self, aspect: str, tools: List[Dict], top_k: int) -> List[str]:
        """Use LLM for semantic matching"""
        tool_descriptions = "\n".join([
            f"- {t['name']}: {t['description']}"
            for t in tools
        ])
        
        prompt = f"""Given a research aspect "{aspect}", select the most relevant tools.

Available tools:
{tool_descriptions}

Return only the tool names, one per line, up to {top_k} most relevant tools.
If no tools are relevant, return "none"."""

        response = await self._llm_client.generate(prompt)
        
        if "none" in response.lower():
            return []
        
        return [line.strip() for line in response.strip().split("\n") if line.strip()]


# Static fallback mapping (for reliability)
ASPECT_MCP_FALLBACK = {
    "财务分析": ["wind.get_stock_data", "wind.get_financials"],
    "估值分析": ["wind.get_valuation"],
    "技术趋势": ["github.repo_search", "arxiv.search_papers"],
    "竞争格局": ["wind.industry_company_list"],
}
```

### 4.2 AgentSpec Extension

```python
@dataclass
class AgentSpec:
    agent_id: str
    agent_type: str
    category: str
    skills: List[str] = field(default_factory=list)
    mcp_tools: List[str] = field(default_factory=list)
    fallback_on_mcp_error: bool = True  # New: graceful degradation flag
    ...
```

### 4.3 AgentFactory Integration

```python
# In orchestrator.py _create_agents():

# Initialize MCP matcher (once)
if not hasattr(self, '_mcp_matcher'):
    self._mcp_matcher = MCPToolMatcher(self._mcp_handler, self._llm_client)

for i, aspect in normal_aspects:
    # Existing skill resolution
    base_skills = ASPECT_SKILL_MAP.get(aspect, ["llm_skill", "search_skill"])
    
    # MCP tool resolution (semantic matching with fallback)
    # Note: match() is async, must be awaited
    mcp_tools = await self._mcp_matcher.match(aspect)
    if not mcp_tools:
        mcp_tools = ASPECT_MCP_FALLBACK.get(aspect, [])
    
    capability = AgentCapability(
        name=f"{aspect}研究Agent",
        required_skills=base_skills,
        mcp_tools=mcp_tools,
        ...
    )
    
    # Agent receives mcp_handler via config
    agent_config = {
        "mcp_handler": self._mcp_handler,
        "mcp_tools": mcp_tools,
        ...
    }
```

> **Important**: `MCPToolMatcher.match()` is an `async` method because `_semantic_match()` uses LLM. All callers must use `await`.

---

## 5. Error Handling Strategy

### 5.1 Error Categories and Responses

| Error Code | Description | Response Strategy |
|------------|-------------|-------------------|
| `unknown_tool` | Tool not found in index | Return error, no retry |
| `server_disconnected` | MCP server not connected | Retry connection once, then fallback |
| `auth_refresh_failed` | OAuth refresh failed | Prompt user re-auth, fallback to alternative |
| `server_rate_limit` | Server returned 429 | Wait `retry_after` seconds, then retry |
| `rate_limit_exceeded` | Local rate limit hit | Wait and retry, or queue request |
| `timeout` | Request timed out | Retry with exponential backoff |
| `server_error` | 5xx from server | Retry with backoff, then fallback |

### 5.2 Graceful Degradation Flow

```python
# In GenericAgent.execute() for action="mcp"

async def execute(self, task):
    ...
    if action == "mcp":
        mcp_result = await self._mcp_handler.execute(tool, params)
        
        if not mcp_result.get("success"):
            error_code = mcp_result.get("error_code")
            
            # Strategy 1: Retry for transient errors
            if error_code in ["timeout", "server_error"]:
                await asyncio.sleep(2)
                mcp_result = await self._mcp_handler.execute(tool, params)
            
            # Strategy 2: Rate limit handling
            if error_code == "rate_limit_exceeded":
                retry_after = mcp_result.get("retry_after", 60)
                # Option A: Wait and retry
                # Option B: Queue and continue with fallback
                
            # Strategy 3: Fallback to alternative data source
            if not mcp_result.get("success"):
                parameters["mcp_fallback"] = True
                parameters["mcp_error"] = mcp_result.get("error")
                
                # Try alternative tools if available
                alternatives = self._get_alternative_tools(tool)
                for alt_tool in alternatives:
                    alt_result = await self._mcp_handler.execute(alt_tool, params)
                    if alt_result.get("success"):
                        parameters["mcp_data"] = alt_result.get("result")
                        parameters["mcp_source"] = alt_tool
                        break
        
        # Continue with LLM processing
        action = "llm"
```

### 5.3 Error Notification to Orchestrator

```python
# In ResearchOrchestrator

async def _handle_agent_error(self, agent_id: str, error: Dict):
    """Handle agent errors and decide on recovery"""
    error_code = error.get("error_code")
    
    if error_code == "auth_refresh_failed":
        # Notify user for re-authentication
        await self._notify_user({
            "type": "auth_required",
            "server": error.get("server"),
            "message": "Please re-authenticate for continued access"
        })
    
    elif error_code == "server_disconnected":
        # Attempt to reconnect
        await self._mcp_handler.reconnect(error.get("server"))
```

---

## 6. Data Flow

### 6.1 End-to-End Flow

```
User: "分析新能源汽车行业"
    │
    ▼
Orchestrator.research()
    │
    ├── SmartClarifier: 用户选择"财务分析"章节
    │
    ├── IntelligentRoutingAdapter.analyze()
    │   └── TaskStructure: sections = [财务分析, 市场规模, 竞争格局, ...]
    │
    ├── MCPToolMatcher.match("财务分析")
    │   └── → ["wind.get_stock_data", "wind.get_financials"]
    │
    ├── _create_agents()
    │   ├── "财务分析" agent → skills=["llm_skill"], mcp_tools=["wind.get_stock_data"]
    │   ├── "市场规模" agent → skills=["llm_skill", "search_skill"], mcp_tools=[]
    │   └── "竞争格局" agent → skills=["llm_skill", "search_skill"], mcp_tools=[]
    │
    ├── ExecutionEngine._execute_batch()
    │   │
    │   │  "财务分析" agent:
    │   │   GenericAgent.execute({action: "mcp", parameters: {
    │   │     tool: "wind.get_stock_data",
    │   │     params: {industry: "新能源汽车"}
    │   │   }})
    │   │     │
    │   │     ▼
    │   │   MCPProtocolHandler.execute("wind.get_stock_data", ...)
    │   │     │
    │   │     ├── CredentialManager.get_auth("wind") → API Key
    │   │     ├── RateLimiter.acquire() → OK
    │   │     ├── MCPClient.call_tool("get_stock_data", params)
    │   │     │   └── Wind MCP Server → 返回原始数据
    │   │     │       {stocks: [{code: "002594", pe: 25.3, ...}], ...}
    │   │     │
    │   │     └── 原始数据注入 LLM 上下文
    │   │
    │   │   GenericAgent → llm_skill(mcp_data + prompt)
    │   │     └── 返回 {content, data_points, sources, charts}
    │   │
    │   │  "市场规模" agent:
    │   │   GenericAgent.execute({action: "search", ...})
    │   │     └── search_skill → llm_skill
    │   │
    │   └── batch_results → [{content, data_points, sources}, ...]
    │
    ├── Harness constraint check (AgentConstraintChecker)
    │   └── quality_metadata injected into each result
    │
    ├── ResultAggregator.aggregate()
    │
    ├── QualityCheckAgent (report-level)
    │
    └── DocumentGenerationAgent → final report
```

### 6.2 Data Format Contract

The system already has a stable data contract. MCP does not change it:

```python
# Each agent result (whether from search_skill or MCP) returns:
{
    "success": bool,
    "content": str,                    # Main output
    "result": str | dict,              # Fallback content
    "data_points": List[Dict],         # Structured data
    "sources": List[Dict],             # Source references
    "charts": List[Dict],              # Chart data
    "facts": List[Dict],               # Key facts
    "quality_metadata": {              # Harness check results
        "harness": {...}
    },
    "mcp_metadata": {                  # New: MCP-specific metadata
        "tool": "wind.get_stock_data",
        "latency_ms": 234,
        "cached": false
    }
}
```

---

## 7. Configuration

### 7.1 Single File, Multiple MCP Servers

```yaml
# config/mcp.yaml — or .json, auto-detected

version: "2.0"

# Rate limiting defaults (can be overridden per server)
rate_limits:
  default:
    requests_per_minute: 60
    requests_per_hour: 1000
    tokens_per_day: 100000  # For token-based pricing

servers:
  - name: wind
    description: "Wind Financial Data MCP Server"
    transport: sse
    url: "https://mcp.wind.com/sse"
    enabled: true
    tags: ["financial", "china"]
    timeout:
      connect: 10
      request: 60
      read: 120
      total: 300
    retry:
      enabled: true
      max_attempts: 3
      initial_delay: 1.0
      max_delay: 30.0
    rate_limit:
      requests_per_minute: 30
      requests_per_hour: 500
    auth:
      type: api_key
      api_key: "${WIND_API_KEY}"
      api_key_header: "X-Wind-Token"
    security:
      encryption: true
      audit: true
      rotation_days: 90
    tools:
      - name: "get_stock_data"
        enabled: true
        cost_per_call: 0.01  # USD (optional, for reference only)
        # Note: Actual pricing may vary by data volume or subscription tier.
        # This value is for cost estimation only, not for billing.
      - name: "get_financials"
        enabled: true
        cost_per_call: 0.02  # USD (optional, for reference only)
      - name: "get_industry_data"
        enabled: true

  - name: slack
    description: "Slack Messaging MCP Server"
    transport: sse
    url: "https://mcp.slack.com/sse"
    enabled: true
    tags: ["communication"]
    auth:
      type: bearer
      token: "${SLACK_BOT_TOKEN}"
    tools:
      - name: "send_message"
        enabled: true
        permissions: ["notify"]
      - name: "list_channels"
        enabled: false

  - name: local_db
    description: "Internal Database MCP Server"
    transport: stdio
    command: "python"
    args: ["-m", "mcp_servers.db_server"]
    enabled: true
    tags: ["internal", "database"]

  - name: wind_backup
    description: "Wind Backup Server (Failover)"
    transport: sse
    url: "https://mcp-backup.wind.com/sse"
    enabled: false  # Enabled automatically on primary failure
    tags: ["financial", "china", "failover"]
    failover_for: "wind"

# Built-in tools (not MCP)
tools:
  - name: "web_search"
    type: builtin
    enabled: true

# Data sources
data_sources:
  - name: "knowledge_base"
    type: sqlite
    database: "data/knowledge.db"
    enabled: true
```

### 7.2 Environment Variables

```bash
# .env
WIND_API_KEY=your_wind_api_key_here
SLACK_BOT_TOKEN=xoxb-your-slack-token

# Optional: encryption key for stored credentials
MCP_ENCRYPTION_KEY=your_32_byte_encryption_key
```

---

## 8. Observability & Monitoring

### 8.1 Metrics Collection

```python
# Location: src/core/mcp/metrics.py

from prometheus_client import Counter, Histogram, Gauge

# Request metrics
MCP_REQUESTS_TOTAL = Counter(
    'mcp_requests_total',
    'Total MCP tool requests',
    ['server', 'tool', 'status']
)

MCP_REQUEST_LATENCY = Histogram(
    'mcp_request_latency_seconds',
    'MCP tool request latency',
    ['server', 'tool'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

MCP_ACTIVE_CONNECTIONS = Gauge(
    'mcp_active_connections',
    'Active MCP server connections',
    ['server']
)

# Rate limiting
MCP_RATE_LIMIT_HITS = Counter(
    'mcp_rate_limit_hits_total',
    'Rate limit hits',
    ['server']
)

# Cost tracking
MCP_COST_TOTAL = Counter(
    'mcp_cost_total_dollars',
    'Total MCP API cost in dollars',
    ['server', 'tool']
)
```

### 8.2 Distributed Tracing

```python
# Location: src/core/mcp/tracing.py

from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

tracer = trace.get_tracer(__name__)

class TracingMCPClient(MCPClient):
    """MCPClient with OpenTelemetry tracing"""
    
    async def call_tool(self, tool_name, params):
        with tracer.start_as_current_span(
            f"mcp.{self.config.name}.{tool_name}"
        ) as span:
            span.set_attribute("mcp.server", self.config.name)
            span.set_attribute("mcp.tool", tool_name)
            span.set_attribute("mcp.params", json.dumps(params))
            
            try:
                result = await super().call_tool(tool_name, params)
                span.set_attribute("mcp.success", result.get("success", False))
                return result
            except Exception as e:
                span.record_exception(e)
                raise
```

### 8.3 Structured Logging

```python
# Location: src/core/mcp/logging.py

import structlog

logger = structlog.get_logger()

# In MCPProtocolHandler
async def execute(self, tool: str, params: Dict) -> Dict:
    log = logger.bind(
        server=self._tool_index.get(tool),
        tool=tool,
        params_hash=hash(json.dumps(params))
    )
    
    log.info("mcp_tool_call_start")
    start_time = time.time()
    
    result = await client.call_tool(tool, params)
    
    log.info(
        "mcp_tool_call_end",
        success=result.get("success"),
        latency_ms=(time.time() - start_time) * 1000
    )
    
    return result
```

### 8.4 Health Checks

```python
# Location: src/core/mcp/health.py

class MCPHealthChecker:
    """Health check for MCP servers"""
    
    async def check_server(self, server_name: str) -> Dict:
        """Check health of a single MCP server"""
        client = self._clients.get(server_name)
        if not client:
            return {"status": "disconnected"}
        
        try:
            # Simple ping or tools/list call
            tools = await client.discover_tools()
            return {
                "status": "healthy",
                "tools_count": len(tools),
                "latency_ms": client.last_request_latency
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def check_all(self) -> Dict[str, Dict]:
        """Check health of all MCP servers"""
        results = {}
        for server_name in self._clients.keys():
            results[server_name] = await self.check_server(server_name)
        return results
```

---

## 9. Security Considerations

### 9.1 Credential Storage

```python
# Location: src/core/mcp/security.py

from cryptography.fernet import Fernet
import keyring

class SecureCredentialStorage:
    """
    Secure storage for MCP credentials.
    
    Storage hierarchy:
    1. Keyring (OS-level secure storage) - preferred
    2. Encrypted file - fallback
    3. Environment variables - for system-level only
    """
    
    def __init__(self, encryption_key: Optional[bytes] = None):
        self._fernet = Fernet(encryption_key) if encryption_key else None
        self._storage_file = "data/credentials.enc"
    
    def store(self, server_name: str, credential: Dict):
        """Store credential securely"""
        # Try keyring first
        try:
            keyring.set_password(
                "mcp_credentials",
                server_name,
                json.dumps(credential)
            )
            return
        except Exception:
            pass
        
        # Fallback to encrypted file
        if self._fernet:
            encrypted = self._fernet.encrypt(json.dumps(credential).encode())
            self._write_to_file(server_name, encrypted)
    
    def retrieve(self, server_name: str) -> Optional[Dict]:
        """Retrieve credential from secure storage"""
        # Try keyring first
        try:
            data = keyring.get_password("mcp_credentials", server_name)
            if data:
                return json.loads(data)
        except Exception:
            pass
        
        # Fallback to encrypted file
        if self._fernet:
            encrypted = self._read_from_file(server_name)
            if encrypted:
                return json.loads(self._fernet.decrypt(encrypted))
        
        return None
```

### 9.2 Credential Rotation

```python
class CredentialRotationManager:
    """Manage credential rotation"""
    
    def __init__(self, credential_manager: CredentialManager):
        self._credential_manager = credential_manager
        self._rotation_schedule: Dict[str, datetime] = {}
    
    def schedule_rotation(self, server_name: str, interval_days: int):
        """Schedule automatic rotation reminder"""
        self._rotation_schedule[server_name] = datetime.now() + timedelta(days=interval_days)
    
    async def check_rotation_needed(self) -> List[str]:
        """Check which credentials need rotation"""
        needs_rotation = []
        for server_name, rotation_date in self._rotation_schedule.items():
            if datetime.now() >= rotation_date:
                needs_rotation.append(server_name)
        return needs_rotation
    
    async def notify_rotation_needed(self, server_name: str):
        """Notify user/admin that rotation is needed"""
        # Send notification via configured channels
        pass
```

### 9.3 Audit Logging

```python
# In CredentialManager
def _log_access(self, server_name: str, action: str, source: str):
    """Log credential access for audit"""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "server": server_name,
        "action": action,  # "register", "get", "refresh", "rotate"
        "source": source,  # "system", "user", "session", "cache"
        "success": True,
        "ip_address": self._get_client_ip(),  # If applicable
    }
    
    self._audit_log.append(entry)
    
    # Also write to persistent audit log
    audit_file = "logs/credential_audit.jsonl"
    with open(audit_file, "a") as f:
        f.write(json.dumps(entry) + "\n")
```

### 9.4 Permission Model

```yaml
# config/mcp_permissions.yaml

roles:
  admin:
    servers: ["*"]
    tools: ["*"]
  
  analyst:
    servers: ["wind", "arxiv", "github"]
    tools:
      - "wind.get_stock_data"
      - "wind.get_financials"
      - "arxiv.search_papers"
      - "github.repo_search"
  
  viewer:
    servers: ["wind"]
    tools:
      - "wind.get_stock_data"

# User-role mapping
users:
  admin@example.com: ["admin"]
  analyst@example.com: ["analyst"]
```

---

## 10. Testing Strategy

### 10.1 Mock MCP Server

```python
# tests/mcp/mock_server.py

class MockMCPServer:
    """Mock MCP server for testing without real external services"""
    
    TOOLS = {
        "wind.get_stock_data": {
            "description": "获取A股行情数据",
            "mock_result": {
                "success": True,
                "result": {
                    "stocks": [
                        {"code": "002594", "name": "比亚迪", "pe": 25.3, "price": 250.5},
                        {"code": "300750", "name": "宁德时代", "pe": 30.2, "price": 180.2}
                    ]
                }
            }
        },
        "wind.get_financials": {
            "description": "获取财务数据",
            "mock_result": {
                "success": True,
                "result": {
                    "revenue": 1000000000,
                    "profit": 50000000,
                    "assets": 5000000000
                }
            }
        },
        "github.repo_search": {
            "description": "Search GitHub repositories",
            "mock_result": {
                "success": True,
                "result": {
                    "repos": [
                        {"name": "awesome-project", "stars": 1000, "language": "Python"}
                    ]
                }
            }
        }
    }
    
    async def handle_request(self, request: Dict) -> Dict:
        tool = request.get("tool")
        params = request.get("params", {})
        
        if tool in self.TOOLS:
            # Simulate delay
            await asyncio.sleep(0.1)
            return self.TOOLS[tool]["mock_result"]
        
        return {"success": False, "error": f"Unknown tool: {tool}"}
    
    async def handle_discovery(self) -> Dict:
        """Return list of available tools"""
        return {
            "tools": [
                {"name": name, "description": data["description"]}
                for name, data in self.TOOLS.items()
            ]
        }
```

### 10.2 Unit Tests

```python
# tests/mcp/test_mcp_handler.py

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.core.mcp.mcp_handler import MCPProtocolHandler, MCPConfig

@pytest.fixture
def mock_mcp_client():
    client = MagicMock()
    client.connect = AsyncMock()
    client.discover_tools = AsyncMock(return_value=[
        ToolMeta(name="wind.get_stock_data", description="获取行情", parameters={})
    ])
    client.call_tool = AsyncMock(return_value={"success": True, "result": {"data": "test"}})
    return client

@pytest.fixture
def mock_credential_manager():
    manager = MagicMock()
    manager.get_auth = MagicMock(return_value=MagicMock(build_headers=MagicMock(return_value={})))
    return manager

@pytest.mark.asyncio
async def test_mcp_handler_initialize():
    """Test MCP handler initialization"""
    config = MCPConfig(servers=[...])
    handler = await MCPProtocolHandler.create(config, mock_credential_manager)
    
    assert len(handler._clients) > 0
    assert "wind.get_stock_data" in handler._tool_index

@pytest.mark.asyncio
async def test_mcp_handler_execute_success():
    """Test successful tool execution"""
    handler = MCPProtocolHandler(mock_credential_manager)
    handler._clients["wind"] = mock_mcp_client
    handler._tool_index["wind.get_stock_data"] = "wind"
    
    result = await handler.execute("wind.get_stock_data", {"code": "002594"})
    
    assert result["success"] is True

@pytest.mark.asyncio
async def test_mcp_handler_execute_unknown_tool():
    """Test error handling for unknown tool"""
    handler = MCPProtocolHandler(mock_credential_manager)
    
    result = await handler.execute("unknown.tool", {})
    
    assert result["success"] is False
    assert result["error_code"] == "unknown_tool"

@pytest.mark.asyncio
async def test_rate_limiting():
    """Test rate limiting"""
    rate_limiter = MagicMock()
    rate_limiter.acquire = AsyncMock(return_value=False)
    rate_limiter.retry_after = AsyncMock(return_value=30)
    
    client = MCPClient(config, credential_manager, rate_limiter)
    result = await client.call_tool("any.tool", {})
    
    assert result["success"] is False
    assert result["error"] == "rate_limit_exceeded"
```

### 10.3 Integration Tests

```python
# tests/mcp/test_integration.py

@pytest.mark.asyncio
async def test_full_mcp_flow():
    """Test full MCP integration flow"""
    # 1. Start mock server
    mock_server = MockMCPServer()
    
    # 2. Initialize handler
    config = MCPConfig(servers=[
        ServerConfig(name="mock", transport="mock", mock_server=mock_server)
    ])
    handler = await MCPProtocolHandler.create(config)
    
    # 3. Discover tools
    tools = handler.list_available_tools()
    assert len(tools) > 0
    
    # 4. Execute tool
    result = await handler.execute("wind.get_stock_data", {"industry": "新能源汽车"})
    assert result["success"] is True
    
    # 5. Verify data format
    assert "stocks" in result["result"]

@pytest.mark.asyncio
async def test_mcp_to_agent_integration():
    """Test MCP integration with GenericAgent"""
    # Setup agent with MCP handler
    agent = GenericAgent(config={
        "mcp_handler": handler,
        "mcp_tools": ["wind.get_stock_data"]
    })
    
    # Execute MCP action
    result = await agent.execute({
        "action": "mcp",
        "parameters": {
            "tool": "wind.get_stock_data",
            "params": {"industry": "新能源汽车"}
        }
    })
    
    assert result["success"] is True
    assert "mcp_data" in result or "mcp_error" in result
```

### 10.4 Contract Testing

```python
# tests/mcp/test_contract.py

class MCPContractTest:
    """Test MCP protocol compliance"""
    
    @pytest.mark.asyncio
    async def test_tool_discovery_contract(self):
        """Verify tool discovery returns expected schema"""
        tools = await client.discover_tools()
        
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert isinstance(tool["name"], str)
            assert isinstance(tool["description"], str)
    
    @pytest.mark.asyncio
    async def test_tool_call_contract(self):
        """Verify tool call returns expected schema"""
        result = await client.call_tool("wind.get_stock_data", {})
        
        assert "success" in result
        assert isinstance(result["success"], bool)
        
        if result["success"]:
            assert "result" in result
        else:
            assert "error" in result
```

---

## 11. Implementation Plan

### Phase 1: Foundation (Week 1)

| Task | Files | Effort | Priority |
|------|-------|--------|----------|
| CredentialManager with caching | `src/core/mcp/credentials.py` | 4h | P0 |
| MCPClient remote mode (SSE/HTTP) | `src/core/mcp/client.py` | 4h | P0 |
| Auth error handling (401 refresh) | `src/core/mcp/client.py` | 2h | P0 |
| Rate limiting | `src/core/mcp/rate_limiter.py` | 3h | P1 |
| Unit tests for core components | `tests/mcp/` | 3h | P0 |

**Deliverable**: Working MCP client with auth and rate limiting

### Phase 2: MCP Protocol Layer (Week 2)

| Task | Files | Effort | Priority |
|------|-------|--------|----------|
| MCPProtocolHandler | `src/core/agents/mcp_handler.py` | 4h | P0 |
| GenericAgent action="mcp" route | `src/core/agents/generic_agent.py` | 2h | P0 |
| MCP tool discovery | `src/core/mcp/client.py` | 2h | P1 |
| Tool index and metadata | `src/core/agents/mcp_handler.py` | 1h | P1 |
| Integration tests | `tests/mcp/` | 3h | P0 |

**Deliverable**: Working MCP protocol handler integrated with agents

### Phase 3: Intelligent Routing (Week 2-3)

| Task | Files | Effort | Priority |
|------|-------|--------|----------|
| MCPToolMatcher (semantic) | `src/core/decomposition/mcp_matcher.py` | 4h | P1 |
| AgentSpec.mcp_tools | `src/core/dynamic_orchestrator.py` | 1h | P0 |
| AgentCapability.mcp_tools | `src/core/agents/factory.py` | 1h | P0 |
| MCP tool injection in _create_agents() | `src/core/orchestrator/orchestrator.py` | 2h | P0 |
| Fallback mechanism | `src/core/agents/generic_agent.py` | 2h | P1 |

**Deliverable**: Automatic MCP tool routing for research aspects

### Phase 4: Observability & Security (Week 3)

> **Note**: For v1, we recommend a simplified approach—structured logging and health checks only. Prometheus and OpenTelemetry are deferred to v2.

| Task | Files | Effort | Priority |
|------|-------|--------|----------|
| Structured logging | `src/core/mcp/logging.py` | 2h | P0 |
| Health checks | `src/core/mcp/health.py` | 2h | P0 |
| Secure credential storage | `src/core/mcp/security.py` | 3h | P1 |
| Audit logging | `src/core/mcp/credentials.py` | 2h | P1 |
| ~~Metrics collection~~ | ~~`src/core/mcp/metrics.py`~~ | ~~3h~~ | **P2 (v2)** |
| ~~Distributed tracing~~ | ~~`src/core/mcp/tracing.py`~~ | ~~2h~~ | **P2 (v2)** |

**Deliverable**: Basic observability and security (v1 scope reduced from 11h to 7h)

### Phase 5: Testing & Documentation (Week 4)

| Task | Effort | Priority |
|------|--------|----------|
| Mock MCP server | 3h | P0 |
| Integration test suite | 4h | P0 |
| Contract tests | 2h | P1 |
| LSP diagnostics: zero new errors | 1h | P0 |
| API documentation | 3h | P1 |
| Deployment guide | 2h | P2 |
| **Update requirements.txt** | 0.5h | P0 |

**Deliverable**: Fully tested and documented MCP integration

### New Dependencies

Add the following to `requirements.txt`:

```txt
# MCP Integration
aiohttp>=3.9.0           # HTTP client for SSE/HTTP transport
httpx>=0.27.0            # Alternative HTTP client (choose one)
cryptography>=42.0.0     # Credential encryption
keyring>=25.0.0          # OS-level secure storage
structlog>=24.1.0        # Structured logging

# Optional (v2)
# prometheus-client>=0.19.0    # Metrics collection
# opentelemetry-api>=1.22.0    # Distributed tracing
```

---

## Summary of Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| MCP is a protocol layer, not a Skill | Preserves MCP's standardized discovery/invocation; Skill system is for internal capabilities |
| No format conversion on MCP output | Closed-source MCPs cannot be modified; LLM is the natural format adapter |
| Semantic tool matching (primary) | Flexible for new aspects; static fallback for reliability |
| CredentialManager with priority stacking | Supports system-level + user-level + session-level credentials |
| Rate limiting at client level | Prevents cost overruns and respects API quotas |
| Graceful degradation with fallback | Ensures system continues even when external services fail |
| Single config file, multiple MCP servers | Simplifies deployment; JSON/YAML auto-detected |
| MCP data enters pipeline via existing contract | No changes needed to Engine, Aggregator, or Harness |
| Observability built-in | Metrics, tracing, logging for production monitoring |
| Security by design | Encryption, audit logging, permission model |

---

## Appendix A: MCP Protocol Reference

### A.1 Tool Discovery Request

```json
// Request
POST /tools/list
Content-Type: application/json

{}

// Response
{
  "tools": [
    {
      "name": "get_stock_data",
      "description": "获取A股行情数据",
      "parameters": {
        "type": "object",
        "properties": {
          "code": {"type": "string", "description": "股票代码"},
          "start_date": {"type": "string", "format": "date"},
          "end_date": {"type": "string", "format": "date"}
        },
        "required": ["code"]
      }
    }
  ]
}
```

### A.2 Tool Call Request

```json
// Request
POST /tools/call
Content-Type: application/json
Authorization: Bearer <token>

{
  "tool": "get_stock_data",
  "params": {
    "code": "002594",
    "start_date": "2024-01-01",
    "end_date": "2024-12-31"
  }
}

// Response
{
  "success": true,
  "result": {
    "code": "002594",
    "name": "比亚迪",
    "data": [
      {"date": "2024-01-02", "close": 245.5, "volume": 1234567},
      ...
    ]
  }
}
```

### A.3 Error Response

```json
{
  "success": false,
  "error": "Invalid stock code",
  "error_code": "invalid_parameter",
  "details": {
    "parameter": "code",
    "expected": "6-digit stock code",
    "received": "abc"
  }
}
```

---

## Appendix B: Checklist for Production Readiness

- [ ] All Phase 1-5 tasks completed
- [ ] Unit test coverage ≥ 80%
- [ ] Integration tests passing
- [ ] LSP diagnostics: 0 errors
- [ ] Security audit completed
- [ ] Performance benchmarks documented
- [ ] Runbook for common issues
- [ ] Monitoring dashboards configured
- [ ] Alert rules for rate limits, errors
- [ ] Credential rotation schedule set
- [ ] Backup/failover tested
