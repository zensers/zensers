# -*- coding: utf-8 -*-
"""
akshare real data e2e test (HTTP fallback)
Usage: D:\conda\python.exe scripts/test_akshare_real_data.py [--symbol 600519]

This script patches requests to use HTTP instead of HTTPS for East Money APIs,
since HTTPS connections are blocked on this machine.
"""
import sys
import os
import json
import asyncio
import traceback
import datetime
import time

os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SYMBOL = "600519"
RETRIES = 3
DELAY = 3


def patch_requests_for_http():
    import requests
    _orig_get = requests.get
    _orig_post = requests.post

    def _http_fallback_get(url, **kwargs):
        if "eastmoney.com" in url and url.startswith("https://"):
            http_url = url.replace("https://", "http://", 1)
            try:
                return _orig_get(http_url, **kwargs)
            except Exception:
                pass
        return _orig_get(url, **kwargs)

    def _http_fallback_post(url, **kwargs):
        if "eastmoney.com" in url and url.startswith("https://"):
            http_url = url.replace("https://", "http://", 1)
            try:
                return _orig_post(http_url, **kwargs)
            except Exception:
                pass
        return _orig_post(url, **kwargs)

    requests.get = _http_fallback_get
    requests.post = _http_fallback_post

    _orig_session_get = requests.Session.get
    _orig_session_post = requests.Session.post

    def _session_http_get(self, url, **kwargs):
        if "eastmoney.com" in url and url.startswith("https://"):
            http_url = url.replace("https://", "http://", 1)
            try:
                return _orig_session_get(self, http_url, **kwargs)
            except Exception:
                pass
        return _orig_session_get(self, url, **kwargs)

    def _session_http_post(self, url, **kwargs):
        if "eastmoney.com" in url and url.startswith("https://"):
            http_url = url.replace("https://", "http://", 1)
            try:
                return _orig_session_post(self, http_url, **kwargs)
            except Exception:
                pass
        return _orig_session_post(self, url, **kwargs)

    requests.Session.get = _session_http_get
    requests.Session.post = _session_http_post
    print("  [patch] requests.get/post + Session.get/post patched: HTTPS->HTTP for eastmoney.com")


def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def subsection(title):
    print(f"\n--- {title} ---")


def print_json(data, max_items=3):
    if isinstance(data, list):
        print(f"  type: list, len: {len(data)}")
        for i, item in enumerate(data[:max_items]):
            s = json.dumps(item, ensure_ascii=False, indent=4)[:500]
            print(f"  [{i}] {s}")
        if len(data) > max_items:
            print(f"  ... total {len(data)} items")
    elif isinstance(data, dict):
        print(f"  type: dict, keys: {list(data.keys())[:10]}")
        for k, v in list(data.items())[:5]:
            if isinstance(v, (list, dict)):
                val_str = f"{type(v).__name__}(len={len(v)})"
            else:
                val_str = str(v)[:200]
            print(f"  {k}: {val_str}")
    else:
        print(f"  type: {type(data).__name__}, value: {str(data)[:300]}")


def call_with_retry(fn, *args, **kwargs):
    for attempt in range(RETRIES):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            print(f"  [attempt {attempt+1}/{RETRIES}] {type(e).__name__}: {e}")
            if attempt < RETRIES - 1:
                time.sleep(DELAY * (attempt + 1))
            else:
                raise


async def test_company_info(ak, symbol, agent):
    section("1. company_info")
    try:
        df = call_with_retry(ak.stock_individual_info_em, symbol=symbol)
        info = dict(zip(df["item"], df["value"]))
        print_json(info)

        subsection("data type check")
        for k, v in list(info.items())[:10]:
            print(f"  {k}: type={type(v).__name__}, value={v!r}")

        subsection("skill_result structure")
        skill_result = {
            "success": True,
            "data": info,
            "symbol": symbol,
            "source": "akshare/East Money",
            "content": (f"Stock Name: {info.get('股票简称','')}\n"
                        f"Industry: {info.get('行业','')}\n"
                        f"Total Shares: {info.get('总股本','')}\n"
                        f"Tradable Shares: {info.get('流通股','')}\n"
                        f"Main Business: {info.get('主营业务','')}\n"),
        }
        print(f"  content len: {len(skill_result['content'])}")
        print(f"  content:\n{skill_result['content']}")

        subsection("_extract_numeric_metrics result")
        cm = agent._extract_numeric_metrics(info)
        print(f"  extracted {len(cm)} numeric metrics:")
        for k, v in list(cm.items())[:10]:
            print(f"    {k}: {v}")
        if not cm:
            print("  WARNING: no numeric metrics - all values contain units")

        subsection("_format_structured_data result")
        formatted = agent._format_structured_data(info, "company_info", symbol)
        print(f"  formatted len: {len(formatted)}")
        print(f"  formatted:\n{formatted[:500]}")

        return skill_result
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        traceback.print_exc()
        return None


async def test_financials(ak, symbol, agent):
    section("2. financials")
    try:
        subsection("income_statement")
        income = call_with_retry(ak.stock_profit_sheet_by_report_em, symbol=symbol)
        if income is not None and not income.empty:
            print(f"  columns: {income.columns.tolist()}")
            print(f"  rows: {len(income)}")
            records = income.head(2).to_dict(orient="records")
            for i, rec in enumerate(records):
                subsection(f"  income row {i+1} (first 10 cols)")
                for k in list(rec.keys())[:10]:
                    v = rec[k]
                    print(f"    {k}: type={type(v).__name__}, value={v!r}")
        else:
            print("  NO DATA")
            income = None

        subsection("balance_sheet")
        bs = call_with_retry(ak.stock_balance_sheet_by_report_em, symbol=symbol)
        if bs is not None and not bs.empty:
            print(f"  columns: {bs.columns.tolist()}")
            print(f"  rows: {len(bs)}")
        else:
            print("  NO DATA")
            bs = None

        subsection("cash_flow")
        cf = call_with_retry(ak.stock_cash_flow_sheet_by_report_em, symbol=symbol)
        if cf is not None and not cf.empty:
            print(f"  columns: {cf.columns.tolist()}")
            print(f"  rows: {len(cf)}")
        else:
            print("  NO DATA")
            cf = None

        subsection("skill_result structure")
        data = {}
        if income is not None and not income.empty:
            data["income_statement"] = income.head(4).to_dict(orient="records")
        if bs is not None and not bs.empty:
            data["balance_sheet"] = bs.head(4).to_dict(orient="records")
        if cf is not None and not cf.empty:
            data["cash_flow"] = cf.head(4).to_dict(orient="records")

        skill_result = {
            "success": True,
            "data": data,
            "symbol": symbol,
            "source": "akshare/East Money",
            "content": f"Retrieved three financial statements for {symbol}",
        }

        subsection("format test")
        formatted = agent._format_structured_data(data, "financials", symbol)
        print(f"  formatted len: {len(formatted)}")
        print(f"  formatted:\n{formatted}")

        subsection("content selection logic")
        raw_content = skill_result.get("content", "")
        print(f"  skill_result['content']: '{raw_content}' ({len(raw_content)} chars)")
        print(f"  formatted: {len(formatted)} chars")
        selected = formatted if formatted and len(formatted) > len(raw_content) else raw_content
        print(f"  selected: {'formatted (longer)' if len(formatted) > len(raw_content) else 'raw content'}")

        subsection("_extract_numeric_metrics result")
        cm = agent._extract_numeric_metrics(data)
        print(f"  extracted {len(cm)} numeric metrics:")
        for k, v in list(cm.items())[:15]:
            print(f"    {k}: {v}")

        subsection("first 300 chars coverage check")
        first_300 = selected[:300]
        print(f"  first 300 chars:\n{first_300}")
        has_digit = any(c.isdigit() for c in first_300)
        print(f"  has digit in first 300: {has_digit}")

        return skill_result
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        traceback.print_exc()
        return None


async def test_key_metrics(ak, symbol, agent):
    section("3. key_metrics")
    try:
        df = call_with_retry(ak.stock_financial_abstract_ths, symbol=symbol)
        if df is not None and not df.empty:
            print(f"  columns: {df.columns.tolist()}")
            print(f"  rows: {len(df)}")
            subsection("first 3 rows")
            for i, row in df.head(3).iterrows():
                print(f"  row {i}: {dict(row)}")
            records = df.head(4).to_dict(orient="records")
            metrics = {"periods": records, "columns": df.columns.tolist()}
        else:
            print("  NO DATA")
            metrics = {}

        print_json(metrics)

        subsection("data type check")
        if metrics.get("periods"):
            for rec in metrics["periods"][:2]:
                for k, v in list(rec.items())[:10]:
                    print(f"  {k}: type={type(v).__name__}, value={v!r}")

        subsection("_extract_numeric_metrics result")
        cm = agent._extract_numeric_metrics(metrics)
        print(f"  extracted {len(cm)} numeric metrics:")
        for k, v in list(cm.items())[:15]:
            print(f"    {k}: {v}")

        subsection("_format_structured_data result")
        formatted = agent._format_structured_data(metrics, "key_metrics", symbol)
        print(f"  formatted len: {len(formatted)}")
        print(f"  formatted:\n{formatted}")

        skill_result = {
            "success": True,
            "data": metrics,
            "symbol": symbol,
            "source": "akshare/Tonghuashun",
            "content": "\n".join(
                " | ".join(f"{k}:{v}" for k, v in rec.items() if v is not None and v is not False)[:60]
                for rec in (metrics.get("periods", [])[:4])
            ),
        }

        subsection("content output")
        print(f"  content len: {len(skill_result['content'])}")
        print(f"  content:\n{skill_result['content'][:500]}")

        return skill_result
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        traceback.print_exc()
        return None


async def test_price_history(ak, symbol, agent):
    section("4. price_history")
    try:
        df = call_with_retry(ak.stock_zh_a_hist, symbol=symbol, period="daily", adjust="qfq")
        if df is not None and not df.empty:
            print(f"  columns: {df.columns.tolist()}")
            print(f"  rows: {len(df)}")
            records = df.head(5).to_dict(orient="records")

            subsection("first 2 rows type check")
            for i, rec in enumerate(records[:2]):
                print(f"  [{i}]")
                for k, v in rec.items():
                    print(f"    {k}: type={type(v).__name__}, value={v!r}")

            subsection("list->dict wrap test")
            price_data = df.head(120).to_dict(orient="records")
            skill_result = {
                "success": True,
                "data": price_data,
                "symbol": symbol,
                "source": "akshare/A-share historical prices",
                "content": f"Retrieved price data for {symbol} (last 120 trading days)",
            }

            data = price_data
            print(f"  isinstance(data, list): {isinstance(data, list)}")
            if isinstance(data, list):
                data = {"records": data}
            print(f"  after wrap isinstance(data, dict): {isinstance(data, dict)}")
            print(f"  records len: {len(data.get('records', []))}")

            subsection("format test")
            formatted = agent._format_structured_data(data, "price_history", symbol)
            print(f"  formatted len: {len(formatted)}")
            print(f"  formatted:\n{formatted}")

            subsection("_extract_numeric_metrics result")
            cm = agent._extract_numeric_metrics(data)
            print(f"  extracted {len(cm)} numeric metrics:")
            for k, v in list(cm.items())[:10]:
                print(f"    {k}: {v}")

            return skill_result
        else:
            print("  NO DATA")
            return None
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        traceback.print_exc()
        return None


async def test_validation(skill_results, symbol, agent):
    section("5. _validate_collected_data e2e test")

    data_points = []
    for sr in skill_results:
        if sr is None:
            continue
        data = sr.get("data", {})
        if isinstance(data, list):
            data = {"records": data}
        content = sr.get("content", "")
        formatted = agent._format_structured_data(data, "financials", symbol)
        if formatted and len(formatted) > len(content):
            content = formatted

        data_points.append({
            "title": f"{symbol} test",
            "content": content,
            "url": f"stock_data://{symbol}/test",
            "quality_score": 95,
            "credibility": "structured_source",
        })

    if not data_points:
        print("  WARNING: no valid data points, skip validation test")
        return

    result = agent._validate_collected_data(data_points, [])
    validated = result.get("validated_data_points", [])

    subsection("validation result")
    print(f"  input data_points: {len(data_points)}")
    print(f"  validated: {len(validated)}")
    for i, vp in enumerate(validated):
        print(f"\n  [{i}] title: {vp.get('title', '')}")
        print(f"      quality_score: {vp.get('quality_score', 0)}")
        print(f"      credibility_score: {vp.get('credibility_score', 0)}")
        print(f"      credibility_source: {vp.get('credibility_source', '')}")
        print(f"      content first 100 chars: {vp.get('content', '')[:100]}")


async def test_analysis_prompt(data_points, agent):
    section("6. _build_analysis_prompt_with_data truncation test")

    if not data_points:
        print("  WARNING: no valid data points, skip")
        return

    prompt = agent._build_analysis_prompt_with_data(
        topic="贵州茅台", aspect="财务分析", aspects=["财务分析"],
        data_points=data_points, sources=[],
    )

    subsection("Prompt data section")
    data_start = prompt.find("Pre-collected Data")
    if data_start > 0:
        data_section = prompt[data_start:data_start+2000]
        print(f"  Data section first 2000 chars:\n{data_section}")
    else:
        print("  WARNING: 'Pre-collected Data' section not found")


async def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else SYMBOL

    section(f"akshare real data test - symbol={symbol}")
    print(f"  time: {datetime.datetime.now().isoformat()}")

    patch_requests_for_http()

    try:
        import akshare as ak
        print(f"  akshare version: {ak.__version__}")
    except ImportError:
        print("  FAIL: akshare not installed: pip install akshare")
        return

    sys.path.insert(0, "E:\\market_report_systerm")
    from src.core.agents.generic_agent import GenericAgent
    agent = GenericAgent(agent_id="test", agent_type="dynamic", config={"skills": [], "context": {}})

    skill_results = []

    sr = await test_company_info(ak, symbol, agent)
    skill_results.append(sr)

    sr = await test_financials(ak, symbol, agent)
    skill_results.append(sr)

    sr = await test_key_metrics(ak, symbol, agent)
    skill_results.append(sr)

    sr = await test_price_history(ak, symbol, agent)
    skill_results.append(sr)

    await test_validation(skill_results, symbol, agent)

    valid_dps = []
    for sr in skill_results:
        if sr is None:
            continue
        data = sr.get("data", {})
        if isinstance(data, list):
            data = {"records": data}
        content = sr.get("content", "")
        formatted = agent._format_structured_data(data, "financials", symbol)
        if formatted and len(formatted) > len(content):
            content = formatted
        valid_dps.append({
            "title": f"{symbol} test",
            "content": content,
            "url": f"stock_data://{symbol}/test",
            "quality_score": 95,
            "credibility": "structured_source",
        })
    await test_analysis_prompt(valid_dps, agent)

    section("SUMMARY")
    success = sum(1 for sr in skill_results if sr is not None)
    total = len(skill_results)
    print(f"  success: {success}/{total}")
    if success == total:
        print("  ALL PASSED!")
    else:
        print("  PARTIAL FAILURE - check network or akshare version")


if __name__ == "__main__":
    asyncio.run(main())
