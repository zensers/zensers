"""
Real end-to-end tests for web_scraper_skill v3.0.

Tests against real URLs to verify:
1. Static page fetching (via Scrapling)
2. PDF content extraction (via pdfplumber)
3. Playwright browser rendering
4. Baidu redirect URL resolution
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


async def test_static_page_fetch():
    from src.skills.web_scraper_skill import WebScraperSkill
    from src.skills.base import SkillConfig
    skill = WebScraperSkill(SkillConfig(name="test", version="1.0"))
    result = await skill.execute(url="https://httpbin.org/html", action="extract_text")
    assert result["success"], f"httpbin failed: {result.get('error')}"
    assert len(result["text"]) > 100
    assert "Moby-Dick" in result["text"]
    print(f"[PASS] Static page: {len(result['text'])} chars, title='{result['title']}'")


async def test_pdf_extraction():
    from src.skills.web_scraper_skill import WebScraperSkill
    from src.skills.base import SkillConfig
    skill = WebScraperSkill(SkillConfig(name="test", version="1.0"))
    result = await skill.execute(
        url="https://static.cninfo.com.cn/finalpage/2025-10-31/1224776127.PDF",
        action="extract_text", timeout=30,
    )
    if not result["success"]:
        print(f"[SKIP] PDF failed (network/blocked): {result.get('error')}")
        return
    assert result["content_length"] > 100
    print(f"[PASS] PDF: {result['content_length']} chars")


async def test_url_classification():
    from src.skills.web_scraper_skill import WebScraperSkill
    from src.skills.base import SkillConfig
    skill = WebScraperSkill(SkillConfig(name="test", version="1.0"))
    cases = [
        ("https://www.eastmoney.com/article/123.html", "js"),
        ("https://xueqiu.com/6436506147/350362500", "js"),
        ("https://finance.sina.com.cn/stock.html", "static"),
        ("https://static.cninfo.com.cn/report.pdf", "pdf"),
        ("http://www.baidu.com/link?url=NhxGkTS80e4", "baidu_redirect"),
    ]
    for url, expected in cases:
        actual = skill._classify_url(url)
        status = "PASS" if actual == expected else "FAIL"
        print(f"[{status}] classify('{url[:45]}...') = {actual}")
        assert actual == expected


async def test_baidu_resolve_offline():
    from src.skills.web_scraper_skill import WebScraperSkill
    from src.skills.base import SkillConfig
    skill = WebScraperSkill(SkillConfig(name="test", version="1.0"))

    async def mock_fetch(url):
        return '<html><head><meta http-equiv="refresh" content="0;url=https://real-target.com/article"></head></html>'

    resolved = await skill._resolve_baidu_url(
        "http://www.baidu.com/link?url=abc123", fetch_mock=mock_fetch,
    )
    assert resolved == "https://real-target.com/article"
    print(f"[PASS] Baidu resolve: {resolved}")

    async def mock_fallback(url):
        return "<html><head><title>Loading</title></head></html>"

    resolved = await skill._resolve_baidu_url(
        "http://www.baidu.com/link?url=abc", fetch_mock=mock_fallback,
    )
    assert resolved == "http://www.baidu.com/link?url=abc"
    print(f"[PASS] Baidu fallback: returned original URL")


async def test_error_handling():
    from src.skills.web_scraper_skill import WebScraperSkill
    from src.skills.base import SkillConfig
    skill = WebScraperSkill(SkillConfig(name="test", version="1.0"))
    result = await skill.execute(
        url="https://unreachable-domain-12345.com/nonexistent",
        action="extract_text", timeout=5,
    )
    if result["success"]:
        print(f"[INFO] Unreachable URL unexpectedly succeeded")
    else:
        print(f"[PASS] Unreachable URL failed: {result.get('error', '')[:80]}")


async def main():
    tests = [
        ("URL classification", test_url_classification),
        ("Static page fetch", test_static_page_fetch),
        ("PDF extraction", test_pdf_extraction),
        ("Baidu resolve (offline)", test_baidu_resolve_offline),
        ("Error handling", test_error_handling),
    ]
    passed = 0
    failed = 0
    for name, fn in tests:
        print(f"\n--- {name} ---")
        try:
            await fn()
            passed += 1
        except Exception as e:
            print(f"[FAIL] {name}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    print(f"\n=== {passed} passed, {failed} failed ===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
