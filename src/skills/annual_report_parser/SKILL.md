---
name: annual_report_parser
description: "Parse PDF annual reports from global exchanges. Extracts TOC, chapters, financial highlights, and key narrative sections."
version: "1.0"
categories:
  - data-collection
  - document-processing
priority: structured_db
keywords:
  - 年报
  - annual report
  - PDF解析
  - 财报
  - 10-K
aliases: []
capabilities:
  - parse
  - analyze
action_rules:
  - pattern: ".*"
    actions: [parse]
action_param_map:
  parse: {query: query}
  analyze: {query: query}
supports_topic_fallback: false
is_intrinsic: false
skill_type: standard
data_source_keywords:
  - 年报
  - annual report
  - 10-K
aspect_coverage: []
---
