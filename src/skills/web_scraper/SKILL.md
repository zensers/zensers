---
name: web_scraper
description: "Extract content from a specific web page URL. Use this tool when the user provides a URL or link. NOT for: searching the web (use search_skill or news_search). Supports markdown/text extraction, auto-filters ads and navigation."
version: "1.0"
categories:
  - data-collection
  - web-search
priority: web_search
keywords:
  - 爬虫
  - 抓取
  - scraper
  - web scraping
  - 网页抓取
aliases: []
capabilities:
  - scrape
action_rules:
  - pattern: ".*"
    actions: [scrape]
action_param_map:
  scrape: {}
supports_topic_fallback: false
is_intrinsic: false
skill_type: standard
aspect_coverage: []
---
