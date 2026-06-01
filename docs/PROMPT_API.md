# Prompt Management API Documentation

## Overview

The Prompt Management API provides RESTful endpoints for managing prompts, agent profiles, and cache operations. This API is part of the prompt externalization refactoring.

## Base URL

```
/api/prompts
```

## Authentication

Currently, the API uses no authentication. In production, implement appropriate authentication mechanisms.

---

## Endpoints

### 1. List Categories

List all available prompt categories.

**Endpoint:** `GET /api/prompts/categories`

**Response:**
```json
{
  "categories": ["_shared", "agents", "phases", "tasks"]
}
```

**Status Codes:**
- `200 OK` - Success

---

### 2. List Prompts in Category

List all prompts within a specific category.

**Endpoint:** `GET /api/prompts/{category}`

**Parameters:**
- `category` (path): Category name (`_shared`, `agents`, `phases`, `tasks`)

**Response:**
```json
{
  "category": "tasks",
  "count": 10,
  "prompts": [
    {
      "name": "basic_research",
      "path": "tasks/basic_research.md",
      "has_frontmatter": true,
      "size_bytes": 1234
    }
  ]
}
```

**Status Codes:**
- `200 OK` - Success
- `404 Not Found` - Category not found (returns empty list)

---

### 3. Get Prompt Content

Get the raw content of a specific prompt file.

**Endpoint:** `GET /api/prompts/{category}/{name}`

**Parameters:**
- `category` (path): Category name
- `name` (path): Prompt name (without `.md` extension)

**Response:**
```json
{
  "category": "tasks",
  "name": "basic_research",
  "content": "---\nname: Basic Research\n---\n# Task Description\n...",
  "length": 1234
}
```

**Status Codes:**
- `200 OK` - Success
- `404 Not Found` - Prompt not found

---

### 4. Render Prompt

Render a prompt template with variable substitution.

**Endpoint:** `POST /api/prompts/render`

**Request Body:**
```json
{
  "category": "tasks",
  "name": "research_with_data",
  "variables": {
    "aspect": "Market Size",
    "data_points": ["CAGR: 15%", "Market Value: $10B"],
    "sources": ["Source 1", "Source 2"]
  },
  "strip_frontmatter": true
}
```

**Response:**
```json
{
  "success": true,
  "category": "tasks",
  "name": "research_with_data",
  "rendered": "# Research Task\n\nAnalyze Market Size...",
  "length": 456
}
```

**Status Codes:**
- `200 OK` - Success
- `404 Not Found` - Prompt not found
- `400 Bad Request` - Render error

---

### 5. List Agent Profiles

List all available agent profiles.

**Endpoint:** `GET /api/agents/profiles`

**Response:**
```json
{
  "count": 18,
  "profiles": [
    "data_collection",
    "market_size",
    "competition_analysis",
    "industry_chain",
    "policy_analysis",
    "company_research",
    "investment_analysis",
    "risk_assessment",
    "report_writing",
    "editor",
    "summarizer",
    "conclusion",
    "decomposer",
    "clarifier",
    "planner",
    "research_director",
    "research_follower",
    "industry_overview"
  ]
}
```

**Status Codes:**
- `200 OK` - Success

---

### 6. Get Agent Profile

Get detailed information about a specific agent profile.

**Endpoint:** `GET /api/agents/profiles/{name}`

**Parameters:**
- `name` (path): Agent profile name

**Response:**
```json
{
  "name": "market_size",
  "description": "Expert in market size estimation and forecasting",
  "role": "Senior Market Research Analyst specializing in market sizing",
  "goal": "Deliver accurate, well-sourced market size estimates with clear methodology",
  "backstory": "You are a senior analyst at a top consulting firm...",
  "required_skills": ["web_search", "data_analysis"],
  "optional_skills": ["chart_generation"],
  "config": {
    "temperature": 0.7,
    "max_tokens": 4000
  }
}
```

**Status Codes:**
- `200 OK` - Success
- `404 Not Found` - Agent profile not found

---

### 7. Get Agent Full Prompt

Get the complete system prompt for an agent (combines role, goal, backstory, and body content).

**Endpoint:** `GET /api/agents/profiles/{name}/prompt`

**Parameters:**
- `name` (path): Agent profile name

**Response:**
```json
{
  "name": "market_size",
  "full_prompt": "## Role\nSenior Market Research Analyst specializing in market sizing\n\n## Goal\nDeliver accurate, well-sourced market size estimates...\n\n## Backstory\nYou are a senior analyst at a top consulting firm...",
  "length": 2048
}
```

**Status Codes:**
- `200 OK` - Success
- `404 Not Found` - Agent profile not found

---

### 8. Get Skills for Aspect

Get the required skills for a research aspect.

**Endpoint:** `GET /api/agents/skills/{aspect}`

**Parameters:**
- `aspect` (path): Research aspect name (e.g., "Market Size", "Competitive Landscape")

**Response:**
```json
{
  "aspect": "Market Size",
  "skills": ["web_search", "data_analysis"]
}
```

**Status Codes:**
- `200 OK` - Success

---

### 9. Invalidate Cache

Clear the prompt cache (useful during development).

**Endpoint:** `POST /api/prompts/cache/invalidate`

**Query Parameters:**
- `key` (optional): Specific cache key to invalidate. If omitted, clears all cache.

**Response:**
```json
{
  "success": true,
  "message": "Cache invalidated: all"
}
```

**Status Codes:**
- `200 OK` - Success

---

### 10. Get Cache Statistics

Get information about the current cache state.

**Endpoint:** `GET /api/prompts/cache/stats`

**Response:**
```json
{
  "cache_size": 28,
  "cached_keys": [
    "agents/market_size",
    "agents/competition_analysis",
    "tasks/basic_research",
    "phases/decomposition"
  ]
}
```

**Status Codes:**
- `200 OK` - Success

---

## Error Responses

All error responses follow this format:

```json
{
  "detail": "Error message describing the issue"
}
```

Common error codes:
- `404 Not Found` - Resource not found
- `400 Bad Request` - Invalid request parameters
- `500 Internal Server Error` - Server-side error

---

## Usage Examples

### Python

```python
import httpx

# List all categories
response = httpx.get("http://localhost:8000/api/prompts/categories")
categories = response.json()["categories"]

# Get a prompt
response = httpx.get("http://localhost:8000/api/prompts/tasks/basic_research")
content = response.json()["content"]

# Render a prompt with variables
response = httpx.post(
    "http://localhost:8000/api/prompts/render",
    json={
        "category": "tasks",
        "name": "research_with_data",
        "variables": {
            "aspect": "Market Size",
            "data_points": ["CAGR: 15%"]
        }
    }
)
rendered = response.json()["rendered"]
```

### JavaScript/TypeScript

```typescript
// List all categories
const response = await fetch('/api/prompts/categories');
const { categories } = await response.json();

// Get a prompt
const response = await fetch('/api/prompts/tasks/basic_research');
const { content } = await response.json();

// Render a prompt with variables
const response = await fetch('/api/prompts/render', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    category: 'tasks',
    name: 'research_with_data',
    variables: { aspect: 'Market Size' }
  })
});
const { rendered } = await response.json();
```

### cURL

```bash
# List categories
curl http://localhost:8000/api/prompts/categories

# Get a prompt
curl http://localhost:8000/api/prompts/tasks/basic_research

# Render a prompt
curl -X POST http://localhost:8000/api/prompts/render \
  -H "Content-Type: application/json" \
  -d '{"category":"tasks","name":"research_with_data","variables":{"aspect":"Market Size"}}'

# List agent profiles
curl http://localhost:8000/api/agents/profiles

# Get agent profile
curl http://localhost:8000/api/agents/profiles/market_size
```

---

## Direct Python Usage (Without HTTP)

You can also use the `PromptAPI` class directly in Python:

```python
from src.api.prompt_api import PromptAPI, create_prompt_api

# Create instance
api = create_prompt_api(base_dir="prompts")

# List categories
categories = api.list_categories()

# Get prompt content
content = api.get_prompt("tasks", "basic_research")

# Render with variables
result = api.render_prompt(
    category="tasks",
    name="research_with_data",
    variables={"aspect": "Market Size", "data_points": ["CAGR: 15%"]}
)

# Get agent profile
profile = api.get_agent_profile("market_size")

# Get full system prompt for agent
full_prompt = api.get_agent_full_prompt("market_size")

# Cache management
api.invalidate_cache()  # Clear all
api.invalidate_cache("agents/market_size")  # Clear specific

# Get cache stats
stats = api.get_cache_stats()
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      PromptAPI                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  PromptManager (Singleton)           │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │   │
│  │  │   Cache     │  │   Parser    │  │  Renderer   │  │   │
│  │  │  (TTL 1hr)  │  │ (YAML+MD)   │  │ (Template)  │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    prompts/ directory                       │
│  ├── _shared/                                               │
│  │   └── style_guide.md                                     │
│  ├── agents/                                                │
│  │   ├── market_size.md                                     │
│  │   ├── competition_analysis.md                            │
│  │   └── ... (18 profiles)                                  │
│  ├── tasks/                                                 │
│  │   ├── basic_research.md                                  │
│  │   ├── research_with_data.md                              │
│  │   └── ... (10 task prompts)                              │
│  └── phases/                                                │
│      ├── decomposition.md                                   │
│      └── ... (5 phase prompts)                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Rate Limiting

Currently, no rate limiting is implemented. In production, consider adding:
- Rate limiting per IP/user
- Request throttling for expensive operations

---

## Security Considerations

1. **Path Traversal Prevention**: The API validates paths to prevent directory traversal attacks
2. **Read-Only by Default**: No file modification endpoints
3. **Cache Isolation**: Each cache entry is isolated by key
4. **Input Validation**: All inputs are validated before processing

---

## Changelog

### v1.0.0 (2024-01-XX)
- Initial release
- Prompt listing and retrieval
- Agent profile management
- Variable substitution
- Cache management
