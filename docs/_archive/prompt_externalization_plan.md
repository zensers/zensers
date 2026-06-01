# Prompt 外置重构方案

> 目标：将硬编码在 Python 代码中的 LLM prompt 抽取到独立的 `.md` 文件，
> 实现 prompt 与代码的分离。改 prompt 不碰 Python，非开发者也能直接编辑。
>
> 设计原则：
> 1. 不引入新依赖 — 只用 Python 标准库 + 项目已有依赖（PyYAML 已存在）
> 2. 纯文本 — `.md` 文件，`string.Template` 填充变量
> 3. 不动逻辑 — 只抽纯文本，条件分支/循环留 Python
> 4. 接口不变 — 现有 API 签名不改，调用方零修改
> 5. 渐进替换 — 逐个迁移，对比验证输出一致性

---

## 一、现状

代码库中存在 4 条独立的 prompt 构建链路：

| 链路 | 位置 | 内容 | 行数 |
|------|------|------|------|
| A | `generic_agent.py` | 角色定义 14 个 + 研究 prompt 3 个 + 合成 prompt 3 变体 | ~250 行 |
| B | `strategies.py` | 数据收集/验证/分析/综合(4变体)/报告 共 5 阶段 | ~250 行 |
| C | `orchestrator.py` | body_agent + summary_agent + conclusion_agent 系统提示 | ~80 行 |
| D | `phase_prompts.py` | 结构化 PhasePromptTemplate 7 个阶段模板，已有管理器 | ~160 行 |

其中链路 D 已经具备结构化模板系统（`PhasePromptTemplate` dataclass + `PhasePrompts` manager），
其 prompt 内容分布在 `_init_phase_prompts()` 的 14 个 f-string 块中。

---

## 二、目标架构

### 2.1 目录结构

```
prompts/
├── _shared/
│   ├── writing_style.md         # 写作风格规范
│   └── output_spec.md           # 输出规范（format_rules）
│
├── agents/                      # Agent Profile = system_prompt + skills + config
│   ├── market_size.md           # 市场规模
│   ├── competition.md           # 竞争格局
│   ├── trend.md                 # 发展趋势
│   ├── industry_chain.md        # 产业链
│   ├── financial_analysis.md    # 财务分析
│   ├── valuation.md             # 估值分析
│   ├── policy.md                # 政策法规
│   ├── technology.md            # 技术趋势
│   ├── enterprise.md            # 企业分析
│   ├── risk.md                  # 风险分析
│   ├── investment.md            # 投资价值
│   ├── executive_summary_role.md # 执行摘要（角色定义）
│   ├── conclusion_role.md       # 研究结论（角色定义）
│   ├── validation.md            # 数据验证
│   ├── general.md               # 通用研究（默认回退）
│   ├── body_agent.md            # 链路 C Agent 系统提示
│   ├── executive_summary.md     # 链路 C Agent 系统提示
│   └── research_conclusion.md   # 链路 C Agent 系统提示
│
├── tasks/                       # User prompt：当前任务定义（链路 A/B）
│   ├── research_with_data.md    # 带数据的研究 prompt
│   ├── basic_research.md        # 无数据的基础研究
│   ├── synthesis_target.md      # 综合分析 — 有 target_aspect
│   ├── synthesis_aspect.md      # 综合分析 — 有 aspect 无 target
│   └── synthesis_default.md     # 综合分析 — 无 aspect 无 target
│
└── phases/                      # 阶段模板（链路 D，PhasePromptTemplate 格式）
    ├── data_collection.md
    ├── data_validation.md
    ├── deep_analysis.md
    ├── synthesis_summary.md
    ├── synthesis_conclusion.md
    ├── synthesis_insight.md
    ├── synthesis_general.md
    └── report_generation.md
```

**变更说明：**

| 原方案 | 新方案 | 原因 |
|--------|--------|------|
| `roles/` + `agents/` | → `agents/` | 同属 system prompt，合并 |
| system prompt 只有正文 | → frontmatter + body | skill 映射和配置一并管理 |

### 2.2 Agent Profile 文件格式

每个 `agents/*.md` 文件遵循标准 Agent 定义格式：

```markdown
---
name: Market Size Analyst
description: Expert in market size estimation and quantitative analysis
role: Senior Industry Research Analyst specializing in market size quantification
goal: Provide accurate market size estimates using top-down and bottom-up approaches
backstory: You are an experienced market research analyst with expertise in market sizing, growth driver decomposition, and market concentration analysis.
skills:
  required:
    - llm_skill
    - search_skill
    - data_analysis
    - lc_python_repl
  optional:
    - file_skill
config:
  max_queries: 20
  max_results: 50
---

## Expertise Areas
- Market size estimation (top-down / bottom-up)
- Growth driver decomposition (volume-price split, penetration rate drivers)
- Market concentration analysis (CR3/CR5/HHI)

## Analysis Framework
1. Total size assessment: Current market size and growth stage
2. Structural analysis: Market distribution by segment
3. Growth decomposition: Volume vs price contribution
4. Driving factors: Quantified impact of key variables
```

**Frontmatter 字段说明：**

| 字段 | 必需 | 说明 |
|------|------|------|
| `name` | ✅ | Agent 名称（简短，用于显示） |
| `description` | ✅ | Agent 描述（一句话说明功能） |
| `role` | ✅ | 角色定义（用于 system prompt） |
| `goal` | ✅ | 目标定义（用于 system prompt） |
| `backstory` | ❌ | 背景故事（增强角色深度） |
| `skills.required` | ✅ | 必需技能列表 |
| `skills.optional` | ❌ | 可选技能列表 |
| `config` | ❌ | 配置参数 |

**正文（body）**：详细的专业领域、分析框架等补充信息，与 frontmatter 中的 role/goal 组合形成完整的 system prompt。

### 2.2.1 Skills 映射表（基于 `strategies.py` 的 `ASPECT_SKILL_MAP`）

| 角色文件 | required_skills | 说明 |
|---------|-----------------|------|
| `市场规模.md` | `[llm_skill, search_skill, data_analysis, lc_python_repl]` | 市场规模测算需要数据分析和Python计算 |
| `竞争格局.md` | `[llm_skill, search_skill, market_analysis]` | 竞争分析使用市场分析框架 |
| `发展趋势.md` | `[llm_skill, search_skill, data_analysis]` | 趋势分析需要数据分析 |
| `产业链.md` | `[llm_skill, search_skill, market_analysis]` | 产业链分析使用市场分析 |
| `财务分析.md` | `[llm_skill, stock_data, stock_analysis, data_analysis]` | 财务分析需要股票数据和分析技能 |
| `估值分析.md` | `[llm_skill, stock_analysis, data_analysis]` | 估值分析需要股票分析 |
| `政策法规.md` | `[llm_skill, search_skill, policy_analysis]` | 政策分析使用政策分析技能 |
| `技术趋势.md` | `[llm_skill, search_skill, tech_trend]` | 技术趋势使用专门的技术趋势技能 |
| `企业分析.md` | `[llm_skill, stock_data, stock_analysis, market_analysis]` | 企业分析需要股票数据和市场分析 |
| `风险分析.md` | `[llm_skill, search_skill, risk_analysis]` | 风险分析使用专门的风险分析技能 |
| `投资价值.md` | `[llm_skill, stock_analysis, data_analysis]` | 投资建议需要股票分析和数据分析 |
| `执行摘要.md` | `[llm_skill]` | 执行摘要只需要LLM综合能力 |
| `研究结论.md` | `[llm_skill]` | 研究结论只需要LLM综合能力 |
| `数据验证.md` | `[llm_skill]` | 数据验证只需要LLM判断能力 |
| `通用研究.md` | `[llm_skill, search_skill]` | 默认回退配置 |
| `body_agent.md` | `[llm_skill, search_skill]` | orchestrator body agent |
| `executive_summary.md` | `[llm_skill]` | orchestrator summary agent |
| `research_conclusion.md` | `[llm_skill]` | orchestrator conclusion agent |

**来源：** `src/core/decomposition/strategies.py` 第 34-57 行的 `ASPECT_SKILL_MAP`。

**迁移时注意：** 
1. 方案中使用 `required_skills` 替代原代码中的 `skills` 列表
2. 原 `get_skills_for_aspect()` 函数的模糊匹配逻辑（`key in aspect`）需要保留在 Python 代码中
3. frontmatter 中的 `required` 是精确匹配，模糊匹配仍由代码处理

### 2.3 AgentProfile 数据结构

```python
@dataclass
class AgentProfile:
    """Agent 完整定义（prompt + skills + 配置），来自一个 .md 文件"""
    name: str
    system_prompt: str               # 正文 → LLM system prompt
    required_skills: List[str]       # frontmatter.skills.required
    optional_skills: List[str]       # frontmatter.skills.optional
    config: Dict[str, Any]           # frontmatter.config
    
    @classmethod
    def from_md(cls, path: Path) -> "AgentProfile":
        """从 .md 文件解析 Agent Profile"""
        content = path.read_text(encoding="utf-8")
        return cls.from_text(path.stem, content)
    
    @classmethod
    def from_text(cls, name: str, content: str) -> "AgentProfile":
        """从文本内容解析 Agent Profile（支持缓存的输入）"""
        # 逐行扫描 --- 分隔符，确保容错
        lines = content.split('\n')
        if lines and lines[0].strip() == '---':
            end = None
            for i in range(1, len(lines)):
                if lines[i].strip() == '---':
                    end = i
                    break
            if end is not None:
                fm_text = '\n'.join(lines[1:end])
                body = '\n'.join(lines[end+1:]).strip()
                import yaml
                try:
                    fm = yaml.safe_load(fm_text) if fm_text.strip() else {}
                except yaml.YAMLError as e:
                    logger.warning(f"YAML frontmatter parse error in {name}: {e}")
                    fm = {}
                skills = fm.get("skills", {})
                return cls(
                    name=name,
                    system_prompt=body,
                    required_skills=skills.get("required", []),
                    optional_skills=skills.get("optional", []),
                    config=fm.get("config", {}),
                )
        # 无 frontmatter，全文为 system_prompt
        return cls(name=name, system_prompt=content.strip(),
                   required_skills=[], optional_skills=[], config={})
```

**注意：** frontmatter 使用 YAML 是合理的——它不是 prompt 正文，而是结构化元数据（列表、字典、数值）。正文仍然是纯文本 `.md`。这是方案中唯一的结构化格式，仅在 frontmatter 段使用。`PromptManager` 可以选择性解析 frontmatter，不影响正文的纯文本本质。

### 2.4 命名策略

**统一使用英文命名**，利于跨平台兼容性和国际化。

| 用途 | 命名方式 | 示例 | 加载方式 |
|------|---------|------|---------|
| 角色定义（链路 A） | 英文，snake_case | `market_size.md`、`competition.md` | `load_profile("market_size")` |
| Agent 系统提示（链路 C） | 英文，snake_case | `body_agent.md`、`executive_summary.md` | `load_profile("body_agent")` |

**Aspect 中文到英文映射**（在代码中处理）：
```python
ASPECT_NAME_MAP = {
    "市场规模": "market_size",
    "竞争格局": "competition",
    "发展趋势": "trend",
    "产业链": "industry_chain",
    "财务分析": "financial_analysis",
    "估值分析": "valuation",
    "政策法规": "policy",
    "技术趋势": "technology",
    "企业分析": "enterprise",
    "风险分析": "risk",
    "投资价值": "investment",
    "执行摘要": "executive_summary_role",
    "研究结论": "conclusion_role",
    "数据验证": "validation",
    "综合分析": "general",
}

def get_profile_name_for_aspect(aspect: str) -> str:
    """将中文 aspect 映射到英文文件名"""
    return ASPECT_NAME_MAP.get(aspect, "general")
```

跨平台兼容性：英文命名避免 UTF-8 编码问题。

---

## 三、变量语法

使用 `string.Template`（Python 标准库，零依赖）替代 `str.format`：

| 场景 | 语法 | 说明 |
|------|------|------|
| 普通变量 | `$topic` 或 `${topic}` | 直接替换 |
| 上下文无关 | `${topic}${aspect}` | 花括号消除边界歧义 |
| 缺省变量 | `safe_substitute()` 不抛异常 | 保留 `$xxx` 原样 |

```python
from string import Template

def render(self, category, name, **variables):
    template = self.load(category, name)
    return Template(template).safe_substitute(**variables)
```

**为什么不用 `str.format`：** 当 `.md` 文件中出现 `{"key": "value"}`（JSON 示例）或代码块中的 `{` 时，`str.format` 会视为未闭合的占位符而崩溃。`string.Template` 的 `$` 语法与 `{` `}` 无冲突。

> **$ 语法安全性确认：** `string.Template` 只识别 `$` 后跟有效 Python 标识符（`[a-zA-Z_][a-zA-Z0-9_]*`）的变量。
> `$10亿`、`$100M` 等金额写法中 `$1` 后跟数字 `0` 不是合法标识符，`safe_substitute` 会保留原样。
> LaTeX 公式 `$x^2$` 同理。无需转义。

---

## 四、公共片段引用机制

跨文件重复的写作风格规范（`writing_style.md`）通过 `{include:writing_style}` 标记引用：

```
prompts/tasks/research_with_data.md：

# 研究任务

## 主题
${topic}

## 维度
${aspect}
...

{include:writing_style}
```

```
prompts/_shared/writing_style.md：

1. 直接输出分析正文，禁止任何对话式前缀
2. 每个段落以明确的判断句开头，直接陈述核心观点
3. 数据与分析自然融合，避免割裂的事实/观点分段
4. 禁止在正文中添加来源标注，如（来源：XXX，可信度：XX）
5. 避免口语化表达：值得关注的是、巧合的是、值得注意的是等
```

PromptManager 在 render 时检测 `{include:xxx}` 并替换为 `_shared/xxx.md` 的内容：

```python
def render(self, category, name, **variables):
    template = self.load(category, name)
    # 解析 {include:xxx} 引用
    def resolve_include(m):
        include_name = m.group(1)
        return self.load("_shared", include_name)
    template = re.sub(r'\{include:(\w+)\}', resolve_include, template)
    return Template(template).safe_substitute(**variables)
```

---

## 五、PromptManager

```python
"""src/core/prompt_manager.py"""
import re
import logging
from pathlib import Path
from string import Template
from threading import Lock
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AgentProfile:
    """Agent 完整定义（prompt + skills + 配置），来自一个 .md 文件"""
    name: str
    system_prompt: str
    required_skills: List[str] = field(default_factory=list)
    optional_skills: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_md(cls, path: Path) -> "AgentProfile":
        """从 .md 文件解析 Agent Profile"""
        content = path.read_text(encoding="utf-8")
        return cls.from_text(path.stem, content)
    
    @classmethod
    def from_text(cls, name: str, content: str) -> "AgentProfile":
        """从文本内容解析 Agent Profile（支持缓存的输入）"""
        import yaml
        lines = content.split('\n')
        if lines and lines[0].strip() == '---':
            end = None
            for i in range(1, len(lines)):
                if lines[i].strip() == '---':
                    end = i
                    break
            if end is not None:
                fm_text = '\n'.join(lines[1:end])
                body = '\n'.join(lines[end+1:]).strip()
                try:
                    fm = yaml.safe_load(fm_text) if fm_text.strip() else {}
                except yaml.YAMLError as e:
                    logger.warning(f"YAML frontmatter parse error in {name}: {e}")
                    fm = {}
                skills = fm.get("skills", {})
                return cls(
                    name=name,
                    system_prompt=body,
                    required_skills=skills.get("required", []),
                    optional_skills=skills.get("optional", []),
                    config=fm.get("config", {}),
                )
        return cls(name=name, system_prompt=content.strip())


class PromptManager:
    """Prompt 文件加载器。零依赖，纯文本。"""
    
    def __init__(self, base_dir: str = "prompts"):
        self._base_dir = Path(base_dir)
        self._cache: Dict[str, str] = {}
        self._lock = Lock()  # asyncio 多 Agent 并发保护
    
    def load(self, category: str, name: str) -> str:
        """加载 .md 文件，带缓存。双重检查锁定防止竞态。"""
        key = f"{category}/{name}"
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        
        path = self._base_dir / category / f"{name}.md"
        if not path.exists():
            raise FileNotFoundError(f"Prompt not found: {path}")
        content = path.read_text(encoding="utf-8")
        
        # 再次加锁写入，防止双写
        with self._lock:
            if key not in self._cache:
                self._cache[key] = content
        return content
    
    def render(self, category: str, name: str, strip_frontmatter=False, **variables) -> str:
        return self._render_with_includes(category, name, 0, strip_frontmatter, **variables)

    def _render_with_includes(self, category, name, depth, strip_frontmatter=False, **variables):
        if depth > 5:
            raise RuntimeError(f"Prompt include recursion too deep: {name}")
        template = self.load(category, name)
        if strip_frontmatter:
            template = re.sub(r'^---\n.*?\n---\n', '', template, flags=re.DOTALL)
        template = re.sub(
            r'\{include:(\w+)\}',
            lambda m: self._render_with_includes("_shared", m.group(1), depth + 1),
            template
        )
        result = Template(template).safe_substitute(**variables)
        
        # 检查未填充的变量
        if '$' in result:
            unresolved = re.findall(r'\$[a-zA-Z_]\w*|\$\{[a-zA-Z_]\w*\}', result)
            if unresolved:
                logger.warning(f"Unresolved variables in {category}/{name}: {unresolved}")
        
        return result
    
    def invalidate(self, key: Optional[str] = None):
        with self._lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()
    
    # ─── Agent Profile 加载（prompt + skills + config 统一管理）───
    
    def load_profile(self, name: str) -> AgentProfile:
        """加载 Agent Profile = system_prompt + skills + config（经过缓存）"""
        raw = self.load("agents", name)  # 经过缓存
        return AgentProfile.from_text(name, raw)
    
    def load_profile_system_prompt(self, name: str) -> str:
        """仅加载 Agent 的 system prompt（忽略 frontmatter）"""
        return self.load_profile(name).system_prompt
```

---

## 六、各链路的迁移方式

### 链路 A：generic_agent.py

**替换 `_get_professional_role_prompt`（角色 system prompt）并获取 skills：**
```python
# 改前
def _get_professional_role_prompt(self, aspect):
    role_map = {"市场规模": "你是一位...", ...}
    return role_map.get(aspect, default) + format_rules

# 改后（中文文件名直接匹配 agents/*.md）
def _get_professional_role_prompt(self, aspect):
    try:
        profile = self._pm.load_profile(aspect)
    except FileNotFoundError:
        # 回退到通用角色
        profile = self._pm.load_profile("通用研究")
    spec = self._pm.render("_shared", "output_spec")
    # profile.required_skills 可用于 Agent 能力配置
    return profile.system_prompt + "\n\n" + spec, profile.required_skills
```

**替换 `get_skills_for_aspect()`（保留模糊匹配逻辑）：**
```python
# 改前：从 ASPECT_SKILL_MAP 硬编码字典获取
def get_skills_for_aspect(aspect: str) -> List[str]:
    if aspect in ASPECT_SKILL_MAP:
        return ASPECT_SKILL_MAP[aspect]
    for key, skills in ASPECT_SKILL_MAP.items():
        if key in aspect:
            return skills
    return ["llm_skill", "search_skill"]

# 改后：从 .md 文件 frontmatter 获取，保留模糊匹配
def get_skills_for_aspect(aspect: str) -> List[str]:
    pm = PromptManager()
    # 精确匹配
    try:
        profile = pm.load_profile(aspect)
        return profile.required_skills
    except FileNotFoundError:
        pass
    # 模糊匹配（保留原逻辑）
    # 遍历所有 agents/*.md 文件，检查文件名是否包含在 aspect 中
    agents_dir = Path("prompts/agents")
    for md_file in agents_dir.glob("*.md"):
        if md_file.stem in aspect:
            profile = pm.load_profile(md_file.stem)
            return profile.required_skills
    # 默认
    return ["llm_skill", "search_skill"]
```

**替换 `_build_research_prompt_with_data`：**
```python
return self._pm.render("tasks", "research_with_data",
    topic=topic, aspect=aspect, data_str=data_str, ...)
```

**替换 `_build_basic_research_prompt`：**
```python
return self._pm.render("tasks", "basic_research",
    topic=topic, aspect=aspect, ...)
```

**替换 `_build_synthesis_prompt_with_data` 的变体：**
```python
if target_aspect:
    return self._pm.render("tasks", "synthesis_target", ...)
elif aspect:
    return self._pm.render("tasks", "synthesis_aspect", ...)
else:
    return self._pm.render("tasks", "synthesis_default", ...)
```

### 链路 B：strategies.py

每个 `_build_*_prompt()` 方法替换为：
```python
return self._pm.render("phases", phase_name, topic=topic, ...)
```

### 链路 C：orchestrator.py

**替换 body_agent 的 system_prompt（L2952-2994）：**
```python
# 改前
system_prompt = f"""# 研究任务
## 研究主题
{requirement.topic}
...
"""

# 改后
profile = self._pm.load_profile("body_agent")
system_prompt = self._pm.render("agents", "body_agent", strip_frontmatter=True,
    topic=requirement.topic,
    aspect=aspect,
    focus_areas_str=focus_areas_str,
    metrics_str=metrics_str,
    sources_str=sources_str,
    region=requirement.region,
    analysis_depth=analysis_depth,
    min_length=min_length,
    requires_charts=framework_config.requires_charts(),
    requires_multiple_sources=framework_config.requires_multiple_sources(),
)
```

**替换 summary_agent 的 system_prompt（L3059-3073）：**
```python
system_prompt = self._pm.render("agents", "executive_summary", strip_frontmatter=True,
    topic=requirement.topic,
)
```

**替换 conclusion_agent 的 system_prompt（L3077-3095）：**
```python
system_prompt = self._pm.render("agents", "research_conclusion", strip_frontmatter=True,
    topic=requirement.topic,
)
```

### 链路 D：phase_prompts.py

`_init_phase_prompts()` 内部改造：

```python
def _init_phase_prompts():
    """初始化阶段Prompt模板 - 从文件加载"""
    global PHASE_PROMPTS
    
    pm = PromptManager()
    phases = ["data_collection", "data_validation", "deep_analysis",
              "synthesis_summary", "synthesis_conclusion",
              "synthesis_insight", "synthesis_general", "report_generation"]
    
    for phase in phases:
        try:
            content = pm.load("phases", phase)
            PHASE_PROMPTS[phase] = _parse_phase_md(content, phase)
        except FileNotFoundError:
            logger.warning(f"Phase prompt file not found: phases/{phase}.md")
        except Exception as e:
            logger.error(f"Failed to load phase prompt {phase}: {e}")
```

---

## 七、_parse_phase_md 解析规则

### `.md` 文件规范

每个 `phases/*.md` 使用 `## ` 段落分割。output_schema 和 examples 使用 JSON 代码块包裹：

```markdown
## role_definition
你是一位资深分析师，擅长对 $topic 的 $aspect 进行深入分析。

## goal_template
对 $topic 的 $aspect 进行深入分析，得出有数据支撑的结构化结论。

## instructions
- 每个结论必须有具体数据支撑
- 对不确定的结论标注置信度
- 矛盾数据需说明取舍理由
- 避免口语化表达
- 禁止在正文中标注数据来源
- 每个段落以判断句开头

## output_schema
```json
{"type": "object", "properties": {"conclusion": {"type": "string"}}}
```

## frameworks
- PESTEL
- PORTER_FIVE_FORCES

## examples
```json
{"input": {...}, "output": {...}}
```
```

### 解析函数

```python
import json
import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def _parse_phase_md(content: str, phase: str) -> "PhasePromptTemplate":
    """将 ## 段落解析为 PhasePromptTemplate 字段"""
    from .phase_prompts import PhasePromptTemplate, PromptFramework
    
    fields = {"phase": phase}
    
    # 提取代码块（优先处理，避免代码块中包含 ## 导致误分割）
    code_blocks = {}
    def extract_code_block(m):
        idx = len(code_blocks)
        placeholder = f"__CODE_BLOCK_{idx}__"
        code_blocks[placeholder] = m.group(2)  # group(2) 是代码内容
        return placeholder
    content = re.sub(r'```(\w*)\n(.*?)```', extract_code_block, content, flags=re.DOTALL)
    
    # 按 ## 分割
    sections = re.split(r'\n## ', content)
    
    # 检查第一个 ## 前的文本是否被静默丢弃（放在循环前，逻辑更清晰）
    intro = sections[0].strip() if sections else ''
    if intro and not intro.startswith('#'):
        logger.warning(f"_parse_phase_md: text before first ## in {phase} discarded: {intro[:60]}...")
    
    # 处理各 section
    for section in sections:
        if '\n' not in section:
            continue
        key, _, value = section.partition('\n')
        # 标准化 key：转小写，替换空格和中划线为下划线
        key = key.strip().lower().replace(" ", "_").replace("-", "_")
        value = value.strip()
        
        # 恢复代码块
        for placeholder, code in code_blocks.items():
            value = value.replace(placeholder, f"```\n{code}\n```")
        
        if key == "instructions":
            fields["instructions"] = [
                item.strip().lstrip("- ")
                for item in value.split('\n')
                if item.strip().startswith("- ")
            ]
        elif key == "output_schema":
            # 从代码块中提取 JSON
            json_match = re.search(r'```json\s*(.*?)\s*```', value, re.DOTALL)
            if json_match:
                try:
                    fields["output_schema"] = json.loads(json_match.group(1))
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON in output_schema for {phase}: {e}")
                    fields["output_schema"] = {}
            elif value.strip():
                try:
                    fields["output_schema"] = json.loads(value)
                except json.JSONDecodeError:
                    fields["output_schema"] = {}
            else:
                fields["output_schema"] = {}
        elif key == "frameworks":
            raw_list = [
                item.strip().lstrip("- ").upper().replace("-", "_")
                for item in value.split('\n') if item.strip().startswith("- ")
            ]
            frameworks = []
            for f in raw_list:
                if f in PromptFramework.__members__:
                    frameworks.append(PromptFramework[f])
                # 未知框架静默跳过，不保留字符串
            fields["frameworks"] = frameworks
        elif key == "examples":
            json_match = re.search(r'```json\s*(.*?)\s*```', value, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group(1))
                    fields["examples"] = parsed if isinstance(parsed, list) else [parsed]
                except json.JSONDecodeError:
                    fields["examples"] = []
            else:
                fields["examples"] = []
        elif key in ("role_definition", "goal_template"):
            fields[key] = value.strip()
    
    # 补充默认值
    fields.setdefault("instructions", [])
    fields.setdefault("output_schema", {})
    fields.setdefault("examples", [])
    fields.setdefault("frameworks", [])
    
    return PhasePromptTemplate(**fields)
```

---

## 八、兼容改造

### 8.1 PhasePromptTemplate.render()

现有 `PhasePromptTemplate.render()` 内部使用 `str.format`，迁移后 `.md` 文件使用 `$` 语法。
render 方法需同步改为 `string.Template`：

```python
from string import Template

# 改前
def render(self, topic=None, aspect=None, context=None):
    ...
    goal = self.goal_template.format(topic=topic, aspect=aspect)
    ...

# 改后
def render(self, topic=None, aspect=None, context=None):
    ...
    goal = Template(self.goal_template).safe_substitute(
        topic=topic, aspect=aspect
    )
    ...
```

**调用方 API 不变。** `PhasePrompts.get_prompt()` 和 `get_prompt_for_phase()` 签名不修改。

### 8.2 变量作用域说明

`_render_with_includes()` 不向 include 递传 `variables`。所有变量在外层 `safe_substitute()` 统一替换，include 层只负责拆解 `{include:xxx}` 标记。这是设计故意，避免变量作用域混乱。

---

## 九、验证策略

### 输出对比验证

每条 prompt 迁移必须通过输出对比：

```python
import difflib

def test_prompt_migration():
    """验证迁移前后 LLM 收到的 prompt 一致"""
    # 旧版本（迁移前）
    old = old_renderer(...)
    # 新版本（迁移后）
    new = PromptManager().render(...)
    
    diff = '\n'.join(difflib.unified_diff(
        old.splitlines(), 
        new.splitlines(), 
        lineterm='',
        fromfile='old',
        tofile='new'
    ))
    if diff:
        raise AssertionError(f"输出不一致:\n{diff}")
```

### 回归测试门禁

| 检查项 | 工具 | 通过标准 |
|--------|------|---------|
| 渲染输出 diff | `difflib.unified_diff` | 无差异或差异可接受 |
| 变量完整性 | `re.findall(r'\$\{?\w+\}?', result)` | 无未替换变量 |
| include 生效 | 检查结果包含 `_shared` 内容 | 内容正确嵌入 |
| Agent Profile 字段 | `hasattr` | skills、config 正确解析 |

### 回滚策略

每个 `.md` 文件迁移后保留旧硬编码代码 1 个版本周期。
若验证失败，切换回硬编码版本：

```python
# 临时回滚
self._pm = None  # 禁用文件加载
# 代码走旧的 f-string 分支
```

---

## 十、实施步骤

### Phase 0：基础设施

1. 创建 `prompts/{_shared,agents,tasks,phases}/` 目录
2. 实现 `src/core/prompt_manager.py`（含 {include} 解析 + AgentProfile）
3. 实现 `_parse_phase_md()` 解析函数
4. 编写 `prompts/_shared/writing_style.md`
5. 编写 `prompts/_shared/output_spec.md`
6. 为链路 D 的 8 个阶段编写 `.md` 文件
7. 修改 `_init_phase_prompts()` 加载方式
8. **验证：** `get_prompt_for_phase("deep_analysis", ...)` 输出与改前一致

### Phase 1：链路 D（phase_prompts.py）

逐个阶段迁移，每次对比渲染输出。8 个阶段完成后再删除旧硬编码。

### Phase 2：链路 C（orchestrator.py）

1. 编写 `prompts/agents/body_agent.md`
2. 编写 `prompts/agents/executive_summary.md`
3. 编写 `prompts/agents/research_conclusion.md`
4. 替换 L2952-2994、L3059-3073、L3077-3095 的 system_prompt
5. **验证：** 运行完整研究流程，确认输出一致

### Phase 3：链路 A（generic_agent.py）

1. 编写 14 个角色文件（`prompts/agents/市场规模.md` 等）
2. 编写 5 个任务文件（`prompts/tasks/*.md`）
3. 替换 `_get_professional_role_prompt()`
4. 替换 `_build_research_prompt_with_data()`
5. 替换 `_build_basic_research_prompt()`
6. 替换 `_build_synthesis_prompt_with_data()`
7. **验证：** 运行各类型研究任务，确认输出一致

### Phase 4：链路 B（strategies.py）

1. 编写 `prompts/phases/data_collection.md` 等
2. 替换 `_build_data_collection_prompt()`
3. 替换 `_build_validation_prompt()`
4. 替换 `_build_analysis_prompt()`
5. 替换 `_build_synthesis_prompt()` 4 个变体
6. 替换 `_build_report_prompt()`
7. **验证：** 运行完整研究流程，确认输出一致

---

## 十一、清理方案

每个 Phase 完成后，删除被替换的旧代码。

### Phase 1 完成后清理（链路 D）

| 清理内容 | 位置 | 说明 |
|---------|------|------|
| `_init_phase_prompts()` 函数体 | `phase_prompts.py` L135-302 | 删除约 170 行硬编码 |

### Phase 2 完成后清理（链路 C）

| 清理内容 | 位置 | 说明 |
|---------|------|------|
| body_agent 的 system_prompt f-string | `orchestrator.py` L2952-2994 | ~43 行 → 删除 |
| summary_agent 的 system_prompt f-string | `orchestrator.py` L3059-3073 | ~15 行 → 删除 |
| conclusion_agent 的 system_prompt f-string | `orchestrator.py` L3077-3095 | ~19 行 → 删除 |

### Phase 3 完成后清理（链路 A）

| 清理内容 | 位置 | 说明 |
|---------|------|------|
| `role_map` 字典 | `generic_agent.py` L1679-1886 | ~200 行 |
| `format_rules` 常量 | `generic_agent.py` L1671-1677 | ~7 行 |
| `_build_research_prompt_with_data()` 的 f-string | `generic_agent.py` | ~30 行 |
| `_build_basic_research_prompt()` 的 f-string | `generic_agent.py` | ~15 行 |
| `_build_synthesis_prompt_with_data()` 的 f-string | `generic_agent.py` | ~42 行 |

### Phase 4 完成后清理（链路 B）

| 清理内容 | 位置 | 说明 |
|---------|------|------|
| `ASPECT_SKILL_MAP` 字典 | `strategies.py` L34-57 | 迁移到各 `.md` 文件的 frontmatter |
| `get_skills_for_aspect()` 硬编码逻辑 | `strategies.py` L60-80 | 替换为从 frontmatter 读取 |
| `_build_data_collection_prompt()` | `strategies.py` | 替换为 `pm.render()` |
| `_build_validation_prompt()` | `strategies.py` | 替换为 `pm.render()` |
| `_build_analysis_prompt()` | `strategies.py` | 替换为 `pm.render()` |
| `_build_synthesis_prompt()` | `strategies.py` | 替换为 `pm.render()` |
| `_build_report_prompt()` | `strategies.py` | 替换为 `pm.render()` |

### 不回退的遗留代码

以下代码与 prompt 有交集但不属于 prompt 外置范围，保持不动：

| 代码 | 理由 |
|------|------|
| `content_quality.py` 的正则过滤 | 后处理清理，与 prompt 分离 |
| `skills/analysis/*.py` 中的 prompt | 已有独立模块，与技能逻辑耦合 |
| `template_engine.py` 的 HTML 模板 | 已有独立 `config/document_templates/` |
| `_clean_llm_output()` | 输出后处理，不是 prompt |

---

## 十二、不变的部分

| 模块 | 保持不动 |
|------|---------|
| `PhasePromptTemplate` dataclass | 接口不变，调用方零修改 |
| `PhasePrompts` manager | `get_prompt()` API 不变 |
| `generic_agent.py` 的 `_build_*` 逻辑代码 | 条件分支、数据格式化、循环 |
| `orchestrator.py` 的 Agent 创建逻辑 | 结构不变 |
| `content_quality.py` 的正则过滤 | 不是 prompt |
| `skills/` 下的技能 prompt | 已有独立模块 |

---

## 十三、实施完成状态

### 已完成 ✅

| Phase | 内容 | 状态 |
|-------|------|------|
| Phase 0 | 基础设施（PromptManager + AgentProfile + 目录结构） | ✅ 完成 |
| Phase 1 | 链路 D（phase_prompts.py）迁移 | ✅ 完成 |
| Phase 2 | 链路 C（orchestrator.py）迁移 | ✅ 完成 |
| Phase 3 | 链路 A（generic_agent.py）迁移 | ✅ 完成 |
| Phase 4 | 链路 B（strategies.py）迁移 | ✅ 完成 |

### 实际创建的文件

```
prompts/
├── _shared/
│   ├── writing_style.md         # 写作风格规范
│   └── output_spec.md           # 输出规范
│
├── agents/ (18 files)
│   ├── market_size.md           # 市场规模分析师
│   ├── competition.md           # 竞争格局分析师
│   ├── trend.md                 # 发展趋势分析师
│   ├── industry_chain.md        # 产业链分析师
│   ├── financial_analysis.md    # 财务分析师
│   ├── valuation.md             # 估值分析师
│   ├── policy.md                # 政策法规分析师
│   ├── technology.md            # 技术趋势分析师
│   ├── enterprise.md            # 企业分析师
│   ├── risk.md                  # 风险分析师
│   ├── investment.md            # 投资分析师
│   ├── executive_summary_role.md # 执行摘要撰写专家
│   ├── conclusion_role.md       # 研究结论撰写专家
│   ├── validation.md            # 数据验证专家
│   ├── general.md               # 通用研究分析师
│   ├── body_agent.md            # 正文 Agent
│   ├── executive_summary.md     # 执行摘要 Agent
│   └── research_conclusion.md   # 研究结论 Agent
│
├── tasks/ (8 files)
│   ├── data_collection.md       # 数据收集任务
│   ├── data_validation.md       # 数据验证任务
│   ├── deep_analysis.md         # 深度分析任务
│   ├── synthesis_summary.md     # 执行摘要综合
│   ├── synthesis_conclusion.md  # 研究结论综合
│   ├── synthesis_insight.md     # 核心洞察综合
│   ├── synthesis_general.md     # 通用综合任务
│   └── report_generation.md     # 报告生成任务
│
└── phases/ (5 files)
    ├── data_collection.md       # 数据收集阶段
    ├── data_validation.md       # 数据验证阶段
    ├── deep_analysis.md         # 深度分析阶段
    ├── synthesis.md             # 综合整合阶段
    └── report_generation.md     # 报告生成阶段
```

### 关键改进

1. **单例模式**：`PromptManager` 使用单例模式，确保全局缓存共享
2. **完整 System Prompt**：`AgentProfile.get_full_prompt()` 组合 role + goal + backstory + body
3. **Fallback 机制**：保留 fallback prompt 用于文件加载失败时的备用
4. **ASPECT_NAME_MAP**：支持中文维度名称到英文文件名的映射

### 未迁移部分（保持不动）

| 文件 | 原因 |
|------|------|
| `skills/analysis/tech_trend.py` | 与技能逻辑耦合 |
| `skills/analysis/stock_analysis.py` | 与技能逻辑耦合 |
| `skills/analysis/risk_analysis.py` | 与技能逻辑耦合 |
| `skills/analysis/policy_analysis.py` | 与技能逻辑耦合 |
| `skills/analysis/market_analysis.py` | 与技能逻辑耦合 |
| `skills/analysis/data_analysis.py` | 与技能逻辑耦合 |
| `document_generation_agent.py` | 报告修订 prompt |
