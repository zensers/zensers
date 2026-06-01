# Zensers System Architecture Design

> Open-source automated market research system  
> Version: v1.3  
> Date: 2026-04-05  
> Dependency Documents: GLOSSARY.md (Glossary), [ARCHITECTURE_CLOUD.md](./ARCHITECTURE_CLOUD.md) (Cloud Deployment Architecture)

---

## Revision Record

| Version | Date | Revisions | Author |
|---------|------|-----------|--------|
| v1.3 | 2026-04-05 | Added module dependency relationships, interface contracts, unified communication layer, dependency injection container, interface version management | AI Engineer |
| v1.2 | 2026-04-05 | Added constraint engineering layer (Harness Engineering) | AI Engineer |
| v1.1 | 2026-04-02 | Added report pipeline, user survey, simulated respondent reserved interfaces | AI Engineer |
| v1.0 | 2026-04-01 | Initial version | AI Engineer |

---

## 1. System Overview

### 1.1 Project Positioning

**Zensers** is an open-source automated market research system that completes the full-process research task from requirement analysis to report generation through multi-Agent collaboration.

### 1.2 Core Features

- **Multi-Agent Collaboration**: Master Agent dynamically generates specialized Agents to collaboratively complete complex research
- **Open Source Ecosystem Reuse**: Integrates LangChain, LlamaIndex and other open-source Skill ecosystems
- **Three-Layer Memory Architecture**: Core + Session + Knowledge Base, progressive storage
- **Dream Mode**: Background knowledge compression and promotion mechanism
- **Constraint Engineering**: Source whitelist, fact tracing, cross-validation
- **MCP Protocol Support**: Standardized integration with external tools
- **Dual-Track Learning**: Tool layer evolution + Knowledge layer accumulation
- **Multi-Format Output**: Word, PPT, PDF with McKinsey-style professional formatting

### 1.3 System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 7: Application Layer                                   │
│   CLI / Web API                                              │
├─────────────────────────────────────────────────────────────┤
│ Layer 6: Orchestration Layer                                 │
│   ResearchOrchestrator / AgentFactory                       │
├─────────────────────────────────────────────────────────────┤
│ Layer 5: Agent Layer                                        │
│   FixedAgents / DynamicAgents / Session Management          │
├─────────────────────────────────────────────────────────────┤
│ Layer 4: Capability Layer                                   │
│   Skills / MCP Tools / Converters                           │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: Memory Layer                                       │
│   CoreMemory / SessionMemory / KnowledgeBank                │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: Communication Layer                                │
│   MessageBus / SharedMemory / EventBus                      │
├─────────────────────────────────────────────────────────────┤
│ Layer 1: Storage Layer                                      │
│   TaskStorage / WAL / ResearchResultStore                   │
├─────────────────────────────────────────────────────────────┤
│ Layer 0: Constraint Layer                                   │
│   SourceWhitelist / FactTracer / CrossValidator             │
└─────────────────────────────────────────────────────────────┘
```

[Content continues with detailed descriptions of all seven layers]
