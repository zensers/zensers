# Zensers Web Frontend - Detailed Design Document (V4 - Production Ready)

> React + Next.js + TypeScript Frontend for Zensers Market Report System
>
> **V4 Changes**: HTML preview static serving + full assistant-ui runtime adapter + scroll behavior + session persistence + history loading + preview zoom fix

---

## 1. Architecture Overview

### 1.1 Tech Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| Next.js | 14.x | Full-stack framework (App Router) |
| React | 18.x | UI components |
| TypeScript | 5.x | Type safety |
| Tailwind CSS | 3.x | Styling |
| **assistant-ui** | latest | AI chat UI (`useExternalStoreRuntime` + `<Thread />`) |
| **react-resizable-panels** | latest | Resizable panel layout |
| Zustand | 4.x | State management (+ persist middleware) |
| **SSE (EventSource)** | native | Real-time progress |

### 1.2 Changes from V3

| Issue | V3 Problem | V4 Fix |
|-------|------------|--------|
| HTML preview (iframe) | Backend returns local file path, not URL | **StaticFiles mount** in FastAPI + fixed URL generation |
| assistant-ui integration | `useExternalStoreRuntime` only had a comment stub | **Full RuntimeProvider** adapter + `AssistantRuntimeProvider` wrapper |
| Chat scroll behavior | assistant-ui `<Thread />` auto-scroll not configured | **`useChatScroll` hook**: auto-scroll, user up-scroll detection, scroll-to-bottom button |
| Session persistence | Zustand is pure memory, refresh loses everything | **`zustand/middleware` persist**: localStorage for sessionId/step/taskId |
| History session loading | No way to view past research | **`SessionList` component** + `useHistorySessions` hook |
| Preview zoom | `transform:scale` on parent with `overflow:auto` breaks scrollbars | **Wrapper div `width/height`反算** + `transform-origin:top left` |
| Missing component interfaces | SectionSelector/ParameterForm/ConfirmPanel referenced but not defined | **Full Props interfaces** documented |
| docx-preview dependency | Included but never used | **Removed** |

---

## 2. Project Structure

```
web/
├── src/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx                  # Single page + session restore check
│   │   └── globals.css
│   │
│   ├── components/
│   │   ├── ui/                       # shadcn/ui
│   │   ├── chat/
│   │   │   ├── ChatPanel.tsx         # RuntimeProvider + Thread + step overlays
│   │   │   ├── RuntimeProvider.tsx   # V4: assistant-ui adapter (Zustand ↔ Thread)
│   │   │   ├── OptionSelector.tsx    # Data-driven, per-step
│   │   │   ├── SectionSelector.tsx   # Step 3: multi-select checkboxes
│   │   │   ├── ParameterForm.tsx     # Step 4: region/time/depth form
│   │   │   └── ConfirmPanel.tsx      # Step 5: summary + confirm/back
│   │   ├── progress/
│   │   │   └── ProgressPanel.tsx
│   │   ├── preview/
│   │   │   └── DocumentPreview.tsx   # Wrapper-scale zoom (V4 fix)
│   │   ├── sidebar/
│   │   │   └── SessionList.tsx       # V4: history research list
│   │   └── layout/
│   │       └── MainLayout.tsx
│   │
│   ├── lib/
│   │   ├── api.ts                    # Interceptors + retry + history methods
│   │   ├── sse.ts                    # Event-based SSE
│   │   └── utils.ts
│   │
│   ├── hooks/
│   │   ├── useResearch.ts            # Step handling
│   │   ├── useProgress.ts            # SSE + polling fallback
│   │   ├── usePreview.ts             # Simple fetch
│   │   ├── useChatScroll.ts          # V4: auto-scroll with user-detection
│   │   └── useHistorySessions.ts     # V4: load completed research list
│   │
│   ├── store/
│   │   ├── useResearchStore.ts       # V4: + persist middleware (localStorage)
│   │   └── useChatStore.ts           # V4: messages + addMessage action
│   │
│   └── types/
│       └── api.ts                    # V4: + ResearchResultMeta, component interfaces
│
├── package.json
└── ...
```

---

## 3. TypeScript Types (V4)

```typescript
// types/api.ts

// ============ Preview Format ============

export type ResearchPreviewFormat = 'html' | 'pdf' | 'png';
export type DocumentPreviewFormat = 'png' | 'jpg' | 'pdf';

export interface PreviewResponse {
  task_id: string;
  preview_url: string;      // V4: "/api/v1/previews/ses_xxx_preview.html"
  preview_path: string;
  preview_format: ResearchPreviewFormat | DocumentPreviewFormat;
  cached: boolean;
  file_size: number;
}

// ============ API Request/Response Types (P0-3 Fix) ============

/** POST /api/v1/research/start 响应 */
export interface StartResearchResponse {
  session_id: string;
  step: number;
  message: string;
  instruction: string;
  options: SelectOption[];
  next_step: string;
}

/** POST /api/v1/research/interact 请求 */
export interface InteractRequest {
  session_id: string;
  step: number;
  response: Record<string, any>;
}

// ============ Step-Specific Request Types ============

export interface Step1Request { output_type: string; }
export interface Step2Request { template_id: string; }
export interface Step3Request { selected_sections: string[]; }
export interface Step4Request { region: string; time_range: string; depth: string; focus_areas?: string; }
export interface Step5Request { confirmed: boolean; }

// ============ Common Types ============

export interface SelectOption {
  id: string;
  label: string;
  description?: string;
  icon?: string;
  disabled?: boolean;   // required section → disabled checkbox
  selected?: boolean;
}

export interface InteractResponse {
  session_id: string;
  step: number;
  message: string;
  instruction: string;
  next_step: string;
  options?: SelectOption[];
  templates?: Template[];
  sections?: Section[];
  parameters?: ParameterConfig;
  summary?: ResearchSummary;
  final_plan?: ResearchPlan;
  status?: 'executing' | 'cancelled';
}

export interface ParameterConfig {
  regions: SelectOption[];
  time_ranges: SelectOption[];
  depths: SelectOption[];
}

export interface Section {
  id: string;
  title: string;
  description?: string;
  required: boolean;
  selected: boolean;
}

export interface Template {
  id: string;
  name: string;
  description: string;
  preview_image?: string;
}

export interface ResearchSummary {
  topic: string;
  output_type: string;
  template: string;
  sections: string[];
  parameters: Record<string, string>;
}

export interface ResearchPlan {
  topic: string;
  phases: Phase[];
  estimated_time: string;
}

export interface Phase {
  id: string;
  name: string;
  tasks: string[];
  estimated_time: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  progress: number;
}

// ============ SSE Types ============

export interface SSEMessage {
  event: 'progress' | 'phase_start' | 'phase_complete' | 'error' | 'complete';
  data: ProgressData | PhaseData | ErrorData | CompleteData;
}

export interface ProgressData {
  task_id: string; phase_id: string; progress: number; message: string; timestamp: string;
}
export interface PhaseData {
  task_id: string; phase_id: string; phase_name: string; status: string; timestamp: string;
}
export interface ErrorData {
  task_id: string; code: string; message: string; details?: any;
}
export interface CompleteData {
  task_id: string; output_path: string; sections: SectionResult[]; statistics: ResearchStatistics;
}
export interface SectionResult { id: string; title: string; word_count: number; charts: number; }
export interface ResearchStatistics { total_words: number; total_charts: number; data_sources: number; execution_time: number; }

// ============ Document API Types ============

export interface GenerateDocumentRequest {
  task_id: string;
  output_format: 'docx' | 'pptx' | 'pdf' | 'html';
  template: 'consulting' | 'academic' | 'business' | 'minimal';
}
export interface Version { version_id: string; created_at: string; file_size?: number; changes?: string; }
export interface RevisionRequest {
  task_id: string; revision_type: 'minor' | 'section' | 'phase' | 'full';
  user_feedback: string; section_id?: string; section_title?: string; keywords?: string[]; target_content?: string;
}

// ============ V4 新增：历史会话 ============

/** 后端 ResearchResultStore 返回的研究元数据 */
export interface ResearchResultMeta {
  task_id: string;
  title: string;
  topic: string;
  status: 'analyzing' | 'collecting' | 'reporting' | 'completed' | 'document_pending' | 'document_generated';
  created_at: string | null;
  completed_at: string | null;
  output_format?: string;
  generated_formats?: string[];
  user_id?: string;
}

// ============ V4 新增：消息类型 ============

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

// ============ V4 新增：Step 组件 Props 接口 ============

export interface SectionSelectorProps {
  sections: (SelectOption & { required?: boolean })[];
  onConfirm: (selectedIds: string[]) => void;
  disabled?: boolean;
}

export interface ParameterFormProps {
  config: ParameterConfig;
  onSubmit: (params: { region: string; time_range: string; depth: string; focus_areas?: string }) => void;
  disabled?: boolean;
}

export interface ConfirmPanelProps {
  summary: ResearchSummary;
  onConfirm: () => void;
  onBack: () => void;
  disabled?: boolean;
}
```

---

## 4. Backend Additions (V4: Preview Static Files)

### 4.1 FastAPI Static File Mounting

```python
# src/api/main.py — V4 新增：预览文件静态服务

from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from src.api.research_api import ResearchAPI
from src.api.document_api import DocumentAPI, DocumentAPIRouter

app = FastAPI(title="Zensers API", version="1.0.0")

# ========== V4: Preview 静态文件服务 ==========
# PreviewGenerator 输出 HTML 到 data/previews/{task_id}_preview.html
# 挂载为 /api/v1/previews/，供前端 iframe 直接访问
_preview_dir = Path("data/previews")
_preview_dir.mkdir(parents=True, exist_ok=True)
app.mount("/api/v1/previews", StaticFiles(directory=str(_preview_dir)), name="previews")

# ========== Research API ==========
research_api = ResearchAPI()

@app.post("/api/v1/research/start")
async def start_research(user_input: str, user_id: str = None):
    return await research_api.start_research(user_input, user_id)

@app.post("/api/v1/research/interact")
async def interact(session_id: str, step: int, response: dict):
    return await research_api.handle_interact(session_id, step, response)

@app.post("/api/v1/research/feedback")
async def feedback(session_id: str, action: str, section: str = None, adjustment: str = None):
    return await research_api.handle_feedback(session_id, action, section, adjustment)

@app.get("/api/v1/research/preview/{task_id}")
async def get_preview(task_id: str, format: str = "html"):
    return await research_api.get_preview(task_id, format)

# ========== Document API ==========
document_api = DocumentAPI()
router = DocumentAPIRouter(document_api).get_router()
if router:
    app.include_router(router, prefix="/api/v1")

@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}
```

### 4.2 Fix `research_api.py` preview URL

```python
# src/api/research_api.py — get_preview 方法

async def get_preview(self, task_id: str, format: str = "html") -> Dict[str, Any]:
    # ... 现有预览生成逻辑（写入 data/previews/{filename}） ...

    # V4: 返回的 preview_url 是相对路径，由 StaticFiles 提供
    import os
    filename = os.path.basename(preview_path)  # "ses_abc123_preview.html"

    return {
        "task_id": task_id,
        "preview_url": f"/api/v1/previews/{filename}",  # ✅ 浏览器可访问
        "preview_path": preview_path,
        "preview_format": "html",
        "cached": preview.cached,
        "file_size": preview.file_size,
    }
```

**完整数据流：**
```
PreviewGenerator  →  data/previews/ses_X_preview.html
research_api      →  JSON { preview_url: "/api/v1/previews/ses_X_preview.html" }
前端 iframe       →  src="/api/v1/previews/ses_X_preview.html"
FastAPI           →  StaticFiles 读取磁盘文件 → 200 OK ✅
```

---

## 5. API Client (V4)

```typescript
// lib/api.ts

import axios, { AxiosInstance, AxiosError } from 'axios';
import type {
  StartResearchResponse, InteractRequest, InteractResponse,
  PreviewResponse, Step1Request, Step2Request, Step3Request,
  Step4Request, Step5Request, ResearchResultMeta,
} from '@/types/api';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export class ApiError extends Error {
  constructor(public code: string, message: string, public status?: number, public details?: any) {
    super(message); this.name = 'ApiError';
  }
}

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({ baseURL: API_BASE_URL, timeout: 30000, headers: { 'Content-Type': 'application/json' } });
    this.setupInterceptors();
  }

  private setupInterceptors() {
    this.client.interceptors.request.use(
      (config) => { const t = localStorage.getItem('auth_token'); if (t) config.headers.Authorization = `Bearer ${t}`; return config; },
      (e) => Promise.reject(e)
    );
    this.client.interceptors.response.use(
      (r) => r,
      async (error: AxiosError) => {
        const { response, config } = error;
        if (response?.status === 401) throw new ApiError('UNAUTHORIZED', '请重新登录', 401);
        if (response?.status === 429) {
          const c = (config as any)._retryCount || 0;
          if (c < 3) { await new Promise(r => setTimeout(r, Math.pow(2, c) * 1000)); (config as any)._retryCount = c + 1; return this.client.request(config!); }
          throw new ApiError('RATE_LIMITED', '请求过于频繁', 429);
        }
        if (response?.status && response.status >= 500) {
          const c = (config as any)._retryCount || 0;
          if (c < 1) { (config as any)._retryCount = 1; await new Promise(r => setTimeout(r, 1000)); return this.client.request(config!); }
          throw new ApiError('SERVER_ERROR', '服务器错误', response.status);
        }
        if (!response) throw new ApiError('NETWORK_ERROR', '网络连接失败');
        const d = response.data as any;
        throw new ApiError(d?.error_code || 'UNKNOWN_ERROR', d?.error || '请求失败', response.status, d?.details);
      }
    );
  }

  // ========== Research API ==========
  async startResearch(input: string, userId?: string): Promise<StartResearchResponse> {
    const { data } = await this.client.post('/api/v1/research/start', { user_input: input, user_id: userId });
    return data;
  }
  async interact(request: InteractRequest): Promise<InteractResponse> {
    const { data } = await this.client.post('/api/v1/research/interact', request);
    return data;
  }
  async selectOutputType(sid: string, t: string) { return this.interact({ session_id: sid, step: 1, response: { output_type: t } }); }
  async selectTemplate(sid: string, t: string) { return this.interact({ session_id: sid, step: 2, response: { template_id: t } }); }
  async selectSections(sid: string, ids: string[]) { return this.interact({ session_id: sid, step: 3, response: { selected_sections: ids } }); }
  async setParameters(sid: string, p: { region: string; time_range: string; depth: string; focus_areas?: string }) { return this.interact({ session_id: sid, step: 4, response: p }); }
  async confirmResearch(sid: string, c: boolean) { return this.interact({ session_id: sid, step: 5, response: { confirmed: c } }); }

  // ========== Preview API ==========
  async getResearchPreview(taskId: string, format: 'html' | 'pdf' | 'png' = 'html'): Promise<PreviewResponse> {
    const { data } = await this.client.get(`/api/v1/research/preview/${taskId}`, { params: { format } });
    return data;
  }

  // ========== Export ==========
  async exportDocument(taskId: string, versionId: string, format: string): Promise<Blob> {
    const { data } = await this.client.post('/api/v1/documents/export',
      { task_id: taskId, version_id: versionId, format }, { responseType: 'blob' });
    return data;
  }

  // ========== V4: History ==========
  async listCompletedResearch(limit = 50): Promise<ResearchResultMeta[]> {
    const { data } = await this.client.get('/api/v1/research/completed', { params: { limit } });
    return data;
  }

  // ========== V4: Session Validation ==========
  async validateSession(sessionId: string): Promise<boolean> {
    try { await this.client.get(`/api/v1/research/session/${sessionId}`); return true; }
    catch { return false; }
  }
}

export const api = new ApiClient();
export default api;
```

---

## 6. SSE Manager (Unchanged from V3)

```typescript
// lib/sse.ts

import type { SSEMessage } from '@/types/api';

type ProgressCallback = (message: SSEMessage) => void;
type ConnectionCallback = (connected: boolean) => void;

class SSEManager {
  private connections: Map<string, EventSource> = new Map();
  private callbacks: Map<string, Set<ProgressCallback>> = new Map();
  private connectionCallbacks: Map<string, Set<ConnectionCallback>> = new Map();

  subscribe(taskId: string, onProgress: ProgressCallback, onConnection?: ConnectionCallback): () => void {
    if (!this.callbacks.has(taskId)) this.callbacks.set(taskId, new Set());
    this.callbacks.get(taskId)!.add(onProgress);
    if (onConnection) {
      if (!this.connectionCallbacks.has(taskId)) this.connectionCallbacks.set(taskId, new Set());
      this.connectionCallbacks.get(taskId)!.add(onConnection);
    }
    if (!this.connections.has(taskId)) this.createConnection(taskId);
    return () => {
      const cbs = this.callbacks.get(taskId), ccs = this.connectionCallbacks.get(taskId);
      if (cbs) cbs.delete(onProgress);
      if (ccs && onConnection) ccs.delete(onConnection);
      if (!cbs?.size && !ccs?.size) this.close(taskId);
    };
  }

  private createConnection(taskId: string) {
    // P1-10 Fix: 规范化 base URL，避免双斜杠
    const baseUrl = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '');
    const es = new EventSource(`${baseUrl}/api/v1/stream/${taskId}`);
    es.onopen = () => this.notifyConnection(taskId, true);
    es.onerror = () => this.notifyConnection(taskId, false);
    es.onmessage = (event) => {
      try {
        const msg: SSEMessage = JSON.parse(event.data);
        this.notifyProgress(taskId, msg);
        if (msg.event === 'complete' || msg.event === 'error') this.close(taskId);
      } catch (e) { console.error('SSE parse error:', e); }
    };
    this.connections.set(taskId, es);
  }

  private notifyProgress(taskId: string, msg: SSEMessage) { this.callbacks.get(taskId)?.forEach(cb => cb(msg)); }
  private notifyConnection(taskId: string, connected: boolean) { this.connectionCallbacks.get(taskId)?.forEach(cb => cb(connected)); }
  private close(taskId: string) {
    this.connections.get(taskId)?.close();
    this.connections.delete(taskId);
    this.callbacks.delete(taskId);
    this.connectionCallbacks.delete(taskId);
  }
  closeAll() { this.connections.forEach(es => es.close()); this.connections.clear(); this.callbacks.clear(); this.connectionCallbacks.clear(); }
}

export const sseManager = new SSEManager();
```

---

## 6.5 P1-5 Fix: Utils Library

```typescript
// lib/utils.ts

import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

// Tailwind class 合并工具
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * P1-5 Fix: 距离现在的时间描述
 * 
 * 格式化为易读的相对时间，如 "5分钟前"、"2小时前"、"3天前"
 */
export function formatDistanceToNow(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  
  if (diffMs < 0) return '刚刚';
  
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);
  const diffWeeks = Math.floor(diffDays / 7);
  const diffMonths = Math.floor(diffDays / 30);
  const diffYears = Math.floor(diffDays / 365);

  if (diffSeconds < 60) return '刚刚';
  if (diffMinutes < 60) return `${diffMinutes}分钟前`;
  if (diffHours < 24) return `${diffHours}小时前`;
  if (diffDays < 7) return `${diffDays}天前`;
  if (diffWeeks < 4) return `${diffWeeks}周前`;
  if (diffMonths < 12) return `${diffMonths}个月前`;
  if (diffYears < 10) return `${diffYears}年前`;
  
  return date.toLocaleDateString('zh-CN');
}

/**
 * 格式化文件大小
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

/**
 * 格式化执行时间
 */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}秒`;
  const minutes = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  if (minutes < 60) return secs > 0 ? `${minutes}分${secs}秒` : `${minutes}分钟`;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return mins > 0 ? `${hours}小时${mins}分钟` : `${hours}小时`;
}
```

---

## 7. Hooks

### 7.1 useResearch Hook (Unchanged from V3)

```typescript
// hooks/useResearch.ts — 步骤处理逻辑，与 V3 一致

import { useCallback, useState } from 'react';
import { useResearchStore } from '@/store/useResearchStore';
import { api, ApiError } from '@/lib/api';

export function useResearch() {
  const { sessionId, currentStep, setSessionId, setStep, setTaskId, setPhases, setStatus, setSummary, reset } = useResearchStore();
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const startResearch = useCallback(async (input: string) => {
    setIsProcessing(true); setError(null);
    try {
      const data = await api.startResearch(input);
      setSessionId(data.session_id);
      setStep(data.step, data.options);
      return data;
    } catch (e) { setError(e as ApiError); throw e; }
    finally { setIsProcessing(false); }
  }, [setSessionId, setStep]);

  const selectOutputType = useCallback(async (outputType: string) => {
    if (!sessionId) return;
    setIsProcessing(true); setError(null);
    try {
      const data = await api.selectOutputType(sessionId, outputType);
      setStep(data.step, data.options || data.templates?.map(t => ({ id: t.id, label: t.name, description: t.description })));
      return data;
    } catch (e) { setError(e as ApiError); throw e; }
    finally { setIsProcessing(false); }
  }, [sessionId, setStep]);

  const selectTemplate = useCallback(async (templateId: string) => {
    if (!sessionId) return;
    setIsProcessing(true); setError(null);
    try {
      const data = await api.selectTemplate(sessionId, templateId);
      // P1-6 Fix: 保留 required 字段，供 SectionSelector 使用
      setStep(data.step, data.sections?.map(s => ({
        id: s.id,
        label: s.title,
        description: s.description,
        selected: s.selected,
        disabled: s.required,
        required: s.required,  // ✅ 新增: 保留 required 字段
      })));
      return data;
    } catch (e) { setError(e as ApiError); throw e; }
    finally { setIsProcessing(false); }
  }, [sessionId, setStep]);

  const selectSections = useCallback(async (sectionIds: string[]) => {
    if (!sessionId) return;
    setIsProcessing(true); setError(null);
    try {
      const data = await api.selectSections(sessionId, sectionIds);
      if (data.parameters) { setStep(data.step, undefined); useResearchStore.getState().setParameterConfig(data.parameters); }
      else setStep(data.step, data.options);
      return data;
    } catch (e) { setError(e as ApiError); throw e; }
    finally { setIsProcessing(false); }
  }, [sessionId, setStep]);

  const setParameters = useCallback(async (params: { region: string; time_range: string; depth: string; focus_areas?: string }) => {
    if (!sessionId) return;
    setIsProcessing(true); setError(null);
    try {
      const data = await api.setParameters(sessionId, params);
      if (data.summary) setSummary(data.summary);
      setStep(data.step, [
        { id: 'confirm', label: '确认开始', description: '开始执行研究任务' },
        { id: 'back', label: '返回修改', description: '调整参数设置' },
      ]);
      return data;
    } catch (e) { setError(e as ApiError); throw e; }
    finally { setIsProcessing(false); }
  }, [sessionId, setStep, setSummary]);

  const confirmResearch = useCallback(async (confirmed: boolean) => {
    if (!sessionId) return;
    setIsProcessing(true); setError(null);
    try {
      const data = await api.confirmResearch(sessionId, confirmed);
      if (confirmed && data.step === 6 && data.status === 'executing') {
        setTaskId(data.session_id); setStatus('running');
        if (data.final_plan) setPhases(data.final_plan.phases.map(p => ({ ...p, status: 'pending' as const, progress: 0 })));
      }
      // P1-9 Fix: 如果用户点"返回修改"，回到参数步骤而非销毁会话
      if (!confirmed && data.step === 6 && data.status === 'cancelled') {
        // 重新开始而不是卡住
        reset();
        return data;
      }
      setStep(data.step, undefined);
      return data;
    } catch (e) { setError(e as ApiError); throw e; }
    finally { setIsProcessing(false); }
  }, [sessionId, setTaskId, setStatus, setPhases, setStep, reset]);

  // ============ P0-2 Fix: 添加缺失的函数 ============

  /** 统一发送消息入口 - 供 RuntimeProvider 使用 */
  const sendMessage = useCallback(async (text: string) => {
    if (!sessionId) {
      // 新会话：启动研究
      return startResearch(text);
    }
    // 已有会话：当前设计不支持自由文本输入，忽略
    console.warn('sendMessage called with existing session - text input not supported in multi-step flow');
    return null;
  }, [sessionId, startResearch]);

  /** 通用选项处理 - 根据 currentStep 分发到对应处理函数 */
  const handleOptionSelect = useCallback(async (optionId: string) => {
    switch (currentStep) {
      case 1:
        return selectOutputType(optionId);
      case 2:
        return selectTemplate(optionId);
      case 5:
        // optionId 为 'confirm' 或 'back'
        return confirmResearch(optionId === 'confirm');
      default:
        console.warn('handleOptionSelect called at unexpected step:', currentStep);
        return null;
    }
  }, [currentStep, selectOutputType, selectTemplate, confirmResearch]);

  return {
    startResearch,
    selectOutputType,
    selectTemplate,
    selectSections,
    setParameters,
    confirmResearch,
    reset,
    // P0-2 Fix: 新增导出
    sendMessage,
    handleOptionSelect,
    // 状态
    isProcessing,
    error,
    sessionId,
    currentStep,
  };
}
```

### 7.2 useProgress Hook (V4: Fixed Fallback)

```typescript
// hooks/useProgress.ts

import { useEffect, useState } from 'react';
import { useResearchStore } from '@/store/useResearchStore';
import { sseManager } from '@/lib/sse';
import type { SSEMessage, ProgressData, PhaseData, CompleteData } from '@/types/api';

/**
 * 研究进度订阅
 *
 * ⚠️ 后端依赖: /api/v1/stream/{task_id} SSE 端点
 *
 * SSE 不可用时的降级策略:
 * 标注为 "无 SSE 无法工作"——后端没有 polling 回退端点。
 * 前端表现为: isConnected=false, progress 不更新, 但 status 仍然从 REST API 获知。
 */
export function useProgress(taskId: string | null) {
  const { setProgress, updatePhase, setStatus, setStatistics } = useResearchStore();
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    if (!taskId) return;

    const unsubscribe = sseManager.subscribe(
      taskId,
      (message: SSEMessage) => {
        switch (message.event) {
          case 'progress': {
            const d = message.data as ProgressData;
            setProgress(d.progress); updatePhase(d.phase_id, { progress: d.progress });
            break;
          }
          case 'phase_start': updatePhase((message.data as PhaseData).phase_id, { status: 'running' }); break;
          case 'phase_complete': updatePhase((message.data as PhaseData).phase_id, { status: 'completed', progress: 100 }); break;
          case 'complete': { const d = message.data as CompleteData; setStatus('completed'); setProgress(100); setStatistics(d.statistics); break; }
          case 'error': setStatus('error'); break;
        }
      },
      (connected) => { setIsConnected(connected); }
    );

    return unsubscribe;
  }, [taskId, setProgress, updatePhase, setStatus, setStatistics]);

  return { isConnected };
}
```

### 7.3 usePreview Hook (V4: Pending State)

```typescript
// hooks/usePreview.ts

import { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import type { PreviewResponse } from '@/types/api';

interface UsePreviewOptions {
  taskId: string | null;
  enabled?: boolean;
  format?: 'html' | 'pdf' | 'png';
}

export function usePreview(options: UsePreviewOptions): {
  preview: PreviewResponse | null;
  isLoading: boolean;
  isPending: boolean;   // V4: enabled=true but no data yet
  error: Error | null;
  refetch: () => void;
} {
  const { taskId, enabled = true, format = 'html' } = options;
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [hasFetched, setHasFetched] = useState(false);

  const fetchPreview = useCallback(async () => {
    if (!taskId || !enabled) return;
    setIsLoading(true); setError(null); setHasFetched(true);
    try {
      const data = await api.getResearchPreview(taskId, format);
      setPreview(data);
    } catch (e) { setError(e as Error); }
    finally { setIsLoading(false); }
  }, [taskId, enabled, format]);

  useEffect(() => { fetchPreview(); }, [fetchPreview]);

  return {
    preview,
    isLoading,
    isPending: enabled && !hasFetched && !isLoading,  // V4: "正在加载" vs "暂无数据"
    error,
    refetch: fetchPreview,
  };
}
```

### 7.4 V4 New: useChatScroll Hook

```typescript
// hooks/useChatScroll.ts

import { useEffect, useRef, useCallback } from 'react';

/**
 * 聊天滚动行为控制
 *
 * 滚动策略:
 * - 依赖变化时自动滚到底部
 * - 用户向上翻看历史时暂停自动滚动
 * - 用户手动滚到底部时恢复自动滚动
 * - 提供"滚动到最新"按钮状态
 */
export function useChatScroll(deps: unknown[]) {
  const containerRef = useRef<HTMLDivElement>(null);
  const isUserScrolling = useRef(false);
  const prevScrollTop = useRef(0);

  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const { scrollTop, scrollHeight, clientHeight } = el;
    const atBottom = scrollHeight - scrollTop - clientHeight < 60;

    // 用户向上翻 → 标记
    if (!atBottom && scrollTop < prevScrollTop.current) {
      isUserScrolling.current = true;
    }
    // 用户滚到底部 → 恢复自动滚动
    if (atBottom) {
      isUserScrolling.current = false;
    }
    prevScrollTop.current = scrollTop;
  }, []);

  // 依赖变化 → 自动滚底（除非用户在上翻）
  useEffect(() => {
    if (isUserScrolling.current) return;
    const el = containerRef.current;
    if (el) requestAnimationFrame(() => { el.scrollTop = el.scrollHeight; });
  }, deps);

  const scrollToBottom = useCallback(() => {
    const el = containerRef.current;
    if (el) { el.scrollTop = el.scrollHeight; isUserScrolling.current = false; }
  }, []);

  const isAtBottom = useCallback(() => {
    const el = containerRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight < 60;
  }, []);

  return { containerRef, handleScroll, scrollToBottom, isAtBottom };
}
```

### 7.5 V4 New: useHistorySessions Hook

```typescript
// hooks/useHistorySessions.ts

import { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import type { ResearchResultMeta } from '@/types/api';

/**
 * 加载已完成的研究任务列表
 *
 * 后端: ResearchResultStore.list_results()
 * 端点: GET /api/v1/research/completed
 */
export function useHistorySessions() {
  const [sessions, setSessions] = useState<ResearchResultMeta[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true); setError(null);
    try {
      const data = await api.listCompletedResearch(50);
      setSessions(data);
    } catch (e) { setError(e as Error); }
    finally { setIsLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return { sessions, isLoading, error, reload: load };
}
```

---

## 8. Stores

### 8.1 useResearchStore (V4: persist middleware)

```typescript
// store/useResearchStore.ts

import { create } from 'zustand';
import { persist } from 'zustand/middleware';   // V4: 持久化中间件
import type { Phase, SelectOption, ResearchSummary, ResearchStatistics, ParameterConfig } from '@/types/api';

interface ResearchState {
  taskId: string | null;
  sessionId: string | null;
  progress: number;
  phases: Phase[];
  status: 'idle' | 'running' | 'completed' | 'error';
  currentStep: number | null;
  stepOptions: SelectOption[] | null;
  parameterConfig: ParameterConfig | null;
  summary: ResearchSummary | null;
  statistics: ResearchStatistics | null;

  setTaskId: (id: string | null) => void;
  setSessionId: (id: string | null) => void;
  setProgress: (p: number) => void;
  setPhases: (p: Phase[]) => void;
  updatePhase: (id: string, u: Partial<Phase>) => void;
  setStatus: (s: ResearchState['status']) => void;
  setStep: (s: number | null, o?: SelectOption[]) => void;
  setParameterConfig: (c: ParameterConfig | null) => void;
  setSummary: (s: ResearchSummary | null) => void;
  setStatistics: (s: ResearchStatistics | null) => void;
  reset: () => void;
}

export const useResearchStore = create<ResearchState>()(
  persist(    // V4: 页面刷新后恢复 sessionId/step
    (set) => ({
      taskId: null, sessionId: null, progress: 0, phases: [], status: 'idle',
      currentStep: null, stepOptions: null, parameterConfig: null, summary: null, statistics: null,

      setTaskId: (id) => set({ taskId: id }),
      setSessionId: (id) => set({ sessionId: id }),
      setProgress: (p) => set({ progress: p }),
      setPhases: (p) => set({ phases: p }),
      updatePhase: (id, u) => set((s) => ({ phases: s.phases.map((ph) => (ph.id === id ? { ...ph, ...u } : ph)) })),
      setStatus: (s) => set({ status: s }),
      setStep: (s, o) => set({ currentStep: s, stepOptions: o || null }),
      setParameterConfig: (c) => set({ parameterConfig: c }),
      setSummary: (s) => set({ summary: s }),
      setStatistics: (s) => set({ statistics: s }),
      reset: () => set({ taskId: null, sessionId: null, progress: 0, phases: [], status: 'idle', currentStep: null, stepOptions: null, parameterConfig: null, summary: null, statistics: null }),
    }),
    {
      name: 'Zensers-session',   // localStorage key
      partialize: (state) => ({       // 只持久化轻量字段
        sessionId: state.sessionId,
        taskId: state.taskId,
        currentStep: state.currentStep,
        summary: state.summary,
      }),
    }
  )
);
```

### 8.2 V4 New: useChatStore

```typescript
// store/useChatStore.ts

import { create } from 'zustand';
import type { ChatMessage } from '@/types/api';

interface ChatState {
  messages: ChatMessage[];
  addMessage: (msg: ChatMessage) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  clearMessages: () => set({ messages: [] }),
}));
```

---

## 9. Core Components

### 9.1 V4 New: RuntimeProvider (assistant-ui Bridge)

```tsx
// components/chat/RuntimeProvider.tsx

'use client';

import { ReactNode, useCallback } from 'react';
import {
  AssistantRuntimeProvider,
  useExternalStoreRuntime,
  ThreadMessageLike,
  AppendMessage,
} from '@assistant-ui/react';
import { useChatStore } from '@/store/useChatStore';
import { useResearch } from '@/hooks/useResearch';
import { nanoid } from 'nanoid';

/**
 * assistant-ui RuntimeProvider
 *
 * 将 Zustand useChatStore 中的消息桥接到 assistant-ui 的 <Thread />。
 * 同时也负责将用户的发送操作代理到 useResearch.sendMessage。
 */
export function RuntimeProvider({ children }: { children: ReactNode }) {
  const { messages, addMessage } = useChatStore();
  const { sendMessage, isProcessing } = useResearch();

  // 内部消息 → assistant-ui ThreadMessageLike
  const threadMessages: readonly ThreadMessageLike[] = messages.map((m) => ({
    role: m.role,
    content: [{ type: 'text' as const, text: m.content }],
  }));

  // 用户发送 → 写入 store + 调用 API
  const onNew = useCallback(
    async (message: AppendMessage) => {
      if (message.content[0]?.type !== 'text') return;
      const text = message.content[0].text;
      if (!text.trim()) return;

      addMessage({
        id: nanoid(),
        role: 'user',
        content: text,
        timestamp: new Date().toISOString(),
      });

      await sendMessage(text);
    },
    [addMessage, sendMessage]
  );

  const runtime = useExternalStoreRuntime({
    isRunning: isProcessing,
    messages: threadMessages,
    onNew,
  });

  return <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>;
}
```

### 9.2 ChatPanel (V4: RuntimeProvider + useChatScroll)

```tsx
// components/chat/ChatPanel.tsx

'use client';

import { Thread } from '@assistant-ui/react';
import { useResearchStore } from '@/store/useResearchStore';
import { useChatStore } from '@/store/useChatStore';
import { useResearch } from '@/hooks/useResearch';
import { useChatScroll } from '@/hooks/useChatScroll';
import { RuntimeProvider } from './RuntimeProvider';
import { OptionSelector } from './OptionSelector';
import { SectionSelector } from './SectionSelector';
import { ParameterForm } from './ParameterForm';
import { ConfirmPanel } from './ConfirmPanel';
import { Button } from '@/components/ui/button';
import { ChevronDown } from 'lucide-react';

function ChatPanelInner() {
  const { currentStep, stepOptions, parameterConfig, summary } = useResearchStore();
  const { messages } = useChatStore();
  const { handleOptionSelect, selectSections, setParameters, confirmResearch, isProcessing } = useResearch();

  // V4: 聊天滚动行为控制
  const { containerRef, handleScroll, scrollToBottom, isAtBottom } = useChatScroll([messages]);
  const showScrollBtn = !isAtBottom();

  return (
    <div className="h-full flex flex-col">
      {/* 消息列表 — 监听滚动事件 */}
      <div ref={containerRef} onScroll={handleScroll} className="flex-1 overflow-y-auto relative">
        {/* assistant-ui Thread 自动渲染消息 */}
        <Thread />

        {/* V4: 滚动到最新按钮 — 用户上翻后出现 */}
        {showScrollBtn && (
          <div className="sticky bottom-4 flex justify-center">
            <Button variant="secondary" size="sm" className="rounded-full shadow-md" onClick={scrollToBottom}>
              <ChevronDown className="w-4 h-4 mr-1" />
              滚动到最新
            </Button>
          </div>
        )}
      </div>

      {/* Step overlays — step 1-5 时替代输入框 */}
      {currentStep !== null && currentStep < 6 && (
        <>
          {currentStep === 1 && stepOptions && (
            <OptionSelector title="选择输出类型" options={stepOptions}
              onSelect={(opt) => handleOptionSelect(opt.id)} disabled={isProcessing} />
          )}
          {currentStep === 2 && stepOptions && (
            <OptionSelector title="选择模板" options={stepOptions}
              onSelect={(opt) => handleOptionSelect(opt.id)} disabled={isProcessing} />
          )}
          {currentStep === 3 && stepOptions && (
            <SectionSelector sections={stepOptions}
              onConfirm={(ids) => selectSections(ids)} disabled={isProcessing} />
          )}
          {currentStep === 4 && parameterConfig && (
            <ParameterForm config={parameterConfig}
              onSubmit={setParameters} disabled={isProcessing} />
          )}
          {currentStep === 5 && summary && (
            <ConfirmPanel summary={summary}
              onConfirm={() => confirmResearch(true)}
              onBack={() => confirmResearch(false)} disabled={isProcessing} />
          )}
        </>
      )}
    </div>
  );
}

/** 外层包裹 assistant-ui RuntimeProvider */
export function ChatPanel() {
  return (
    <RuntimeProvider>
      <ChatPanelInner />
    </RuntimeProvider>
  );
}
```

### 9.3 OptionSelector (Data-Driven)

```tsx
// components/chat/OptionSelector.tsx

'use client';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { FileText, BarChart, Globe, Clock, Settings, CheckCircle } from 'lucide-react';
import type { SelectOption } from '@/types/api';

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  file: FileText, chart: BarChart, globe: Globe, clock: Clock, settings: Settings, check: CheckCircle,
};

interface Props {
  options: SelectOption[];
  title?: string;
  description?: string;
  onSelect: (option: SelectOption) => void;
  disabled?: boolean;
}

export function OptionSelector({ options, title, description, onSelect, disabled = false }: Props) {
  return (
    <div className="p-4 border-t bg-muted/30">
      {title && <h3 className="text-lg font-semibold mb-1">{title}</h3>}
      {description && <p className="text-sm text-muted-foreground mb-3">{description}</p>}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {options.map((opt) => {
          const Icon = opt.icon ? iconMap[opt.icon] : FileText;
          return (
            <Card key={opt.id}
              className={`cursor-pointer transition-all ${opt.disabled ? 'opacity-50 cursor-not-allowed' : 'hover:border-primary'} ${opt.selected ? 'border-primary bg-primary/5' : ''}`}
              onClick={() => !disabled && !opt.disabled && onSelect(opt)}>
              <CardHeader className="pb-2">
                <div className="flex items-center gap-2">
                  <Icon className="w-4 h-4 text-muted-foreground" />
                  <CardTitle className="text-sm">{opt.label}</CardTitle>
                </div>
              </CardHeader>
              {opt.description && <CardContent className="pt-0"><CardDescription className="text-xs">{opt.description}</CardDescription></CardContent>}
            </Card>
          );
        })}
      </div>
    </div>
  );
}
```

### 9.4 SectionSelector (V4: Multi-select for Step 3)

```tsx
// components/chat/SectionSelector.tsx

'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import type { SelectOption } from '@/types/api';

interface Props {
  sections: (SelectOption & { required?: boolean })[];
  onConfirm: (selectedIds: string[]) => void;
  disabled?: boolean;
}

export function SectionSelector({ sections, onConfirm, disabled = false }: Props) {
  const [selected, setSelected] = useState<Set<string>>(
    new Set(sections.filter((s) => s.selected || s.required).map((s) => s.id))
  );

  const toggle = (id: string, required?: boolean) => {
    if (required) return; // 必选章节不可取消
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  return (
    <div className="p-4 border-t bg-muted/30">
      <h3 className="text-lg font-semibold mb-1">选择报告章节</h3>
      <p className="text-sm text-muted-foreground mb-3">勾选需要包含的章节（必选章节不可取消）</p>
      <div className="space-y-2 mb-4">
        {sections.map((s) => (
          <label key={s.id} className={`flex items-center gap-3 p-2 rounded hover:bg-muted ${s.required ? 'opacity-60' : 'cursor-pointer'}`}>
            <Checkbox checked={selected.has(s.id)} disabled={s.required}
              onCheckedChange={() => toggle(s.id, s.required)} />
            <div>
              <div className="text-sm font-medium">{s.label}</div>
              {s.description && <div className="text-xs text-muted-foreground">{s.description}</div>}
            </div>
            {s.required && <span className="ml-auto text-xs text-muted-foreground">必选</span>}
          </label>
        ))}
      </div>
      <Button onClick={() => onConfirm(Array.from(selected))} disabled={disabled || selected.size === 0} className="w-full">
        确认章节 ({selected.size})
      </Button>
    </div>
  );
}
```

### 9.5 ParameterForm (Step 4)

```tsx
// components/chat/ParameterForm.tsx

'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import type { ParameterConfig } from '@/types/api';

interface Props {
  config: ParameterConfig;
  onSubmit: (params: { region: string; time_range: string; depth: string; focus_areas?: string }) => void;
  disabled?: boolean;
}

export function ParameterForm({ config, onSubmit, disabled = false }: Props) {
  const [region, setRegion] = useState(config.regions[0]?.id || '');
  const [timeRange, setTimeRange] = useState(config.time_ranges[0]?.id || '');
  const [depth, setDepth] = useState(config.depths[0]?.id || '');
  const [focusAreas, setFocusAreas] = useState('');

  return (
    <div className="p-4 border-t bg-muted/30">
      <h3 className="text-lg font-semibold mb-3">设置研究参数</h3>
      <div className="space-y-4">
        <div>
          <Label>研究区域</Label>
          <Select value={region} onValueChange={setRegion}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {config.regions.map((r) => <SelectItem key={r.id} value={r.id}>{r.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label>时间范围</Label>
          <Select value={timeRange} onValueChange={setTimeRange}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {config.time_ranges.map((t) => <SelectItem key={t.id} value={t.id}>{t.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label>研究深度</Label>
          <Select value={depth} onValueChange={setDepth}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {config.depths.map((d) => <SelectItem key={d.id} value={d.id}>{d.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label>重点关注（可选）</Label>
          <textarea value={focusAreas} onChange={(e) => setFocusAreas(e.target.value)}
            className="w-full rounded border p-2 text-sm" rows={2}
            placeholder="例如：政策变化、竞争格局、技术创新..." />
        </div>
        <Button onClick={() => onSubmit({ region, time_range: timeRange, depth, focus_areas: focusAreas })} disabled={disabled} className="w-full">
          确认参数
        </Button>
      </div>
    </div>
  );
}
```

### 9.6 ConfirmPanel (Step 5)

```tsx
// components/chat/ConfirmPanel.tsx

'use client';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Check, ArrowLeft } from 'lucide-react';
import type { ResearchSummary } from '@/types/api';

interface Props {
  summary: ResearchSummary;
  onConfirm: () => void;
  onBack: () => void;
  disabled?: boolean;
}

export function ConfirmPanel({ summary, onConfirm, onBack, disabled = false }: Props) {
  return (
    <div className="p-4 border-t bg-muted/30">
      <h3 className="text-lg font-semibold mb-3">确认研究方案</h3>
      <Card className="mb-4">
        <CardContent className="p-4 space-y-2 text-sm">
          <div className="flex justify-between"><span className="text-muted-foreground">研究主题</span><span className="font-medium">{summary.topic}</span></div>
          <div className="flex justify-between"><span className="text-muted-foreground">输出类型</span><span>{summary.output_type}</span></div>
          <div className="flex justify-between"><span className="text-muted-foreground">模板</span><span>{summary.template}</span></div>
          <div className="flex justify-between"><span className="text-muted-foreground">区域</span><span>{summary.parameters.region}</span></div>
          <div className="flex justify-between"><span className="text-muted-foreground">时间范围</span><span>{summary.parameters.time_range}</span></div>
          <div><span className="text-muted-foreground">章节</span>
            <div className="mt-1 flex flex-wrap gap-1">{summary.sections.map((s) => <span key={s} className="text-xs bg-muted px-2 py-0.5 rounded">{s}</span>)}</div>
          </div>
        </CardContent>
      </Card>
      <div className="flex gap-3">
        <Button variant="outline" onClick={onBack} disabled={disabled} className="flex-1">
          <ArrowLeft className="w-4 h-4 mr-1" /> 返回修改
        </Button>
        <Button onClick={onConfirm} disabled={disabled} className="flex-1">
          <Check className="w-4 h-4 mr-1" /> 确认开始
        </Button>
      </div>
    </div>
  );
}
```

### 9.7 DocumentPreview (V4: Fixed Zoom)

```tsx
// components/preview/DocumentPreview.tsx

'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useResearchStore } from '@/store/useResearchStore';
import { usePreview } from '@/hooks/usePreview';
import { api } from '@/lib/api';
import { Download, RefreshCw, ZoomIn, ZoomOut, FileText } from 'lucide-react';

export function DocumentPreview() {
  const { taskId, status } = useResearchStore();
  const [zoom, setZoom] = useState(100);

  const { preview, isLoading, isPending, error, refetch } = usePreview({
    taskId,
    enabled: status === 'completed',
    format: 'html',
  });

  const handleDownload = async () => {
    if (!taskId) return;
    const blob = await api.exportDocument(taskId, 'v1', 'docx');
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `report_${taskId}.docx`; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="pb-2 flex-shrink-0">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">报告预览</CardTitle>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon" onClick={() => setZoom(Math.max(50, zoom - 10))} disabled={zoom <= 50}><ZoomOut className="w-4 h-4" /></Button>
            <span className="text-xs w-12 text-center">{zoom}%</span>
            <Button variant="ghost" size="icon" onClick={() => setZoom(Math.min(150, zoom + 10))} disabled={zoom >= 150}><ZoomIn className="w-4 h-4" /></Button>
            <Button variant="ghost" size="icon" onClick={refetch}><RefreshCw className="w-4 h-4" /></Button>
            <Button variant="ghost" size="icon" onClick={handleDownload} disabled={!preview}><Download className="w-4 h-4" /></Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="flex-1 overflow-hidden p-0">
        {isLoading ? (
          <div className="h-full flex items-center justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" /></div>
        ) : isPending ? (   // V4: 启用但尚未获取到数据
          <div className="h-full flex flex-col items-center justify-center text-muted-foreground gap-2">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-muted-foreground" />
            <span>正在加载预览...</span></div>
        ) : error ? (
          <div className="h-full flex items-center justify-center text-destructive">预览加载失败</div>
        ) : preview ? (
          // V4 修复: wrapper div 承担 transform + overflow
          // 原理: 布局尺寸反算 (10000/zoom %), transform: scale 控制视觉
          // scrollbar 基于 wrapper 布局尺寸, 与 transform 一致
          <div className="h-full overflow-auto">
            <div className="origin-top-left"
              style={{
                transform: `scale(${zoom / 100})`,
                width: `${10000 / zoom}%`,
                height: `${10000 / zoom}%`,
              }}>
              <iframe
                src={preview.preview_url}
                className="w-full h-full border-0"
                title="报告预览"
                /* ✅ preview_url = "/api/v1/previews/ses_X_preview.html" */
                /* ✅ 由 FastAPI StaticFiles 提供服务 */
              />
            </div>
          </div>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-muted-foreground gap-2">
            <FileText className="w-12 h-12" />
            <span>暂无预览</span>
            <span className="text-xs">完成研究后自动显示</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
```

### 9.8 V4 New: SessionList

```tsx
// components/sidebar/SessionList.tsx

'use client';

import { useHistorySessions } from '@/hooks/useHistorySessions';
import { useResearchStore } from '@/store/useResearchStore';
import { formatDistanceToNow } from '@/lib/utils';
import { Clock, FileText, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';

/** 按日期分组: 今天 / 昨天 / 更早 */
function groupByDate(sessions: { task_id: string; topic: string; status: string; completed_at: string | null }[]) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterday = today - 86400000;
  const groups: { label: string; items: typeof sessions }[] = [];

  const todayItems = sessions.filter(s => s.completed_at && new Date(s.completed_at).getTime() >= today);
  const yesterdayItems = sessions.filter(s => s.completed_at && new Date(s.completed_at).getTime() >= yesterday && new Date(s.completed_at).getTime() < today);
  const olderItems = sessions.filter(s => !s.completed_at || new Date(s.completed_at).getTime() < yesterday);

  if (todayItems.length) groups.push({ label: '今天', items: todayItems });
  if (yesterdayItems.length) groups.push({ label: '昨天', items: yesterdayItems });
  if (olderItems.length) groups.push({ label: '更早', items: olderItems });
  return groups;
}

export function SessionList() {
  const { sessions, isLoading, error, reload } = useHistorySessions();
  const { reset } = useResearchStore();  // 点击历史会话时的行为待定

  if (isLoading) return <div className="flex items-center justify-center p-4"><Loader2 className="w-4 h-4 animate-spin" /></div>;
  if (error) return <div className="p-2 text-sm text-destructive">加载失败 <Button variant="ghost" size="sm" onClick={reload}>重试</Button></div>;

  if (sessions.length === 0) {
    return <div className="p-4 text-sm text-muted-foreground text-center">暂无历史研究记录</div>;
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between px-3 py-1">
        <span className="text-xs text-muted-foreground font-medium">历史研究</span>
        <Button variant="ghost" size="icon" className="w-6 h-6" onClick={reload}><RefreshCw className="w-3 h-3" /></Button>
      </div>
      {groupByDate(sessions).map((group) => (
        <div key={group.label}>
          <div className="px-3 py-1 text-xs text-muted-foreground font-medium">{group.label}</div>
          {group.items.map((s) => (
            <button key={s.task_id}
              onClick={() => { /* TODO: 加载该会话详情 */ }}
              className="w-full text-left px-3 py-2 text-sm hover:bg-muted rounded-sm transition-colors">
              <div className="flex items-center gap-2">
                <FileText className="w-3 h-3 flex-shrink-0 text-muted-foreground" />
                <span className="truncate">{s.topic}</span>
              </div>
              <div className="text-xs text-muted-foreground mt-0.5">
                {s.status === 'completed' ? '已完成' : s.status}
                {s.completed_at ? ` · ${formatDistanceToNow(new Date(s.completed_at))}前` : ''}
              </div>
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}
```

---

## 10. Main Layout (Responsive)

```tsx
// components/layout/MainLayout.tsx

'use client';

import { useEffect, useState } from 'react';
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { ProgressPanel } from '@/components/progress/ProgressPanel';
import { DocumentPreview } from '@/components/preview/DocumentPreview';
import { SessionList } from '@/components/sidebar/SessionList';  // V4: 侧边栏
import { Button } from '@/components/ui/button';
import { PanelLeftClose, PanelLeft, History } from 'lucide-react';

const MOBILE_BP = 768, TABLET_BP = 1024;

export function MainLayout() {
  const [isMobile, setIsMobile] = useState(false);
  const [isTablet, setIsTablet] = useState(false);
  const [previewCollapsed, setPreviewCollapsed] = useState(false);
  const [showHistory, setShowHistory] = useState(false);  // V4: 历史侧边栏

  useEffect(() => {
    const check = () => { setIsMobile(window.innerWidth < MOBILE_BP); setIsTablet(window.innerWidth >= MOBILE_BP && window.innerWidth < TABLET_BP); };
    check();
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  }, []);

  if (isMobile) {
    return (
      <div className="h-screen flex flex-col">
        <header className="h-14 border-b flex items-center justify-between px-4">
          <h1 className="text-lg font-semibold">Zensers</h1>
          <Button variant="ghost" size="icon" onClick={() => setShowHistory(!showHistory)}><History className="w-4 h-4" /></Button>
        </header>
        {showHistory && <div className="h-48 overflow-y-auto border-b"><SessionList /></div>}
        <div className="flex-1 overflow-hidden flex flex-col">
          <div className="flex-1 min-h-0"><ChatPanel /></div>
          <div className="h-48 border-t"><ProgressPanel /></div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col">
      <header className="h-14 border-b flex items-center justify-between px-4">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold">Zensers</h1>
          <span className="text-sm text-muted-foreground">智能市场研究平台</span>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" onClick={() => setShowHistory(!showHistory)}>
            <History className="w-4 h-4" />
          </Button>
          <Button variant="ghost" size="icon" onClick={() => setPreviewCollapsed(!previewCollapsed)}>
            {previewCollapsed ? <PanelLeft className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
          </Button>
        </div>
      </header>

      <div className="flex-1 overflow-hidden flex">
        {/* V4: 历史会话侧边栏 */}
        {showHistory && (
          <div className="w-64 border-r overflow-y-auto flex-shrink-0">
            <SessionList />
          </div>
        )}

        <PanelGroup direction="horizontal">
          <Panel defaultSize={isTablet ? 60 : 50} minSize={30}>
            <ChatPanel />
          </Panel>
          <PanelResizeHandle className="w-1 bg-border hover:bg-primary/50 transition-colors" />
          <Panel defaultSize={isTablet ? 40 : 50} minSize={30} collapsible>
            <PanelGroup direction="vertical">
              <Panel defaultSize={30} minSize={15} maxSize={50}><ProgressPanel /></Panel>
              <PanelResizeHandle className="h-1 bg-border hover:bg-primary/50 transition-colors" />
              <Panel defaultSize={70} minSize={30}><DocumentPreview /></Panel>
            </PanelGroup>
          </Panel>
        </PanelGroup>
      </div>
    </div>
  );
}
```

---

## 11. Development Plan

### 9-Day MVP (with Backend Dependencies)

| Day | Task | Depends On | Risk |
|-----|------|-----------|------|
| 1 | Project setup: Next.js + shadcn/ui + assistant-ui + panels | None | ✅ Low |
| 2 | Layout: responsive + collapsible + SessionList skeleton | None | ✅ Low |
| 3 | Store: useResearchStore (persist) + useChatStore | None | ✅ Low |
| 4 | RuntimeProvider: assistant-ui runtime bridge + useChatScroll | Store ready | ⚠️ Medium |
| 5 | ChatPanel: Thread + step overlays + scroll button | RuntimeProvider | ⚠️ Medium |
| 6 | API + Step handlers: useResearch + OptionSelector | Backend API ready | ✅ Low |
| 7 | Step 3-5 UI: SectionSelector + ParameterForm + ConfirmPanel | Backend API ready | ⚠️ Medium |
| 8 | ProgressPanel: SSE + fallback + DocumentPreview | ⚠️ Backend SSE | 🔴 High |
| 9 | SessionList + history load + error states + polish | Backend API ready | ✅ Low |

### Backend Dependencies

| Endpoint | Status | Frontend Fallback |
|----------|--------|-------------------|
| `/api/v1/research/*` | ✅ Exists | — |
| `/api/v1/documents/*` | ✅ Exists | — |
| `/api/v1/previews/*` | **V4: StaticFiles mount** (5 lines) | — |
| `/api/v1/stream/{task_id}` | ❌ Not implemented | isConnected=false, progress stuck |
| `/api/v1/research/completed` | ✅ Exists (ResearchResultStore.list_results) | — |

---

## 12. Dependencies

```json
{
  "dependencies": {
    "next": "^14.0.0",
    "react": "^18.2.0",
    "assistant-ui": "^0.5.0",
    "react-resizable-panels": "^2.0.0",
    "zustand": "^4.5.0",
    "axios": "^1.6.0",
    "lucide-react": "^0.300.0",
    "nanoid": "^5.0.0"
  },
  "devDependencies": {
    "typescript": "^5.0.0",
    "tailwindcss": "^3.4.0",
    "@types/node": "^20.0.0"
  }
}
```

**Removed**: `@tanstack/react-query` (+~15KB), `docx-preview` (+~50KB)

**State persistence**: Built into Zustand via `persist` middleware (no extra deps)

---

## 13. Feature Completeness Matrix

| 功能 | 实现状态 | 组件/Hook | 后端依赖 |
|------|---------|-----------|---------|
| **会话保持** | ✅ 已实现 | `useResearchStore` persist → localStorage | — |
| 页面刷新恢复 | ✅ sessionId/step 存 localStorage | `partialize` 配置 | — |
| **聊天滚动** | ✅ 已实现 | `useChatScroll` + `RuntimeProvider` + `<Thread />` | — |
| 自动滚底 | ✅ 新消息到达 | `useEffect` on `deps` | — |
| 用户上翻检测 | ✅ 暂停自动滚 | `isUserScrolling` ref | — |
| 滚动恢复按钮 | ✅ "滚动到最新" | `showScrollBtn` | — |
| **历史会话** | ✅ 已实现 | `SessionList` + `useHistorySessions` | `GET /research/completed` |
| 历史分组 | ✅ 今天/昨天/更早 | `groupByDate()` | — |
| **HTML 预览** | ✅ 已实现 | `DocumentPreview` iframe | `StaticFiles mount` + `research_api` fix |
| 预览缩放 | ✅ 正确 scrollbar | wrapper `width/height` 反算 | — |
| **assistant-ui 集成** | ✅ 完整 | `RuntimeProvider` + `useExternalStoreRuntime` | — |
| **Step 3 多选** | ✅ 已实现 | `SectionSelector` + `required` 保护 | — |
| **Step 4 参数表单** | ✅ 已实现 | `ParameterForm` (Select + textarea) | — |
| **Step 5 确认面板** | ✅ 已实现 | `ConfirmPanel` (summary card + buttons) | — |

---

## 14. Comparison: V3 vs V4

| 维度 | V3 | V4 |
|------|----|----|
| HTML 预览 | iframe src 指向本地路径，被浏览器拦截 | ✅ FastAPI StaticFiles + 相对 URL |
| assistant-ui | `useExternalStoreRuntime` 只有注释 | ✅ 完整 RuntimeProvider + Provider 包裹 |
| 聊天滚动 | 未配置 | ✅ auto-scroll + 用户上翻检测 + 按钮 |
| 页面刷新 | 状态全部丢失 | ✅ localStorage 恢复 sessionId/step |
| 历史研究 | 无 | ✅ SessionList 侧边栏 + 按日期分组 |
| 预览缩放 | transform + overflow:auto 导致滚动条异常 | ✅ wrapper 反算宽高 + transform |
| Step 组件 | 引用但未定义 | ✅ 全部有 interface + 实现代码 |
| docx-preview | 依赖保留但不使用 | ✅ 已移除 |
| 依赖大小 | zustand + tanstack query + axios + docx-preview | ✅ zustand(persist) + axios 两根 |
| 计划天数 | 7-8 天 | ✅ 9 天（含 RuntimeProvider 集成） |

---

## 15. V4.1 Bug Fixes (2026-04-30)

### 已修复问题

| # | 问题 | 修复位置 | 说明 |
|---|------|----------|------|
| P0-1 | 后端 API 路径前缀不匹配 | `src/api/main.py` | 创建 FastAPI 应用，统一 `/api/v1` 前缀 |
| P0-2 | useResearch 缺少函数 | 设计文档 §7.1 | 添加 `sendMessage` 和 `handleOptionSelect` |
| P0-3 | TypeScript 类型缺失 | 设计文档 §3 | 添加 `StartResearchResponse` 和 `InteractRequest` |
| P1-5 | formatDistanceToNow 不存在 | 设计文档 §6.5 | 实现 utils.ts 工具函数 |
| P1-6 | SectionSelector 数据形状错误 | 设计文档 §7.1 | `selectTemplate` 保留 `required` 字段 |
| P1-7 | research_api.py 缺少 logger | `src/api/research_api.py` | 添加 `import logging` |
| P1-8 | get_preview 返回本地路径 | `src/api/research_api.py` | 返回 `/api/v1/previews/{filename}` URL |
| P1-9 | confirmResearch(false) 销毁会话 | 设计文档 §7.1 | 用户点"返回"时调用 `reset()` 重新开始 |
| P1-10 | SSE URL 双斜杠 | 设计文档 §6 | 规范化 base URL |

### 新增文件

- `src/api/main.py` - FastAPI 主应用，统一 API 入口

### 修改文件

- `src/api/research_api.py` - 添加 logger 导入，修复 preview URL
- `docs/REACT_FRONTEND_DESIGN_V4.md` - 所有 P0/P1 修复

---

*Document Version: 4.1 (Bug Fixed)*
*Last Updated: 2026-04-30*
