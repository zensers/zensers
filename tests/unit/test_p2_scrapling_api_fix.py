# -*- coding: utf-8 -*-
"""
P2 Fix: Scrapling 废弃 API 警告

Bug: 2,578 次 WARNING "This logic is deprecated now"
根因: 使用旧 API AsyncFetcher() + .adaptive = True
修复: 迁移到 AsyncFetcher.configure()
"""

import pytest


class TestScraplingApiMigration:
    """web_scraper_skill 应使用新 API"""

    def test_uses_configure_not_deprecated(self):
        """应使用 AsyncFetcher.configure() 而非旧 API"""
        with open("src/skills/web_scraper_skill.py", "r", encoding="utf-8") as f:
            content = f.read()
        has_deprecated_pattern = (
            "AsyncFetcher()" in content and ".adaptive" in content
        )
        assert not has_deprecated_pattern, \
            "应使用 AsyncFetcher.configure() 而非 AsyncFetcher() + .adaptive = True"

    def test_uses_configure_method(self):
        """应使用 configure() 方法"""
        with open("src/skills/web_scraper_skill.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "configure" in content, "应使用 AsyncFetcher.configure()"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
