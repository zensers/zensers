---
name: lc_arxiv
description: "ArXiv 学术论文搜索"
version: "1.0"
categories:
  - data-collection
  - academic
priority: web_search
keywords:
  - arxiv
  - academic
  - paper
  - 论文
  - 学术
capabilities:
  - arxiv_search
action_rules:
  - pattern: ".*"
    actions: [arxiv_search]
action_param_map:
  arxiv_search: {query: query}
is_intrinsic: false
skill_type: langchain
---
