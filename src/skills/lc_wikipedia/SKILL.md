---
name: lc_wikipedia
description: "Wikipedia 百科搜索"
version: "1.0"
categories:
  - data-collection
  - reference
priority: web_search
keywords:
  - wikipedia
  - encyclopedia
  - 百科
  - 维基
capabilities:
  - wiki_search
  - wikipedia_search
action_rules:
  - pattern: ".*"
    actions: [wiki_search]
action_param_map:
  wiki_search: {query: query}
  wikipedia_search: {query: query}
is_intrinsic: false
skill_type: langchain
---
