# Zensers Human-in-the-Loop Mechanism Design (HITL)

> Humans are the ultimate quality gatekeepers; system assists decisions but does not replace responsibility  
> Version: v1.0  
> Date: 2026-04-05  
> Related Documents: ARCHITECTURE.md, QUALITY_ASSURANCE.md, HARNESS_ENGINEERING.md

---

## 1. Design Principles

### 1.1 Core Principles

| Principle | Description |
|-----------|-------------|
| **Humans are final decision-makers** | System provides suggestions, humans have veto power |
| **Hierarchical authorization** | Different risk levels require different human confirmation levels |
| **Non-blocking but visible** | Low-risk tasks auto-execute but are fully auditable |
| **Traceable** | Every decision is recorded with clear responsibility |
| **Configurable** | Users can adjust intervention level and trigger conditions |

### 1.2 Intervention Trigger Conditions

```
Scenarios requiring human confirmation:
├── Report release (100% required)
├── Critical data citation (first use of new data source)
├── Research scope change (beyond original requirements)
├── Low confidence content (system marked as "medium" or "low")
├── Anomaly detection results (data contradictions, logic conflicts)
├── Cost overrun warning (estimated cost exceeds budget threshold)
└── User-defined rules

Optional intervention scenarios:
├── Agent generation strategy selection (multiple options)
├── Data source selection (multiple candidates)
├── Report style adjustment (template selection)
└── Task priority adjustment
```
