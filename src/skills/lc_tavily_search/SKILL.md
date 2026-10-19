---
name: lc_tavily_search
description: "Tavily 实时网络搜索"
version: "1.0"
categories:
  - data-collection
  - web-search
priority: web_search
keywords:
  - tavily
  - web search
  - search
  - 搜索
capabilities:
  - tavily_search
action_rules:
  - pattern: ".*"
    actions: [tavily_search]
action_param_map:
  tavily_search: {query: query}
is_intrinsic: false
skill_type: langchain
---
