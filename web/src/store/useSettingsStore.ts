import { create } from 'zustand';
import type { LLMConfig, ThemeConfig, UploadedFile, LLMModel, BackendLLMConfig, AppSettings } from '@/types/settings';
import { DEFAULT_SETTINGS, PROVIDER_DEFAULTS, PRESET_MODELS } from '@/types/settings';

const STORAGE_KEY = 'Zensers-settings-v2';
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

function loadFromStorage(): Partial<AppSettings> | null {
  if (typeof localStorage === 'undefined') return null;
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      return parsed.state || null;
    }
  } catch {}
  return null;
}

function saveToStorage(state: SettingsState & SettingsMethods) {
  if (typeof localStorage === 'undefined') return;
  try {
    const data = JSON.stringify({
      state: {
        llm: state.llm,
        theme: state.theme,
        language: state.language,
        sendOnEnter: state.sendOnEnter,
        showTokenCount: state.showTokenCount,
        autoSaveDraft: state.autoSaveDraft,
      },
      version: 0,
    });
    localStorage.setItem(STORAGE_KEY, data);
  } catch (e) {
    console.error('[persist] FAILED to save settings:', e);
  }
}

type SettingsMethods = {
  updateLLMConfig: (config: Partial<LLMConfig>) => void;
  persistLLMConfig: () => Promise<void>;
  applyBackendConfig: (config: BackendLLMConfig) => void;
  syncConfigToBackend: () => Promise<void>;
  updateThemeConfig: (config: Partial<ThemeConfig>) => void;
  updateSettings: (settings: Partial<AppSettings>) => void;
  resetSettings: () => void;
  loadModels: () => Promise<void>;
  addUploadedFile: (file: UploadedFile) => void;
  updateUploadedFile: (id: string, updates: Partial<UploadedFile>) => void;
  removeUploadedFile: (id: string) => void;
  clearUploadedFiles: () => void;
  switchProvider: (provider: LLMConfig['provider']) => void;
};

interface SettingsState {
  llm: LLMConfig;
  theme: ThemeConfig;
  language: string;
  sendOnEnter: boolean;
  showTokenCount: boolean;
  autoSaveDraft: boolean;

  savedLlm: LLMConfig;
  isSaving: boolean;
  saveError: string | null;

  uploadedFiles: UploadedFile[];
  availableModels: LLMModel[];
}

const INITIAL_DATA: Omit<SettingsState, keyof SettingsMethods> = {
  llm: { ...DEFAULT_SETTINGS.llm },
  theme: { ...DEFAULT_SETTINGS.theme },
  language: DEFAULT_SETTINGS.language,
  sendOnEnter: DEFAULT_SETTINGS.sendOnEnter,
  showTokenCount: DEFAULT_SETTINGS.showTokenCount,
  autoSaveDraft: DEFAULT_SETTINGS.autoSaveDraft,
  savedLlm: { ...DEFAULT_SETTINGS.llm },
  isSaving: false,
  saveError: null,
  uploadedFiles: [],
  availableModels: PRESET_MODELS,
};

function getInitialState(): Omit<SettingsState, keyof SettingsMethods> {
  if (typeof window === 'undefined') return { ...INITIAL_DATA };

  const persisted = loadFromStorage();
  if (!persisted || typeof persisted.llm !== 'object') {
    if (persisted) try { localStorage.removeItem(STORAGE_KEY); } catch {}
    return { ...INITIAL_DATA };
  }

  const mergedLlm = { ...DEFAULT_SETTINGS.llm, ...persisted.llm };
  return {
    ...INITIAL_DATA,
    llm: mergedLlm,
    savedLlm: mergedLlm,
    theme: { ...DEFAULT_SETTINGS.theme, ...(persisted.theme || {}) },
    language: persisted.language ?? DEFAULT_SETTINGS.language,
    sendOnEnter: persisted.sendOnEnter ?? DEFAULT_SETTINGS.sendOnEnter,
    showTokenCount: persisted.showTokenCount ?? DEFAULT_SETTINGS.showTokenCount,
    autoSaveDraft: persisted.autoSaveDraft ?? DEFAULT_SETTINGS.autoSaveDraft,
  };
}

function mapBackendToLLM(config: BackendLLMConfig): LLMConfig {
  return {
    provider: config.provider as LLMConfig['provider'],
    model: config.model,
    apiKey: config.apiKey,
    apiEndpoint: config.apiEndpoint,
    temperature: config.temperature,
    maxTokens: config.maxTokens,
    topP: config.topP,
    frequencyPenalty: config.frequencyPenalty,
    presencePenalty: config.presencePenalty,
  };
}

const _initial = getInitialState();

export const useSettingsStore = create<SettingsState & SettingsMethods>()((set, get) => ({
  ..._initial,

  updateLLMConfig: (config) => {
    set((state) => ({ llm: { ...state.llm, ...config } }));
  },

  persistLLMConfig: async () => {
    const current = get().llm;
    set({ isSaving: true, saveError: null });

    saveToStorage(get());

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000);

      const res = await fetch(`${API_BASE_URL}/api/v1/llm/config`, {
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
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      set({ savedLlm: { ...current }, isSaving: false, saveError: null });
    } catch (e: any) {
      const msg = e?.name === 'AbortError' ? 'Request timed out' : String(e);
      set({ isSaving: false, saveError: msg });
      setTimeout(() => {
        if (get().saveError === msg) set({ saveError: null });
      }, 5000);
    }
  },

  applyBackendConfig: (config) => {
    const mapped = mapBackendToLLM(config);
    set({ llm: mapped, savedLlm: { ...mapped } });
  },

  syncConfigToBackend: async () => {
    const current = get().llm;
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 8000);
      await fetch(`${API_BASE_URL}/api/v1/llm/config`, {
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
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
    } catch {}
  },

  updateThemeConfig: (config) => {
    set((state) => ({ theme: { ...state.theme, ...config } }));
    saveToStorage(get());
  },

  updateSettings: (settings) => {
    set(settings);
    saveToStorage(get());
  },

  resetSettings: () => {
    const newLlm = { ...DEFAULT_SETTINGS.llm };
    set({
      llm: newLlm,
      savedLlm: { ...newLlm },
      theme: { ...DEFAULT_SETTINGS.theme },
      language: DEFAULT_SETTINGS.language,
      sendOnEnter: DEFAULT_SETTINGS.sendOnEnter,
      showTokenCount: DEFAULT_SETTINGS.showTokenCount,
      autoSaveDraft: DEFAULT_SETTINGS.autoSaveDraft,
      uploadedFiles: [],
    });
    saveToStorage(get());
  },

  addUploadedFile: (file) =>
    set((state) => ({
      uploadedFiles: [...state.uploadedFiles, file],
    })),

  updateUploadedFile: (id, updates) =>
    set((state) => ({
      uploadedFiles: state.uploadedFiles.map((f) =>
        f.id === id ? { ...f, ...updates } : f
      ),
    })),

  removeUploadedFile: (id) =>
    set((state) => ({
      uploadedFiles: state.uploadedFiles.filter((f) => f.id !== id),
    })),

  clearUploadedFiles: () =>
    set({ uploadedFiles: [] }),

  loadModels: async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/llm/models`);
      if (res.ok) {
        const data = await res.json();
        if (data.models?.length) {
          const mapped: LLMModel[] = data.models.map((m: any) => ({
            id: m.id,
            name: m.name,
            provider: m.provider,
            maxTokens: m.max_tokens ?? 128000,
          }));
          set({ availableModels: mapped });
        }
      }
    } catch {}
  },

  switchProvider: (provider) => {
    const defaults = PROVIDER_DEFAULTS[provider];
    set((state) => ({
      llm: {
        ...state.llm,
        provider,
        ...defaults,
        apiKey: provider === state.llm.provider ? state.llm.apiKey : '',
      },
    }));
  },
}));