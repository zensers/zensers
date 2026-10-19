---
name: market_analysis
description: "Professional market analysis: SWOT/PEST/Porter's Five Forces + data computation"
version: "1.0"
categories:
  - analysis
priority: llm
keywords:
  - market analysis
  - competitive landscape
  - market share
  - market size
  - 行业分析
  - 竞争格局
  - 市场份额
  - 市场规模
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
  - Competitive Landscape
  - Industry Chain
  - Strategic Intent
  - 战略意图
  - 战略意图推断
  - Company Analysis
---
