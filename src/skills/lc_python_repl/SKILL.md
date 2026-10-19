---
name: lc_python_repl
description: "Python REPL 代码执行环境"
version: "1.0"
categories:
  - computation
  - data-analysis
priority: llm
keywords:
  - python
  - repl
  - code
  - 代码
  - 计算
capabilities:
  - python_repl
  - data_analysis
action_rules:
  - pattern: ".*"
    actions: [python_repl]
action_param_map:
  python_repl: {}
  data_analysis: {}
is_intrinsic: false
skill_type: langchain
---
