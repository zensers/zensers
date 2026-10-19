---
name: http_skill
description: "HTTP request operations, supports GET/POST with timeout, SSRF protection and error handling"
version: "1.0"
categories:
  - network
priority: llm
keywords:
  - HTTP
  - 请求
  - request
  - API
  - 网络请求
aliases: []
capabilities:
  - get
  - post
  - put
  - delete
action_rules:
  - pattern: ".*"
    actions: [get]
action_param_map:
  get: {}
supports_topic_fallback: false
is_intrinsic: false
skill_type: standard
aspect_coverage: []
---
