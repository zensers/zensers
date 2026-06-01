# /template 命令简化方案设计 v6（终稿）

> 日期：2026-05-13
> 状态：设计方案（定稿，可进入实施）
> v5 → v6：修复 1 个 Critical（C8 递归循环）、1 个 Suggestion（S17 plan.aspects）

---

## 1. 背景与目标

### 1.1 现状

当前 `/template` 命令交互链路过长：

```
用户输入 /template industry-research 新能源汽车
  → 前端解析命令，匹配 RESEARCH_TEMPLATES[]
  → 调用 quickStartResearch()
  → POST /api/v1/research/quick-start (后端)
  → 后端 SmartClarifier 创建 Step 4 session
  → 前端收到 step=4 + parameters
  → 渲染 DynamicParameterForm（参数配置表单）
  → 用户填表提交
  → setParameters() → Step 5（确认页）
  → confirmResearch() → Step 6 → 开始执行
```

### 1.2 目标

```
用户输入 /template industry-research 新能源汽车
  → 前端解析，在聊天窗口直接输出框架基本信息    ← 纯前端
  → 用户阅读后，通过自然语言对话修改框架       ← 对话式
  → 用户满意后确认 → 研究开始
```

### 1.3 Phase 界定

| Phase | 范围 | 状态 |
|-------|------|------|
| Phase 1 | 参数提取（LLM），sections 使用后端默认值 | ✅ 当前 |
| Phase 2 | sections 提取（需要建立 ID 映射层） | 📋 后续 |
| Phase 3 | conversation agent prompt 增强 | 📋 后续 |

---

## 2. 核心架构

### 2.1 流程总览

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌────────────────────────┐     ┌──────────┐
│ /template    │────>│ 聊天窗口输出      │────>│ 对话修订框架      │────>│ 创建执行 session      │────>│ Research │
│              │     │ 框架基本信息      │     │ (sendMessage)    │     │ + session 消息继承    │     │ 执行     │
│              │     │ 纯前端，无后端调用  │     │ conversation     │     │ (I8 防 pending 重复)  │     │          │
└─────────────┘     └──────────────────┘     └──────────────────┘     └────────────────────────┘     └──────────┘

session 演变:
  无 session → /template 展示（纯前端）
            → 用户对话 → sendMessage 自动创建 chat session A
            → 用户点击 Start Research
            → quickStartResearch → 后端创建 research session B
            → session B 继承 session A 的消息
            → 研究在 session B 中执行
```

### 2.2 关键数据流

```
用户点击 "Start Research"
  │
  ├─ collectTemplateContext(active, messages, topic)
  │   提取 /template 后的所有用户消息原文
  │
  ├─ quickStartResearch(context, templateId, { autoConfirm: true })
  │    │
  │    ├─ 剥离控制字段（S14): { autoConfirm, ...params }
  │    ├─ 判断 prevSessionId 是否为 __pending__（I8）
  │    ├─ 保存 session A 消息（非 __pending__ 时）
  │    ├─ api.quickStart() → 后端创建 research session B
  │    ├─ setSessionId(id_B) → researchStore 先更新          ← C8: 调换到 createSession 之前
  │    ├─ createSession(id_B) → subscription 触发时 sessionId 已匹配 → 不调 set()
  │    ├─ 恢复 session A 消息到 session B（跳过 __pending__）
  │    └─ 无递归循环（C8 修复）
  │
  ├─ [后端] quick_start(context, auto_confirm=true)
  │    ├─ template_id.replace('-', '_')（C1）
  │    ├─ LLM 从 context 提取 parameters（不含 sections，C7/I12）
  │    ├─ sections 使用后端默认值（C7 fix）
  │    ├─ 构建 session_data 含 aspects/sections/final_plan（C5）
  │    └─ 创建 session，step=6，直接执行
  │
  └─ [前端] step=6 → setStatus('running') → 消息完整保留
```

---

## 3. 详细设计

### 3.1 `web/src/lib/templates.ts`

**改动量：** 新增约 45 行

```typescript
import type { ChatMessage } from '@/types/api';

export interface ResearchTemplate {
  id: string;
  name: string;
  description: string;
  keywords: string[];
  outputType: string;
  templateId: string;
  sections: string[];
  parameters: Record<string, any>;
  prompt: string;
}

export const RESEARCH_TEMPLATES: ResearchTemplate[] = [
  {
    id: 'industry-research',
    name: 'Industry Research',
    description: 'Comprehensive analysis of industry status, competitive landscape, and development trends',
    keywords: ['industry research', 'industry analysis', 'industry report', 'industry'],
    outputType: 'report',
    templateId: 'consulting',
    sections: ['overview', 'market-size', 'competition', 'trends', 'risks', 'conclusion'],
    parameters: { region: 'China', time_range: 'Last 3 Years' },
    prompt: '',
  },
  // ... 其余 4 个模板不变 ...
];

/**
 * 格式化模板信息展示
 */
export function formatTemplateMessage(template: ResearchTemplate, topic?: string): string {
  const header = topic
    ? `**${template.name}** — Topic: **${topic}**`
    : `**${template.name}**`;

  const sections = template.sections
    .map(s => s.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase()))
    .map(s => `- ${s}`)
    .join('\n');

  const params = Object.entries(template.parameters)
    .map(([k, v]) => {
      const label = k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      return `  - **${label}**: \`${v}\``;
    })
    .join('\n');

  // I12: Phase 1 不支持 sections 定制，UI 中标注
  return `${header}

> ${template.description}

**Sections:**
${sections}

**Default Parameters:**
${params}

*You can customize parameters through conversation (e.g. "change region to Global").*
*When ready, click "Start Research" to begin.*`;
}

/**
 * 模板未找到提示
 */
export function formatTemplateNotFound(keyword: string): string {
  const available = RESEARCH_TEMPLATES
    .map(t => `  - \`/template ${t.id}\` — ${t.name}`)
    .join('\n');
  return `No template found for "${keyword}". Available templates:\n\n${available}`;
}

/**
 * 收集对话上下文（不含 sections 修改，Phase 2 加入）
 */
export function collectTemplateContext(
  template: ResearchTemplate,
  messages: { role: string; content: string }[],
  topic: string
): string {
  const templateIndex = messages.findIndex(m =>
    m.role === 'user' && /^\/(template|t)\s/i.test(m.content)
  );

  const userModifications = templateIndex >= 0
    ? messages.slice(templateIndex + 1).filter(m => m.role === 'user').map(m => m.content)
    : [];

  const parts = [
    `Research topic: ${topic}`,
    `Template: ${template.name} (${template.id})`,
    `Parameters: ${JSON.stringify(template.parameters)}`,
    '',
    ...(userModifications.length > 0
      ? [`User's modification requests:`,
         ...userModifications.map((m, i) => `  ${i + 1}. "${m}"`)]
      : []),
  ];
  return parts.join('\n');
}

/**
 * 提取 /template 命令中的关键词
 */
export function extractTemplateKeyword(input: string): string {
  const match = input.trim().match(/^\/(template|t)\s+(\S+)/i);
  return match ? match[2] : '';
}
```

### 3.2 `web/src/store/useResearchStore.ts`

**改动量：** 新增约 35 行

```typescript
import { RESEARCH_TEMPLATES } from '@/lib/templates';

// ResearchState interface 新增
activeTemplate: ResearchTemplate | null;
activeTemplateId: string | null;
researchTopic: string | null;

setActiveTemplate: (template: ResearchTemplate | null) => void;
setResearchTopic: (topic: string | null) => void;

// create 回调
activeTemplate: null,
activeTemplateId: null,
researchTopic: null,

// S12 fix: syncActive 与 set 分离
setActiveTemplate: (template) => {
  const id = template?.id || null;
  set({ activeTemplate: template, activeTemplateId: id });
  const s = useSessionStore.getState();
  if (s.activeId) s.syncActive({ activeTemplateId: id });
},

setResearchTopic: (topic) => {
  set({ researchTopic: topic });
  const s = useSessionStore.getState();
  if (s.activeId) s.syncActive({ researchTopic: topic });
},

// reset + clearResearch 清理
// 两处返回中都增加: activeTemplate: null, activeTemplateId: null, researchTopic: null

// 保持现有简单订阅逻辑（C8: 不添加 I9 subscription fix）
// C8 修复方案：在 quickStartResearch 中调换 setSessionId/createSession 顺序，
// 使订阅触发时 sessionId 已匹配，set(next) 不被调用，无需 subscription 介入。
useSessionStore.subscribe((state) => {
  const active = state.activeId ? state.sessions[state.activeId] : undefined;
  const current = get();
  const next = stateFromCache(active);
  if (current.sessionId !== next.sessionId || current.status !== next.status) {
    set(next);
  }
});
```

### 3.3 `web/src/components/chat/ChatPanel.tsx`

**改动量：** 约 25 行

#### 3.3.1 handleSend — C6 fix

```typescript
const handleSend = async (text: string, attachments?: File[], selectedModel?: string) => {
  // === C6 fix: 通用 cancel 块，保持现有消息不变 ===
  if ((status === 'running' || status === 'processing') && taskId) {
    try { await api.cancelResearch(taskId); } catch {}
    useResearchStore.getState().setStatus('idle');
    useResearchStore.getState().setPhases([]);
    useResearchStore.getState().setProgress(0);
    const label = status === 'running' ? 'Research' : 'Previous search';
    addMessage({
      id: nanoid(), role: 'assistant',
      content: `${label} cancelled. Continuing conversation.`,
      timestamp: new Date().toISOString(),
    });
  }

  // 添加用户消息
  addMessage({ id: nanoid(), role: 'user', content: text, timestamp: new Date().toISOString() });

  // === /template 命令处理 ===
  const { isTemplateCommand, templateId, remainingText } = parseTemplateCommand(text);

  if (isTemplateCommand) {
    // C6 fix: template 清理在分支内部
    useResearchStore.getState().setActiveTemplate(null);
    useResearchStore.getState().setResearchTopic(null);

    if (templateId) {
      const template = RESEARCH_TEMPLATES.find(t => t.id === templateId);
      if (template) {
        useResearchStore.getState().setActiveTemplate(template);
        if (remainingText) {
          useResearchStore.getState().setResearchTopic(remainingText);
        }
        addMessage({
          id: nanoid(), role: 'assistant',
          content: formatTemplateMessage(template, remainingText || undefined),
          timestamp: new Date().toISOString(),
        });
        useResearchStore.getState().setStep(0, []);
        return;
      }
    }

    const keyword = extractTemplateKeyword(text);
    addMessage({
      id: nanoid(), role: 'assistant',
      content: formatTemplateNotFound(keyword),
      timestamp: new Date().toISOString(),
    });
    return;
  }
  // === /template 处理结束 ===

  // ... 正常 sendMessage / startResearch 逻辑不变 ...
};
```

#### 3.3.2 "Start Research" 建议按钮

```typescript
if (isChatMode) {
  const tpl = useResearchStore.getState().activeTemplate;
  const topic = useResearchStore.getState().researchTopic;
  const baseOptions = stepOptions || [];

  const enhancedOptions = (tpl && topic)
    ? [...baseOptions, { id: 'start_research', label: 'Start Research',
        example: `Start research with customized ${tpl.name}`,
        description: `Use customized framework to start research` }]
    : baseOptions;

  if (enhancedOptions.length > 0) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-muted-foreground px-1">You can choose:</p>
        <div className="grid grid-cols-2 gap-2">
          {enhancedOptions.map(option => (
            <button key={option.id} onClick={() => handleOptionSelect(option.id, option.example)}>
              <div className="font-medium text-sm text-foreground">{option.label}</div>
              {option.example && <div className="text-xs text-muted-foreground mt-1">{option.example}</div>}
            </button>
          ))}
        </div>
      </div>
    );
  }
}
```

### 3.4 `web/src/hooks/useResearch.ts`

**改动量：** 新增约 65 行

#### 3.4.1 handleOptionSelect — 集成 start_research

```typescript
// S11 fix: start_research 在 useResearch 内部处理，ChatPanel 直接使用
const handleOptionSelect = useCallback(async (optionId: string, exampleText?: string) => {
  // start_research — 最先检查，独立于 currentStep
  if (optionId === 'start_research') {
    return handleStartResearch();
  }

  if (optionId === 'view_report') {
    if (useResearchStore.getState().status !== 'completed') {
      useResearchStore.getState().setStatus('completed');
    }
    useResearchStore.getState().triggerPreviewRefresh();
    return;
  }

  // Chat mode: suggestion click
  if (currentStep === 0) {
    try {
      setIsNetworkBusy(true);
      const data = await api.clickSuggestion(sessionId!, optionId, exampleText);
      // ... 不变 ...
    }
  }

  switch (currentStep) {
    case 1: return selectOutputType(optionId);
    case 2: return selectTemplate(optionId);
    case 5: return confirmResearch(optionId === 'confirm');
  }
// S16 fix: 添加 handleStartResearch 到依赖数组
}, [currentStep, sessionId, selectOutputType, selectTemplate, confirmResearch,
    handleStartResearch, setIsNetworkBusy, setStep, setTaskId, setStatus, addMessage]);
```

#### 3.4.2 handleStartResearch

```typescript
const handleStartResearch = useCallback(async () => {
  const active = useResearchStore.getState().activeTemplate;
  const topic = useResearchStore.getState().researchTopic || active?.name || '';
  if (!active) return;

  try {
    const allMessages = useChatStore.getState().messages;
    const context = collectTemplateContext(active, allMessages, topic);

    setIsNetworkBusy(true);
    await quickStartResearch(context, active.id, undefined, undefined, {
      ...active.parameters,
      autoConfirm: true,
    });

    useResearchStore.getState().setActiveTemplate(null);
    useResearchStore.getState().setResearchTopic(null);
  } catch (error) {
    setError(error as ApiError);
    addMessage({
      id: nanoid(), role: 'assistant',
      content: 'Failed to start research. Please try again.',
      timestamp: new Date().toISOString(),
    });
  } finally {
    setIsNetworkBusy(false);
  }
}, [quickStartResearch, addMessage]);
```

#### 3.4.3 quickStartResearch — C4/I8/S14 fix

```typescript
const quickStartResearch = useCallback(async (
  input: string, templateId: string,
  attachments?: File[], selectedModel?: string,
  customParams?: Record<string, any>
) => {
  setIsNetworkBusy(true);
  setError(null);

  try {
    const llmConfig = { /* ... */ };

    // S14 fix: 剥离控制字段
    const { autoConfirm: _flag, ...paramValues } = customParams || {};
    const autoConfirm = !!_flag;

    const data = await api.quickStart(input, templateId, {
      llmConfig,
      parameters: paramValues,
      autoConfirm,
    });

    // I8 fix: 排除 __pending__
    const prevId = useSessionStore.getState().activeId;
    const isPending = prevId === '__pending__';
    const prevMessages = (!isPending && prevId)
      ? useSessionStore.getState().sessions[prevId]?.messages || []
      : [];

    // C8 fix: 先设 sessionId，再 createSession。
    // 这样 createSession 触发 subscription 时 sessionId 已匹配，
    // set(next) 不被调用，避免递归循环。
    useResearchStore.getState().setSessionId(data.session_id);
    useSessionStore.getState().createSession(data.session_id, input);

    // C4 fix: 批量写入
    if (prevMessages.length > 0) {
      const store = useSessionStore.getState();
      if (store.sessions[data.session_id]) {
        store.syncActive({ messages: prevMessages });
      }
    }
    setTaskId(data.task_id);

    if (autoConfirm && data.step === 6) {
      setStatus('running');
      setStep(6, undefined);
      addMessage({
        id: nanoid(), role: 'assistant',
        content: `Starting research with template **${templateId}**.`,
        timestamp: new Date().toISOString(),
      });
    } else if (data.step === 4) {
      setStatus('idle');
      setStep(data.step, undefined);
      if (data.parameters) {
        useResearchStore.getState().setParameterConfig(data.parameters);
      }
      addMessage({
        id: nanoid(), role: 'assistant',
        content: data.message || `Template loaded. Configure parameters to continue.`,
        timestamp: new Date().toISOString(),
      });
    } else {
      setStatus('running');
      setStep(6, undefined);
      addMessage({
        id: nanoid(), role: 'assistant',
        content: data.message || `Quick start successful.`,
        timestamp: new Date().toISOString(),
      });
    }

    return data;
  } catch (e) {
    setError(e as ApiError);
    throw e;
  } finally {
    setIsNetworkBusy(false);
  }
}, [setSessionId, setTaskId, setStatus, setStep, addMessage, llm]);
```

### 3.5 后端 `src/api/research_api.py`

**改动量：** 约 55 行

#### 3.5.1 quick_start — template_id 修复 + auto_confirm 分支

```python
async def quick_start(self, user_input, template_id, ..., auto_confirm=False):
    template_id = template_id.replace('-', '_')  # C1
    TEMPLATES = {
        "industry_research": {...}, "company_analysis": {...},
        "market_sizing": {...}, "competitive_analysis": {...},
        "investment_research": {...},
    }
    template = TEMPLATES.get(template_id)
    if not template:
        return {"error": f"Unknown template: {template_id}", "error_code": "UNKNOWN_TEMPLATE"}

    output_type = template["output_type"]
    params = custom_params or {}

    if auto_confirm:
        # C7/I12: sections 使用后端默认值，不依赖 LLM 提取
        aspects = template["aspects"]
        section_details = self._get_section_details_for_type(output_type)
        selected_sections = [s["id"] for s in section_details[:8]] if section_details else aspects[:8]

        # I6 fix: LLM 只提取 parameters
        extracted = await self._extract_params_from_context(user_input, output_type, params)
        params.update(extracted)

        task_id = f"research_{uuid.uuid4().hex[:8]}"

        # C5 fix: 与 Step 4 路径一致的 session_data
        session_data = {
            "user_input": user_input,
            "template_id": template_id,
            "output_type": output_type,
            "aspects": aspects,
            "selected_sections": selected_sections,
            "section_details": section_details,
            "final_plan": {
                "topic": user_input,
                "output_type": output_type,
                "aspects": selected_sections,
            },
            "params": params,
            "current_step": 6,
            "mode": "research",
            "status": "executing",
            "created_at": datetime.now(),
        }
        session_manager.create(task_id, session_data)
        asyncio.create_task(self.execute_research(task_id, session_data))

        # S17: plan.aspects 用人类可读的 template aspects，非 YAML section IDs
        return {
            "session_id": task_id,
            "task_id": task_id,
            "step": 6,
            "status": "executing",
            "message": f"Starting research with template **{template_id}**.",
            "plan": {"topic": user_input, "output_type": output_type, "aspects": aspects},
        }
    else:
        # 原有 Step 4 逻辑（不变）
        # ...
```

#### 3.5.2 _extract_params_from_context — LLM 提取（I11 fix）

```python
async def _extract_params_from_context(
    self,
    context: str,
    output_type: str,
    default_params: Dict[str, Any],
) -> Dict[str, Any]:
    """
    使用 LLM 从对话上下文中提取最终参数。
    I12: Phase 1 只提取 parameters，不包含 sections。
    C7: sections 由后端默认值决定，避免前后端 ID 体系冲突。
    """
    fw_config = get_framework_config(output_type)
    raw_params = fw_config.get_interaction_parameters()
    if not raw_params:
        return default_params

    param_descriptions = []
    for key, config in raw_params.items():
        label = config.get("label", {}).get("en", key)
        options = [o["value"] for o in config.get("options", [])]
        param_descriptions.append(f"  - {key} ({label}): options = {options}")

    prompt = f"""Extract research parameters from user conversation.

Conversation:
{context}

Parameters:
{chr(10).join(param_descriptions)}

Default values: {json.dumps(default_params, ensure_ascii=False)}

Return ONLY a JSON object with extracted values.
Use default value if a parameter is not mentioned.
Do NOT include explanations.
"""

    try:
        from src.skills.llm_skill import LLMSkill
        llm = LLMSkill()
        # I11 fix: use execute() not generate()
        result = await llm.execute(prompt=prompt)
        raw = result.get("content", "") if isinstance(result, dict) else str(result)

        # I11 fix: manual JSON parsing
        import re
        extracted = None
        try:
            extracted = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
            if match:
                extracted = json.loads(match.group(1))

        if extracted and isinstance(extracted, dict):
            merged = dict(default_params)
            merged.update({k: v for k, v in extracted.items() if v is not None and v != ''})
            return merged
    except Exception as e:
        logger.warning(f"LLM param extraction failed: {e}")

    return default_params
```

### 3.6 `src/api/main.py`

```python
@app.post("/api/v1/research/quick-start")
async def quick_start(
    user_input: str = Form(...),
    template_id: str = Form(...),
    auto_confirm: str = Form("false"),
):
    return await research_api.quick_start(
        user_input, template_id, ...,
        auto_confirm=auto_confirm.lower() == "true",
    )
```

### 3.7 `web/src/lib/api.ts`

```typescript
async quickStart(input, templateId, options?) {
  const formData = new FormData();
  formData.append('user_input', input);
  formData.append('template_id', templateId);
  if (options?.autoConfirm) formData.append('auto_confirm', 'true');
  // ... 其他参数 ...

  const { data } = await this.client.post('/api/v1/research/quick-start', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });

  if (data.error) {
    throw new ApiError(data.error_code || 'QUICK_START_ERROR', data.error);
  }

  return data;
}
```

---

## 4. 消息合并（C4 + I8）

```typescript
const prevId = useSessionStore.getState().activeId;
const isPending = prevId === '__pending__';           // I8
const prevMessages = (!isPending && prevId)
  ? useSessionStore.getState().sessions[prevId]?.messages || []
  : [];

useSessionStore.getState().createSession(data.session_id, input);

if (prevMessages.length > 0) {                        // C4
  const store = useSessionStore.getState();
  if (store.sessions[data.session_id]) {
    store.syncActive({ messages: prevMessages });
  }
}
```

| 前置状态 | prevSessionId | createSession 自带 | C4 合并 | 结果 |
|----------|--------------|-------------------|---------|------|
| 无聊天，直接点 | `__pending__` | ✅ 已转移 | ❌ 跳过 | ✅ 不重复 |
| 有聊天 | `chat_xxx` | ❌ 空 | ✅ 合并 | ✅ 完整 |
| 已有 research | `research_xxx` | ❌ 空 | ✅ 合并 | ✅ 完整 |

---

## 5. 用户交互流程

```
[Empty state]

User: /template industry-research 新能源汽车
  → 纯前端展示，不调后端
  → active = industry-research, topic = "新能源汽车"
  → "Start Research" 按钮可见

User: 把地区改成全球
  → sendMessage → conversation agent → "好的，已修改"

User: [点击 Start Research]
  → collectTemplateContext → 上下文含修改
  → quickStartResearch(context, { autoConfirm: true })
  → 后端 LLM 提取: { region: "Global", time_range: "Last 3 Years" }
  → sections 使用后端默认值（Phase 2 支持定制）
  → 创建 session，step=6，直接执行
  → 消息完整保留
```

---

## 6. 文件修改清单

| # | 文件 | 改动量 | 关联问题 |
|---|------|--------|----------|
| 1 | `web/src/lib/templates.ts` | +45 行 | S4, S7, I12 |
| 2 | `web/src/store/useResearchStore.ts` | +35 行 | I2, S5, S6, S12, I9 |
| 3 | `web/src/components/chat/ChatPanel.tsx` | +25 行 | C3, C6, S8, S10 |
| 4 | `web/src/hooks/useResearch.ts` | +65 行 | C4, I5, I8, S11, S14, S16 |
| 5 | `web/src/lib/api.ts` | +12 行 | I3 |
| 6 | `src/api/research_api.py` | +55 行 | C1, C5, C7, I6, I11, I12 |
| 7 | `src/api/main.py` | +3 行 | — |

**总计约 240 行代码变更，零新增 API 端点。**

---

## 7. Normal 路径兼容性验证

| 场景 | 是否进入新代码 | 影响 |
|------|--------------|------|
| 新聊天窗口正常输入 | `isTemplateCommand=false`, `activeTemplate=null` | 零影响 |
| 研究运行时输入任意文字 | cancel 块保持通用消息（C6） | 零影响 |
| 历史 session 恢复 | `activeTemplateId` 恢复仅在模板 session 中 | 零影响 |
| `startResearch`（非 template） | 不走 `quickStartResearch` | 零影响 |
| `sendMessage` 对话 | 同上 | 零影响 |

---

## 8. 审查对照总表

| 编号 | 严重度 | 摘要 | 修复 |
|------|--------|------|------|
| C1 | Critical | 连字符/下划线 | `template_id.replace('-', '_')` |
| C2 | Critical | 对话修改丢失 | `collectTemplateContext` + 后端 LLM 提取 |
| C3 | Critical | session 不一致 | `/template` 纯前端 |
| C4 | Critical | 消息合并丢失 | 批量 syncActive |
| C5 | Critical | Section 未传递 | session_data 补齐 aspects/sections/final_plan |
| C6 | Critical | S10 cancel 块在 template 外 | 通用 cancel 保持原消息，template 清理移入分支 |
| C7 | Critical | 前后端 section ID 体系不同 | Phase 1 用后端默认 sections，LLM 不提取 |
| I1 | Important | topic 提取 | 独立 `researchTopic` |
| I2 | Important | 刷新丢失 | session store 持久化 activeTemplateId |
| I3 | Important | 错误检测 | `data.error` throw |
| I4 | Important | 中英文混用 | 统一英文 |
| I5 | Important | handleOptionSelect 位置 | `start_research` 在 useResearch 内部 |
| I6 | Important | 中文提取无效 | LLM 驱动 |
| I7 | Important | 文本入口 | 按钮主入口 |
| I8 | Important | pending 重复消息 | `__pending__` 跳过合并 |
| I9 | Important | createSession 丢弃 template 字段 | subscription 中跨 session 保留 |
| I11 | Important | LLMSkill.generate() 不存在 | 改为 `execute()` + 手动 JSON 解析 |
| I12 | Important | Section 提取标记 Phase 2 | UI 标注 + LLM 不提取 sections |
| C8 | Critical | I9 subscription fix 导致递归循环 | 调换 setSessionId/createSession 顺序→无需 I9 fix |
| S17 | Suggestion | auto_confirm 返回 plan.aspects 用 YAML ID | 改用人类可读 `aspects` |
| S1 | Suggestion | fallback | 第 10 节 |
| S3 | Suggestion | autoConfirm passthrough | api.ts + useResearch.ts |
| S4 | Suggestion | 模板不存在 | `formatTemplateNotFound()` |
| S5 | Suggestion | reset 清理 | reset + clearResearch |
| S6 | Suggestion | require ESM | 顶部 `import` |
| S7 | Suggestion | 占位符 | `extractTemplateKeyword()` |
| S8 | Suggestion | 无条件按钮 | `researchTopic` 非空检查 |
| S9 | Suggestion | prompt 未更新 | 第 9 节 |
| S10 | Suggestion | running 冲突 | C6 修复 |
| S11 | Suggestion | 命名冲突 | useResearch 内统一处理 |
| S12 | Suggestion | Zustand 语法 | `syncActive` 与 `set` 分离 |
| S13 | Suggestion | `_build_execution_session` 未定义 | 统一内联 dict |
| S14 | Suggestion | autoConfirm 混入 parameters | 剥离控制字段 |
| S16 | Suggestion | 缺少依赖项 | 添加 deps |

---

## 9. conversation agent prompt（S9）

`prompts/agents/conversation.md` 新增：

```markdown
## Template Customization

When user selected a template via `/template`:
- Help them refine parameters (region, time_range, etc.)
- Acknowledge changes conversationally
- Phase 1 does not support section-level customization
- When user types "start research" → respond "Click 'Start Research' button"
```

---

## 10. Fallback（S1）

```typescript
if (autoConfirm && data.step === 4) {
  const paramData = await api.setParameters(data.session_id, params);
  await api.confirmResearch(data.session_id, true);
  setStatus('running');
  setStep(6, undefined);
}
```

---

## 11. 实施顺序

```
Step 0: C1 — 连字符 Bug（`template_id.replace('-', '_')`，1 行，可独立上线）
Step 1: #1, #2 — templates.ts + store（无 I9 subscription fix，保持简单订阅）
Step 2: #3 — ChatPanel（C6 fix: template 清理移入 isTemplateCommand 分支）
Step 3: #4 — useResearch（C4/I8 消息合并 + S14 剥离控制字段 + C8 setSessionId 提前）
Step 4: #6, #7, #5 — 后端（C5 session_data 补齐 + C7 默认 sections + I11 execute + S17 aspects）
Step 5: 端到端测试
```
