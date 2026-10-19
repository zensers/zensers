---
name: xueqiu
description: "雪球实时行情/热门股票/热帖/K线 (A股/港股/美股)"
version: "1.0"
categories:
  - financial-analysis
  - research
  - data-collection
priority: structured_db
keywords:
  - 雪球
  - 行情
  - 港股
  - 美股
  - 热门股
  - 换手率
  - 实时行情
  - K线
  - xueqiu
  - stock quote
  - real-time quote
  - hot stock
  - 热门股票
  - 人气股
  - 关注榜
  - 热帖
  - kline
  - 港股行情
  - 美股行情
  - A股行情
  - 股票搜索
  - turnover rate
  - pe_ttm
  - 市盈率
  - market capital
  - 市值
  - 涨跌
  - 大盘
aliases:
  - xueqiu_stock
  - stock_quote
capabilities:
  - quote
  - kline
  - hot_stocks
  - search
  - search_and_quote
  - hot_posts
  - check
data_types:
  zh:
    - 股价
    - 估值
    - 换手率
    - 热门股
    - 实时行情
data_source_keywords:
  - 财务
  - 估值
  - 公司
  - 盈利
  - 营收
  - 市值
  - 市场规模
  - 利润
  - roe
  - pe
  - pb
  - 增长
  - 投资
  - 行情
  - 热门
  - 港股
  - 美股
  - 趋势
  - 竞争
  - financial
  - valuation
  - company
  - market_size
  - competitive
action_rules:
  - pattern: "^(SH|SZ|BJ)?\\d{6}$"
    aspect_keywords: [竞争, 热门, 人气, 排行, competitive, hot]
    actions: [quote, kline, hot_stocks]
  - pattern: "^(SH|SZ|BJ)?\\d{6}$"
    actions: [quote, kline]
  - pattern: ".*"
    actions: [search_and_quote]
action_param_map:
  quote: {symbol: symbol}
  kline: {symbol: symbol}
  hot_stocks: {}
  search: {query: query}
  search_and_quote: {query: symbol}
  hot_posts: {}
  check: {}
supports_topic_fallback: true
topic_fallback_pattern: "[\\u4e00-\\u9fff]+"
is_intrinsic: false
skill_type: standard
aspect_coverage:
  - Financial Analysis
  - 财务分析
  - Valuation
  - 估值分析
  - Company Research
  - 公司研究
  - Investment Analysis
  - 投资分析
  - Competitive Landscape
  - 竞争格局
  - Industry Research
  - 行业研究
---

# Xueqiu Skill

## When to use
用户需要实时股票行情、港股/美股数据、热门股票排名时使用。
当 EntityResolver 无法解析港股/美股代码时，xueqiu 可通过 search_and_quote 用中文名搜索。

## Actions

| Action | 描述 | 必需参数 | 可选参数 |
|--------|------|----------|----------|
| quote | 获取股票实时报价 | symbol | - |
| kline | 获取K线历史数据 | symbol | period, count |
| hot_stocks | 获取热门股票排名 | - | limit |
| search | 搜索股票 | query | limit |
| search_and_quote | 搜索并获取报价 | query | - |
| hot_posts | 获取热门帖子 | - | limit |
| check | 检查API连通性 | - | - |

## Notes
- 未登录时 quote/hot_stocks/search 自动通过 Screener 公共 API 降级
- kline 需要登录 Cookie，Screener 无法提供
- symbol 格式: A股=SH600519/SZ002594, 港股=00700, 美股=AAPL
