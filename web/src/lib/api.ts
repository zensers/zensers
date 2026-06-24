// lib/api.ts

import axios, { AxiosInstance, AxiosError } from 'axios';
import type {
  StartResearchResponse,
  InteractRequest,
  InteractResponse,
  PreviewResponse,
  ResearchResultMeta,
  Phase,
  AgentMessageEvent,
  ResearchResult,
} from '@/types/api';
import type { VersionInfo } from '@/types/version';
import type {
  MCPServerListResponse,
  MCPServerActionResponse,
} from '@/types/mcp';
import type {
  SurveySummary,
  CreateSurveyRequest,
  CreateSurveyResponse,
  SurveyDetail,
  SimulateRequest,
  SimulateResponse,
  SurveyStatusResponse,
  AnalysisReport,
  TemplatesResponse,
  RegionsResponse,
} from '@/types/survey';

/**
 * Get API Base URL
 */
const getApiBaseUrl = () => {
  const configuredUrl = process.env.NEXT_PUBLIC_API_URL;
  if (configuredUrl) {
    return configuredUrl;
  }
  // Default backend address
  return 'http://localhost:8000';
};

const API_BASE_URL = getApiBaseUrl();

/**
 * 构建后端下载请求的完整 URL
 * - 如果已经是完整 URL（以 http 开头），直接使用
 * - 否则用 API_BASE_URL 拼接（API_BASE_URL 为空则使用相对路径，走 next rewrites）
 */
export function buildDownloadUrl(path: string): string {
  if (path.startsWith('http')) return path;
  return API_BASE_URL ? `${API_BASE_URL}${path}` : path;
}

/**
 * Custom API Error class
 */
export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status?: number,
    public details?: any
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Section info type
 */
export interface SectionInfo {
  id: string;
  title: string;
  word_count: number;
  level: number;
  parent?: string;
  children?: SectionInfo[];
}

/**
 * Revision result type
 */
export interface RevisionResult {
  task_id: string;
  status: string;
  message: string;
  output_path?: string;
  revised_aspects: string[];
  adjustment?: string;
}

/** Export response from /api/v1/documents/export */
interface ExportResponse {
  status: 'success' | 'failed';
  download_url?: string;
  file_name?: string;
  file_size?: number;
  error?: string;
}

/**
 * API Client class
 */
class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 60000,  // P0 fix: increased from 30s to 60s for long LLM requests
      headers: { 'Content-Type': 'application/json' },
    });
    this.setupInterceptors();
  }

  private setupInterceptors() {
    this.client.interceptors.request.use(
      (config) => {
        const token = localStorage.getItem('auth_token');
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        const { response, config } = error;

        if (response?.status === 401) {
          localStorage.removeItem('auth_token');
          throw new ApiError('UNAUTHORIZED', 'Please log in again', 401);
        }

        if (response?.status === 429) {
          const retryCount = (config as any)._retryCount || 0;
          if (retryCount < 3) {
            const delay = Math.pow(2, retryCount) * 1000;
            await new Promise((r) => setTimeout(r, delay));
            (config as any)._retryCount = retryCount + 1;
            return this.client.request(config!);
          }
          throw new ApiError('RATE_LIMITED', 'Too many requests, please try again later', 429);
        }

        if (response?.status && response.status >= 500) {
          const retryCount = (config as any)._retryCount || 0;
          if (retryCount < 1) {
            (config as any)._retryCount = retryCount + 1;
            await new Promise((r) => setTimeout(r, 1000));
            return this.client.request(config!);
          }
          throw new ApiError('SERVER_ERROR', 'Server error, please try again later', response.status);
        }

        if (!response) {
          // P0 fix: Network error - retry before giving up
          const config = error.config as any;
          const retryCount = config?._retryCount || 0;
          
          if (retryCount < 3) {
            config._retryCount = retryCount + 1;
            const delay = Math.pow(2, retryCount) * 1000;  // 1s, 2s, 4s
            await new Promise((r) => setTimeout(r, delay));
            return this.client.request(config);
          }
          
          throw new ApiError('NETWORK_ERROR', 'Network connection failed after retries, please check your network');
        }

        const data = response.data as any;
        throw new ApiError(
          data?.error_code || 'UNKNOWN_ERROR',
          data?.error || data?.message || 'Request failed',
          response.status,
          data?.details
        );
      }
    );
  }

  // ============ Research API ============

  async startResearch(
    input: string,
    userId?: string,
    llmConfig?: {
      provider?: string;
      model?: string;
      apiKey?: string;
      apiEndpoint?: string;
      temperature?: number;
      maxTokens?: number;
      topP?: number;
      frequencyPenalty?: number;
      presencePenalty?: number;
    },
    fileIds?: string[]
  ): Promise<StartResearchResponse> {
    const formData = new FormData();
    formData.append('user_input', input);
    if (userId) formData.append('user_id', userId);
    if (llmConfig?.provider) formData.append('llm_provider', llmConfig.provider);
    if (llmConfig?.model) formData.append('llm_model', llmConfig.model);
    if (llmConfig?.apiKey) formData.append('llm_api_key', llmConfig.apiKey);
    if (llmConfig?.apiEndpoint) formData.append('llm_api_endpoint', llmConfig.apiEndpoint);
    if (llmConfig?.temperature !== undefined) formData.append('llm_temperature', String(llmConfig.temperature));
    if (llmConfig?.maxTokens !== undefined) formData.append('llm_max_tokens', String(llmConfig.maxTokens));
    if (llmConfig?.topP !== undefined) formData.append('llm_top_p', String(llmConfig.topP));
    if (llmConfig?.frequencyPenalty !== undefined) formData.append('llm_frequency_penalty', String(llmConfig.frequencyPenalty));
    if (llmConfig?.presencePenalty !== undefined) formData.append('llm_presence_penalty', String(llmConfig.presencePenalty));
    if (fileIds && fileIds.length > 0) formData.append('file_ids', JSON.stringify(fileIds));

    const { data } = await this.client.post('/api/v1/research/start', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  }

  async interact(request: InteractRequest): Promise<InteractResponse> {
    // Backend expects FormData format
    const formData = new FormData();
    formData.append('session_id', request.session_id);
    formData.append('step', String(request.step));
    formData.append('response', JSON.stringify(request.response));
    
    const { data } = await this.client.post('/api/v1/research/interact', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  }

  async selectOutputType(sessionId: string, outputType: string): Promise<InteractResponse> {
    return this.interact({ session_id: sessionId, step: 1, response: { output_type: outputType } });
  }

  async selectTemplate(sessionId: string, templateId: string): Promise<InteractResponse> {
    return this.interact({ session_id: sessionId, step: 2, response: { template_id: templateId } });
  }

  async selectSections(sessionId: string, sectionIds: string[]): Promise<InteractResponse> {
    return this.interact({ session_id: sessionId, step: 3, response: { selected_sections: sectionIds } });
  }

  async setParameters(
    sessionId: string,
    params: Record<string, any>  // ← No longer fixed 3 fields
  ): Promise<InteractResponse> {
    return this.interact({ session_id: sessionId, step: 4, response: params });
  }

  async confirmResearch(sessionId: string, confirmed: boolean): Promise<InteractResponse> {
    return this.interact({ session_id: sessionId, step: 5, response: { confirmed } });
  }

  /**
   * Send chat message (chat mode step=0)
   */
  async sendChatMessage(sessionId: string, text: string): Promise<InteractResponse> {
    return this.interact({ session_id: sessionId, step: 0, response: { text } });
  }

  /**
   * Click suggestion option (chat mode)
   * Sends both the suggestion_id and the example text (in user's language) so the backend
   * can use the natural-language example as the user message instead of an English fallback.
   */
  async clickSuggestion(sessionId: string, suggestionId: string, exampleText?: string): Promise<InteractResponse> {
    const payload: Record<string, any> = { suggestion_id: suggestionId };
    if (exampleText) {
      payload.text = exampleText;  // Natural-language query in user's language
    }
    return this.interact({ session_id: sessionId, step: 0, response: payload });
  }

  /**
   * Quick start research (use preset template, skip interaction flow)
   */
  async quickStart(
    input: string,
    templateId: string,
    options?: {
      userId?: string;
      llmConfig?: {
        provider?: string;
        model?: string;
        apiKey?: string;
        apiEndpoint?: string;
        temperature?: number;
        maxTokens?: number;
        topP?: number;
        frequencyPenalty?: number;
        presencePenalty?: number;
      };
      parameters?: Record<string, any>;
      autoConfirm?: boolean;
    }
  ): Promise<{
    session_id: string;
    task_id: string;
    step: number;
    status: string;
    message: string;
    template: string;
    plan: {
      topic: string;
      aspects: string[];
      region: string;
      time_range: string;
    };
    final_plan: any;
    next_step: string;
    parameters?: any;
  }> {
    const formData = new FormData();
    formData.append('user_input', input);
    formData.append('template_id', templateId);
    if (options?.userId) formData.append('user_id', options.userId);
    if (options?.llmConfig?.provider) formData.append('llm_provider', options.llmConfig.provider);
    if (options?.llmConfig?.model) formData.append('llm_model', options.llmConfig.model);
    if (options?.llmConfig?.apiKey) formData.append('llm_api_key', options.llmConfig.apiKey);
    if (options?.llmConfig?.apiEndpoint) formData.append('llm_api_endpoint', options.llmConfig.apiEndpoint);
    if (options?.llmConfig?.temperature !== undefined) formData.append('llm_temperature', String(options.llmConfig.temperature));
    if (options?.llmConfig?.maxTokens !== undefined) formData.append('llm_max_tokens', String(options.llmConfig.maxTokens));
    if (options?.llmConfig?.topP !== undefined) formData.append('llm_top_p', String(options.llmConfig.topP));
    if (options?.llmConfig?.frequencyPenalty !== undefined) formData.append('llm_frequency_penalty', String(options.llmConfig.frequencyPenalty));
    if (options?.llmConfig?.presencePenalty !== undefined) formData.append('llm_presence_penalty', String(options.llmConfig.presencePenalty));
    if (options?.autoConfirm) formData.append('auto_confirm', 'true');
    const { templateContext: _ctx, ...restParams } = options?.parameters || {};
    if (_ctx) formData.append('template_context', String(_ctx));
    if (restParams) {
      for (const [key, value] of Object.entries(restParams)) {
        if (value !== undefined && value !== null && value !== '') {
          formData.append(key, String(value));
        }
      }
    }

    const { data } = await this.client.post('/api/v1/research/quick-start', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });

    // I3: detect backend errors returned as HTTP 200 with error field
    if (data.error) {
      throw new ApiError(data.error_code || 'QUICK_START_ERROR', data.error);
    }

    return data;
  }

  // ============ Preview API ============

  async getResearchPreview(taskId: string, format: 'html' | 'pdf' | 'png' = 'html'): Promise<PreviewResponse> {
    const { data } = await this.client.get(`/api/v1/research/preview/${taskId}`, { params: { format } });
    return data;
  }

  // ============ Export ============

  async exportDocument(taskId: string, versionId: string, format: string): Promise<ExportResponse> {
    const { data } = await this.client.post('/api/v1/documents/export', { task_id: taskId, version_id: versionId, format });
    return data;
  }

  // ============ History ============

  async listCompletedResearch(limit = 50): Promise<ResearchResultMeta[]> {
    const { data } = await this.client.get('/api/v1/research/completed', { params: { limit } });
    return data;
  }

  async listAllSessions(limit = 20, offset = 0): Promise<{
    sessions: ResearchResultMeta[];
    total: number;
    has_more: boolean;
  }> {
    const { data } = await this.client.get('/api/v1/research/sessions', { params: { limit, offset } });
    return data;
  }

  async getResearchStatus(taskId: string): Promise<{
    task_id: string;
    status: string;
    progress: number;
    current_phase?: string;
    error?: string;
    phases?: Array<{ id: string; name: string; status: string; progress: number }>;
    // Extended fields for state persistence
    interrupted?: boolean;
    agent_messages?: AgentMessageEvent[];
  }> {
    const { data } = await this.client.get(`/api/v1/research/${taskId}/status`);
    return data;
  }

  async getResearchDetail(taskId: string): Promise<ResearchResultMeta & {
    messages?: Array<{ id: string; role: string; content: string; timestamp: string }>;
    config?: Record<string, any>;
    // Extended fields for state persistence
    phases?: Phase[];
    progress?: number;
    agent_messages?: AgentMessageEvent[];
    result?: ResearchResult;
    preview_url?: string;
    download_url?: string;
    interrupted?: boolean;
    mode?: string;
    current_step?: number;
    language?: string;
  }> {
    const { data } = await this.client.get(`/api/v1/research/${taskId}`);
    return data;
  }

  async getMessages(
    sessionId: string,
    offset: number = 0,
    limit: number = 50,
  ): Promise<{
    messages: Array<{ id: string; role: string; content: string; timestamp: string }>;
    total: number;
    offset: number;
    limit: number;
    has_more: boolean;
  }> {
    const { data } = await this.client.get(
      `/api/v1/research/${sessionId}/messages`,
      { params: { offset, limit } },
    );
    return data;
  }

  // ============ File Upload ============

  async uploadFiles(files: File[], sessionId?: string): Promise<{
    session_id?: string;
    files: Array<{ id: string; filename: string; size: number; type: string }>;
    count: number;
  }> {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));
    if (sessionId) formData.append('session_id', sessionId);
    const { data } = await this.client.post('/api/v1/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  }

  async deleteFile(fileId: string): Promise<void> {
    await this.client.delete(`/api/v1/upload/${fileId}`);
  }

  // ============ LLM Models ============

  async getLLMModels(): Promise<{
    providers: Array<{ id: string; name: string; default_endpoint: string }>;
    models: Array<{ id: string; name: string; provider: string; max_tokens: number }>;
  }> {
    const { data } = await this.client.get('/api/v1/llm/models');
    return data;
  }

  // ============ Cancel API ============

  async cancelResearch(taskId: string): Promise<{ status: string; message: string }> {
    const { data } = await this.client.post(`/api/v1/research/${taskId}/cancel`);
    return data;
  }

  async pauseResearch(taskId: string): Promise<{ status: string; message: string }> {
    const { data } = await this.client.post(`/api/v1/research/${taskId}/pause`);
    return data;
  }

  async resumeResearch(taskId: string): Promise<{ status: string; message: string }> {
    const { data } = await this.client.post(`/api/v1/research/${taskId}/resume`);
    return data;
  }

  // ============ Revision API ============

  /**
   * Get report section list
   */
  async getSections(taskId: string): Promise<{
    task_id: string;
    sections: SectionInfo[];
    total_sections: number;
    total_words: number;
  }> {
    const { data } = await this.client.get(`/api/v1/research/sections/${taskId}`);
    return data;
  }

  /**
   * Execute report revision
   */
  async reviseSections(
    taskId: string,
    aspects: string[],
    adjustment?: string
  ): Promise<RevisionResult> {
    const formData = new FormData();
    formData.append('task_id', taskId);
    formData.append('aspects', JSON.stringify(aspects));
    if (adjustment) formData.append('adjustment', adjustment);

    const { data } = await this.client.post('/api/v1/research/revise', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  }

  // ============ MCP API ============

  /**
   * Get MCP server list
   */
  async getMCPServers(): Promise<MCPServerListResponse> {
    const { data } = await this.client.get('/api/v1/mcp/servers');
    return data;
  }

  /**
   * Start MCP server
   */
  async startMCPServer(serverName: string): Promise<MCPServerActionResponse> {
    const { data } = await this.client.post(`/api/v1/mcp/servers/${serverName}/start`);
    return data;
  }

  /**
   * Stop MCP server
   */
  async stopMCPServer(serverName: string): Promise<MCPServerActionResponse> {
    const { data } = await this.client.post(`/api/v1/mcp/servers/${serverName}/stop`);
    return data;
  }

  /**
   * Get single MCP server status
   */
  async getMCPServerStatus(serverName: string): Promise<MCPServerListResponse['servers'][0]> {
    const { data } = await this.client.get(`/api/v1/mcp/servers/${serverName}/status`);
    return data;
  }

  /**
   * Get MCP health status
   */
  async getMCPHealth(): Promise<{
    summary: {
      total_servers: number;
      healthy: number;
      unhealthy: number;
      healthy_ratio: number;
      last_check: string;
    };
    details: Record<string, unknown>;
  }> {
    const { data } = await this.client.get('/api/v1/mcp/health');
    return data;
  }

  /**
   * Reload MCP config
   */
  async reloadMCPConfig(): Promise<{ success: boolean; message: string; servers_count: number }> {
    const { data } = await this.client.post('/api/v1/mcp/reload');
    return data;
  }

  // ================================================================ //
  // Survey API
  // ================================================================ //

  async listSurveys(): Promise<SurveySummary[]> {
    const { data } = await this.client.get('/api/v1/surveys');
    return data;
  }

  async createSurvey(req: CreateSurveyRequest): Promise<CreateSurveyResponse> {
    const { data } = await this.client.post('/api/v1/surveys', req);
    return data;
  }

  async getSurvey(surveyId: string): Promise<SurveyDetail> {
    const { data } = await this.client.get(`/api/v1/surveys/${surveyId}`);
    return data;
  }

  async simulateSurvey(surveyId: string, req: SimulateRequest): Promise<SimulateResponse> {
    const { data } = await this.client.post(`/api/v1/surveys/${surveyId}/simulate`, req);
    return data;
  }

  async getSurveyStatus(surveyId: string): Promise<SurveyStatusResponse> {
    const { data } = await this.client.get(`/api/v1/surveys/${surveyId}/status`);
    return data;
  }

  async getSurveyResults(surveyId: string, limit?: number): Promise<any> {
    const { data } = await this.client.get(`/api/v1/surveys/${surveyId}/results`, { params: { limit } });
    return data;
  }

  async getSurveyAnalysis(surveyId: string): Promise<AnalysisReport> {
    const { data } = await this.client.get(`/api/v1/surveys/${surveyId}/analysis`);
    return data;
  }

  async listSurveyTemplates(): Promise<TemplatesResponse> {
    const { data } = await this.client.get('/api/v1/surveys/templates');
    return data;
  }

  async listSurveyRegions(): Promise<RegionsResponse> {
    const { data } = await this.client.get('/api/v1/surveys/regions');
    return data;
  }

  async getVersion(): Promise<VersionInfo> {
    const { data } = await this.client.get('/api/v1/version');
    return data;
  }

  async qualityAction(sessionId: string, action: string, params?: Record<string, any>): Promise<any> {
    const { data } = await this.client.post('/api/v1/research/quality/action', {
      session_id: sessionId,
      action,
      ...params,
    });
    return data;
  }

  async getQualityState(sessionId: string): Promise<any> {
    const { data } = await this.client.get(`/api/v1/research/quality/${sessionId}`);
    return data;
  }
}

export const api = new ApiClient();
export default api;
