# -*- coding: utf-8 -*-
"""
P2 Fix: Scrapling API compatibility

Bug: 2,578 次 WARNING "This logic is deprecated now"
根因: 使用旧 API AsyncFetcher() + .adaptive = True / AsyncFetcher.configure()
修复: 使用 AsyncFetcher.get(url) 直接调用（Scrapling 0.4.9+ 推荐）
"""

import pytest


class TestScraplingApiMigration:
    """web_scraper_skill 应使用正确的 Scrapling API"""

    def test_uses_direct_get_not_deprecated(self):
        """应使用 AsyncFetcher.get(url) 而非废弃的 configure()"""
        with open("src/skills/web_scraper_skill.py", "r", encoding="utf-8") as f:
            content = f.read()
        has_deprecated_configure = "configure" in content and "AsyncFetcher.configure" in content
        assert not has_deprecated_configure, \
            "AsyncFetcher.configure() 在 0.4.9 已废弃（返回 None），应使用 AsyncFetcher.get(url)"

    def test_uses_async_fetcher_get(self):
        """应使用 AsyncFetcher.get() 直接调用"""
        with open("src/skills/web_scraper_skill.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "AsyncFetcher.get" in content, "应使用 AsyncFetcher.get(url)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
