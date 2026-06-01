# LLM 配置持久化与后端同步设计方案

## 1. 问题陈述

### 1.1 当前行为

前端 LLM 配置面板的每一次输入变更都直接调用 `updateLLMConfig()`，该函数同时执行：
- 更新 Zustand store（内存状态）
- 保存至 localStorage（持久化）
- 通过 `debouncedSyncToBackend`（800ms 防抖）通知后端

但**刷新后后端回到 `.env` 默认值**，因为后端配置仅存于内存（module-level singleton），重启即丢失。后端在以下入口也接收 LLM 配置：
- `POST /api/v1/research/start`（对话式研究启动）
- `POST /api/v1/research/quick-start`（快捷研究启动）

聊天模式（`sendChatMessage` → `interact`）全程不带 LLM 参数，后端始终使用 `settings.llm` 中的值。若用户在当前会话中修改过配置，后端已通过 debounced sync 收到更新；但刷新后，后端丢失配置，聊天模式会回到默认值。

### 1.2 副作用

| 场景 | 表现 |
|------|------|
| 刷新浏览器 | 前端从 localStorage 恢复配置，后端回到 `.env` 默认值 |
| 重启桌面应用 | 同上 |
| 聊天模式发送消息 | 后端用默认配置（而非用户配置）调用 LLM |
| 多次修改未「固定」 | 每按一次键都写 localStorage，无意义 I/O |

### 1.3 设计目标

1. 用户显式「保存」配置，而不是每个按键触发写盘 + 网络请求
2. 保存时同步持久化：localStorage + 后端
3. 应用重启后自动将保存的配置推送给后端
4. 清晰的「已保存 / 未保存」状态反馈

---

## 2. 数据流架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Frontend (Browser)                          │
│                                                                     │
│  ┌───────────────────┐    updateLLMConfig()    ┌───────────────┐   │
│  │                   │ ───────────────────────▶ │               │   │
│  │  LLMConfigPanel   │   仅更新内存store        │  Zustand      │   │
│  │  (UI组件)          │                         │  Store        │   │
│  │                   │ ◀─────────────────────── │  (llm config) │   │
│  └───────────────────┘    useState 绑定         │               │   │
│                                                  │  + savedLlm  │   │
│       Save 按钮点击                               │  (快照)      │   │
│            │                                      └──────┬──────┘   │
│            │ persistLLMConfig()                          │          │
│            ▼                                              │          │
│  ┌──────────────────┐                                    │          │
│  │  localStorage    │ ◀──────────────────────────────────┘          │
│  │  (Zensers-       │   写入 JSON                                │
│  │   settings-v2)   │                                              │
│  └──────────────────┘                                              │
│            │                                                        │
│            │ POST /api/v1/llm/config (JSON body)                   │
│            ▼                                                        │
│  ┌──────────────────┐                                              │
│  │ fetch()          │                                              │
│  └──────────────────┘                                              │
└───────────────────────────────────┬─────────────────────────────────┘
                                    │ HTTP
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Backend (FastAPI)                            │
│                                                                     │
│  ┌──────────────────────────────────────────────┐                   │
│  │  POST /api/v1/llm/config                     │                   │
│  │  ──────────────────────────                  │                   │
│  │  接收 JSON: {provider, model, api_key, ...}  │                   │
│  │  调用 settings.update_from_request()          │                   │
│  │  返回当前生效配置                               │                   │
│  └────────────────────┬─────────────────────────┘                   │
│                       │ settings.llm 更新                           │
│                       ▼                                              │
│  ┌──────────────────────────────────────────────┐                   │
│  │  Module-level settings object                 │                   │
│  │  (src.config.settings)                        │                   │
│  │                                               │                   │
│  │  所有 LLM 调用都从此读取:                      │                   │
│  │  - generic_agent._call_llm_directly()         │                   │
│  │  - llm_judge                                  │                   │
│  │  - translation 等                             │                   │
│  └──────────────────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.1 重启恢复流程

```
Browser / Desktop App 启动
         │
         ▼
  getInitialState()
         │
         ├── localStorage 有数据 ──▶ 恢复 llm 配置
         │                           │
         │                           ▼
         │                    useEffect (on mount)
         │                           │
         │                           ▼
         │                    POST /api/v1/llm/config
         │                           │
         │                           ▼
         │                    后端同步完成，可正确调用LLM
         │
         └── localStorage 无数据 ──▶ GET /api/v1/llm/config
                                    从后端获取 .env 默认
                                    填充表单 + 设置 savedLlm
```

---

## 3. 状态模型

### 3.1 Zustand Store 新增状态

```typescript
// SettingsState 不再 extends AppSettings，改为包含所有字段
// 避免 AppSettings 和 SettingsState 的类型冲突
interface SettingsState {
  // === 以下字段来自 AppSettings（展开而非继承） ===
  llm: LLMConfig;
  theme: ThemeConfig;
  language: string;
  sendOnEnter: boolean;
  showTokenCount: boolean;
  autoSaveDraft: boolean;

  // === 新增状态字段 ===
  savedLlm: LLMConfig;                 // 最后一次保存的LLM配置快照
  isSaving: boolean;                   // 保存进行中（用于按钮loading）
  saveError: string | null;            // 保存失败的错误信息

  // === 已有业务字段 ===
  uploadedFiles: UploadedFile[];
  availableModels: LLMModel[];

  // === 方法 ===
  updateLLMConfig: (config: Partial<LLMConfig>) => void;
  persistLLMConfig: () => Promise<void>;
  applyBackendConfig: (config: BackendLLMConfig) => void;
  updateThemeConfig: (config: Partial<ThemeConfig>) => void;
  updateSettings: (settings: Partial<AppSettings>) => void;
  resetSettings: () => void;
  loadModels: () => Promise<void>;
  addUploadedFile: (file: UploadedFile) => void;
  updateUploadedFile: (id: string, updates: Partial<UploadedFile>) => void;
  removeUploadedFile: (id: string) => void;
  clearUploadedFiles: () => void;
  switchProvider: (provider: LLMConfig['provider']) => void;
}
```

### 3.2 派生状态（不存store，组件内计算）

```typescript
const hasUnsavedChanges = useMemo(
  () => JSON.stringify(llm) !== JSON.stringify(savedLlm),
  [llm, savedLlm]
);
```

### 3.3 保存按钮三段式状态

| `hasUnsavedChanges` | `isSaving` | `saveError` | 按钮文案 | 按钮行为 |
|---|---|---|---|---|
| `false` | `false` | `null` | "Saved" | disabled |
| `true` | `false` | `null` | "Save" | enabled，可点击 |
| - | `true` | - | "Saving..." | disabled + spinner |
| `true` | `false` | `"..."` | "Save" | enabled + 红色错误提示 |

---

## 4. 函数行为规格

### 4.1 `updateLLMConfig(config: Partial<LLMConfig>)`

**当前行为**（需修改）：
1. `set(state => ({ llm: { ...state.llm, ...config } }))`
2. `saveToStorage(get())`
3. `debouncedSyncToBackend(get().llm)`

**修改后行为**：
1. 仅：`set(state => ({ llm: { ...state.llm, ...config } }))`
2. 不再调 `saveToStorage`，不再调后端 sync

### 4.2 `persistLLMConfig()`

```typescript
async persistLLMConfig() {
  const current = get().llm;
  set({ isSaving: true, saveError: null });
  
  // Step 1: 写入 localStorage
  saveToStorage(get());
  
  // Step 2: 推送到后端
  try {
    const res = await fetch('/api/v1/llm/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider: current.provider,
        model: current.model,
        api_key: current.apiKey,
        api_endpoint: current.apiEndpoint,
        temperature: current.temperature,
        max_tokens: current.maxTokens,
        top_p: current.topP,
        frequency_penalty: current.frequencyPenalty,
        presence_penalty: current.presencePenalty,
      }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    
    // Step 3: 更新快照
    set({ savedLlm: { ...current }, isSaving: false });
  } catch (e) {
    set({ isSaving: false, saveError: String(e) });
  }
}
```

### 4.3 `getInitialState()` 加载逻辑（调整后）

返回类型改为 `SettingsState`，包含新增字段的默认值。

```typescript
// 为 getInitialState 定义完整的初始状态常量，
// 避免在函数体内重复 DEFAULT_SETTINGS 字段展开
const INITIAL_STATE: SettingsState = {
  llm: { ...DEFAULT_SETTINGS.llm },
  theme: { ...DEFAULT_SETTINGS.theme },
  language: DEFAULT_SETTINGS.language,
  sendOnEnter: DEFAULT_SETTINGS.sendOnEnter,
  showTokenCount: DEFAULT_SETTINGS.showTokenCount,
  autoSaveDraft: DEFAULT_SETTINGS.autoSaveDraft,
  savedLlm: { ...DEFAULT_SETTINGS.llm },      // 快照初始值与 llm 相同
  isSaving: false,
  saveError: null,
  uploadedFiles: [],
  availableModels: PRESET_MODELS,
  // 方法由 create() 填充，此处不定义
};

function getInitialState(): SettingsState {
  if (typeof window === 'undefined') {
    return { ...INITIAL_STATE };
  }
  
  const persisted = loadFromStorage();
  if (!persisted || typeof persisted.llm !== 'object') {
    // 数据损坏，清除
    if (persisted) try { localStorage.removeItem(STORAGE_KEY); } catch {}
    return { ...INITIAL_STATE };
  }
  
  const mergedLlm = { ...DEFAULT_SETTINGS.llm, ...persisted.llm };
  return {
    ...INITIAL_STATE,
    llm: mergedLlm,
    savedLlm: mergedLlm,       // 从 localStorage 恢复后视为已保存
    theme: { ...DEFAULT_SETTINGS.theme, ...(persisted.theme || {}) },
    language: persisted.language ?? DEFAULT_SETTINGS.language,
    sendOnEnter: persisted.sendOnEnter ?? DEFAULT_SETTINGS.sendOnEnter,
    showTokenCount: persisted.showTokenCount ?? DEFAULT_SETTINGS.showTokenCount,
    autoSaveDraft: persisted.autoSaveDraft ?? DEFAULT_SETTINGS.autoSaveDraft,
  };
}
```

### 4.4 新增 action：`applyBackendConfig(config)`

解决 `loadBackendConfig` 中无法直接调 `set()` 的问题（LLMConfigPanel 拿不到 store 的 set 引用）。

```typescript
// 在 store 中新增，原子性地设置 llm + savedLlm
applyBackendConfig(config: BackendLLMConfig) {
  set({
    llm: {
      provider: config.provider as LLMProvider,
      model: config.model,
      apiKey: config.apiKey,
      apiEndpoint: config.apiEndpoint,
      temperature: config.temperature,
      maxTokens: config.maxTokens,
      topP: config.topP,
      frequencyPenalty: config.frequencyPenalty,
      presencePenalty: config.presencePenalty,
    },
    savedLlm: {
      provider: config.provider as LLMProvider,
      model: config.model,
      apiKey: config.apiKey,
      apiEndpoint: config.apiEndpoint,
      temperature: config.temperature,
      maxTokens: config.maxTokens,
      topP: config.topP,
      frequencyPenalty: config.frequencyPenalty,
      presencePenalty: config.presencePenalty,
    },
  });
}
```

### 4.5 首次访问（无 localStorage）的数据流

在 `LLMConfigPanel.tsx` 的 `loadBackendConfig` 中，首次访问时不再调 `updateLLMConfig`（旧行为），改为调 `applyBackendConfig`：

```typescript
// 修改后：通过 store action 一次性设置 llm + savedLlm
applyBackendConfig(config);
```

注意：首次访问存在**一次渲染闪烁**——`getInitialState()` 先返回 `DEFAULT_SETTINGS`（默认值）渲染首帧，随后 `useEffect` 异步加载后端配置后更新为真实值。这是可接受的，因为：
- 后端配置加载通常在 100-300ms 内完成
- LLMConfigPanel 是设置面板，非首屏关键路径
- 若未来需要消除闪烁，可在 SSR 阶段注入后端配置

### 4.6 `switchProvider` 行为调整

当前：
```
set + 清空 apiKey + saveToStorage(get()) + syncToBackend(get().llm)（立即同步，非防抖）
```

修改后（仅内存更新，不再自动存盘）：
```
set + 清空 apiKey
// 不复 saveToStorage，不复调后端 sync
```

用户切换 provider 后必须手动点 Save 才会持久化。刷新页面将恢复为上次保存的 provider。

---

## 5. UI 交互规格

### 5.1 LLMConfigPanel 改动

在 Card 底部（`</CardContent>` 前）增加保存区域：

```
┌─────────────────────────────────────────┐
│  LLM Configuration                      │
│                                         │
│  [Provider 下拉]                         │
│  [API Endpoint 输入框]                   │
│  [API Key 输入框]                        │
│  [Model 选择/输入]                       │
│                                         │
│  ────────────────────────────────────   │
│  [Save Button]    "Settings saved" ✓    │  ← 新增区域
│  ────────────────────────────────────   │
└─────────────────────────────────────────┘
```

### 5.2 Save 按钮详细行为

| 交互 | 行为 |
|------|------|
| 页面加载完成，配置 = savedLlm | 按钮灰色，"Saved"，disabled |
| 用户修改任意字段 | `updateLLMConfig()` → `hasUnsavedChanges = true` → 按钮蓝色 "Save"，enabled |
| 用户再次改回保存状态 | 如果 `llm === savedLlm` → 按钮恢复灰色 "Saved" |
| 点击 Save | 立即 disabled + spinner；调 `persistLLMConfig()` |
| 保存成功 | 按钮灰色 "Saved"；`savedLlm = llm` |
| 保存失败 | 按钮恢复蓝色 "Save"；红色错误提示（5秒后自动消失） |
| 组件卸载时（关闭面板） | 如果有 unsaved changes → 控制台 warn，丢弃 |

### 5.3 错误处理

```
[Save] 点击
   │
   ├── 网络错误 ──▶ set({ saveError: '无法连接到后端服务' })
   │                  5秒后自动清除
   │
   ├── HTTP 4xx/5xx ──▶ set({ saveError: '后端拒绝配置: ...' })
   │                     5秒后自动清除
   │
   └── 成功 ──▶ set({ savedLlm, isSaving: false })
                 按钮恢复 "Saved"
```

---

## 6. 涉及文件与改动范围

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `web/src/store/useSettingsStore.ts` | 修改 | 将 `SettingsState` 改为独立接口（不再 `extends AppSettings`）；新增 `savedLlm`、`isSaving`、`saveError` 字段；新增 `persistLLMConfig()`、`applyBackendConfig()` action；重写 `getInitialState()` 返回 `SettingsState`；修改 `updateLLMConfig` 去掉自动存盘和后端 sync；修改 `switchProvider` 去掉自动存盘；新增 `INITIAL_STATE` 常量 |
| `web/src/components/settings/LLMConfigPanel.tsx` | 修改 | 增加 Save 按钮、unsaved indicator、loading spinner、错误提示；`loadBackendConfig` 首次访问改调 `applyBackendConfig`（而非 `updateLLMConfig`）；新增 `useEffect` 用于重启后自动向后端推送已保存配置 |
| `src/api/main.py` | 已完成 | `POST /api/v1/llm/config` 已实现 |

### 6.1 不涉及的改动

- `web/src/lib/api.ts`：不需要改，用原生 `fetch` 即可
- `web/src/types/settings.ts`：不需要改（`AppSettings` 保持不变）
- `web/src/components/chat/ChatInput.tsx`：不需要改（`updateLLMConfig` 签名不变，但行为变为仅内存更新——用户在 ChatInput 顶部切换模型不再自动保存，需在 LLMConfigPanel 中手动 Save）
- 其他 `*.py` 文件：不需要改

---

## 7. 迁移策略

### 7.1 兼容性

- 现有 localStorage 数据的格式不变，向后兼容
- `updateLLMConfig` 签名不变，已有调用方无需改代码
- 后端 `POST /api/v1/llm/config` 已上线，旧版前端调用不失败

### 7.2 风险点

| 风险 | 缓解措施 |
|------|----------|
| `ChatInput.tsx` 的 `handleModelChange` 调 `updateLLMConfig`，用户选择模型后不会自动保存 | 用户在 Panel 中统一保存即可；ChatInput 的模型选择用于即时聊天，不要求持久化 |
| `switchProvider` 不再自动保存，切换后刷新会丢失 | 这是设计意图——切换后用户必须手动保存才会持久化 |
| 用户忘了保存就关闭页面 | 组件卸载时检测 `hasUnsavedChanges` 并 warn；可后续考虑 `beforeunload` 拦截 |
| 首次访问渲染闪烁：`getInitialState()` 先返回默认值，异步加载后端配置后更新 | 可接受：LLMConfigPanel 非关键路径，后端加载通常在 100-300ms 内完成；未来可在 SSR 阶段注入后端配置来消除 |

---

## 8. 验收标准

1. 修改 LLM 配置后刷新页面，配置恢复到 **上一次保存** 的值（而非最新编辑的值）
2. 修改配置后不点 Save，启动新聊天 → 后端使用 **旧配置**（非用户编辑中的值）
3. 点击 Save → localStorage 写入 + 后端更新 → 启动新聊天 → 后端使用 **新配置**
4. 重启应用（浏览器/桌面）→ 前端从 localStorage 恢复 → 自动推送给后端 → 聊天正常使用新配置
5. 首次访问无 localStorage → 从后端获取 .env 默认配置 → 填充表单
6. Save 按钮在保存成功时灰色禁用，有未保存修改时蓝色可点
