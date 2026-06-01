# 固定模板模块清理方案

> 生成时间: 2025-01-XX
> 分析范围: config/templates/*.yaml 及相关代码

---

## 一、核心发现

### 1.1 三套独立的模板定义（严重冗余）

| 位置 | 类型 | 内容 | 状态 |
|------|------|------|------|
| `config/templates/*.yaml` | 后端YAML | 12个报告结构模板 | 🔴 待清理 |
| `web/src/lib/templates.ts` | 前端TS | 5个固定模板定义 | 🔴 待清理 |
| `src/api/research_api.py` L2270 | 后端硬编码 | 5个模板字典 | 🔴 待清理 |

**问题：三套定义完全独立，内容重复，未完成集成！**

### 1.2 真正使用的配置

| 配置文件 | 用途 | 是否保留 |
|---------|------|---------|
| `config/research_frameworks.yaml` | 智能路由核心配置，定义Agent行为、交互参数 | ✅ **必须保留** |
| `config/document_templates/*.html` | HTML样式模板，用于文档渲染 | ✅ **必须保留** |
| `config/templates/*.yaml` | 报告章节结构定义 | ❌ 待清理 |

---

## 二、依赖关系全图谱

### 2.1 config/templates/*.yaml 的调用链

```
config/templates/*.yaml
        │
        ├─► src/core/orchestrator/smart_clarifier.py
        │   ├─ TemplateLoader.load_templates()          [L197-230]
        │   ├─ TemplateLoader._load_template_from_yaml() [L232-267]
        │   └─ SmartClarifier.TEMPLATES 属性            [L364-371]
        │       └─ 被以下调用:
        │           ├─ orchestrator._load_template_sections() [L2954]
        │           └─ research_api._get_section_details_for_type() [L2383]
        │
        ├─► src/core/orchestrator/orchestrator.py
        │   └─ _load_template_sections() [L2940-2975]
        │       ├─ 直接读取YAML文件 [L2961-2970]
        │       └─ 被以下调用:
        │           ├─ _build_research_task() [L2852, 2861]
        │           └─ _build_research_task_from_intent() [L2917]
        │
        ├─► src/config/report_template.py
        │   ├─ load_template() [L62-107]
        │   └─ ReportTemplate 数据类 [L34-60]
        │       └─ 无活跃调用 ⚠️
        │
        └─► src/config/settings.py & system.py
            └─ template_dir = "config/templates" 配置项
```

### 2.2 前端模板的调用链

```
web/src/lib/templates.ts
        │
        ├─► RESEARCH_TEMPLATES 数组 [L21-93]
        │   └─ 定义5个模板: industry-research, company-analysis, market-sizing, 
        │                competitive-analysis, investment-research
        │
        ├─► web/src/components/chat/ChatPanel.tsx
        │   ├─ parseTemplateCommand() [L142] - 解析 /template 命令
        │   ├─ RESEARCH_TEMPLATES.find() [L145] - 查找模板
        │   └─ quickStartResearch() [L149] - 快速启动
        │       └─ 传递 templateId 和 template.parameters
        │
        └─► web/src/hooks/useResearch.ts
            └─ quickStartResearch() [L38-112]
                └─ api.quickStart(input, templateId, {...})
                    └─ POST /api/v1/research/quick-start
```

### 2.3 后端 quick_start 的处理

```
src/api/research_api.py:quick_start() [L2256-2378]
        │
        ├─► TEMPLATES 字典 [L2270-2291] ⚠️ 硬编码定义
        │   └─ 与前端 templates.ts 内容重复！
        │
        ├─► 获取模板: template = TEMPLATES.get(template_id) [L2293]
        │
        ├─► 获取章节: _get_section_details_for_type(output_type) [L2331]
        │   └─ 调用 TemplateLoader.get_templates_by_type() [L2383-2387]
        │       └─ 读取 config/templates/*.yaml ⚠️
        │
        └─► 获取交互参数: get_framework_config(output_type) [L2310]
            └─ 读取 config/research_frameworks.yaml ✅
```

---

## 三、清理难度评估

### 3.1 难度等级: ⭐⭐⭐⭐ 较高

### 3.2 风险矩阵

| 组件 | 风险 | 影响 | 缓解措施 |
|------|------|------|----------|
| `config/templates/*.yaml` | 中 | SmartClarifier.TEMPLATES 返回空 | 保留内置fallback模板 |
| `src/config/report_template.py` | 低 | 无活跃调用 | 直接删除 |
| `web/src/lib/templates.ts` | 高 | /template 命令失效 | 需同步修改前端 |
| `research_api.py` TEMPLATES | 高 | quick_start 失效 | 需改用framework配置 |
| CLI `--template` 参数 | 中 | 参数语义变化 | 改为选择样式模板 |

### 3.3 关键约束

1. **前端 /template 命令依赖 templates.ts**
   - ChatPanel.tsx 直接导入 RESEARCH_TEMPLATES
   - 删除会导致前端编译错误

2. **后端 quick_start 依赖硬编码 TEMPLATES**
   - research_api.py L2270 定义了模板字典
   - 删除会导致 quick_start 返回 UNKNOWN_TEMPLATE 错误

3. **章节结构需要来源**
   - orchestrator._load_template_sections() 需要返回章节列表
   - 删除YAML后需要替代方案

---

## 四、清理方案

### 方案A: 完全清理（激进）

**删除内容:**
- config/templates/ 整个目录
- src/config/report_template.py
- web/src/lib/templates.ts 中的 RESEARCH_TEMPLATES
- research_api.py 中的 TEMPLATES 字典

**替代方案:**
- 章节结构从 research_frameworks.yaml 获取
- 前端 /template 改为调用后端API获取可用框架列表
- quick_start 改为直接使用 framework 配置

**优点:** 彻底清理，无冗余
**缺点:** 改动量大，需要前后端同步修改

### 方案B: 保留前端模板，清理后端YAML（折中）

**删除内容:**
- config/templates/ 整个目录
- src/config/report_template.py

**保留内容:**
- web/src/lib/templates.ts（前端快速启动功能）
- research_api.py 中的 TEMPLATES 字典（后端快速启动）

**修改内容:**
- _get_section_details_for_type() 改为从内置定义获取
- SmartClarifier.TemplateLoader 简化为只返回内置模板

**优点:** 前端功能不受影响，改动量适中
**缺点:** 前后端模板定义仍然分离

### 方案C: 最小清理（保守）

**删除内容:**
- config/templates/ 整个目录
- src/config/report_template.py

**保留内容:**
- 所有其他代码
- SmartClarifier 内置 fallback 模板

**修改内容:**
- TemplateLoader.load_templates() 改为只返回内置模板
- _load_template_sections() 简化逻辑

**优点:** 风险最小，改动量最小
**缺点:** 前后端模板定义仍然冗余

---

## 五、推荐方案: 方案B（折中）

### 5.1 理由

1. **保留前端功能**: /template 命令是用户快速启动研究的主要入口
2. **清理冗余文件**: config/templates/*.yaml 确实无实际价值
3. **改动可控**: 不需要修改前端代码，后端改动量适中
4. **向后兼容**: CLI 和 API 接口保持不变

### 5.2 具体步骤

#### Step 1: 删除YAML模板文件
```
删除: config/templates/ 整个目录（13个文件）
```

#### Step 2: 删除 report_template.py
```
删除: src/config/report_template.py
修改: src/config/__init__.py - 移除相关导入
```

#### Step 3: 简化 smart_clarifier.py
```python
# 移除:
TEMPLATE_CONFIG_DIR = Path("config/templates")
TEMPLATE_CUSTOM_DIR = Path("config/templates/custom")

# 移除 TemplateLoader 类（L184-337）

# 修改 SmartClarifier.TEMPLATES 属性:
@property
def TEMPLATES(self) -> Dict[str, Template]:
    """获取内置模板（已移除YAML配置文件）"""
    return self._get_builtin_templates()
```

#### Step 4: 简化 orchestrator._load_template_sections()
```python
def _load_template_sections(self, template_id: str) -> List[Dict[str, Any]]:
    """从内置模板获取章节信息"""
    if hasattr(self, '_smart_clarifier') and self._smart_clarifier:
        template = self._smart_clarifier.TEMPLATES.get(template_id)
        if template and hasattr(template, 'sections'):
            return template.sections
    return []
```

#### Step 5: 简化 research_api._get_section_details_for_type()
```python
def _get_section_details_for_type(self, output_type: str) -> List[Dict[str, Any]]:
    """从内置模板获取章节详情"""
    # 直接从内置定义获取，不再读取YAML
    BUILTIN_SECTIONS = {
        "industry_report": [
            {"id": "industry_overview", "name": "Industry Overview", "required": True},
            {"id": "market_size", "name": "Market Size", "required": True},
            {"id": "competitive_landscape", "name": "Competitive Landscape", "required": True},
            # ... 更多章节
        ],
        "company_research": [...],
        # ... 更多类型
    }
    return BUILTIN_SECTIONS.get(output_type, [])
```

#### Step 6: 清理配置文件
```
修改: src/config/settings.py - 移除 template_dir 配置项
修改: src/config/system.py - 移除 template_dir 配置项
```

#### Step 7: 更新测试文件
```
删除或更新: tests/unit/content/test_template_engine.py（如涉及YAML模板）
```

---

## 六、需要保留的内容

| 内容 | 位置 | 原因 |
|------|------|------|
| 内置fallback模板 | smart_clarifier._get_builtin_templates() | 保证系统可用 |
| research_frameworks.yaml | config/ | 智能路由核心配置 |
| document_templates/*.html | config/document_templates/ | 文档样式渲染 |
| 前端 templates.ts | web/src/lib/ | /template 命令功能 |
| 后端 TEMPLATES 字典 | research_api.py | quick_start 功能 |

---

## 七、验证清单

清理后需要验证：

- [ ] 系统启动正常
- [ ] 前端 /template 命令正常工作
- [ ] quick_start API 正常返回
- [ ] 研究任务执行正常（智能路由接管）
- [ ] SmartClarifier.TEMPLATES 返回内置模板
- [ ] 无 ImportError
- [ ] 无 FileNotFoundError（YAML文件）
- [ ] 测试通过

---

## 八、附录：文件清单

### 8.1 待删除文件

```
config/templates/annual_analysis.yaml
config/templates/commercial_plan.yaml
config/templates/company_research.yaml
config/templates/competitor_analysis.yaml
config/templates/conference_call.yaml
config/templates/industry_report.yaml
config/templates/industry_weekly.yaml
config/templates/investment_memo.yaml
config/templates/market_brief.yaml
config/templates/pitch_deck.yaml
config/templates/policy_brief.yaml
config/templates/quarterly_commentary.yaml
config/templates/template_schema.yaml
src/config/report_template.py
```

### 8.2 待修改文件

```
src/core/orchestrator/smart_clarifier.py
src/core/orchestrator/orchestrator.py
src/api/research_api.py
src/config/__init__.py
src/config/settings.py
src/config/system.py
```

### 8.3 不修改文件

```
config/research_frameworks.yaml          # 智能路由配置
config/document_templates/*.html         # 样式模板
web/src/lib/templates.ts                 # 前端模板定义
src/content/template_engine.py           # HTML模板引擎
src/content/content_orchestrator.py      # 内容编排器
```

---

## 九、总结

| 维度 | 评估 |
|------|------|
| **清理价值** | 高 - 移除13个冗余YAML文件，简化代码逻辑 |
| **技术风险** | 中 - 需保证内置模板覆盖所有场景 |
| **工作量** | 约3-4小时 - 代码修改、测试验证 |
| **建议** | ✅ 推荐方案B（折中方案） |

**核心结论：**
- `config/templates/*.yaml` 可以安全清理
- 前端 `templates.ts` 和后端 `TEMPLATES` 字典需要保留（快速启动功能）
- `research_frameworks.yaml` 是真正的智能路由配置，必须保留
- 清理后系统通过内置模板 + framework配置 正常运行
