# Zensers Configuration Guide

## Configuration Priority

Configuration values are loaded in the following priority order (highest to lowest):

1. **`.env`** - Environment variables (secrets, API keys)
2. **`config/settings.yaml`** - User settings (runtime configuration)
3. **`config/system.yaml`** - System defaults
4. **Code defaults** - Hardcoded fallback values

---

## Environment Variables (`.env`)

Reference: `.env.example`

| Variable | Description | Required |
|----------|-------------|----------|
| `LLM_API_KEY` | LLM API key (OpenAI, etc.) | Yes (production) |
| `LLM_BASE_URL` | LLM API endpoint | No |
| `LLM_MODEL` | Primary model name | No |
| `LLM_CHEAP_MODEL` | Cost-effective model for simple tasks | No |
| `DB_PASSWORD` | PostgreSQL password | Yes (if Postgres enabled) |
| `REDIS_PASSWORD` | Redis password | Yes (if Redis enabled) |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated) | Yes (production) |
| `ZENSERS_API_URL` | API server URL for CLI | No |

### Knowledge Auto-Import (Optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `DREAM_SOURCE_DIRS` | Directories to scan (comma-separated) | - |
| `DREAM_SCAN_INTERVAL` | Scan interval in seconds | 300 |
| `DREAM_AUTO_IMPORT` | Enable auto-import | false |
| `DREAM_STORE_TO_BANK` | Store to knowledge bank | true |
| `DREAM_IMPORT_MAX_WORKERS` | Max parallel imports | 2 |

---

## Settings File (`config/settings.yaml`)

Reference: `config/settings.example.yaml`

### LLM Settings

```yaml
llm:
  embedding_model: "text-embedding-3-small"
  temperature: 0.7
  max_tokens: 4096
  top_p: 0.9
  cost_limit_per_report: 5.0
```

### Database Settings

```yaml
database:
  postgres:
    enabled: false          # Set true for production
    host: "localhost"
    port: 5432
    name: "zensers"
    pool_size: 10

  redis:
    enabled: false          # Set true for caching
    host: "localhost"
    port: 6379
    default_ttl: 3600

  sqlite:
    enabled: true           # Default for development
    path: "data/zensers.db"
```

### Agent Settings

```yaml
agents:
  orchestrator:
    max_retries: 3

  fixed:
    requirement_analysis_timeout: 120
    data_collection_timeout: 300
    report_generation_timeout: 180
    quality_check_timeout: 60

  dynamic:
    max_lifetime: 3600
    max_count: 20
```

### Search Settings

```yaml
search:
  max_results_per_query: 20
  max_queries_per_aspect: 10
  max_total_searches: 100
  min_quality_score: 50.0
  min_sources: 8
  region: "cn-cn"
```

### MCP Settings

```yaml
mcp:
  max_concurrent_servers: 5
  max_concurrent_tools: 10
  default_timeout:
    connect: 30
    request: 60
  cache:
    enabled: true
    ttl: 600
```

---

## System Configuration (`config/system.yaml`)

System-level defaults and development settings:

- **Database defaults** (overridden by `settings.yaml`)
- **Logging configuration** (level, format, rotation)
- **Path configuration** (data, output, logs, temp directories)
- **Concurrency limits** (max concurrent tasks, timeouts)
- **Quality thresholds** (data collection, analysis, report scores)
- **Retry strategies** per stage
- **Data providers** (akshare, public APIs)
- **Platform integrations** (DingTalk, WeCom, Email)

---

## Agent Configuration (`config/agents.yaml`)

Detailed configuration for each fixed agent:

### Requirement Analysis Agent
- LLM: `gpt-4o`, temperature: `0.3`
- Capabilities: Industry identification, topic extraction, dimensional analysis
- Industry templates: New Energy, Semiconductors, Healthcare

### Data Collection Agent
- LLM: `gpt-4o`, temperature: `0.3`
- Data sources: Public (akshare, tushare), Web search (tavily, serper)
- Timeouts: search 30s, API 60s, total 600s

### Report Generation Agent
- LLM: `gpt-4o`, temperature: `0.5`, max_tokens: `8000`
- Templates: Market research, Investment, Competitor analysis
- Output formats: markdown, html, docx

### Layout Design Agent
- Supported formats: docx, pptx, pdf, html
- Libraries: python-docx, python-pptx, reportlab

### Quality Check Agent
- LLM: `gpt-4o`, temperature: `0.2`
- Check items: Data accuracy (0.3), Completeness (0.25), Logic (0.2), Format (0.15), Language (0.1)
- Pass threshold: 0.7

### Global Timeouts & Retries

```yaml
timeouts:
  requirement_analysis: 300
  data_collection: 600
  report_generation: 1800
  layout_design: 300
  quality_check: 300

retries:
  max_attempts: 3
  initial_delay: 1.0
  backoff_multiplier: 2.0
```

---

## Quick Start

1. Copy example files:
   ```bash
   cp .env.example .env
   cp config/settings.example.yaml config/settings.yaml
   ```

2. Edit `.env` with your API keys

3. Edit `config/settings.yaml` for runtime configuration

4. (Optional) Modify `config/agents.yaml` for agent-specific tuning
