---
name: file_skill
description: "File read/write operations, supporting text and JSON formats. By default restricted to data/, output/, cache/, temp/ directories."
version: "1.0"
categories:
  - file-operation
priority: llm
keywords:
  - 文件
  - file
  - 读写
  - 文件操作
aliases: []
capabilities:
  - read
  - write
  - list
  - delete
action_rules:
  - pattern: ".*"
    actions: [read]
action_param_map:
  read: {}
supports_topic_fallback: false
is_intrinsic: false
skill_type: standard
aspect_coverage: []
---
