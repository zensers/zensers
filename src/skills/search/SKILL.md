---
name: search_skill
description: "多搜索引擎集成 (Baidu/DuckDuckGo/Google/Bing 等6引擎)"
version: "1.0"
categories:
  - data-collection
  - web-search
priority: web_search
keywords:
  - 搜索
  - 搜索引擎
  - web search
  - search
  - 百度
  - 必应
  - 谷歌
aliases:
  - web_search
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
