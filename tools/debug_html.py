# -*- coding: utf-8 -*-
import sys, re
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8')

html = open('output/full_research/revised_report.html', 'r', encoding='utf-8').read()
html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
html = re.sub(r'<head[^>]*>.*?</head>', '', html, flags=re.DOTALL | re.IGNORECASE)

# Find article content
start = html.find('<article')
end = html.find('</article>') + len('</article>')
article = html[start:end]

# Show first 2000 chars of article
print(article[:2000])
