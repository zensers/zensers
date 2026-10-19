import { create } from 'zustand';
import type { LLMConfig, ThemeConfig, UploadedFile, LLMModel, LLMProviderInfo, AppSettings, LLMProfile, RoutingConfig } from '@/types/settings';
import { DEFAULT_SETTINGS, DEFAULT_LLM_PROFILE, normalizeProfileResponse, profileToLLMConfig, migrateLlmToProfile } from '@/types/settings';
import { MIMO_ENDPOINT, MIMO_MODEL, MIMO_PROVIDER } from '@/lib/mimo-config';

const STORAGE_KEY = 'Zensers-settings-v3';
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

function loadFromStorage(): Record<string, any> | null {
  if (typeof localStorage === 'undefined') return null;
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      return JSON.parse(stored);
    }
  } catch {}
  return null;
}

function saveToStorage(state: SettingsState & SettingsMethods) {
  if (typeof localStorage === 'undefined') return;
  try {
    const data = JSON.stringify({
      state: {
        profiles: state.profiles,
        activeProfileName: state.activeProfileName,
        defaultProfileName: state.defaultProfileName,
        routingConfig: state.routingConfig,
        llm: state.llm,
        savedLlm: state.savedLlm,
        theme: state.theme,
        language: state.language,
        sendOnEnter: state.sendOnEnter,
        showTokenCount: state.showTokenCount,
        autoSaveDraft: state.autoSaveDraft,
      },
      version: 1,
    });
    localStorage.setItem(STORAGE_KEY, data);
  } catch (e) {
    console.error('[persist] FAILED to save settings:', e);
  }
}

// Explicit user selection (provider/model) persisted separately so a backend
// profile re-sync (loadProfiles) cannot silently wipe a custom model name.
const LLM_SELECTION_KEY = 'zensers.llm.selection';

type LLMSelection = {
  provider?: string;
  model?: string;
  base_url?: string;
  api_key?: string;
};

function loadLLMSelection(): LLMSelection | null {
  if (typeof localStorage === 'undefined') return null;
  try {
    const raw = localStorage.getItem(LLM_SELECTION_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!data || typeof data !== 'object') return null;
    return data as LLMSelection;
  } catch {
    return null;
  }
}

function hasExplicitSelection(sel: LLMSelection | null): sel is LLMSelection {
  return !!sel && (Boolean((sel.model || '').trim()) || Boolean((sel.provider || '').trim()));
}

function applyLLMSelection(llm: LLMConfig, sel: LLMSelection): LLMConfig {
  return {
    ...llm,
    ...(sel.provider ? { provider: sel.provider } : {}),
    ...(sel.model ? { model: sel.model } : {}),
    ...(sel.base_url ? { apiEndpoint: sel.base_url } : {}),
    ...(sel.api_key ? { apiKey: sel.api_key } : {}),
  };
}

function saveLLMSelection(llm: LLMConfig) {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(LLM_SELECTION_KEY, JSON.stringify({
      provider: llm.provider,
      model: llm.model,
      base_url: llm.apiEndpoint,
      api_key: llm.apiKey,
    }));
  } catch {}
}

function clearLLMSelection() {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.removeItem(LLM_SELECTION_KEY);
  } catch {}
}

type SettingsMethods = {
  updateLLMConfig: (config: Partial<LLMConfig>) => void;
  persistLLMConfig: () => Promise<void>;
  applyBackendConfig: (config: any) => void;
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
  loadProfiles: () => Promise<void>;
  createProfile: (data: Record<string, any>) => Promise<void>;
  updateProfile: (name: string, fields: Record<string, any>) => Promise<void>;
  deleteProfile: (name: string) => Promise<void>;
  setDefaultProfile: (name: string) => Promise<void>;
  switchProfile: (name: string) => void;
  updateRouting: (config: RoutingConfig) => Promise<void>;
};

interface SettingsState {
  profiles: Record<string, LLMProfile>;
  savedProfiles: Record<string, LLMProfile>;
  activeProfileName: string;
  defaultProfileName: string;
  routingConfig: RoutingConfig;
  isLoadingProfiles: boolean;

  llm: LLMConfig;
  savedLlm: LLMConfig;
  isSaving: boolean;
  saveError: string | null;

  theme: ThemeConfig;
  language: string;
  sendOnEnter: boolean;
  showTokenCount: boolean;
  autoSaveDraft: boolean;

  uploadedFiles: UploadedFile[];
  availableModels: LLMModel[];
  availableProviders: LLMProviderInfo[];
}

const INITIAL_PROFILES: Record<string, LLMProfile> = {};
const INITIAL_ROUTING: RoutingConfig = { fixed_agent_routing: {}, action_routing: {}, fallback_chain: [] };
const INITIAL_MIMO_MODELS: LLMModel[] = [{
  id: MIMO_MODEL,
  name: MIMO_MODEL,
  provider: MIMO_PROVIDER,
  maxTokens: 128000,
}];
const INITIAL_MIMO_PROVIDERS: LLMProviderInfo[] = [{
  id: MIMO_PROVIDER,
  name: MIMO_PROVIDER,
  description: '',
  defaultEndpoint: MIMO_ENDPOINT,
}];

function getInitialState(): Omit<SettingsState, keyof SettingsMethods> {
  if (typeof window === 'undefined') {
    return {
      profiles: INITIAL_PROFILES,
      savedProfiles: INITIAL_PROFILES,
      activeProfileName: '',
      defaultProfileName: '',
      routingConfig: INITIAL_ROUTING,
      isLoadingProfiles: false,
      llm: { ...DEFAULT_SETTINGS.llm },
      savedLlm: { ...DEFAULT_SETTINGS.llm },
      isSaving: false,
      saveError: null,
      theme: { ...DEFAULT_SETTINGS.theme },
      language: DEFAULT_SETTINGS.language,
      sendOnEnter: DEFAULT_SETTINGS.sendOnEnter,
      showTokenCount: DEFAULT_SETTINGS.showTokenCount,
      autoSaveDraft: DEFAULT_SETTINGS.autoSaveDraft,
      uploadedFiles: [],
      availableModels: INITIAL_MIMO_MODELS,
      availableProviders: INITIAL_MIMO_PROVIDERS,
    };
  }

  const persisted = loadFromStorage();
  const selection = loadLLMSelection();
  if (persisted?.state) {
    const st = persisted.state;
    const baseLlm = { ...DEFAULT_SETTINGS.llm, ...(st.llm || {}) };
    return {
      profiles: INITIAL_PROFILES,
      savedProfiles: INITIAL_PROFILES,
      activeProfileName: st.activeProfileName ?? '',
      defaultProfileName: '',
      routingConfig: INITIAL_ROUTING,
      isLoadingProfiles: false,
      llm: hasExplicitSelection(selection) ? applyLLMSelection(baseLlm, selection) : baseLlm,
      savedLlm: { ...DEFAULT_SETTINGS.llm, ...(st.savedLlm || st.llm || {}) },
      isSaving: false,
      saveError: null,
      theme: { ...DEFAULT_SETTINGS.theme, ...(st.theme || {}) },
      language: st.language ?? DEFAULT_SETTINGS.language,
      sendOnEnter: st.sendOnEnter ?? DEFAULT_SETTINGS.sendOnEnter,
      showTokenCount: st.showTokenCount ?? DEFAULT_SETTINGS.showTokenCount,
      autoSaveDraft: st.autoSaveDraft ?? DEFAULT_SETTINGS.autoSaveDraft,
      uploadedFiles: [],
      availableModels: INITIAL_MIMO_MODELS,
      availableProviders: INITIAL_MIMO_PROVIDERS,
    };
  }

  const defaultLlm = hasExplicitSelection(selection)
    ? applyLLMSelection({ ...DEFAULT_SETTINGS.llm }, selection)
    : { ...DEFAULT_SETTINGS.llm };
  return {
    profiles: INITIAL_PROFILES,
    savedProfiles: INITIAL_PROFILES,
    activeProfileName: '',
    defaultProfileName: '',
    routingConfig: INITIAL_ROUTING,
    isLoadingProfiles: false,
    llm: defaultLlm,
    savedLlm: { ...DEFAULT_SETTINGS.llm },
    isSaving: false,
    saveError: null,
    theme: { ...DEFAULT_SETTINGS.theme },
    language: DEFAULT_SETTINGS.language,
    sendOnEnter: DEFAULT_SETTINGS.sendOnEnter,
    showTokenCount: DEFAULT_SETTINGS.showTokenCount,
    autoSaveDraft: DEFAULT_SETTINGS.autoSaveDraft,
    uploadedFiles: [],
    availableModels: INITIAL_MIMO_MODELS,
    availableProviders: INITIAL_MIMO_PROVIDERS,
  };
}

function _syncLLMFromProfiles(
  profiles: Record<string, LLMProfile>,
  activeName: string,
  preserveLocalSelection = false,
): LLMConfig {
  const p = profiles[activeName];
  const base = p ? profileToLLMConfig(p) : { ...DEFAULT_SETTINGS.llm };
  if (preserveLocalSelection) {
    const selection = loadLLMSelection();
    if (hasExplicitSelection(selection)) {
      return applyLLMSelection(base, selection);
    }
  }
  return base;
}

const _initial = getInitialState();

export const useSettingsStore = create<SettingsState & SettingsMethods>()((set, get) => ({
  ..._initial,

  loadProfiles: async () => {
    set({ isLoadingProfiles: true });
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000);
      const res = await fetch(`${API_BASE_URL}/api/v1/llm/profiles`, { signal: controller.signal });
      clearTimeout(timeoutId);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      const profiles: Record<string, LLMProfile> = {};
      for (const [name, raw] of Object.entries(data.profiles || {})) {
        profiles[name] = normalizeProfileResponse(raw as Record<string, any>);
      }

      const defaultProfileName = data.default_profile || '';
      const currentActive = get().activeProfileName;
      const activeProfileName = (currentActive && profiles[currentActive]) ? currentActive : defaultProfileName;
      const routingController = new AbortController();
      const routingTimeoutId = setTimeout(() => routingController.abort(), 10000);
      const routingRes = await fetch(`${API_BASE_URL}/api/v1/llm/routing`, { signal: routingController.signal });
      clearTimeout(routingTimeoutId);
      let routingData: any = {};
      if (routingRes.ok) {
        routingData = await routingRes.json();
      }

      const routingConfig: RoutingConfig = {
        fixed_agent_routing: routingData.fixed_agent_routing || {},
        action_routing: routingData.action_routing || {},
        fallback_chain: data.fallback_chain || [],
      };

      const llm = _syncLLMFromProfiles(profiles, activeProfileName, true);
      set({
        profiles,
        savedProfiles: JSON.parse(JSON.stringify(profiles)),
        defaultProfileName,
        activeProfileName,
        routingConfig,
        llm,
        savedLlm: { ...llm },
        isLoadingProfiles: false,
      });
      saveToStorage(get());
    } catch (e) {
      console.error('[loadProfiles] failed:', e);
      set({ isLoadingProfiles: false });
    }
  },

  createProfile: async (data) => {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000);
      const res = await fetch(`${API_BASE_URL}/api/v1/llm/profiles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const name = data.name;
      const profile: LLMProfile = { ...DEFAULT_LLM_PROFILE, ...data, hasApiKey: !!data.api_key };
      set((state) => {
        const profiles = { ...state.profiles, [name]: profile };
        const llm = _syncLLMFromProfiles(profiles, state.activeProfileName);
        saveLLMSelection(llm);
        return { profiles, savedProfiles: { ...state.savedProfiles, [name]: { ...profile } }, llm, savedLlm: { ...llm } };
      });
      saveToStorage(get());
      get().loadModels();
    } catch (e: any) {
      throw e;
    }
  },

  updateProfile: async (name, fields) => {
    set({ isSaving: true, saveError: null });
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000);
      const res = await fetch(`${API_BASE_URL}/api/v1/llm/profiles/${name}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(fields),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      set((state) => {
        const existing = state.profiles[name] || DEFAULT_LLM_PROFILE;
        const updated = { ...existing, ...fields };
        if (fields.api_key !== undefined && fields.api_key !== '***') {
          updated.hasApiKey = !!fields.api_key;
        }
        const profiles = { ...state.profiles, [name]: updated };
        const llm = _syncLLMFromProfiles(profiles, state.activeProfileName);
        saveLLMSelection(llm);
        return {
          profiles,
          savedProfiles: { ...state.savedProfiles, [name]: { ...updated } },
          llm,
          savedLlm: { ...llm },
          isSaving: false,
          saveError: null,
        };
      });
      saveToStorage(get());
      if (fields.provider || fields.model) get().loadModels();
    } catch (e: any) {
      const msg = e?.name === 'AbortError' ? 'Request timed out' : String(e?.message || e);
      set({ isSaving: false, saveError: msg });
      setTimeout(() => {
        if (get().saveError === msg) set({ saveError: null });
      }, 5000);
      throw e;
    }
  },

  deleteProfile: async (name) => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);
    const res = await fetch(`${API_BASE_URL}/api/v1/llm/profiles/${name}`, {
      method: 'DELETE',
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    set((state) => {
      const profiles = { ...state.profiles };
      delete profiles[name];
      const savedProfiles = { ...state.savedProfiles };
      delete savedProfiles[name];
      let activeProfileName = state.activeProfileName;
      if (activeProfileName === name) activeProfileName = state.defaultProfileName;
      const llm = _syncLLMFromProfiles(profiles, activeProfileName);
      saveLLMSelection(llm);
      return { profiles, savedProfiles, activeProfileName, llm, savedLlm: { ...llm } };
    });
    saveToStorage(get());
    get().loadModels();
  },

  setDefaultProfile: async (name) => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);
    const res = await fetch(`${API_BASE_URL}/api/v1/llm/profiles/${name}/default`, {
      method: 'POST',
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    set((state) => {
      const profiles = { ...state.profiles };
      for (const [k, p] of Object.entries(profiles)) {
        profiles[k] = { ...p, is_default: k === name };
      }
      return { defaultProfileName: name, profiles, savedProfiles: { ...profiles } };
    });
    saveToStorage(get());
  },

  switchProfile: (name) => {
    const state = get();
    const llm = _syncLLMFromProfiles(state.profiles, name);
    saveLLMSelection(llm);
    set({ activeProfileName: name, llm, savedLlm: { ...llm } });
    saveToStorage(get());
  },

  updateRouting: async (config) => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);
    const res = await fetch(`${API_BASE_URL}/api/v1/llm/routing`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    set({ routingConfig: config });
    saveToStorage(get());
  },

  // ========== Compat wrappers (keep downstream consumers working) ==========

  updateLLMConfig: (config) => {
    const current = get();
    const newLlm = { ...current.llm, ...config };
    saveLLMSelection(newLlm);
    set((state) => {
      const activeName = state.activeProfileName;
      if (activeName && state.profiles[activeName]) {
        const p = state.profiles[activeName];
        const updated: LLMProfile = {
          ...p,
          provider: newLlm.provider,
          api_key: newLlm.apiKey,
          hasApiKey: !!newLlm.apiKey,
          base_url: newLlm.apiEndpoint,
          model: newLlm.model,
          temperature: newLlm.temperature,
          max_tokens: newLlm.maxTokens,
          top_p: newLlm.topP,
          frequency_penalty: newLlm.frequencyPenalty,
          presence_penalty: newLlm.presencePenalty,
        };
        const profiles = { ...state.profiles, [activeName]: updated };
        return { llm: newLlm, profiles };
      }
      return { llm: newLlm };
    });
  },

  persistLLMConfig: async () => {
    const current = get().llm;
    const activeName = get().activeProfileName;
    if (activeName) {
      const fields: Record<string, any> = {
        provider: current.provider,
        api_key: current.apiKey,
        base_url: current.apiEndpoint,
        model: current.model,
        temperature: current.temperature,
        max_tokens: current.maxTokens,
        top_p: current.topP,
        frequency_penalty: current.frequencyPenalty,
        presence_penalty: current.presencePenalty,
      };
      try {
        await get().updateProfile(activeName, fields);
      } catch (e) {
        // updateProfile already handles error state
      }
      return;
    }
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
    const mapped: LLMConfig = {
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
    set({ llm: mapped, savedLlm: { ...mapped } });
  },

  syncConfigToBackend: async () => {
    await get().loadProfiles();
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
    clearLLMSelection();
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
        const providers: LLMProviderInfo[] = (data.providers || []).map((p: any) => ({
          id: p.id,
          name: p.name,
          description: p.description || '',
          defaultEndpoint: p.default_endpoint || '',
        }));
        const models: LLMModel[] = (data.models || []).map((m: any) => ({
          id: m.id,
          name: m.name,
          provider: m.provider,
          maxTokens: m.max_tokens ?? 128000,
          supportsVision: m.supports_vision ?? false,
          key: m.key || m.id,
        }));
        set((state) => ({
          availableModels: models,
          availableProviders: providers,
        }));
      }
    } catch {}
  },

  switchProvider: (provider) => {
    const state = get();
    const pInfo = state.availableProviders.find(p => p.id === provider);
    const defaultModel = state.availableModels.find(m => m.provider === provider)?.id || '';
    const defaults = pInfo ? {
      apiEndpoint: pInfo.defaultEndpoint,
      model: defaultModel,
      maxTokens: 4096,
    } : {};
    const newLlm = {
      ...state.llm,
      provider,
      ...defaults,
      apiKey: provider === state.llm.provider ? state.llm.apiKey : '',
    };
    saveLLMSelection(newLlm);
    set({ llm: newLlm });
  },
}));
