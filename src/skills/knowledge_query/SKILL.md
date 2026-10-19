---
name: knowledge_query
description: "Query existing knowledge before analysis. Provides entity references, historical patterns, and analytical frameworks."
version: "1.0"
categories:
  - knowledge
  - research
priority: llm
keywords:
  - 知识查询
  - 知识库
  - knowledge
aliases: []
capabilities:
  - enrich
  - record_observation
  - query
action_rules:
  - pattern: ".*"
    actions: [enrich]
action_param_map:
  enrich: {topic: query}
  record_observation: {}
  query: {query: query}
supports_topic_fallback: false
is_intrinsic: false
skill_type: standard
aspect_coverage: []
---
