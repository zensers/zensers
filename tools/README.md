# 开发审计工具

本目录存放用于检查项目一致性和潜在缺陷的开发辅助脚本，不参与生产服务启动流程。

## 核心工具

### `system_audit.py`

系统一致性扫描器，检查以下内容：

- 对话 Action 与后端处理器是否一致
- 会话状态转换是否完整
- 异步任务和潜在竞态
- 异常恢复和状态持久化风险
- 对话历史记录是否完整

运行：

```powershell
python tools/system_audit.py
```

### `audit_v2.py`

扩展版综合审计器，在基础扫描之外，增加以下检查：

- SSE 事件前后端一致性
- API 路由前后端一致性
- 前端状态字段使用情况
- 前端模式和状态处理
- 更详细的错误处理检查

运行：

```powershell
python tools/audit_v2.py
```

运行 `audit_v2.py` 后，会生成报告：

```text
.sisyphus/audit-report.md
```

### `professional_report_generator.py`

专业报告生成核心工具，用于生成符合德勤风格的研究报告。

运行：

```powershell
python tools/professional_report_generator.py
```

### `batch_generate_reports.py`

批量报告生成工具，用于批量生成多个行业的研究报告。

运行：

```powershell
python tools/batch_generate_reports.py
```

### `verify_word_quality.py`

Word 文档质量验证工具，用于检查生成的 Word 文档是否符合质量标准。

运行：

```powershell
python tools/verify_word_quality.py
```

## 测试脚本

以下脚本用于测试和调试，不属于核心工具：

- `test_cover.py` - 封面测试
- `test_div_tracking.py` - div 追踪测试
- `test_parser.py` - 解析器测试
- `test_prompt_format.py` - 提示词格式测试
- `test_span.py` - span 测试
- `test_toc.py` - 目录测试
- `test_toc_real.py` - 真实目录测试
- `test_tracking.py` - 追踪测试
- `test_ul.py` - 列表测试

## 临时脚本

以下脚本为一次性生成特定报告的临时脚本，可按需清理：

- `generate_*.py` - 各种报告生成脚本
- `revise_*.py` - 报告修订脚本
- `regenerate_report.py` - 报告重新生成脚本

## 注意事项

- 核心工具都应从项目根目录运行。
- 审计结果是静态规则扫描，不能替代单元测试、集成测试或人工代码审查。
- `audit_v2.py` 会覆盖 `.sisyphus/audit-report.md`，运行前如需保留历史结果，请先备份该文件。
- 审计脚本只用于开发和排查问题，不应被业务代码直接依赖。
