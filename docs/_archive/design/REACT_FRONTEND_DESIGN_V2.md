# Zensers Web Frontend - Detailed Design Document (Optimized)

> React + Next.js + TypeScript Frontend for Zensers Market Report System
> 
> **Optimized Version**: assistant-ui + SSE + Single Page Layout

---

## 1. Architecture Overview

### 1.1 Tech Stack (Optimized)

| Technology | Version | Purpose |
|------------|---------|---------|
| Next.js | 14.x | Full-stack framework (App Router) |
| React | 18.x | UI components |
| TypeScript | 5.x | Type safety |
| Tailwind CSS | 3.x | Styling |
| **assistant-ui** | latest | AI chat UI components (replaces custom chat) |
| **react-resizable-panels** | latest | Resizable panel layout |
| Zustand | 4.x | Client state management |
| TanStack Query | 5.x | Server state & API requests |
| **SSE (EventSource)** | native | Real-time communication (replaces Socket.IO) |

### 1.2 Key Optimizations

| Before | After | Reason |
|--------|-------|--------|
| Custom ChatInterface | **assistant-ui** | Mature AI chat library, less code to maintain |
| Fixed layout | **react-resizable-panels** | User-adjustable panel sizes |
| Socket.IO | **SSE (EventSource)** | Simpler, no backend WebSocket needed |
| Hardcoded OptionSelector | **Data-driven** | Render from API response |
| Multiple pages | **Single page** | MVP simplicity |

### 1.3 System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                        │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              assistant-ui (Chat Components)              │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │           react-resizable-panels (Layout)                │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │           Zustand + TanStack Query (State)               │   │
│  └─────────────────────────────────────────────────────────┘   │
└──────────────────────────┼──────────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    ┌────┴────┐      ┌─────┴─────┐           │
    │ REST API│      │   SSE     │           │
    └────┬────┘      └─────┬─────┘           │
         │                 │                 │
┌────────┴─────────────────┴─────────────────┐
│           Backend (FastAPI)                 │
│  ┌─────────────────────────────────────┐   │
│  │  /api/v1/research/* (ResearchAPI)   │   │
│  │  /api/v1/documents/* (DocumentAPI)  │   │
│  │  /api/v1/stream/{task_id} (SSE)     │   │
│  └─────────────────────────────────────┘   │
└────────────────────────────────────────────┘
```

---

## 2. Project Structure (Simplified)

```
web/
├── src/
│   ├── app/                          # Next.js App Router
│   │   ├── layout.tsx                # Root layout
│   │   ├── page.tsx                  # Single page (Chat + Preview)
│   │   └── globals.css               # Global styles
│   │
│   ├── components/
│   │   ├── ui/                       # shadcn/ui components
│   │   │
│   │   ├── chat/                     # Chat enhancements
│   │   │   ├── OptionSelector.tsx    # Data-driven options (from API)
│   │   │   └── ChatConfig.tsx        # assistant-ui configuration
│   │   │
│   │   ├── progress/                 # Progress components
│   │   │   ├── ProgressPanel.tsx     # Main progress container
│   │   │   └── PhaseStatus.tsx       # Phase execution status
│   │   │
│   │   ├── preview/                  # Preview components
│   │   │   ├── DocumentPreview.tsx   # Document preview container
│   │   │   └── PreviewControls.tsx   # Zoom, download
│   │   │
│   │   └── layout/                   # Layout components
│   │       └── MainLayout.tsx        # Resizable panel layout
│   │
│   ├── lib/
│   │   ├── api.ts                    # API client (Axios)
│   │   ├── sse.ts                    # SSE (EventSource) manager
│   │   ├── utils.ts                  # Utility functions
│   │   └── constants.ts              # Constants
│   │
│   ├── hooks/
│   │   ├── useResearch.ts            # Research task hook
│   │   ├── useProgress.ts            # SSE progress hook
│   │   └── useDocument.ts            # Document operations hook
│   │
│   ├── store/
│   │   ├── useResearchStore.ts       # Research state
│   │   └── useUIStore.ts             # UI state
│   │
│   └── types/
│       └── api.ts                    # All API types
│
├── package.json
├── tsconfig.json
├── tailwind.config.ts
├── next.config.js
└── .env.local
```

---

## 3. Backend API Integration

### 3.1 Unified API Registration (FastAPI)

```python
# src/api/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.research_api import ResearchAPI
from src.api.document_api import DocumentAPI, DocumentAPIRouter

app = FastAPI(
    title="Zensers API",
    version="1.0.0",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ Unified URL Prefix: /api/v1 ============

# Research API
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

# SSE Endpoint for Progress
@app.get("/api/v1/stream/{task_id}")
async def stream_progress(task_id: str):
    from fastapi.responses import StreamingResponse
    from src.core.progress import ProgressStreamer
    
    streamer = ProgressStreamer(task_id)
    return StreamingResponse(
        streamer.generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

# Document API (use router)
document_api = DocumentAPI()
document_router = DocumentAPIRouter(document_api).get_router()
app.include_router(document_router, prefix="/api/v1")

# Health check
@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}
```

### 3.2 Complete API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| **Research API** | | |
| `/api/v1/research/start` | POST | Start research session |
| `/api/v1/research/interact` | POST | Handle interaction step |
| `/api/v1/research/feedback` | POST | Handle preview feedback |
| `/api/v1/research/preview/{task_id}` | GET | Get preview document |
| `/api/v1/stream/{task_id}` | GET | **SSE progress stream** |
| **Document API** | | |
| `/api/v1/documents/generate` | POST | Generate document |
| `/api/v1/documents/{task_id}/versions` | GET | List versions |
| `/api/v1/documents/{task_id}/preview` | GET | Get preview |
| `/api/v1/documents/{task_id}/revisions` | GET | Get revision history |
| `/api/v1/documents/revision` | POST | Handle revision request |
| `/api/v1/documents/export` | POST | Export document |
| **Research List** | | |
| `/api/v1/research/completed` | GET | List completed research |

---

## 4. TypeScript Types (Data-Driven)

```typescript
// types/api.ts

// ============ Research API Types ============

export interface StartResearchRequest {
  user_input: string;
  user_id?: string;
}

export interface StartResearchResponse {
  session_id: string;
  step: number;
  message: string;
  instruction: string;
  /** Data-driven options from backend */
  options: SelectOption[];
  next_step: string;
}

/** Generic select option - rendered by OptionSelector */
export interface SelectOption {
  id: string;
  label: string;
  description?: string;
  icon?: string;
  disabled?: boolean;
  selected?: boolean;
}

export interface InteractRequest {
  session_id: string;
  step: number;
  response: Record<string, any>;
}

export type InteractResponse = {
  session_id: string;
  step: number;
  message: string;
  instruction: string;
  next_step: string;
  /** Dynamic options for this step */
  options?: SelectOption[];
  /** Dynamic templates (step 2) */
  templates?: Template[];
  /** Dynamic sections (step 3) */
  sections?: Section[];
  /** Dynamic parameters (step 4) */
  parameters?: ParameterConfig;
  /** Summary for confirmation (step 5) */
  summary?: ResearchSummary;
  /** Final plan (step 6) */
  final_plan?: ResearchPlan;
  status?: 'executing' | 'cancelled';
};

/** Parameter configuration from backend */
export interface ParameterConfig {
  regions: SelectOption[];
  time_ranges: SelectOption[];
  depths: SelectOption[];
}

export interface Template {
  id: string;
  name: string;
  description: string;
  preview_image?: string;
}

export interface Section {
  id: string;
  title: string;
  description?: string;
  required: boolean;
  selected: boolean;
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

// ============ SSE Progress Types ============

export interface SSEMessage {
  event: 'progress' | 'phase_start' | 'phase_complete' | 'error' | 'complete';
  data: ProgressData | PhaseData | ErrorData | CompleteData;
}

export interface ProgressData {
  task_id: string;
  phase_id: string;
  progress: number;  // 0-100
  message: string;
  timestamp: string;
}

export interface PhaseData {
  task_id: string;
  phase_id: string;
  phase_name: string;
  status: 'running' | 'completed' | 'error';
  timestamp: string;
}

export interface ErrorData {
  task_id: string;
  code: string;
  message: string;
  details?: any;
}

export interface CompleteData {
  task_id: string;
  output_path: string;
  sections: SectionResult[];
  statistics: ResearchStatistics;
}

export interface SectionResult {
  id: string;
  title: string;
  word_count: number;
  charts: number;
}

export interface ResearchStatistics {
  total_words: number;
  total_charts: number;
  data_sources: number;
  execution_time: number;
}

// ============ Document API Types ============

export interface GenerateDocumentRequest {
  task_id: string;
  output_format: 'docx' | 'pptx' | 'pdf' | 'html';
  template: 'consulting' | 'academic' | 'business' | 'minimal';
}

export interface Version {
  version_id: string;
  created_at: string;
  file_size?: number;
  changes?: string;
}

export interface PreviewResponse {
  task_id: string;
  preview_url: string;
  preview_path: string;
  preview_format: 'html' | 'pdf' | 'png';
  cached: boolean;
  file_size: number;
}

export interface RevisionRequest {
  task_id: string;
  revision_type: 'minor' | 'section' | 'phase' | 'full';
  user_feedback: string;
  section_id?: string;
  section_title?: string;
  keywords?: string[];
  target_content?: string;
}
```

---

## 5. SSE Manager (Replaces Socket.IO)

```typescript
// lib/sse.ts

import type { SSEMessage } from '@/types/api';

type ProgressCallback = (message: SSEMessage) => void;

class SSEManager {
  private connections: Map<string, EventSource> = new Map();
  private callbacks: Map<string, Set<ProgressCallback>> = new Map();

  /**
   * Subscribe to task progress via SSE
   */
  subscribe(taskId: string, callback: ProgressCallback): () => void {
    // Store callback
    if (!this.callbacks.has(taskId)) {
      this.callbacks.set(taskId, new Set());
    }
    this.callbacks.get(taskId)!.add(callback);

    // Create EventSource if not exists
    if (!this.connections.has(taskId)) {
      const url = `${process.env.NEXT_PUBLIC_API_URL}/api/v1/stream/${taskId}`;
      const eventSource = new EventSource(url);

      eventSource.onmessage = (event) => {
        try {
          const message: SSEMessage = JSON.parse(event.data);
          this.notify(taskId, message);
          
          // Close on complete/error
          if (message.event === 'complete' || message.event === 'error') {
            this.unsubscribe(taskId);
          }
        } catch (e) {
          console.error('Failed to parse SSE message:', e);
        }
      };

      eventSource.onerror = (error) => {
        console.error('SSE error:', error);
        this.notify(taskId, {
          event: 'error',
          data: {
            task_id: taskId,
            code: 'SSE_ERROR',
            message: 'Connection lost',
          },
        });
        // Auto-reconnect is handled by EventSource
      };

      this.connections.set(taskId, eventSource);
    }

    // Return unsubscribe function
    return () => {
      const callbacks = this.callbacks.get(taskId);
      if (callbacks) {
        callbacks.delete(callback);
        if (callbacks.size === 0) {
          this.callbacks.delete(taskId);
          this.close(taskId);
        }
      }
    };
  }

  private notify(taskId: string, message: SSEMessage): void {
    const callbacks = this.callbacks.get(taskId);
    if (callbacks) {
      callbacks.forEach((cb) => cb(message));
    }
  }

  private close(taskId: string): void {
    const eventSource = this.connections.get(taskId);
    if (eventSource) {
      eventSource.close();
      this.connections.delete(taskId);
    }
  }

  /**
   * Close all connections
   */
  closeAll(): void {
    this.connections.forEach((es) => es.close());
    this.connections.clear();
    this.callbacks.clear();
  }

  /**
   * Check if connected to a task
   */
  isConnected(taskId: string): boolean {
    const es = this.connections.get(taskId);
    return es?.readyState === EventSource.OPEN;
  }
}

export const sseManager = new SSEManager();
export default sseManager;
```

---

## 6. Core Components

### 6.1 Main Layout (Resizable Panels)

```tsx
// components/layout/MainLayout.tsx

'use client';

import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { ProgressPanel } from '@/components/progress/ProgressPanel';
import { DocumentPreview } from '@/components/preview/DocumentPreview';
import { useUIStore } from '@/store/useUIStore';

export function MainLayout() {
  const { previewVisible } = useUIStore();

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <header className="h-14 border-b flex items-center px-4">
        <h1 className="text-lg font-semibold">Zensers</h1>
        <span className="text-sm text-muted-foreground ml-2">
          智能市场研究平台
        </span>
      </header>

      {/* Main Content */}
      <div className="flex-1 overflow-hidden">
        <PanelGroup direction="horizontal">
          {/* Chat Panel */}
          <Panel defaultSize={50} minSize={30}>
            <ChatPanel />
          </Panel>

          <PanelResizeHandle className="w-1 bg-border hover:bg-primary/50 transition-colors" />

          {/* Right Side: Progress + Preview */}
          <Panel defaultSize={50} minSize={30}>
            <PanelGroup direction="vertical">
              {/* Progress Panel */}
              <Panel defaultSize={30} minSize={20}>
                <ProgressPanel />
              </Panel>

              <PanelResizeHandle className="h-1 bg-border hover:bg-primary/50 transition-colors" />

              {/* Document Preview */}
              {previewVisible && (
                <Panel defaultSize={70} minSize={30}>
                  <DocumentPreview />
                </Panel>
              )}
            </PanelGroup>
          </Panel>
        </PanelGroup>
      </div>
    </div>
  );
}
```

### 6.2 Chat Panel (assistant-ui)

```tsx
// components/chat/ChatPanel.tsx

'use client';

import { useChat as useAssistantChat } from 'assistant-ui';
import { useResearchStore } from '@/store/useResearchStore';
import { OptionSelector } from './OptionSelector';
import { useResearch } from '@/hooks/useResearch';

export function ChatPanel() {
  const { currentStep, stepOptions, sessionId } = useResearchStore();
  const { sendMessage, selectOption, isProcessing } = useResearch();

  const {
    messages,
    input,
    handleSubmit,
    setInput,
    append,
  } = useAssistantChat({
    initialMessages: [],
    onComplete: (message) => {
      // Handle assistant response
    },
  });

  return (
    <div className="h-full flex flex-col">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`
                max-w-[80%] rounded-lg px-4 py-2
                ${message.role === 'user'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted'
                }
              `}
            >
              {message.content}
            </div>
          </div>
        ))}
      </div>

      {/* Data-Driven Option Selector */}
      {currentStep && stepOptions && stepOptions.length > 0 && (
        <OptionSelector
          options={stepOptions}
          onSelect={(option) => selectOption(option)}
          disabled={isProcessing}
        />
      )}

      {/* Input */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (input.trim()) {
            sendMessage(input);
            setInput('');
          }
        }}
        className="p-4 border-t"
      >
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              sessionId
                ? '输入修订意见或确认定稿...'
                : '输入研究主题开始...'
            }
            disabled={isProcessing}
            className="flex-1 rounded-lg border p-3 focus:outline-none focus:ring-2 focus:ring-primary"
          />
          <button
            type="submit"
            disabled={isProcessing || !input.trim()}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-lg disabled:opacity-50"
          >
            发送
          </button>
        </div>
      </form>
    </div>
  );
}
```

### 6.3 Data-Driven Option Selector

```tsx
// components/chat/OptionSelector.tsx

'use client';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { FileText, BarChart, Globe, Clock, Settings, CheckCircle } from 'lucide-react';
import type { SelectOption } from '@/types/api';

// Icon mapping from string to component
const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  file: FileText,
  chart: BarChart,
  globe: Globe,
  clock: Clock,
  settings: Settings,
  check: CheckCircle,
};

interface OptionSelectorProps {
  options: SelectOption[];
  title?: string;
  description?: string;
  onSelect: (option: SelectOption) => void;
  disabled?: boolean;
  multiSelect?: boolean;
}

export function OptionSelector({
  options,
  title,
  description,
  onSelect,
  disabled = false,
  multiSelect = false,
}: OptionSelectorProps) {
  return (
    <div className="p-4 border-t bg-muted/30">
      {title && <h3 className="text-lg font-semibold mb-1">{title}</h3>}
      {description && (
        <p className="text-sm text-muted-foreground mb-3">{description}</p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {options.map((option) => {
          const IconComponent = option.icon ? iconMap[option.icon] : FileText;

          return (
            <Card
              key={option.id}
              className={`
                cursor-pointer transition-all
                ${option.disabled ? 'opacity-50 cursor-not-allowed' : 'hover:border-primary'}
                ${option.selected ? 'border-primary bg-primary/5' : ''}
              `}
              onClick={() => !disabled && !option.disabled && onSelect(option)}
            >
              <CardHeader className="pb-2">
                <div className="flex items-center gap-2">
                  <IconComponent className="w-4 h-4 text-muted-foreground" />
                  <CardTitle className="text-sm">{option.label}</CardTitle>
                </div>
              </CardHeader>
              {option.description && (
                <CardContent className="pt-0">
                  <CardDescription className="text-xs">
                    {option.description}
                  </CardDescription>
                </CardContent>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
}
```

### 6.4 Progress Panel (SSE)

```tsx
// components/progress/ProgressPanel.tsx

'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { useResearchStore } from '@/store/useResearchStore';
import { useProgress } from '@/hooks/useProgress';
import { CheckCircle2, Circle, Loader2, AlertCircle } from 'lucide-react';

export function ProgressPanel() {
  const { phases, progress, status, taskId } = useResearchStore();
  const { isConnected } = useProgress(taskId);

  if (!taskId) {
    return (
      <Card className="h-full">
        <CardContent className="h-full flex items-center justify-center text-muted-foreground">
          等待研究任务开始...
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">研究进度</CardTitle>
          {isConnected ? (
            <span className="text-xs text-green-500 flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
              实时更新
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">○ 离线</span>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {/* Overall Progress */}
        <div className="space-y-1">
          <div className="flex justify-between text-xs">
            <span>总体进度</span>
            <span>{progress}%</span>
          </div>
          <Progress value={progress} />
        </div>

        {/* Phase Status */}
        <div className="space-y-2">
          {phases.map((phase) => (
            <div key={phase.id} className="flex items-center gap-2 text-sm">
              {phase.status === 'completed' ? (
                <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0" />
              ) : phase.status === 'running' ? (
                <Loader2 className="w-4 h-4 text-primary animate-spin flex-shrink-0" />
              ) : phase.status === 'error' ? (
                <AlertCircle className="w-4 h-4 text-destructive flex-shrink-0" />
              ) : (
                <Circle className="w-4 h-4 text-muted-foreground flex-shrink-0" />
              )}
              <span className={phase.status === 'running' ? 'font-medium' : ''}>
                {phase.name}
              </span>
              {phase.status === 'running' && (
                <span className="text-muted-foreground text-xs">
                  ({phase.progress}%)
                </span>
              )}
            </div>
          ))}
        </div>

        {/* Status Message */}
        {status === 'completed' && (
          <div className="text-sm text-green-600 font-medium pt-2">
            ✓ 研究完成
          </div>
        )}
        {status === 'error' && (
          <div className="text-sm text-destructive pt-2">
            研究过程中出现错误
          </div>
        )}
      </CardContent>
    </Card>
  );
}
```

### 6.5 Document Preview

```tsx
// components/preview/DocumentPreview.tsx

'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { useResearchStore } from '@/store/useResearchStore';
import { Download, RefreshCw, ZoomIn, ZoomOut, FileText } from 'lucide-react';

export function DocumentPreview() {
  const { taskId, status } = useResearchStore();
  const [zoom, setZoom] = useState(100);

  const { data: preview, isLoading, error, refetch } = useQuery({
    queryKey: ['preview', taskId],
    queryFn: () => api.getPreview(taskId!),
    enabled: !!taskId && status === 'completed',
  });

  const handleDownload = async () => {
    if (!taskId) return;
    const blob = await api.exportDocument(taskId, 'v1', 'docx');
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `report_${taskId}.docx`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="pb-2 flex-shrink-0">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">报告预览</CardTitle>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setZoom(Math.max(50, zoom - 10))}
              disabled={zoom <= 50}
            >
              <ZoomOut className="w-4 h-4" />
            </Button>
            <span className="text-xs w-12 text-center">{zoom}%</span>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setZoom(Math.min(150, zoom + 10))}
              disabled={zoom >= 150}
            >
              <ZoomIn className="w-4 h-4" />
            </Button>
            <Button variant="ghost" size="icon" onClick={() => refetch()}>
              <RefreshCw className="w-4 h-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleDownload}
              disabled={!preview}
            >
              <Download className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="flex-1 overflow-hidden p-0">
        {isLoading ? (
          <div className="h-full flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
          </div>
        ) : error ? (
          <div className="h-full flex items-center justify-center text-destructive">
            预览加载失败
          </div>
        ) : preview ? (
          <div className="h-full overflow-auto">
            <iframe
              src={preview.preview_url}
              className="w-full h-full border-0"
              style={{
                transform: `scale(${zoom / 100})`,
                transformOrigin: 'top left',
                width: `${10000 / zoom}%`,
                height: `${10000 / zoom}%`,
              }}
            />
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

---

## 7. Hooks

### 7.1 useResearch Hook

```typescript
// hooks/useResearch.ts

import { useCallback } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useResearchStore } from '@/store/useResearchStore';
import { api } from '@/lib/api';
import { nanoid } from 'nanoid';

export function useResearch() {
  const {
    sessionId,
    currentStep,
    setSessionId,
    setStep,
    setTaskId,
    setPhases,
    setStatus,
    setSummary,
  } = useResearchStore();

  // Start research mutation
  const startMutation = useMutation({
    mutationFn: (input: string) => api.startResearch(input),
    onSuccess: (data) => {
      setSessionId(data.session_id);
      setStep(data.step, data.options);
    },
  });

  // Interact mutation
  const interactMutation = useMutation({
    mutationFn: (response: Record<string, any>) =>
      api.interact({
        session_id: sessionId!,
        step: currentStep!,
        response,
      }),
    onSuccess: (data) => {
      setStep(data.step, data.options);

      // Handle step 6: execution started
      if (data.step === 6 && data.status === 'executing') {
        setTaskId(data.session_id);
        setStatus('running');
        if (data.final_plan) {
          setPhases(
            data.final_plan.phases.map((p) => ({
              ...p,
              status: 'pending' as const,
              progress: 0,
            }))
          );
        }
      }

      // Handle summary (step 5)
      if (data.summary) {
        setSummary(data.summary);
      }
    },
  });

  const sendMessage = useCallback(
    async (content: string) => {
      setStep(null, null); // Hide options while processing

      if (!sessionId) {
        await startMutation.mutateAsync(content);
      } else {
        await interactMutation.mutateAsync({ user_input: content });
      }
    },
    [sessionId, startMutation, interactMutation, setStep]
  );

  const selectOption = useCallback(
    async (option: { id: string }) => {
      // Determine field name based on step
      const fieldMap: Record<number, string> = {
        1: 'output_type',
        2: 'template_id',
        3: 'selected_sections',
        4: 'parameters',
        5: 'confirmed',
      };

      const field = fieldMap[currentStep!] || 'value';
      await interactMutation.mutateAsync({ [field]: option.id });
    },
    [currentStep, interactMutation]
  );

  return {
    sendMessage,
    selectOption,
    isProcessing: startMutation.isPending || interactMutation.isPending,
    error: startMutation.error || interactMutation.error,
  };
}
```

### 7.2 useProgress Hook (SSE)

```typescript
// hooks/useProgress.ts

import { useEffect, useState } from 'react';
import { useResearchStore } from '@/store/useResearchStore';
import { sseManager } from '@/lib/sse';
import type { SSEMessage, ProgressData, PhaseData, CompleteData } from '@/types/api';

export function useProgress(taskId: string | null) {
  const { setProgress, updatePhase, setStatus, setStatistics } = useResearchStore();
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    if (!taskId) return;

    // Subscribe to SSE
    const unsubscribe = sseManager.subscribe(taskId, (message: SSEMessage) => {
      switch (message.event) {
        case 'progress':
          const progressData = message.data as ProgressData;
          setProgress(progressData.progress);
          updatePhase(progressData.phase_id, {
            progress: progressData.progress,
          });
          break;

        case 'phase_start':
          const phaseStart = message.data as PhaseData;
          updatePhase(phaseStart.phase_id, {
            status: 'running',
          });
          break;

        case 'phase_complete':
          const phaseComplete = message.data as PhaseData;
          updatePhase(phaseComplete.phase_id, {
            status: phaseComplete.status,
            progress: 100,
          });
          break;

        case 'complete':
          const completeData = message.data as CompleteData;
          setStatus('completed');
          setProgress(100);
          setStatistics(completeData.statistics);
          break;

        case 'error':
          setStatus('error');
          break;
      }
    });

    // Check connection status periodically
    const interval = setInterval(() => {
      setIsConnected(sseManager.isConnected(taskId));
    }, 1000);

    return () => {
      unsubscribe();
      clearInterval(interval);
    };
  }, [taskId, setProgress, updatePhase, setStatus, setStatistics]);

  return { isConnected };
}
```

---

## 8. Zustand Store

```typescript
// store/useResearchStore.ts

import { create } from 'zustand';
import type {
  Phase,
  SelectOption,
  ResearchSummary,
  ResearchStatistics,
} from '@/types/api';

interface ResearchState {
  // Task info
  taskId: string | null;
  sessionId: string | null;

  // Progress
  progress: number;
  phases: Phase[];
  status: 'idle' | 'running' | 'completed' | 'error';

  // Step flow (data-driven)
  currentStep: number | null;
  stepOptions: SelectOption[] | null;

  // Results
  summary: ResearchSummary | null;
  statistics: ResearchStatistics | null;

  // Actions
  setTaskId: (id: string | null) => void;
  setSessionId: (id: string | null) => void;
  setProgress: (progress: number) => void;
  setPhases: (phases: Phase[]) => void;
  updatePhase: (id: string, updates: Partial<Phase>) => void;
  setStatus: (status: ResearchState['status']) => void;
  setStep: (step: number | null, options?: SelectOption[]) => void;
  setSummary: (summary: ResearchSummary | null) => void;
  setStatistics: (statistics: ResearchStatistics | null) => void;
  reset: () => void;
}

export const useResearchStore = create<ResearchState>((set) => ({
  taskId: null,
  sessionId: null,
  progress: 0,
  phases: [],
  status: 'idle',
  currentStep: null,
  stepOptions: null,
  summary: null,
  statistics: null,

  setTaskId: (id) => set({ taskId: id }),
  setSessionId: (id) => set({ sessionId: id }),
  setProgress: (progress) => set({ progress }),
  setPhases: (phases) => set({ phases }),
  updatePhase: (id, updates) =>
    set((state) => ({
      phases: state.phases.map((p) =>
        p.id === id ? { ...p, ...updates } : p
      ),
    })),
  setStatus: (status) => set({ status }),
  setStep: (step, options) =>
    set({ currentStep: step, stepOptions: options || null }),
  setSummary: (summary) => set({ summary }),
  setStatistics: (statistics) => set({ statistics }),
  reset: () =>
    set({
      taskId: null,
      sessionId: null,
      progress: 0,
      phases: [],
      status: 'idle',
      currentStep: null,
      stepOptions: null,
      summary: null,
      statistics: null,
    }),
}));

// store/useUIStore.ts

import { create } from 'zustand';

interface UIState {
  previewVisible: boolean;

  setPreviewVisible: (visible: boolean) => void;
}

export const useUIStore = create<UIState>((set) => ({
  previewVisible: true,

  setPreviewVisible: (visible) => set({ previewVisible: visible }),
}));
```

---

## 9. API Client

```typescript
// lib/api.ts

import axios, { AxiosInstance } from 'axios';
import type {
  StartResearchResponse,
  InteractRequest,
  InteractResponse,
  PreviewResponse,
  GenerateDocumentRequest,
} from '@/types/api';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 30000,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // Research API
  async startResearch(input: string, userId?: string): Promise<StartResearchResponse> {
    const { data } = await this.client.post('/api/v1/research/start', {
      user_input: input,
      user_id: userId,
    });
    return data;
  }

  async interact(request: InteractRequest): Promise<InteractResponse> {
    const { data } = await this.client.post('/api/v1/research/interact', request);
    return data;
  }

  async getPreview(taskId: string, format = 'html'): Promise<PreviewResponse> {
    const { data } = await this.client.get(`/api/v1/research/preview/${taskId}`, {
      params: { format },
    });
    return data;
  }

  // Document API
  async exportDocument(
    taskId: string,
    versionId: string,
    format: string
  ): Promise<Blob> {
    const { data } = await this.client.post(
      '/api/v1/documents/export',
      { task_id: taskId, version_id: versionId, format },
      { responseType: 'blob' }
    );
    return data;
  }
}

export const api = new ApiClient();
export default api;
```

---

## 10. Development Plan

### MVP Phase (Day 1-5)

| Day | Task | Deliverable |
|-----|------|-------------|
| 1 | Project setup | Next.js + dependencies |
| 2 | Layout + Chat | Resizable panels + assistant-ui |
| 3 | API Integration | ResearchAPI + OptionSelector |
| 4 | Progress + SSE | SSE manager + ProgressPanel |
| 5 | Preview + Polish | DocumentPreview + error handling |

### Dependencies

```json
{
  "dependencies": {
    "next": "^14.0.0",
    "react": "^18.2.0",
    "assistant-ui": "^0.5.0",
    "react-resizable-panels": "^2.0.0",
    "zustand": "^4.5.0",
    "@tanstack/react-query": "^5.0.0",
    "axios": "^1.6.0",
    "docx-preview": "^0.1.0",
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

---

## 11. Getting Started

```bash
# Create project
npx create-next-app@latest web --typescript --tailwind --app --src-dir

# Enter directory
cd web

# Install dependencies
npm install assistant-ui react-resizable-panels zustand @tanstack/react-query axios docx-preview lucide-react nanoid

# Install dev dependencies
npm install -D @types/node

# Initialize shadcn/ui
npx shadcn@latest init

# Add components
npx shadcn@latest add button card progress

# Start development
npm run dev
```

---

## 12. Summary of Optimizations

| Aspect | Before | After | Benefit |
|--------|--------|-------|---------|
| Chat UI | Custom ChatInterface | **assistant-ui** | ~50% less code |
| Layout | Fixed layout | **react-resizable-panels** | User-customizable |
| Real-time | Socket.IO | **SSE (EventSource)** | Simpler backend |
| Options | Hardcoded | **Data-driven from API** | Flexible |
| API URL | Inconsistent | **Unified /api/v1/** | Clear structure |
| Pages | Multiple | **Single page** | Faster MVP |

---

*Document Version: 2.0 (Optimized)*
*Last Updated: 2024*
