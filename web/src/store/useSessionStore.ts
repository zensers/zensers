// store/useSessionStore.ts
// Multi-session registry — unified management of metadata and cache for all sessions

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { api } from '@/lib/api';
import { nanoid } from 'nanoid';
import type {
  Phase,
  SelectOption,
  ResearchSummary,
  ResearchStatistics,
  ParameterConfig,
  ChatMessage,
  ResearchStatus,
  AgentMessageEvent,
  ResearchResult,
  ResearchFramework,
} from '@/types/api';

export interface SessionCache {
  id: string;
  title: string;
  taskId: string | null;
  activeTemplateId: string | null;
  researchTopic: string | null;
  status: ResearchStatus;
  currentStep: number | null;
  stepOptions: SelectOption[] | null;
  parameterConfig: ParameterConfig | null;
  summary: ResearchSummary | null;
  statistics: ResearchStatistics | null;
  framework: ResearchFramework | null;
  progress: number;
  phases: Phase[];
  messages: ChatMessage[];
  agentMessages: AgentMessageEvent[];
  previewUrl: string | null;
  downloadUrl: string | null;
  result: ResearchResult | null;
  interrupted: boolean;
  language: string;
  mode: string;
}

interface SessionRegistry {
  activeId: string | null;
  sessions: Record<string, SessionCache>;

  switchTo: (id: string) => void;
  createSession: (id: string, title?: string) => void;
  closeSession: (id: string) => void;

  /** Sync state back to cache from Research/Chat store */
  syncActive: (patch: Partial<SessionCache>) => void;
}

/**
 * Restore session: fetch details from backend and switch to it.
 * Now preserves execution state instead of resetting to idle.
 */
export async function restoreSession(id: string): Promise<void> {
  const store = useSessionStore.getState();

  // Cache hit → switch directly, preserve cached state
  if (store.sessions[id]) {
    store.switchTo(id);
    return;
  }

  // Create placeholder cache, switch immediately (show loading)
  store.switchTo(id);
  useSessionStore.getState().syncActive({ title: 'Loading...' });

  try {
    const detail: any = await api.getResearchDetail(id);

    const msgs: ChatMessage[] = (detail.messages || []).map((m: any) => ({
      id: m.id || nanoid(),
      role: m.role as 'user' | 'assistant',
      content: m.content,
      timestamp: m.timestamp || new Date().toISOString(),
    }));

    const status = detail.status;

    if (status === 'completed') {
      useSessionStore.getState().syncActive({
        title: detail.title || detail.topic || 'Untitled',
        taskId: id,
        messages: msgs,
        status: 'completed',
        currentStep: 6,
        phases: detail.phases || [],
        progress: detail.progress || 100,
        previewUrl: detail.preview_url || null,
        downloadUrl: detail.download_url || null,
        result: detail.result || null,
        agentMessages: detail.agent_messages || [],
        language: detail.language || 'zh',
        mode: detail.mode || 'chat',
        summary: detail.topic ? {
          topic: detail.topic,
          title: detail.title || detail.topic,
          output_type: detail.output_type || 'report',
          template: 'consulting',
          sections: [],
          parameters: {},
        } : undefined,
      });
    } else if (status === 'running' || status === 'reporting') {
      const interrupted = detail.interrupted;
      useSessionStore.getState().syncActive({
        title: detail.title || detail.topic || 'Untitled',
        taskId: id,
        messages: msgs,
        status: interrupted ? 'paused' : 'running',
        currentStep: 6,
        phases: detail.phases || [],
        progress: detail.progress || 0,
        agentMessages: detail.agent_messages || [],
        interrupted: !!interrupted,
        language: detail.language || 'zh',
        mode: detail.mode || 'research',
      });
    } else {
      // paused / analyzing / idle
      useSessionStore.getState().syncActive({
        title: detail.title || detail.topic || 'Untitled',
        taskId: id,
        messages: msgs,
        status: 'idle',
        currentStep: 0,
        phases: detail.phases || [],
        progress: detail.progress || 0,
        agentMessages: detail.agent_messages || [],
        previewUrl: detail.preview_url || null,
        result: detail.result || null,
        language: detail.language || 'zh',
        mode: detail.mode || 'chat',
      });
    }
  } catch (e) {
    console.error('Failed to restore session:', e);
    useSessionStore.getState().syncActive({
      title: 'Restore Failed',
      messages: [{
        id: nanoid(), role: 'assistant',
        content: 'Sorry, failed to restore session. Please try again or start a new conversation.',
        timestamp: new Date().toISOString(),
      }],
    });
  }
}

function emptyCache(id: string, title?: string): SessionCache {
  return {
    id,
    title: title || 'New Conversation',
    taskId: null,
    activeTemplateId: null,
    researchTopic: null,
    status: 'idle',
    currentStep: 0,
    stepOptions: null,
    parameterConfig: null,
    summary: null,
    statistics: null,
    framework: null,
    progress: 0,
    phases: [],
    messages: [],
    agentMessages: [],
    previewUrl: null,
    downloadUrl: null,
    result: null,
    interrupted: false,
    language: 'zh',
    mode: 'chat',
  };
}

export const useSessionStore = create<SessionRegistry>()(
  persist(
    (set, get) => ({
      activeId: null,
      sessions: {},

      switchTo: (id: string) => {
        set({ activeId: id });
      },

      createSession: (id: string, title?: string) => {
        const { activeId, sessions } = get();
        const pendingMsgs = activeId === '__pending__' ? sessions['__pending__']?.messages || [] : [];
        const { ['__pending__']: _, ...rest } = sessions;
        const newSession = { ...emptyCache(id, title), messages: pendingMsgs };
        set({ sessions: { ...rest, [id]: newSession }, activeId: id });
      },

      closeSession: (id: string) => {
        const { [id]: _, ...rest } = get().sessions;
        const newActive = get().activeId === id ? null : get().activeId;
        set({ sessions: rest, activeId: newActive });
      },

      syncActive: (patch: Partial<SessionCache>) => {
        const { activeId, sessions } = get();
        // Filter undefined values to prevent overwriting existing fields
        const cleanPatch = Object.fromEntries(
          Object.entries(patch).filter(([, v]) => v !== undefined)
        ) as Partial<SessionCache>;

        if (!activeId) {
          const pendingId = '__pending__';
          const newSession = { ...emptyCache(pendingId, cleanPatch.title || 'New Conversation'), ...cleanPatch };
          set({ sessions: { ...sessions, [pendingId]: newSession }, activeId: pendingId });
          return;
        }
        const existing = sessions[activeId];
        const merged = existing
          ? { ...existing, ...cleanPatch }
          : { ...emptyCache(activeId, cleanPatch.title), ...cleanPatch };
        set({ sessions: { ...sessions, [activeId]: merged } });
      },
    }),
    {
      name: 'Zensers-sessions',
      version: 1,
      partialize: (state) => ({
        activeId: (!state.activeId || state.activeId === '__pending__')
          ? null
          : (state.sessions[state.activeId]?.status === 'running' || state.sessions[state.activeId]?.status === 'paused')
            ? state.activeId
            : null,
        sessions: Object.fromEntries(
          Object.entries(state.sessions)
            .filter(([k]) => k !== '__pending__')
            .sort(([, a], [, b]) => {
              const weight = (s: SessionCache) => {
                if (s.status === 'running') return 3;
                if (s.result && typeof s.result === 'object' && Object.keys(s.result).length > 0) return 2;
                if (s.status === 'completed') return 1;
                return 0;
              };
              return weight(b) - weight(a);
            })
            .slice(-50)
            .map(([k, v]) => [k, {
              ...v,
              result: undefined,
              agentMessages: undefined,
            }])
        ),
      }),
      merge: (persisted, current) => ({
        ...current,
        ...(persisted as object),
        sessions: Object.fromEntries(
          Object.entries((persisted as any).sessions || {}).map(([k, v]: [string, any]) => [k, {
            ...(current.sessions[k] || {}),
            ...v,
          }])
        ),
      }),
    }
  )
);
