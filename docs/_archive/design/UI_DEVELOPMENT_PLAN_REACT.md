# Zensers Web UI Development Plan (React + TypeScript)

## 1. Tech Stack

### Frontend
| Technology | Version | Purpose |
|------|------|------|
| Next.js | 14.x | Full-stack Framework (App Router) |
| React | 18.x | UI Components |
| TypeScript | 5.x | Type Safety |
| Tailwind CSS | 3.x | Styling |
| shadcn/ui | latest | UI Component Library |
| Zustand | 4.x | State Management |
| React Query | 5.x | API Requests |
| Socket.IO Client | 4.x | Real-time Communication |
| docx-preview | latest | Word Preview |

### Backend (Existing)
| Technology | Purpose |
|------|------|
| FastAPI | API Framework |
| ResearchAPI | Research Task API |
| DocumentAPI | Document Generation API |
| WebSocket | Real-time Progress Push |

---

## 2. Project Structure

```
web/
├── src/
│   ├── app/                    # Next.js App Router
│   │   ├── layout.tsx          # Root Layout
│   │   ├── page.tsx            # Home Page
│   │   ├── research/
│   │   │   └── [id]/
│   │   │       └── page.tsx    # Research Detail Page
│   │   └── api/                # API Routes (optional)
│   │
│   ├── components/
│   │   ├── ui/                 # shadcn/ui Components
│   │   ├── chat/               # Chat Components
│   │   │   ├── ChatInterface.tsx
│   │   │   ├── MessageList.tsx
│   │   │   └── ChatInput.tsx
│   │   ├── preview/            # Preview Components
│   │   │   ├── DocumentPreview.tsx
│   │   │   └── PDFPreview.tsx
│   │   ├── progress/           # Progress Components
│   │   │   ├── ProgressBar.tsx
│   │   │   └── AgentStatus.tsx
│   │   └── layout/             # Layout Components
│   │
│   ├── lib/
│   │   ├── api.ts              # API Client
│   │   ├── websocket.ts        # WebSocket Connection
│   │   └── utils.ts            # Utility Functions
│   │
│   ├── hooks/
│   │   ├── useChat.ts          # Chat Hook
│   │   ├── useResearch.ts      # Research Task Hook
│   │   └── useProgress.ts      # Progress Hook
│   │
│   ├── store/
│   │   └── useStore.ts         # Zustand State
│   │
│   └── types/
│       └── index.ts            # TypeScript Types
│
├── public/
│   └── assets/
│
├── package.json
├── tsconfig.json
├── tailwind.config.ts
└── next.config.js
```

---

## 3. Core Feature Modules

### 1. Chat Interface (ChatInterface)

```tsx
// Chat Flow
User Input → POST /api/research/start → Returns clarification questions
User Answer → POST /api/research/interact → Returns next step
...
Confirm → Start Research Task → WebSocket pushes progress
```

**Features**:
- Multi-turn dialogue
- Clarification question display
- Quick option buttons
- Chat history

### 2. Progress Panel (ProgressPanel)

```tsx
// Progress Display
Research Task: China Lithium Battery Industry Analysis
├── ✅ Requirements Analysis (2s)
├── ✅ Data Collection (15s)
├── ⏳ Report Generation (in progress...)
│   ├── ✅ Outline
│   ├── ⏳ Content Generation
│   └── ○ Formatting
└── ○ Quality Check
```

**Features**:
- Real-time progress bar
- Agent execution status
- Timeline display
- Error prompts

### 3. Report Preview (DocumentPreview)

```tsx
// Word Preview Solution
import { DocxViewer } from 'docx-preview';

// Or use react-file-viewer
<FileViewer fileType='docx' filePath='/api/document/preview/{id}' />
```

**Features**:
- Word/PPT embedded preview
- Page turning, zoom
- Online reading
- Download export

### 4. Version Management (VersionPanel)

```tsx
// Version List
Version History:
├── v3 (current) - 10:30 - Deleted Chapter 2
├── v2 - 09:45 - Added data charts
└── v1 - 09:00 - Initial Version

[Compare Versions] [Rollback Version]
```

---

## 4. API Integration

### Backend APIs (Existing)

| API | Method | Description |
|-----|------|------|
| `/api/research/start` | POST | Start Research |
| `/api/research/interact` | POST | Interaction Response |
| `/api/research/feedback` | POST | Preview Feedback |
| `/api/research/preview/{id}` | GET | Get Preview |
| `/api/document/generate` | POST | Generate Document |
| `/api/document/preview/{id}` | GET | Document Preview |
| `/api/document/versions/{id}` | GET | Version List |
| `/ws/progress/{id}` | WebSocket | Progress Push |

### Frontend API Client

```typescript
// lib/api.ts
import axios from 'axios';

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
});

export const researchApi = {
  start: (input: string) => api.post('/api/research/start', { input }),
  interact: (sessionId: string, response: any) => 
    api.post('/api/research/interact', { sessionId, response }),
  getPreview: (taskId: string) => 
    api.get(`/api/research/preview/${taskId}`),
};

export const documentApi = {
  generate: (taskId: string, format: string) => 
    api.post('/api/document/generate', { taskId, format }),
  getPreview: (docId: string) => 
    api.get(`/api/document/preview/${docId}`, { responseType: 'blob' }),
  getVersions: (taskId: string) => 
    api.get(`/api/document/versions/${taskId}`),
};
```

---

## 5. Development Plan

### Phase 1: Project Setup + Chat UI (3 days)

| Day | Task |
|-----|------|
| 1 | Next.js project initialization, shadcn/ui installation, base layout |
| 2 | ChatInterface component, API client, chat flow |
| 3 | Chat history, quick options, error handling |

**Deliverable**: Conversational research launch interface

### Phase 2: Progress Panel + Preview (3 days)

| Day | Task |
|-----|------|
| 4 | WebSocket connection, progress push, progress bar component |
| 5 | Agent status display, timeline, docx-preview integration |
| 6 | Document preview page, page turning and zoom, download function |

**Deliverable**: Complete research execution + preview flow

### Phase 3: Enhancement + Deployment (2 days)

| Day | Task |
|-----|------|
| 7 | Version management, task history, settings page |
| 8 | Docker deployment, environment configuration, documentation |

**Deliverable**: Deployable complete application

---

## 6. Startup Commands

```bash
# Create project
npx create-next-app@latest web --typescript --tailwind --app

# Install dependencies
cd web
npm install shadcn-ui zustand @tanstack/react-query socket.io-client docx-preview

# Initialize shadcn/ui
npx shadcn-ui@latest init

# Add components
npx shadcn-ui@latest add button input card dialog tabs

# Start development
npm run dev

# Build for production
npm run build
```

---

## 7. Environment Variables

```env
# .env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

---

## 8. Reference Projects

| Project | GitHub | Description |
|------|--------|------|
| Dify | github.com/langgenius/dify | Open Source LLM Platform, Architecture Reference |
| Chatbot UI | github.com/mckaywrigley/chatbot-ui | ChatGPT-style UI |
| Vercel AI Chatbot | github.com/vercel-labs/ai-chatbot | Vercel Official Template |
