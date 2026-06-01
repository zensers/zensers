// store/useResearchStore.ts
// Delegation layer — state driven by useSessionStore, keeping existing interface unchanged

import { create } from 'zustand';
import type {
  Phase,
  SelectOption,
  ResearchSummary,
  ResearchStatistics,
  ParameterConfig,
  ResearchStatus,
  AgentMessageEvent,
  ResearchResult,
  ResearchFramework,
} from '@/types/api';
import type { ResearchTemplate } from '@/lib/templates';
import { useSessionStore, type SessionCache } from './useSessionStore';
import { nanoid } from 'nanoid';

export type SearchState = 'idle' | 'searching' | 'completed' | 'error';

interface ResearchState {
  taskId: string | null;
  sessionId: string | null;
  progress: number;
  phases: Phase[];
  status: ResearchStatus;
  currentStep: number | null;
  stepOptions: SelectOption[] | null;
  parameterConfig: ParameterConfig | null;
  summary: ResearchSummary | null;
  statistics: ResearchStatistics | null;
  framework: ResearchFramework | null;
  viewingResearch: boolean;
  searchState: SearchState;
  previewRefreshKey: number;  // ← 递增计数器，用于强制预览刷新
  // New fields for state persistence
  agentMessages: AgentMessageEvent[];
  previewUrl: string | null;
  downloadUrl: string | null;
  result: ResearchResult | null;
  interrupted: boolean;

  // Template customization state
  activeTemplate: ResearchTemplate | null;
  activeTemplateId: string | null;
  researchTopic: string | null;

  setActiveTemplate: (template: ResearchTemplate | null) => void;
  setResearchTopic: (topic: string | null) => void;

  setTaskId: (id: string | null) => void;
  setSessionId: (id: string | null) => void;
  setProgress: (progress: number) => void;
  setPhases: (phases: Phase[]) => void;
  updatePhase: (id: string, updates: Partial<Phase>) => void;
  setStatus: (status: ResearchStatus) => void;
  setStep: (step: number | null, options?: SelectOption[]) => void;
  setParameterConfig: (config: ParameterConfig | null) => void;
  setSummary: (summary: ResearchSummary | null) => void;
  setStatistics: (statistics: ResearchStatistics | null) => void;
  setFramework: (fw: ResearchFramework | null) => void;
  setViewingResearch: (v: boolean) => void;
  setSearchState: (state: SearchState) => void;
  triggerPreviewRefresh: () => void;  // ← 递增计数器强制预览刷新
  reset: () => void;
  clearResearch: () => void;
}

const DEFAULT_NEW_FIELDS = {
  agentMessages: [],
  previewUrl: null,
  downloadUrl: null,
  result: null,
  interrupted: false,
};

function cacheFromState(s: {
  taskId: string | null; status: ResearchStatus; currentStep: number | null;
  stepOptions: SelectOption[] | null; parameterConfig: ParameterConfig | null;
  summary: ResearchSummary | null; statistics: ResearchStatistics | null;
  framework: ResearchFramework | null;
  progress: number; phases: Phase[];
}): Partial<SessionCache> {
  return {
    taskId: s.taskId, status: s.status, currentStep: s.currentStep,
    stepOptions: s.stepOptions, parameterConfig: s.parameterConfig,
    summary: s.summary, statistics: s.statistics, framework: s.framework,
    progress: s.progress, phases: s.phases,
    ...DEFAULT_NEW_FIELDS,
  };
}

function stateFromCache(c: SessionCache | undefined): Partial<ResearchState> {
  if (!c) return {
    taskId: null, sessionId: null, progress: 0, phases: [], status: 'idle' as ResearchStatus,
    currentStep: null, stepOptions: null, parameterConfig: null, summary: null, statistics: null,
    framework: null,
    ...DEFAULT_NEW_FIELDS,
  };
  return {
    taskId: c.taskId,
    sessionId: c.id,
    progress: c.progress,
    phases: c.phases,
    status: c.status,
    currentStep: c.currentStep,
    stepOptions: c.stepOptions,
    parameterConfig: c.parameterConfig,
    summary: c.summary,
    statistics: c.statistics,
    framework: c.framework ?? null,
    agentMessages: c.agentMessages || [],
    previewUrl: c.previewUrl || null,
    downloadUrl: c.downloadUrl || null,
    result: c.result || null,
    interrupted: c.interrupted || false,
  };
}

export const useResearchStore = create<ResearchState>()(
  (set, get) => {
    // Subscribe to session store changes (auto-sync on session switch)
    useSessionStore.subscribe((state) => {
      const active = state.activeId ? state.sessions[state.activeId] : undefined;
      const current = get();
      const next = stateFromCache(active);

      // Preserve template state across session transitions
      if (current.activeTemplateId && !next.activeTemplateId) {
        next.activeTemplate = current.activeTemplate;
        next.activeTemplateId = current.activeTemplateId;
        next.researchTopic = current.researchTopic;
      }

      if (current.sessionId !== next.sessionId || current.status !== next.status) {
        set(next);
      }
    });

    return {
      taskId: null,
      sessionId: null,
      activeTemplate: null,
      activeTemplateId: null,
      researchTopic: null,
      progress: 0,
      phases: [],
      status: 'idle',
      currentStep: null,
      stepOptions: null,
      parameterConfig: null,
      summary: null,
      statistics: null,
      framework: null,
      viewingResearch: false,
      searchState: 'idle' as SearchState,
      previewRefreshKey: 0,
      ...DEFAULT_NEW_FIELDS,

      setTaskId: (id) => { set({ taskId: id }); useSessionStore.getState().syncActive({ taskId: id }); },
      setSessionId: (id) => { set({ sessionId: id }); },
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
      setProgress: (progress) => { set({ progress }); useSessionStore.getState().syncActive({ progress }); },
      setPhases: (phases) => { set({ phases }); useSessionStore.getState().syncActive({ phases }); },
      updatePhase: (id, updates) => {
        const current = get().phases;
        const existing = current.find(p => p.id === id);

        let newPhases: Phase[];
        if (existing) {
          // Update existing phase
          newPhases = current.map((p) => (p.id === id ? { ...p, ...updates } : p));
        } else {
          // Create new phase from SSE event (restored session may have partial phases)
          const newPhase: Phase = {
            id,
            name: (updates as any).name || id,
            status: (updates.status as Phase['status']) || 'running',
            progress: (updates as any).progress || 0,
            tasks: [],
            estimated_time: '',
          };
          newPhases = [...current, newPhase];
        }

        set({ phases: newPhases });
        useSessionStore.getState().syncActive({ phases: newPhases });
      },
      setStatus: (status) => { set({ status }); useSessionStore.getState().syncActive({ status }); },
      setStep: (step, options) => {
        set({ currentStep: step, stepOptions: options || null });
        useSessionStore.getState().syncActive({ currentStep: step, stepOptions: options || null });
      },
      setParameterConfig: (config) => { set({ parameterConfig: config }); useSessionStore.getState().syncActive({ parameterConfig: config } as any); },
      setSummary: (summary) => { set({ summary }); useSessionStore.getState().syncActive({ summary }); },
      setFramework: (fw) => { set({ framework: fw }); useSessionStore.getState().syncActive({ framework: fw }); },
      setStatistics: (statistics) => { set({ statistics }); useSessionStore.getState().syncActive({ statistics }); },
      setViewingResearch: (v) => set({ viewingResearch: v }),
      setSearchState: (state) => set({ searchState: state }),
      triggerPreviewRefresh: () => set((s) => ({ previewRefreshKey: s.previewRefreshKey + 1 })),
      reset: () => {
        const cleared = {
          taskId: null, sessionId: null, progress: 0, phases: [],
          status: 'idle' as ResearchStatus, currentStep: null, stepOptions: null,
          parameterConfig: null, summary: null, statistics: null, framework: null,
          viewingResearch: false, searchState: 'idle' as SearchState,
          activeTemplate: null, activeTemplateId: null, researchTopic: null,
          ...DEFAULT_NEW_FIELDS,
        };
        set(cleared);
        const newId = nanoid();
        useSessionStore.getState().createSession(newId);
      },
      clearResearch: () => {
        const cleared = {
          taskId: null, progress: 0, phases: [],
          status: 'idle' as ResearchStatus, currentStep: null, stepOptions: null,
          parameterConfig: null, summary: null, statistics: null, framework: null,
          viewingResearch: false, searchState: 'idle' as SearchState,
          activeTemplate: null, activeTemplateId: null, researchTopic: null,
          ...DEFAULT_NEW_FIELDS,
        };
        set(cleared);
        useSessionStore.getState().syncActive({ framework: null, status: 'idle' as ResearchStatus, currentStep: null, stepOptions: null });
      },
    };
  }
);
