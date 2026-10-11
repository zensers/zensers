# zensers 行业研究报告模板

## 模板说明

本模板用于生成专业的行业研究报告，包含 zensers 品牌标识和 GitHub 仓库推广信息。

## 模板结构

```
zensers_report_template.docx
├── 封面页
│   ├── zensers Logo
│   ├── 报告标题
│   ├── 副标题
│   ├── 发布日期
│   └── GitHub 标识
├── 目录页
├── 执行摘要（1页）
├── 研究背景与方法论
├── 正文章节（5章）
│   ├── 第一章 市场概况
│   ├── 第二章 竞争格局
│   ├── 第三章 技术趋势
│   ├── 第四章 风险分析
│   └── 第五章 投资建议
├── 数据来源与附录
├── 免责声明
└── 关于 zensers
```

## 品牌标识规范

### 页眉
```
ZENSERS   |   {报告标题}
```

### 页脚
```
© 2026 zensers. 保留所有权利。   |   github.com/zensers/zensers   |   第 X 页
```

### 封面
- Logo 位置：底部居中
- GitHub 标识：`github.com/zensers/zensers`
- 主色调：德勤蓝 (#0076A8) + 深蓝 (#003366) + 金色 (#C9A227)
- 设计风格：德勤（Deloitte）咨询公司风格

## 使用方法

### 1. 直接使用模板
```python
from docx import Document

doc = Document('templates/zensers_report_template.docx')
# 填充内容
doc.save('output/report.docx')
```

### 2. 使用生成脚本
```bash
python tools/create_report_template.py
```

## 自定义

### 修改 Logo
将 `[zensers Logo]` 替换为实际的 Logo 图片。

### 修改颜色
在 `tools/create_report_template.py` 中修改以下颜色值：
- 主色调：`RGBColor(0x1a, 0x36, 0x5d)`
- 点缀色：`RGBColor(0xd6, 0x9e, 0x2e)`

### 修改页眉页脚
在 `tools/create_report_template.py` 中修改 `header` 和 `footer` 相关代码。

## 报告类型

本模板适用于以下报告类型：
- 行业月报
- 专题研究
- 技术趋势
- 数据洞察

## 注意事项

1. 使用前请确保安装了 `python-docx` 库
2. 模板中的占位符需要替换为实际内容
3. 页眉页脚中的页码需要手动更新或使用 Word 功能自动生成
4. 水印功能需要额外的 XML 操作（当前版本未实现）

## 更新日志

- 2026-09-22：初始版本发布
