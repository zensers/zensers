---
name: stock_data
description: "A股上市公司财务数据 (akshare 实时数据): 财务报表/股价/公司信息"
version: "1.0"
categories:
  - financial-analysis
  - data-collection
  - research
priority: structured_db
keywords:
  - 股票数据
  - 财务数据
  - akshare
  - 利润表
  - 资产负债表
  - 现金流量表
  - stock data
  - financial data
aliases: []
capabilities:
  - company_info
  - financials
  - key_metrics
  - price_history
  - industry_comparison
action_rules:
  - pattern: ".*"
    aspect_keywords: [盈利, 利润, 营收, 收入, 研发, 技术, 创新, 偿债, 现金流, 运营效率, financial]
    actions: [financials]
  - pattern: ".*"
    aspect_keywords: [估值, 价值, pe, pb, 回报, roe, roa, roic, 投资价值, valuation]
    actions: [key_metrics, financials]
  - pattern: ".*"
    aspect_keywords: [杠杆, 负债, 资本结构, 稳健, leverage]
    actions: [financials]
  - pattern: ".*"
    aspect_keywords: [对比, 竞争, industry]
    actions: [industry_comparison]
  - pattern: ".*"
    aspect_keywords: [增长, 增速, 发展, 成长性, growth]
    actions: [financials, key_metrics]
  - pattern: ".*"
    aspect_keywords: [销售, 渠道, 营收分析, sales]
    actions: [financials]
  - pattern: ".*"
    aspect_keywords: [市场份额, 市占率, market share]
    actions: [industry_comparison]
  - pattern: ".*"
    aspect_keywords: [公司, 企业, company]
    actions: [company_info]
  - pattern: ".*"
    aspect_keywords: [股价, 行情, 走势, 市值变动, price, market_cap]
    actions: [price_history]
  - pattern: ".*"
    actions: [company_info, financials]
action_param_map:
  company_info: {symbol: symbol}
  financials: {symbol: symbol}
  key_metrics: {symbol: symbol}
  price_history: {symbol: symbol}
  industry_comparison: {symbol: symbol}
supports_topic_fallback: false
is_intrinsic: false
skill_type: standard
data_types:
  zh:
    - 营收
    - 净利润
    - 毛利率
    - 净利率
    - ROE
    - ROA
    - ROIC
    - 资产负债率
    - 流动比率
    - 速动比率
    - 现金流
    - 研发费用
    - 销量
    - 产量
    - 市场份额
    - PE
    - PB
    - 利润表
    - 资产负债表
    - 现金流量表
data_source_keywords:
  - 财务
  - 估值
  - 公司
  - 盈利
  - 营收
  - 市值
  - 市场规模
  - 利润
  - 资产负债
  - roe
  - pe
  - pb
  - 增长
  - 投资
  - financial
  - valuation
  - company
  - market_size
aspect_coverage:
  - Financial Analysis
  - 财务分析
  - Valuation Analysis
  - 估值分析
  - Company Analysis
  - 公司分析
  - Investment Advice
  - 投资建议
  - Growth Analysis
  - 增长分析
  - Sales Analysis
  - 销售分析
---
