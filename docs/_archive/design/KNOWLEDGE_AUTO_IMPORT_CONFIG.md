# 知识模块自动导入 — 用户配置指南

> 纯后台自动运行，无需前端操作。配置即启用。

---

## 快速开始

在项目根目录 `.env` 文件中添加：

```bash
# 知识源目录（逗号分隔）
DREAM_SOURCE_DIRS=data/sources/market_reports,data/sources/industry_pdfs

# 可选：扫描间隔（秒），默认 300（5 分钟）
DREAM_SCAN_INTERVAL=300
```

重启后端服务即可。系统自动扫描目录中新文件，提取知识并存入知识库。

---

## 完整配置项

### 知识源目录

| 变量 | 默认 | 说明 |
|------|------|------|
| `DREAM_SOURCE_DIRS` | 空（不启用） | 逗号分隔的目录路径，指向存放 PDF/MD/TXT/CSV 等原始资料的文件夹 |
| `DREAM_SCAN_INTERVAL` | 300 | 每次扫描之间的间隔（秒）。最小建议 60，频繁扫描对性能影响极小（仅 stat 元数据） |
| `DREAM_AUTO_IMPORT` | true | 总开关。设为 `false` 可完全禁用自动导入 |
| `DREAM_STORE_TO_BANK` | true | 导入后是否写入知识库 SQLite（用于搜索和复用）。关闭则仅在文件系统保留 |
| `DREAM_IMPORT_MAX_WORKERS` | 2 | 并发导入数。IO 密集型操作，不宜设太高 |

### 后台调度

以下继承自 DreamMode 现有配置，通常无需修改：

| 变量 | 默认 | 说明 |
|------|------|------|
| `DREAM_IDLE_CHECK_INTERVAL` | 10 | 后台循环检查间隔（秒） |
| `DREAM_TRIGGER_AFTER_TASK` | true | 研究任务完成后是否自动触发知识提取 |
| `DREAM_BATCH_SIZE` | 10 | 单次知识提取最大处理条数 |

---

## 完整配置示例

```bash
# .env 文件

# --- 知识源目录（新增）---
DREAM_SOURCE_DIRS=data/sources/market_reports,data/sources/industry_pdfs
DREAM_SCAN_INTERVAL=300
DREAM_AUTO_IMPORT=true
DREAM_STORE_TO_BANK=true
DREAM_IMPORT_MAX_WORKERS=2

# --- 知识管理（已有，通常保持默认）---
KNOWLEDGE_ENABLE_COMPILER=true
KNOWLEDGE_ENABLE_DREAM_MODE=true
```

---

## 支持的文件格式

| 格式 | 扩展名 | 说明 |
|------|--------|------|
| Markdown | `.md`, `.markdown` | 原生支持 |
| 纯文本 | `.txt`, `.rst` | UTF-8/GBK 自动检测 |
| CSV | `.csv` | 自动解析表头和行 |
| JSON | `.json` | 转可读文本 |
| PDF | `.pdf` | 需安装 `PyPDF2` |
| Word | `.docx`, `.doc` | 需安装 `python-docx` |
| Excel | `.xlsx`, `.xls` | 需安装 `openpyxl` |

单个文件最大支持 **50MB**。超大文件会被静默跳过（日志记录）。

---

## 工作原理

```
你放文件 → 系统自动发现 → 解析 → 知识编译 → 存入知识库（文件系统 + SQLite）
     ↑                    ↑
  任意目录          每 DREAM_SCAN_INTERVAL 秒检查一次
                    仅扫描新增/变更的文件（mtime+size，不做完整 MD5）
```

- 用户发起研究任务时，扫描自动暂停（主任务优先）
- 已导入的文件不会重复处理（MD5 清单去重）
- 文件导入在独立线程池中执行，不阻塞 API 响应

---

## 典型使用场景

**场景一：研究报告归档**

```bash
DREAM_SOURCE_DIRS=data/reports/archive
```

将已完成的研究报告 PDF 放入 `data/reports/archive/`，系统自动提取其中的实体、概念和关系，丰富知识库。下次同类研究可直接复用。

**场景二：行业资料监控**

```bash
DREAM_SOURCE_DIRS=data/sources/daily_news
DREAM_SCAN_INTERVAL=60
```

每分钟扫描 `daily_news/` 目录。放入新的行业新闻 Markdown 文件后，最短 1 分钟内完成知识提取。

---

## 排障

| 现象 | 原因 | 解决 |
|------|------|------|
| 文件放入后长时间未导入 | 扫描间隔未到 | 调小 `DREAM_SCAN_INTERVAL` |
| 日志显示 "No new files" | 文件已导入过或格式不支持 | 检查文件扩展名，检查 `.import_manifest.json` |
| 导入失败无报错 | 文件超过 50MB 或解析出错 | 查看后端日志 `logs/app.log` |
| 目录不生效 | 路径不存在或权限不足 | 检查目录是否可读 |
