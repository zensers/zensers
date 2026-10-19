// types/settings.ts

/**
 * LLM Provider
 */
export type LLMProvider = string;

/**
 * LLM Model config
 */
export interface LLMModel {
  id: string;
  name: string;
  provider: LLMProvider;
  maxTokens: number;
  supportsVision?: boolean;
  supportsFunctionCalling?: boolean;
  /** Provider-scoped unique key ("provider:model"); falls back to id */
  key?: string;
}

export interface LLMProviderInfo {
  id: string;
  name: string;
  description: string;
  defaultEndpoint: string;
}

/**
 * LLM Config
 */
export interface LLMConfig {
  // Provider
  provider: LLMProvider;
  
  // API config
  apiKey: string;
  apiEndpoint: string;
  
  // Model selection
  model: string;
  
  // Parameters
  temperature: number;
  maxTokens: number;
  topP: number;
  frequencyPenalty: number;
  presencePenalty: number;
  
  // Advanced options
  customHeaders?: Record<string, string>;
  timeout?: number;
}

/**
 * Theme config
 */
export interface ThemeConfig {
  mode: 'light' | 'dark' | 'system';
  primaryColor: string;
  fontSize: 'small' | 'medium' | 'large';
  fontFamily: string;
}

/**
 * App settings
 */
export interface AppSettings {
  // LLM config
  llm: LLMConfig;
  
  // Theme config
  theme: ThemeConfig;
  
  // General settings
  language: string;
  sendOnEnter: boolean;
  showTokenCount: boolean;
  autoSaveDraft: boolean;
}

/**
 * Default settings
 */
export const DEFAULT_SETTINGS: AppSettings = {
  llm: {
    provider: 'mimo',
    apiKey: '',
    apiEndpoint: 'https://token-plan-cn.xiaomimimo.com/v1',
    model: 'mimo-v2.5',
    temperature: 0.7,
    maxTokens: 4096,
    topP: 1,
    frequencyPenalty: 0,
    presencePenalty: 0,
  },
  theme: {
    mode: 'system',
    primaryColor: '#3b82f6',
    fontSize: 'medium',
    fontFamily: 'Inter',
  },
  language: 'zh-CN',
  sendOnEnter: true,
  showTokenCount: true,
  autoSaveDraft: true,
};

export function normalizeProfileResponse(raw: Record<string, any>): LLMProfile {
  const { apiKey, hasApiKey, ...rest } = raw;
  return {
    ...rest,
    api_key: apiKey && apiKey !== '***' ? apiKey : '',
    hasApiKey: hasApiKey ?? false,
  } as LLMProfile;
}

export function profileToLLMConfig(p: LLMProfile): LLMConfig {
  return {
    provider: p.provider as LLMProvider,
    apiKey: p.api_key && p.api_key !== '***' ? p.api_key : '',
    apiEndpoint: p.base_url,
    model: p.model,
    temperature: p.temperature,
    maxTokens: p.max_tokens,
    topP: p.top_p,
    frequencyPenalty: p.frequency_penalty,
    presencePenalty: p.presence_penalty,
  };
}

export function migrateLlmToProfile(llm: LLMConfig): LLMProfile {
  return {
    name: 'migrated',
    display_name: '迁移配置',
    provider: llm.provider,
    api_key: llm.apiKey,
    hasApiKey: !!llm.apiKey,
    base_url: llm.apiEndpoint,
    model: llm.model,
    fallback_model: '',
    temperature: llm.temperature,
    max_tokens: llm.maxTokens,
    top_p: llm.topP,
    frequency_penalty: llm.frequencyPenalty,
    presence_penalty: llm.presencePenalty,
    max_context_tokens: 128000,
    cost_limit_per_call: 0.0,
    is_default: true,
    enabled: true,
    created_at: '',
    updated_at: '',
  };
}

/**
 * Backend LLM config response format (DEPRECATED — kept for compat)
 */
export interface BackendLLMConfig {
  provider: string;
  model: string;
  apiKey: string;
  apiEndpoint: string;
  temperature: number;
  maxTokens: number;
  topP: number;
  frequencyPenalty: number;
  presencePenalty: number;
  hasApiKey: boolean;
}

export interface LLMProfile {
  name: string;
  display_name: string;
  provider: string;
  api_key: string;
  hasApiKey: boolean;
  base_url: string;
  model: string;
  fallback_model: string;
  temperature: number;
  max_tokens: number;
  top_p: number;
  frequency_penalty: number;
  presence_penalty: number;
  max_context_tokens: number;
  cost_limit_per_call: number;
  is_default: boolean;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface RoutingConfig {
  fixed_agent_routing: Record<string, string>;
  action_routing: Record<string, string>;
  fallback_chain: string[];
}

export const DEFAULT_LLM_PROFILE: LLMProfile = {
  name: '',
  display_name: '',
  provider: 'openai',
  api_key: '',
  hasApiKey: false,
  base_url: 'https://api.openai.com/v1',
  model: 'gpt-4o',
  fallback_model: '',
  temperature: 0.7,
  max_tokens: 4096,
  top_p: 1.0,
  frequency_penalty: 0.0,
  presence_penalty: 0.0,
  max_context_tokens: 128000,
  cost_limit_per_call: 0.0,
  is_default: false,
  enabled: true,
  created_at: '',
  updated_at: '',
};

/**
 * Uploaded file type
 */
export interface UploadedFile {
  id: string;
  name: string;
  size: number;
  type: string;
  url?: string;
  status: 'uploading' | 'ready' | 'error';
  error?: string;
}
