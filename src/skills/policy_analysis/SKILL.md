---
name: policy_analysis
description: "Policy analysis: policy impact assessment/transmission channels/winners-losers/scenario analysis"
version: "1.0"
categories:
  - analysis
priority: llm
keywords:
  - policy analysis
  - regulation analysis
  - compliance
  - government policy
  - regulatory impact
  - 政策分析
  - 监管分析
  - 合规分析
aliases: []
capabilities:
  - analyze
action_rules:
  - pattern: ".*"
    actions: [analyze]
action_param_map:
  analyze: {}
supports_topic_fallback: false
is_intrinsic: false
skill_type: standard
aspect_coverage:
  - Policy Environment
---
