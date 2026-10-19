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
  QualityStateData,
  ReportContextSnapshot,
} from '@/types/api';
import { normalizeStepOptions } from '@/lib/normalize-options';
import { normalizeChatMessage } from '@/lib/normalize-message';
import { normalizeProgress } from '@/lib/progress';

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
  qualityState: QualityStateData | null;
  reportContext: ReportContextSnapshot | null;
}

interface SessionRegistry {
  activeId: string | null;
  isRestoring: boolean;
  sessions: Record<string, SessionCache>;

  switchTo: (id: string) => void;
  createSession: (id: string, title?: string, initialMessages?: ChatMessage[]) => void;
  closeSession: (id: string) => void;

  /** Sync state back to cache from Research/Chat store */
  syncActive: (patch: Partial<SessionCache>) => void;
  applyReportContext: (context: ReportContextSnapshot) => void;
}

let restoreGeneration = 0;

/**
 * Restore session: fetch details from backend and switch to it.
 * Now preserves execution state instead of resetting to idle.
 */
export async function restoreSession(id: string): Promise<void> {
  const generation = ++restoreGeneration;
  const store = useSessionStore.getState();
  useSessionStore.setState({ isRestoring: true });
  const finishRestore = () => {
    if (generation === restoreGeneration) {
      useSessionStore.setState({ isRestoring: false });
    }
  };

  // A terminal cache is only a fast first paint. Report context must still be
  // reconciled with the backend because revisions can finish after the cache.
  const cached = store.sessions[id];
  if (cached && (cached.status === 'completed' || cached.status === 'error')) {
    store.switchTo(id);
    try {
      const context = await api.getReportContext(id);
      if (generation !== restoreGeneration || useSessionStore.getState().activeId !== id) {
        finishRestore();
        return;
      }
      useSessionStore.getState().applyReportContext(context);
    } catch (e) {
      console.warn('Failed to refresh terminal report context:', e);
    }
    finishRestore();
    return;
  }

  // For non-terminal or missing cache, always fetch fresh state from backend
  store.switchTo(id);
  useSessionStore.getState().syncActive({ title: cached?.title || 'Loading...' });

  try {
    const detail: any = await api.getResearchDetail(id);
    if (generation !== restoreGeneration || useSessionStore.getState().activeId !== id) {
      finishRestore();
      return;
    }

    const msgs: ChatMessage[] = (detail.messages || [])
      .filter((m: any) => m._type !== 'processing_ack')
      .map((m: any) => ({
      id: m.id || nanoid(),
      role: (m.role === 'user' || m.role === 'assistant' || m.role === 'agent'
      ? m.role
        : 'system') as ChatMessage['role'],
      content: normalizeChatMessage(m.content),
      timestamp: m.timestamp || new Date().toISOString(),
      ...(m.response_id ? { metadata: { responseId: m.response_id } } : {}),
      ...(m.agent_id || m.agent_name || m.action ? {
        agent: {
          id: m.agent_id || '',
          name: m.agent_name || '',
          action: m.action || '',
          completedCount: m.completedCount,
          totalCount: m.totalCount,
          provider: m.provider,
          quality_score: m.quality_score,
          cache_hit: m.cache_hit,
          stop_reason: m.stop_reason,
        },
      } : {}),
    }));

    const status = detail.status;

    // Server history is merged into the live chat store (sorted, deduped)
    // instead of blindly replacing the session cache: local messages may be
    // newer than the server snapshot, and a raw replace would let the next
    // streaming flush write the local ordering back over it. The merged array
    // reaches the cache through the chat store's flush sync below.
    // Dynamic import keeps this file off the useChatStore module graph — a
    // static edge would create an import cycle that breaks module
    // initialization order (useChatStore subscribes to this store at eval).
    const { useChatStore } = await import('./useChatStore');
    if (generation !== restoreGeneration || useSessionStore.getState().activeId !== id) {
      finishRestore();
      return;
    }
    useChatStore.getState().mergeServerMessages(msgs);

    if (status === 'completed') {
      const framework = detail.framework || cached?.framework || null;
      const stepOptions = normalizeStepOptions(detail.suggestions?.length ? detail.suggestions : cached?.stepOptions);
      const currentStep = detail.step ?? cached?.currentStep ?? 6;
      const parameterConfig = cached?.parameterConfig || null;
      const activeTemplateId = cached?.activeTemplateId || null;
      const researchTopic = cached?.researchTopic || null;
      useSessionStore.getState().syncActive({
        title: detail.title || detail.topic || 'Untitled',
        taskId: id,
        status: 'completed',
        currentStep,
        stepOptions,
        framework,
        parameterConfig,
        activeTemplateId,
        researchTopic,
        phases: (detail.phases || []).map((phase: any) => ({ ...phase, progress: normalizeProgress(phase.progress) })),
        progress: normalizeProgress(detail.progress ?? 100),
        previewUrl: detail.preview_url || null,
        downloadUrl: detail.download_url || null,
        result: detail.result || null,
        agentMessages: detail.agent_messages || [],
        reportContext: detail.report_context || null,
        language: detail.language || 'zh',
        mode: detail.mode || 'chat',
        summary: detail.topic ? {
          topic: detail.topic,
          title: detail.title || detail.topic,
          output_type: detail.output_type || 'report',
          template: 'consulting',
          sections: detail.selected_sections || [],
          parameters: detail.custom_params || {},
        } : undefined,
      });
    } else if (status === 'running' || status === 'reporting') {
      const interrupted = detail.interrupted;
      const framework = detail.framework || cached?.framework || null;
      const stepOptions = normalizeStepOptions(detail.suggestions?.length ? detail.suggestions : cached?.stepOptions);
      const currentStep = detail.step ?? cached?.currentStep ?? 6;
      const parameterConfig = cached?.parameterConfig || null;
      const activeTemplateId = cached?.activeTemplateId || null;
      const researchTopic = cached?.researchTopic || null;
      useSessionStore.getState().syncActive({
        title: detail.title || detail.topic || 'Untitled',
        taskId: id,
        status: interrupted ? 'paused' : 'running',
        currentStep,
        stepOptions,
        framework,
        parameterConfig,
        activeTemplateId,
        researchTopic,
        phases: (detail.phases || []).map((phase: any) => ({ ...phase, progress: normalizeProgress(phase.progress) })),
        progress: normalizeProgress(detail.progress ?? 0),
        agentMessages: detail.agent_messages || [],
        reportContext: detail.report_context || null,
        interrupted: !!interrupted,
        language: detail.language || 'zh',
        mode: detail.mode || 'research',
      });
    } else {
      const framework = detail.framework || cached?.framework || null;
      const stepOptions = normalizeStepOptions(detail.suggestions?.length ? detail.suggestions : cached?.stepOptions);
      const currentStep = detail.step ?? cached?.currentStep ?? 0;
      const parameterConfig = cached?.parameterConfig || null;
      const activeTemplateId = cached?.activeTemplateId || null;
      const researchTopic = cached?.researchTopic || null;
      useSessionStore.getState().syncActive({
        title: detail.title || detail.topic || 'Untitled',
        taskId: id,
        status: detail.status === 'paused' ? 'paused'
          : detail.status === 'cancelled' ? 'paused'
          : detail.status === 'error' ? 'error'
          : 'idle',
        currentStep,
        stepOptions,
        framework,
        parameterConfig,
        activeTemplateId,
        researchTopic,
        phases: (detail.phases || []).map((phase: any) => ({ ...phase, progress: normalizeProgress(phase.progress) })),
        progress: normalizeProgress(detail.progress ?? 0),
        agentMessages: detail.agent_messages || [],
        previewUrl: detail.preview_url || null,
        result: detail.result || null,
        reportContext: detail.report_context || null,
        language: detail.language || 'zh',
        mode: detail.mode || 'chat',
      });
    }
  } catch (e) {
    if (generation !== restoreGeneration || useSessionStore.getState().activeId !== id) {
      finishRestore();
      return;
    }
    console.error('Failed to restore session:', e);
    useSessionStore.getState().syncActive({
      title: 'Restore Failed',
      messages: [{
        id: nanoid(), role: 'assistant',
        content: 'Sorry, failed to restore session. Please try again or start a new conversation.',
        timestamp: new Date().toISOString(),
      }],
    });
  } finally {
    finishRestore();
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
    qualityState: null,
    reportContext: null,
  };
}

export const useSessionStore = create<SessionRegistry>()(
  persist(
    (set, get) => ({
      activeId: null,
      isRestoring: false,
      sessions: {},

      switchTo: (id: string) => {
        set({ activeId: id });
      },

      createSession: (id: string, title?: string, initialMessages?: ChatMessage[]) => {
        const { activeId, sessions } = get();
        const pendingMsgs = initialMessages && initialMessages.length > 0
          ? initialMessages
          : (activeId === '__pending__' ? sessions['__pending__']?.messages || [] : []);
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

      applyReportContext: (context: ReportContextSnapshot) => {
        const { activeId, sessions } = get();
        if (!activeId || context.session_id !== activeId) return;
        const existing = sessions[activeId];
        const current = existing?.reportContext;
        if (current && current.context_revision > context.context_revision) return;
        const merged = existing
          ? { ...existing, reportContext: context }
          : { ...emptyCache(activeId), reportContext: context };
        set({ sessions: { ...sessions, [activeId]: merged } });
      },
    }),
    {
      name: 'Zensers-sessions',
      version: 2,
      partialize: (state) => ({
        activeId: (!state.activeId || state.activeId === '__pending__')
          ? null
          : state.sessions[state.activeId]?.taskId
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
            .slice(-200)
            .map(([k, v]) => [k, {
               ...v,
               messages: (v as any).messages?.filter((m: any) => !(m.role === 'agent' && (m.agent?.action === 'heartbeat' || m.action === 'heartbeat'))) || [],
               result: undefined,
               qualityState: undefined,
              }])
        ),
      }),
      merge: (persisted, current) => ({
        ...current,
        ...(persisted as object),
        sessions: Object.fromEntries(
          Object.entries((persisted as any).sessions || {}).map(([k, v]: [string, any]) => {
            // On page reload, no task can be truly "running" — downgrade to "paused"
            const fixedStatus = v?.status === 'running' ? 'paused' : v?.status;
            return [k, {
               ...emptyCache(k, v?.title),
               ...(current.sessions[k] || {}),
               ...v,
               messages: v?.messages?.filter((m: any) => !(m.role === 'agent' && (m.agent?.action === 'heartbeat' || m.action === 'heartbeat'))) || [],
               status: fixedStatus,
                qualityState: v?.qualityState ?? null,
              }];
          })
        ),
      }),
    }
  )
);
