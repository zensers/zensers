---
name: docx_skill
description: "Word document generation, supports headings/paragraphs/tables, generates professional format reports"
version: "1.0"
categories:
  - document-generation
priority: llm
keywords:
  - Word
  - 文档
  - docx
  - 报告生成
aliases: []
capabilities:
  - generate_docx
action_rules:
  - pattern: ".*"
    actions: [generate_docx]
action_param_map:
  generate_docx: {}
supports_topic_fallback: false
is_intrinsic: false
skill_type: standard
aspect_coverage: []
---
