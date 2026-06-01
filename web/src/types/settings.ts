// types/settings.ts

/**
 * LLM Provider
 */
export type LLMProvider = 'openai' | 'anthropic' | 'deepseek' | 'azure' | 'local' | 'custom';

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
 * Preset model list - mainstream OpenAI compatible APIs
 */
export const PRESET_MODELS: LLMModel[] = [
  // OpenAI
  { id: 'gpt-4o', name: 'GPT-4o', provider: 'openai', maxTokens: 128000, supportsVision: true },
  { id: 'gpt-4o-mini', name: 'GPT-4o Mini', provider: 'openai', maxTokens: 128000, supportsVision: true },
  { id: 'gpt-4-turbo', name: 'GPT-4 Turbo', provider: 'openai', maxTokens: 128000, supportsVision: true },
  { id: 'gpt-4', name: 'GPT-4', provider: 'openai', maxTokens: 8192 },
  { id: 'gpt-3.5-turbo', name: 'GPT-3.5 Turbo', provider: 'openai', maxTokens: 16385 },
  { id: 'o1-preview', name: 'O1 Preview', provider: 'openai', maxTokens: 128000 },
  { id: 'o1-mini', name: 'O1 Mini', provider: 'openai', maxTokens: 128000 },
  
  // Anthropic
  { id: 'claude-3-5-sonnet-20241022', name: 'Claude 3.5 Sonnet', provider: 'anthropic', maxTokens: 200000, supportsVision: true },
  { id: 'claude-3-opus-20240229', name: 'Claude 3 Opus', provider: 'anthropic', maxTokens: 200000, supportsVision: true },
  { id: 'claude-3-sonnet-20240229', name: 'Claude 3 Sonnet', provider: 'anthropic', maxTokens: 200000, supportsVision: true },
  { id: 'claude-3-haiku-20240307', name: 'Claude 3 Haiku', provider: 'anthropic', maxTokens: 200000, supportsVision: true },
  
  // DeepSeek
  { id: 'deepseek-v4-pro', name: 'DeepSeek V4 Pro', provider: 'deepseek', maxTokens: 128000 },
  { id: 'deepseek-v4-flash', name: 'DeepSeek V4 Flash', provider: 'deepseek', maxTokens: 128000 },
  
  // Azure OpenAI
  { id: 'azure-gpt-4o', name: 'Azure GPT-4o', provider: 'azure', maxTokens: 128000 },
  { id: 'azure-gpt-4', name: 'Azure GPT-4', provider: 'azure', maxTokens: 8192 },
  
  // Local models (Ollama)
  { id: 'llama3.1', name: 'LLaMA 3.1', provider: 'local', maxTokens: 128000 },
  { id: 'llama3.2', name: 'LLaMA 3.2', provider: 'local', maxTokens: 128000 },
  { id: 'mistral', name: 'Mistral', provider: 'local', maxTokens: 32000 },
  { id: 'codellama', name: 'CodeLLaMA', provider: 'local', maxTokens: 16000 },
  { id: 'qwen2.5', name: 'Qwen 2.5', provider: 'local', maxTokens: 32000 },
];

/**
 * Provider default configs
 */
export const PROVIDER_DEFAULTS: Record<LLMProvider, Partial<LLMConfig>> = {
  openai: {
    apiEndpoint: 'https://api.openai.com/v1',
    model: 'gpt-4o',
    maxTokens: 4096,
  },
  anthropic: {
    apiEndpoint: 'https://api.anthropic.com/v1',
    model: 'claude-3-5-sonnet-20241022',
    maxTokens: 4096,
  },
  deepseek: {
    apiEndpoint: 'https://api.deepseek.com/v1',
    model: 'deepseek-v4-pro',
    maxTokens: 4096,
  },
  azure: {
    apiEndpoint: '',
    model: 'gpt-4o',
    maxTokens: 4096,
  },
  local: {
    apiEndpoint: 'http://localhost:11434/v1',
    model: 'llama3.1',
    maxTokens: 4096,
  },
  custom: {
    apiEndpoint: '',
    model: '',
    maxTokens: 4096,
  },
};

/**
 * Provider info
 */
export const PROVIDER_INFO: Record<LLMProvider, { name: string; description: string; defaultEndpoint: string }> = {
  openai: {
    name: 'OpenAI',
    description: 'GPT-4o, GPT-4, GPT-3.5 and other models',
    defaultEndpoint: 'https://api.openai.com/v1',
  },
  anthropic: {
    name: 'Anthropic',
    description: 'Claude 3.5 Sonnet, Claude 3 Opus and other models',
    defaultEndpoint: 'https://api.anthropic.com/v1',
  },
  deepseek: {
    name: 'DeepSeek',
    description: 'DeepSeek V4 Pro, V4 Flash',
    defaultEndpoint: 'https://api.deepseek.com/v1',
  },
  azure: {
    name: 'Azure OpenAI',
    description: 'Azure deployed OpenAI models',
    defaultEndpoint: '',
  },
  local: {
    name: 'Local Model',
    description: 'Ollama, LocalAI and other local deployments',
    defaultEndpoint: 'http://localhost:11434/v1',
  },
  custom: {
    name: 'Custom',
    description: 'Any OpenAI compatible API',
    defaultEndpoint: '',
  },
};

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
    provider: 'openai',
    apiKey: '',
    apiEndpoint: 'https://api.openai.com/v1',
    model: 'gpt-4o',
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

/**
 * Backend LLM config response format
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
