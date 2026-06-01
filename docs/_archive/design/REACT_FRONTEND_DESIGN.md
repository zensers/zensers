# Zensers Web Frontend - Detailed Design Document

> React + Next.js + TypeScript Frontend for Zensers Market Report System

---

## 1. Architecture Overview

### 1.1 Tech Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| Next.js | 14.x | Full-stack framework (App Router) |
| React | 18.x | UI components |
| TypeScript | 5.x | Type safety |
| Tailwind CSS | 3.x | Styling |
| shadcn/ui | latest | UI component library |
| Zustand | 4.x | State management |
| TanStack Query | 5.x | Server state & API requests |
| Socket.IO Client | 4.x | Real-time communication |
| docx-preview | latest | Word document preview |
| React Markdown | 9.x | Markdown rendering |

### 1.2 System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                        │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   Pages     │  │ Components  │  │   Hooks     │             │
│  │  (Routes)   │  │   (UI)      │  │  (Logic)    │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
│         │                │                │                     │
│  ┌──────┴────────────────┴────────────────┴──────┐             │
│  │              Zustand Store (Client State)      │             │
│  └───────────────────────┬───────────────────────┘             │
│                          │                                      │
│  ┌───────────────────────┴───────────────────────┐             │
│  │           TanStack Query (Server State)        │             │
│  └───────────────────────┬───────────────────────┘             │
└──────────────────────────┼──────────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    ┌────┴────┐      ┌─────┴─────┐     ┌─────┴─────┐
    │ REST API│      │ WebSocket │     │  SSE      │
    └────┬────┘      └─────┬─────┘     └─────┬─────┘
         │                 │                 │
┌────────┴─────────────────┴─────────────────┴────────┐
│                    Backend (FastAPI)                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │ ResearchAPI │  │ DocumentAPI │  │  WebSocket  │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## 2. Project Structure

```
web/
├── src/
│   ├── app/                          # Next.js App Router
│   │   ├── layout.tsx                # Root layout
│   │   ├── page.tsx                  # Home page (Chat)
│   │   ├── research/
│   │   │   └── [id]/
│   │   │       └── page.tsx          # Research detail page
│   │   ├── history/
│   │   │   └── page.tsx              # Task history page
│   │   └── settings/
│   │       └── page.tsx              # Settings page
│   │
│   ├── components/
│   │   ├── ui/                       # shadcn/ui components
│   │   │   ├── button.tsx
│   │   │   ├── card.tsx
│   │   │   ├── dialog.tsx
│   │   │   ├── input.tsx
│   │   │   ├── tabs.tsx
│   │   │   ├── progress.tsx
│   │   │   └── ...
│   │   │
│   │   ├── chat/                     # Chat components
│   │   │   ├── ChatInterface.tsx     # Main chat container
│   │   │   ├── MessageList.tsx       # Message display
│   │   │   ├── MessageItem.tsx       # Single message
│   │   │   ├── ChatInput.tsx         # Input area
│   │   │   ├── OptionSelector.tsx    # Multi-step options
│   │   │   └── QuickActions.tsx      # Quick action buttons
│   │   │
│   │   ├── progress/                 # Progress components
│   │   │   ├── ProgressPanel.tsx     # Main progress container
│   │   │   ├── ProgressBar.tsx       # Progress bar
│   │   │   ├── AgentStatus.tsx       # Agent execution status
│   │   │   └── Timeline.tsx          # Execution timeline
│   │   │
│   │   ├── preview/                  # Preview components
│   │   │   ├── DocumentPreview.tsx   # Document preview container
│   │   │   ├── WordPreview.tsx       # Word document viewer
│   │   │   ├── PDFPreview.tsx        # PDF viewer
│   │   │   ├── MarkdownPreview.tsx   # Markdown viewer
│   │   │   └── PreviewControls.tsx   # Zoom, pagination
│   │   │
│   │   ├── version/                  # Version components
│   │   │   ├── VersionList.tsx       # Version history list
│   │   │   ├── VersionDiff.tsx       # Version comparison
│   │   │   └── VersionActions.tsx    # Rollback, compare
│   │   │
│   │   └── layout/                   # Layout components
│   │       ├── Header.tsx            # App header
│   │       ├── Sidebar.tsx           # Navigation sidebar
│   │       └── MainLayout.tsx        # Main layout wrapper
│   │
│   ├── lib/
│   │   ├── api.ts                    # API client (Axios/Fetch)
│   │   ├── websocket.ts              # WebSocket manager
│   │   ├── utils.ts                  # Utility functions
│   │   └── constants.ts              # Constants
│   │
│   ├── hooks/
│   │   ├── useChat.ts                # Chat logic hook
│   │   ├── useResearch.ts            # Research task hook
│   │   ├── useProgress.ts            # Progress tracking hook
│   │   ├── useWebSocket.ts           # WebSocket hook
│   │   └── useDocument.ts            # Document operations hook
│   │
│   ├── store/
│   │   ├── useChatStore.ts           # Chat state
│   │   ├── useResearchStore.ts       # Research state
│   │   └── useUIStore.ts             # UI state (sidebar, modals)
│   │
│   ├── types/
│   │   ├── api.ts                    # API types
│   │   ├── chat.ts                   # Chat types
│   │   ├── research.ts               # Research types
│   │   └── document.ts               # Document types
│   │
│   └── styles/
│       └── globals.css               # Global styles
│
├── public/
│   └── assets/
│
├── package.json
├── tsconfig.json
├── tailwind.config.ts
├── next.config.js
├── .env.local
└── Dockerfile
```

---

## 3. Backend API Integration

### 3.1 API Endpoints Summary

Based on backend analysis:

#### Research API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/research/start` | POST | Start research session |
| `/api/research/interact` | POST | Handle interaction step |
| `/api/research/feedback` | POST | Handle preview feedback |
| `/api/research/preview/{task_id}` | GET | Get preview document |

#### Document API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/documents/generate` | POST | Generate document |
| `/documents/{task_id}/versions` | GET | List versions |
| `/documents/{task_id}/rollback` | POST | Rollback version |
| `/documents/{task_id}/preview` | GET | Get preview |
| `/documents/{task_id}/revisions` | GET | Get revision history |
| `/documents/revision` | POST | Handle revision request |
| `/documents/export` | POST | Export document |

#### Research List API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/research/completed` | GET | List completed research |
| `/research/{task_id}/generate` | POST | Delayed generate |

### 3.2 TypeScript Types

```typescript
// types/api.ts

// ============ Research API Types ============

export interface StartResearchRequest {
  user_input: string;
  user_id?: string;
}

export interface StartResearchResponse {
  session_id: string;
  step: 1;
  message: string;
  instruction: string;
  options: OutputTypeOption[];
  next_step: 'select_output_type';
}

export interface OutputTypeOption {
  id: string;
  label: string;
  description: string;
  icon?: string;
}

export interface InteractRequest {
  session_id: string;
  step: number;
  response: Record<string, any>;
}

export type InteractResponse =
  | Step2Response
  | Step3Response
  | Step4Response
  | Step5Response
  | Step6Response;

export interface Step2Response {
  session_id: string;
  step: 2;
  message: string;
  instruction: string;
  templates: Template[];
  next_step: 'select_template';
}

export interface Template {
  id: string;
  name: string;
  description: string;
  preview_image?: string;
}

export interface Step3Response {
  session_id: string;
  step: 3;
  message: string;
  instruction: string;
  sections: Section[];
  next_step: 'customize_sections';
}

export interface Section {
  id: string;
  title: string;
  description?: string;
  required: boolean;
  selected: boolean;
}

export interface Step4Response {
  session_id: string;
  step: 4;
  message: string;
  instruction: string;
  parameters: ResearchParameters;
  next_step: 'set_parameters';
}

export interface ResearchParameters {
  regions: string[];
  time_ranges: string[];
  depths: { id: string; label: string; description: string }[];
}

export interface Step5Response {
  session_id: string;
  step: 5;
  message: string;
  instruction: string;
  summary: ResearchSummary;
  confirm_action: string;
  back_action: string;
  next_step: 'confirm';
}

export interface ResearchSummary {
  topic: string;
  output_type: string;
  template: string;
  sections: string[];
  parameters: {
    region: string;
    time_range: string;
    depth: string;
    focus_areas: string;
  };
}

export interface Step6Response {
  session_id: string;
  step: 6;
  status: 'executing' | 'cancelled';
  message: string;
  final_plan?: ResearchPlan;
  next_step?: 'execute';
}

export interface ResearchPlan {
  topic: string;
  phases: Phase[];
  estimated_time: string;
}

export interface Phase {
  name: string;
  tasks: string[];
  estimated_time: string;
}

// ============ Feedback API Types ============

export interface FeedbackRequest {
  session_id: string;
  action: 'confirm' | 'revise' | 'cancel';
  section?: string;
  adjustment?: string;
}

export interface FeedbackResponse {
  session_id: string;
  status: 'completed' | 'revising' | 'cancelled';
  message: string;
  output_path?: string;
  revision_count?: number;
}

// ============ Preview API Types ============

export interface PreviewResponse {
  task_id: string;
  preview_url: string;
  preview_path: string;
  preview_format: 'html' | 'pdf' | 'png';
  cached: boolean;
  file_size: number;
}

// ============ Document API Types ============

export interface GenerateDocumentRequest {
  task_id: string;
  output_format: 'docx' | 'pptx' | 'pdf' | 'html';
  template: 'consulting' | 'academic' | 'business' | 'minimal';
}

export interface GenerateDocumentResponse {
  status: 'success' | 'failed';
  document_path?: string;
  version_id?: string;
  error?: string;
}

export interface Version {
  version_id: string;
  created_at: string;
  file_size?: number;
  changes?: string;
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

// ============ Progress Types (WebSocket) ============

export interface ProgressMessage {
  type: 'progress' | 'agent_start' | 'agent_complete' | 'error' | 'complete';
  task_id: string;
  timestamp: string;
  data: ProgressData | AgentData | ErrorData | CompleteData;
}

export interface ProgressData {
  phase: string;
  step: string;
  progress: number;  // 0-100
  message: string;
}

export interface AgentData {
  agent_id: string;
  agent_name: string;
  action: string;
  input?: any;
  output?: any;
}

export interface ErrorData {
  code: string;
  message: string;
  details?: any;
}

export interface CompleteData {
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
```

### 3.3 API Client

```typescript
// lib/api.ts

import axios, { AxiosInstance, AxiosError } from 'axios';
import type {
  StartResearchRequest,
  StartResearchResponse,
  InteractRequest,
  InteractResponse,
  FeedbackRequest,
  FeedbackResponse,
  PreviewResponse,
  GenerateDocumentRequest,
  GenerateDocumentResponse,
  Version,
  RevisionRequest,
} from '@/types/api';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Request interceptor
    this.client.interceptors.request.use(
      (config) => {
        // Add auth token if available
        const token = localStorage.getItem('auth_token');
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Response interceptor
    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        // Handle common errors
        if (error.response?.status === 401) {
          // Handle unauthorized
          window.location.href = '/login';
        }
        return Promise.reject(error);
      }
    );
  }

  // ============ Research API ============

  async startResearch(input: string, userId?: string): Promise<StartResearchResponse> {
    const response = await this.client.post('/api/research/start', {
      user_input: input,
      user_id: userId,
    } as StartResearchRequest);
    return response.data;
  }

  async interact(request: InteractRequest): Promise<InteractResponse> {
    const response = await this.client.post('/api/research/interact', request);
    return response.data;
  }

  async submitFeedback(request: FeedbackRequest): Promise<FeedbackResponse> {
    const response = await this.client.post('/api/research/feedback', request);
    return response.data;
  }

  async getPreview(taskId: string, format: string = 'html'): Promise<PreviewResponse> {
    const response = await this.client.get(`/api/research/preview/${taskId}`, {
      params: { format },
    });
    return response.data;
  }

  // ============ Document API ============

  async generateDocument(request: GenerateDocumentRequest): Promise<GenerateDocumentResponse> {
    const response = await this.client.post('/documents/generate', request);
    return response.data;
  }

  async listVersions(taskId: string, format: string = 'docx'): Promise<Version[]> {
    const response = await this.client.get(`/documents/${taskId}/versions`, {
      params: { format },
    });
    return response.data;
  }

  async rollbackVersion(taskId: string, format: string, targetVersion: string): Promise<any> {
    const response = await this.client.post(`/documents/${taskId}/rollback`, null, {
      params: { format, target_version: targetVersion },
    });
    return response.data;
  }

  async getDocumentPreview(taskId: string, versionId?: string): Promise<PreviewResponse> {
    const response = await this.client.get(`/documents/${taskId}/preview`, {
      params: { version_id: versionId },
    });
    return response.data;
  }

  async requestRevision(request: RevisionRequest): Promise<any> {
    const response = await this.client.post('/documents/revision', request);
    return response.data;
  }

  async getRevisionHistory(taskId: string): Promise<any> {
    const response = await this.client.get(`/documents/${taskId}/revisions`);
    return response.data;
  }

  async exportDocument(taskId: string, versionId: string, format: string): Promise<Blob> {
    const response = await this.client.post(
      '/documents/export',
      {
        task_id: taskId,
        version_id: versionId,
        format,
      },
      { responseType: 'blob' }
    );
    return response.data;
  }

  // ============ Research List API ============

  async listCompletedResearch(limit: number = 100): Promise<any[]> {
    const response = await this.client.get('/research/completed', {
      params: { limit },
    });
    return response.data;
  }

  async delayedGenerate(taskId: string, format: string, template: string): Promise<any> {
    const response = await this.client.post(`/research/${taskId}/generate`, {
      output_format: format,
      template,
    });
    return response.data;
  }
}

export const api = new ApiClient();
export default api;
```

### 3.4 WebSocket Manager

```typescript
// lib/websocket.ts

import { io, Socket } from 'socket.io-client';
import type { ProgressMessage } from '@/types/api';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';

type ProgressCallback = (message: ProgressMessage) => void;
type ConnectionCallback = (connected: boolean) => void;

class WebSocketManager {
  private socket: Socket | null = null;
  private progressCallbacks: Map<string, Set<ProgressCallback>> = new Map();
  private connectionCallbacks: Set<ConnectionCallback> = new Set();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;

  connect(): void {
    if (this.socket?.connected) return;

    this.socket = io(WS_URL, {
      transports: ['websocket'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
    });

    this.socket.on('connect', () => {
      console.log('WebSocket connected');
      this.reconnectAttempts = 0;
      this.notifyConnectionChange(true);
    });

    this.socket.on('disconnect', () => {
      console.log('WebSocket disconnected');
      this.notifyConnectionChange(false);
    });

    this.socket.on('progress', (message: ProgressMessage) => {
      const callbacks = this.progressCallbacks.get(message.task_id);
      if (callbacks) {
        callbacks.forEach((cb) => cb(message));
      }
    });

    this.socket.on('error', (error: Error) => {
      console.error('WebSocket error:', error);
    });
  }

  disconnect(): void {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
    }
  }

  subscribeToTask(taskId: string, callback: ProgressCallback): () => void {
    if (!this.progressCallbacks.has(taskId)) {
      this.progressCallbacks.set(taskId, new Set());
    }
    this.progressCallbacks.get(taskId)!.add(callback);

    // Join task room
    this.socket?.emit('subscribe', { task_id: taskId });

    // Return unsubscribe function
    return () => {
      const callbacks = this.progressCallbacks.get(taskId);
      if (callbacks) {
        callbacks.delete(callback);
        if (callbacks.size === 0) {
          this.progressCallbacks.delete(taskId);
          this.socket?.emit('unsubscribe', { task_id: taskId });
        }
      }
    };
  }

  onConnectionChange(callback: ConnectionCallback): () => void {
    this.connectionCallbacks.add(callback);
    return () => {
      this.connectionCallbacks.delete(callback);
    };
  }

  private notifyConnectionChange(connected: boolean): void {
    this.connectionCallbacks.forEach((cb) => cb(connected));
  }

  get isConnected(): boolean {
    return this.socket?.connected ?? false;
  }
}

export const wsManager = new WebSocketManager();
export default wsManager;
```

---

## 4. Component Design

### 4.1 Page Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  Header: Zensers - 智能市场研究平台         [通知] [设置]     │
├─────────────────────────────────────────────────────────────────────┤
│        │                                                            │
│ Side   │                    Main Content                            │
│ bar    │                                                            │
│        │  ┌──────────────────────────────────────────────────────┐  │
│ [新建] │  │                                                          │  │
│        │  │                                                          │  │
│ 历史   │  │                    Chat Interface                      │  │
│ 任务   │  │                                                          │  │
│        │  │                                                          │  │
│ 设置   │  └──────────────────────────────────────────────────────┘  │
│        │                                                            │
│        │  ┌─────────────────┐  ┌─────────────────────────────────┐  │
│        │  │  Progress Panel │  │       Document Preview          │  │
│        │  │                 │  │                                 │  │
│        │  │  ██████░░ 60%   │  │    [Word Document Preview]      │  │
│        │  │                 │  │                                 │  │
│        │  │  ✓ Phase 1      │  │    Page 1 / 15                  │  │
│        │  │  ✓ Phase 2      │  │    [Zoom] [Download]            │  │
│        │  │  ⏳ Phase 3     │  │                                 │  │
│        │  │  ○ Phase 4      │  │                                 │  │
│        │  └─────────────────┘  └─────────────────────────────────┘  │
│        │                                                            │
└────────┴────────────────────────────────────────────────────────────┘
```

### 4.2 Core Components

#### 4.2.1 ChatInterface

```tsx
// components/chat/ChatInterface.tsx

'use client';

import { useState, useRef, useEffect } from 'react';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { OptionSelector } from './OptionSelector';
import { useChatStore } from '@/store/useChatStore';
import { useChat } from '@/hooks/useChat';

export function ChatInterface() {
  const { messages, currentStep, isProcessing } = useChatStore();
  const { sendMessage, selectOption } = useChat();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex flex-col h-full">
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4">
        <MessageList messages={messages} />
        <div ref={messagesEndRef} />
      </div>

      {/* Option Selector (for multi-step flow) */}
      {currentStep && currentStep < 6 && (
        <OptionSelector
          step={currentStep}
          onSelect={selectOption}
          disabled={isProcessing}
        />
      )}

      {/* Input Area */}
      <div className="border-t p-4">
        <ChatInput
          onSend={sendMessage}
          disabled={isProcessing || (currentStep && currentStep < 6)}
          placeholder={
            currentStep === 6
              ? '输入修订意见或确认定稿...'
              : '输入研究主题开始...'
          }
        />
      </div>
    </div>
  );
}
```

#### 4.2.2 MessageList & MessageItem

```tsx
// components/chat/MessageList.tsx

import { MessageItem } from './MessageItem';
import type { ChatMessage } from '@/types/chat';

interface MessageListProps {
  messages: ChatMessage[];
}

export function MessageList({ messages }: MessageListProps) {
  return (
    <div className="space-y-4">
      {messages.map((message) => (
        <MessageItem key={message.id} message={message} />
      ))}
    </div>
  );
}

// components/chat/MessageItem.tsx

import { cn } from '@/lib/utils';
import { Bot, User } from 'lucide-react';
import type { ChatMessage } from '@/types/chat';

interface MessageItemProps {
  message: ChatMessage;
}

export function MessageItem({ message }: MessageItemProps) {
  const isUser = message.role === 'user';

  return (
    <div
      className={cn(
        'flex gap-3',
        isUser ? 'flex-row-reverse' : 'flex-row'
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          'flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center',
          isUser ? 'bg-primary text-primary-foreground' : 'bg-muted'
        )}
      >
        {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
      </div>

      {/* Message Content */}
      <div
        className={cn(
          'max-w-[80%] rounded-lg px-4 py-2',
          isUser
            ? 'bg-primary text-primary-foreground'
            : 'bg-muted'
        )}
      >
        {message.content}
      </div>
    </div>
  );
}
```

#### 4.2.3 OptionSelector (Multi-step Flow)

```tsx
// components/chat/OptionSelector.tsx

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Check, FileText, Settings, Globe, Clock, BarChart } from 'lucide-react';

interface OptionSelectorProps {
  step: number;
  onSelect: (response: Record<string, any>) => void;
  disabled: boolean;
}

const stepConfigs = {
  1: {
    title: '选择输出类型',
    description: '请选择您需要的报告类型',
    options: [
      { id: 'research_report', label: '研究报告', icon: FileText, description: '完整的市场研究报告' },
      { id: 'brief_report', label: '简要报告', icon: FileText, description: '精简版分析报告' },
      { id: 'data_analysis', label: '数据分析', icon: BarChart, description: '数据可视化分析' },
    ],
    field: 'output_type',
  },
  2: {
    title: '选择模板',
    description: '选择报告模板样式',
    options: [
      { id: 'market_research_standard', label: '标准模板', description: 'McKinsey风格' },
      { id: 'market_research_detailed', label: '详细模板', description: '包含更多分析维度' },
      { id: 'market_research_executive', label: '高管摘要', description: '简洁高层汇报' },
    ],
    field: 'template_id',
  },
  // ... more steps
};

export function OptionSelector({ step, onSelect, disabled }: OptionSelectorProps) {
  const config = stepConfigs[step as keyof typeof stepConfigs];

  if (!config) return null;

  return (
    <div className="border-t p-4 bg-muted/50">
      <h3 className="text-lg font-semibold mb-2">{config.title}</h3>
      <p className="text-sm text-muted-foreground mb-4">{config.description}</p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {config.options.map((option) => (
          <Card
            key={option.id}
            className="cursor-pointer hover:border-primary transition-colors"
            onClick={() => disabled || onSelect({ [config.field]: option.id })}
          >
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">{option.label}</CardTitle>
            </CardHeader>
            <CardContent>
              <CardDescription>{option.description}</CardDescription>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
```

#### 4.2.4 ProgressPanel

```tsx
// components/progress/ProgressPanel.tsx

'use client';

import { useProgress } from '@/hooks/useProgress';
import { ProgressBar } from './ProgressBar';
import { AgentStatus } from './AgentStatus';
import { Timeline } from './Timeline';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Loader2, CheckCircle2, Circle } from 'lucide-react';

interface ProgressPanelProps {
  taskId: string;
}

export function ProgressPanel({ taskId }: ProgressPanelProps) {
  const { progress, phases, currentPhase, isConnected } = useProgress(taskId);

  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between">
          <span>研究进度</span>
          {isConnected ? (
            <span className="text-xs text-muted-foreground">实时更新</span>
          ) : (
            <span className="text-xs text-destructive">连接断开</span>
          )}
        </CardTitle>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Progress Bar */}
        <ProgressBar value={progress} />

        {/* Phase Status */}
        <div className="space-y-2">
          {phases.map((phase, index) => (
            <div
              key={phase.id}
              className="flex items-center gap-2 text-sm"
            >
              {phase.status === 'completed' ? (
                <CheckCircle2 className="w-4 h-4 text-green-500" />
              ) : phase.status === 'running' ? (
                <Loader2 className="w-4 h-4 text-primary animate-spin" />
              ) : (
                <Circle className="w-4 h-4 text-muted-foreground" />
              )}
              <span className={phase.status === 'running' ? 'font-medium' : ''}>
                {phase.name}
              </span>
              {phase.status === 'running' && (
                <span className="text-muted-foreground">
                  ({phase.progress}%)
                </span>
              )}
            </div>
          ))}
        </div>

        {/* Agent Status (expandable) */}
        {currentPhase && (
          <AgentStatus phase={currentPhase} />
        )}
      </CardContent>
    </Card>
  );
}
```

#### 4.2.5 DocumentPreview

```tsx
// components/preview/DocumentPreview.tsx

'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { WordPreview } from './WordPreview';
import { MarkdownPreview } from './MarkdownPreview';
import { PreviewControls } from './PreviewControls';
import { api } from '@/lib/api';
import { Download, FileText, RefreshCw, Maximize2 } from 'lucide-react';

interface DocumentPreviewProps {
  taskId: string;
  versionId?: string;
}

export function DocumentPreview({ taskId, versionId }: DocumentPreviewProps) {
  const [format, setFormat] = useState<'html' | 'markdown'>('html');
  const [zoom, setZoom] = useState(100);

  const { data: preview, isLoading, error, refetch } = useQuery({
    queryKey: ['preview', taskId, versionId],
    queryFn: () => api.getPreview(taskId, format),
    enabled: !!taskId,
  });

  const handleDownload = async () => {
    const blob = await api.exportDocument(taskId, versionId || 'v1', 'docx');
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
          <CardTitle>报告预览</CardTitle>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" onClick={() => refetch()}>
              <RefreshCw className="w-4 h-4" />
            </Button>
            <Button variant="ghost" size="icon" onClick={handleDownload}>
              <Download className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="flex-1 overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-full text-destructive">
            预览加载失败
          </div>
        ) : preview ? (
          <div className="h-full flex flex-col">
            <PreviewControls zoom={zoom} onZoomChange={setZoom} />
            <div className="flex-1 overflow-auto border rounded-lg">
              {preview.preview_format === 'html' ? (
                <iframe
                  src={preview.preview_url}
                  className="w-full h-full"
                  style={{ transform: `scale(${zoom / 100})`, transformOrigin: 'top left' }}
                />
              ) : (
                <WordPreview url={preview.preview_url} />
              )}
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            <FileText className="w-12 h-12 mr-2" />
            <span>暂无预览</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
```

---

## 5. State Management

### 5.1 Zustand Stores

```typescript
// store/useChatStore.ts

import { create } from 'zustand';
import type { ChatMessage } from '@/types/chat';

interface ChatState {
  messages: ChatMessage[];
  currentStep: number | null;
  sessionId: string | null;
  isProcessing: boolean;

  // Actions
  addMessage: (message: ChatMessage) => void;
  setStep: (step: number | null) => void;
  setSessionId: (id: string | null) => void;
  setProcessing: (processing: boolean) => void;
  reset: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  currentStep: null,
  sessionId: null,
  isProcessing: false,

  addMessage: (message) =>
    set((state) => ({
      messages: [...state.messages, message],
    })),

  setStep: (step) => set({ currentStep: step }),

  setSessionId: (id) => set({ sessionId: id }),

  setProcessing: (processing) => set({ isProcessing: processing }),

  reset: () =>
    set({
      messages: [],
      currentStep: null,
      sessionId: null,
      isProcessing: false,
    }),
}));

// store/useResearchStore.ts

import { create } from 'zustand';
import type { ResearchSummary, Phase, Section } from '@/types/api';

interface ResearchState {
  taskId: string | null;
  summary: ResearchSummary | null;
  phases: Phase[];
  sections: Section[];
  progress: number;
  status: 'idle' | 'running' | 'completed' | 'error';

  // Actions
  setTaskId: (id: string | null) => void;
  setSummary: (summary: ResearchSummary | null) => void;
  setPhases: (phases: Phase[]) => void;
  updatePhase: (index: number, updates: Partial<Phase>) => void;
  setProgress: (progress: number) => void;
  setStatus: (status: ResearchState['status']) => void;
  reset: () => void;
}

export const useResearchStore = create<ResearchState>((set) => ({
  taskId: null,
  summary: null,
  phases: [],
  sections: [],
  progress: 0,
  status: 'idle',

  setTaskId: (id) => set({ taskId: id }),
  setSummary: (summary) => set({ summary }),
  setPhases: (phases) => set({ phases }),
  updatePhase: (index, updates) =>
    set((state) => ({
      phases: state.phases.map((p, i) =>
        i === index ? { ...p, ...updates } : p
      ),
    })),
  setProgress: (progress) => set({ progress }),
  setStatus: (status) => set({ status }),
  reset: () =>
    set({
      taskId: null,
      summary: null,
      phases: [],
      sections: [],
      progress: 0,
      status: 'idle',
    }),
}));

// store/useUIStore.ts

import { create } from 'zustand';

interface UIState {
  sidebarOpen: boolean;
  previewVisible: boolean;
  activeTab: 'chat' | 'preview' | 'versions';

  // Actions
  toggleSidebar: () => void;
  setPreviewVisible: (visible: boolean) => void;
  setActiveTab: (tab: UIState['activeTab']) => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: true,
  previewVisible: true,
  activeTab: 'chat',

  toggleSidebar: () =>
    set((state) => ({ sidebarOpen: !state.sidebarOpen })),

  setPreviewVisible: (visible) => set({ previewVisible: visible }),

  setActiveTab: (tab) => set({ activeTab: tab }),
}));
```

### 5.2 Custom Hooks

```typescript
// hooks/useChat.ts

import { useCallback } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useChatStore } from '@/store/useChatStore';
import { useResearchStore } from '@/store/useResearchStore';
import { api } from '@/lib/api';
import { nanoid } from 'nanoid';

export function useChat() {
  const {
    messages,
    sessionId,
    currentStep,
    addMessage,
    setStep,
    setSessionId,
    setProcessing,
    reset,
  } = useChatStore();

  const { setTaskId, setSummary, setPhases, setStatus } = useResearchStore();

  // Start research mutation
  const startMutation = useMutation({
    mutationFn: (input: string) => api.startResearch(input),
    onSuccess: (data) => {
      setSessionId(data.session_id);
      setStep(data.step);
      addMessage({
        id: nanoid(),
        role: 'assistant',
        content: data.message,
        timestamp: new Date().toISOString(),
      });
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
      setStep(data.step);

      if (data.step === 6 && data.status === 'executing') {
        // Research started
        setTaskId(data.session_id);
        setStatus('running');
        if (data.final_plan) {
          setPhases(data.final_plan.phases);
        }
      }

      addMessage({
        id: nanoid(),
        role: 'assistant',
        content: data.message,
        timestamp: new Date().toISOString(),
      });
    },
  });

  const sendMessage = useCallback(
    async (content: string) => {
      // Add user message
      addMessage({
        id: nanoid(),
        role: 'user',
        content,
        timestamp: new Date().toISOString(),
      });

      setProcessing(true);

      try {
        if (!sessionId) {
          // Start new research
          await startMutation.mutateAsync(content);
        } else {
          // Continue interaction
          await interactMutation.mutateAsync({ user_input: content });
        }
      } finally {
        setProcessing(false);
      }
    },
    [sessionId, startMutation, interactMutation, addMessage, setProcessing]
  );

  const selectOption = useCallback(
    async (response: Record<string, any>) => {
      addMessage({
        id: nanoid(),
        role: 'user',
        content: Object.values(response).join(', '),
        timestamp: new Date().toISOString(),
      });

      setProcessing(true);

      try {
        await interactMutation.mutateAsync(response);
      } finally {
        setProcessing(false);
      }
    },
    [interactMutation, addMessage, setProcessing]
  );

  return {
    messages,
    sessionId,
    currentStep,
    isProcessing: startMutation.isPending || interactMutation.isPending,
    sendMessage,
    selectOption,
    reset,
  };
}

// hooks/useProgress.ts

import { useEffect, useState } from 'react';
import { useResearchStore } from '@/store/useResearchStore';
import { wsManager } from '@/lib/websocket';
import type { ProgressMessage } from '@/types/api';

export function useProgress(taskId: string | null) {
  const { progress, phases, setProgress, updatePhase, setStatus } = useResearchStore();
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    if (!taskId) return;

    // Connect WebSocket
    wsManager.connect();

    // Subscribe to task progress
    const unsubscribe = wsManager.subscribeToTask(taskId, (message: ProgressMessage) => {
      switch (message.type) {
        case 'progress':
          setProgress(message.data.progress);
          // Update specific phase if needed
          break;

        case 'agent_start':
          // Mark agent as running
          break;

        case 'agent_complete':
          // Mark agent as completed
          break;

        case 'complete':
          setStatus('completed');
          setProgress(100);
          break;

        case 'error':
          setStatus('error');
          break;
      }
    });

    // Track connection status
    const unsubscribeConnection = wsManager.onConnectionChange(setIsConnected);

    return () => {
      unsubscribe();
      unsubscribeConnection();
    };
  }, [taskId, setProgress, setStatus]);

  return {
    progress,
    phases,
    currentPhase: phases.find((p) => p.status === 'running'),
    isConnected,
  };
}
```

---

## 6. Development Phases

### Phase 1: Project Setup (Day 1-2)

| Task | Description |
|------|-------------|
| Create Next.js project | `npx create-next-app@latest web --typescript --tailwind --app` |
| Install dependencies | shadcn/ui, Zustand, TanStack Query, Socket.IO, docx-preview |
| Configure Tailwind | Custom theme, colors, fonts |
| Setup project structure | Create folders, base files |
| Create base layout | Header, Sidebar, MainLayout |

### Phase 2: Chat Interface (Day 2-3)

| Task | Description |
|------|-------------|
| ChatInterface component | Main chat container |
| MessageList component | Message display |
| ChatInput component | User input area |
| OptionSelector component | Multi-step flow options |
| useChat hook | Chat logic |
| Zustand store | Chat state management |

### Phase 3: Progress Panel (Day 3-4)

| Task | Description |
|------|-------------|
| ProgressPanel component | Progress display |
| ProgressBar component | Visual progress |
| AgentStatus component | Agent execution details |
| Timeline component | Execution timeline |
| useProgress hook | Progress tracking |
| WebSocket integration | Real-time updates |

### Phase 4: Document Preview (Day 4-5)

| Task | Description |
|------|-------------|
| DocumentPreview component | Preview container |
| WordPreview component | Word document viewer |
| MarkdownPreview component | Markdown viewer |
| PreviewControls component | Zoom, pagination |
| Version list | Version history |

### Phase 5: Integration (Day 5-6)

| Task | Description |
|------|-------------|
| API client | Full API integration |
| WebSocket manager | Real-time communication |
| Error handling | User-friendly errors |
| Loading states | Loading indicators |
| End-to-end flow | Complete user journey |

### Phase 6: Polish & Deploy (Day 6-8)

| Task | Description |
|------|-------------|
| Responsive design | Mobile adaptation |
| Dark mode | Theme toggle |
| Docker configuration | Dockerfile, docker-compose |
| Environment config | .env files |
| Documentation | README, deployment guide |

---

## 7. Environment Configuration

```env
# .env.local

# API Configuration
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000

# Optional: Analytics
NEXT_PUBLIC_GA_ID=

# Optional: Auth
NEXT_PUBLIC_AUTH_ENABLED=false
```

---

## 8. Docker Configuration

```dockerfile
# Dockerfile

FROM node:20-alpine AS base

# Install dependencies only when needed
FROM base AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

# Rebuild the source code only when needed
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED 1

RUN npm run build

# Production image
FROM base AS runner
WORKDIR /app

ENV NODE_ENV production
ENV NEXT_TELEMETRY_DISABLED 1

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public

# Set the correct permission for prerender cache
RUN mkdir .next
RUN chown nextjs:nodejs .next

# Automatically leverage output traces to reduce image size
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT 3000
ENV HOSTNAME "0.0.0.0"

CMD ["node", "server.js"]
```

```yaml
# docker-compose.yml

version: '3.8'

services:
  frontend:
    build:
      context: ./web
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://backend:8000
      - NEXT_PUBLIC_WS_URL=ws://backend:8000
    depends_on:
      - backend
    networks:
      - Zensers-network

  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./output:/app/output
    networks:
      - Zensers-network

networks:
  Zensers-network:
    driver: bridge
```

---

## 9. Getting Started

```bash
# Create project
npx create-next-app@latest web --typescript --tailwind --app --src-dir

# Enter directory
cd web

# Install dependencies
npm install zustand @tanstack/react-query socket.io-client docx-preview react-markdown
npm install -D @types/node

# Initialize shadcn/ui
npx shadcn@latest init

# Add components
npx shadcn@latest add button card dialog input tabs progress

# Start development
npm run dev
```

---

## 10. Reference Projects

| Project | GitHub | Reference For |
|---------|--------|---------------|
| Dify | github.com/langgenius/dify | Architecture, Chat UI |
| Vercel AI Chatbot | github.com/vercel-labs/ai-chatbot | Chat patterns, Streaming |
| Chatbot UI | github.com/mckaywrigley/chatbot-ui | UI design |

---

*Document Version: 1.0*
*Last Updated: 2024*
