# B5 核实发现

## 1. 数据层：三级信息存在但未传递到渲染

`section_details` 中 `sub_sections[].points` 包含三级要点（字符串数组），但：
- `_build_subsections_from_skeleton()` 输出 `{id, title, content}` — **points 丢失**
- `_parse_markdown_subsections()` 输出 `{id, title, content}` — 无 points
- `_convert_to_sections()` 输出 `subsections: [{id, title, content}]` — 无 points

## 2. HTML fallback 渲染：二级 OK，三级缺失

- `_render_section_html()` L733-753：section `<h2>` + subsection `<h3>` ✅
- 无 subsection 的 subsection（三级）渲染 ❌
- TOC L587-593：二级缩进 ✅，三级缺失 ❌
- `_content_to_html()` L787-796：内联 `####` markdown 可产生 `<h4>`，但非结构化

## 3. HTML 模板：3 个 Bug

### Bug T1: subsection heading level 错误
- `word_default.html` L404: `<h2 class="section-title">{{ subsection.title }}</h2>`
- `word_research_report.html` L319: 同上
- **应为 `<h3 class="subsection-title">`**，当前与 section 同级

### Bug T2: TOC 完全扁平
- `word_default.html` L385-389: 只迭代 `sections`，不迭代 `subsections`
- `word_research_report.html` L302-306: 同上
- 即使有 subsection，TOC 也只显示一级

### Bug T3: 有 subsection 时 section.content 被丢弃
- `word_default.html` L401-412: `{% if section.subsections %}...{% else %}{{ section.content }}{% endif %}`
- 当 subsections 存在时，section 自身的 content 不渲染

## 4. DOCX 直接渲染：二级 OK，三级 heading 被跳过

- `_populate_document_content()` L560: section → `level=1` ✅
- L639: subsection → `level=2` ✅
- L646-648: `if element["type"] == "heading": continue` — **subsection 内所有 heading 被跳过**，包括可能的三级标题 ❌
- 无 `level=3` 渲染 ❌

## 5. DOCX TOC：只到二级

- `_generate_toc()` L755-765: 只处理 `level=1` 和 `level=2`
- 无 `level=3` ❌

## 6. HTML→DOCX 转换器：基本 OK

- `base_parser.py` L270-271: `h1-h6` → `level=1-6` 自动映射 ✅
- `html_to_word.py` L630: `add_heading(text, level=level)` ✅
- `_apply_heading_style()` L839: `subsection-title` → `h3_size`，但无 `sub-subsection-title` ❌
- 默认样式无 `h4_size` ❌

## 7. 关键设计决策

### 三级模型：points 而非嵌套 subsection

`framework_tree` 的三级结构是：
```json
[{"name": "section1", "sub_sections": [{"name": "sub1", "points": ["point1", "point2"]}]}]
```

`points` 是字符串数组，不是嵌套的 `sub_sections`。这是"要点"而非"子章节"。

**选择保持 points 模型**，在渲染时将每个 point 展开为 `<h4>` 标题 + 匹配内容段落。这比改为完全递归模型改动小得多。
