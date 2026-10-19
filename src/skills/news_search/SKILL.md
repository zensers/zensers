---
name: news_search
description: "新闻搜索 (DuckDuckGo News)"
version: "1.0"
categories:
  - data-collection
  - web-search
priority: web_search
keywords:
  - 新闻
  - 新闻搜索
  - news
  - news search
capabilities:
  - search
action_rules:
  - pattern: ".*"
    actions: [search]
action_param_map:
  search: {query: query}
supports_topic_fallback: false
is_intrinsic: false
skill_type: standard
aspect_coverage: []
---
