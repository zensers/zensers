// types/api.ts
// Zensers API TypeScript Types

// ============ Shared State Types ============

/** 统一的研究状态类型 — 所有 store 和组件共用 */
export type ResearchStatus = 'idle' | 'running' | 'completed' | 'error' | 'paused';

export interface AgentMessageEvent {
  event: string;
  data: AgentMessageData;
  created_at: string;
}

export interface ResearchResult {
  sections: any[];
  sources: any[];
  key_findings: any[];
  data_points: any[];
  completed_agents: string[];
}

// ============ Preview Format ============

export type ResearchPreviewFormat = 'html' | 'pdf' | 'png';
export type DocumentPreviewFormat = 'png' | 'jpg' | 'pdf';

export interface PreviewResponse {
  task_id: string;
  preview_url: string;
  preview_path: string;
  preview_format: ResearchPreviewFormat | DocumentPreviewFormat;
  format?: ResearchPreviewFormat | DocumentPreviewFormat; // Alias
  cached: boolean;
  file_size: number;
  title?: string;
  html_content?: string;
  download_url?: string;
}

// ============ API Request/Response Types ============

export interface FrameworkSubSection {
  name: string;
  points?: string[];
}

export interface FrameworkSection {
  name: string;
  sub_sections?: FrameworkSubSection[];
}

export interface ResearchFramework {
  topic: string;
  sections: string[];
  output_type: string;
  depth: string;
  region: string;
  time_range: string;
  sections_tree?: FrameworkSection[];
}

/** POST /api/v1/research/start response */
export interface StartResearchResponse {
  session_id: string;
  step: number;
  mode?: 'chat' | 'framework' | 'research';
  message: string;
  instruction: string;
  options?: SelectOption[];
  suggestions?: Suggestion[];
  clarification_questions?: string[];
  framework?: ResearchFramework;
  next_step: string;
}

/** POST /api/v1/research/interact response */
export interface InteractResponse {
  session_id: string;
  step: number;
  mode?: 'chat' | 'framework' | 'research';
  message: string;
  instruction: string;
  next_step: string;
  options?: SelectOption[];
  suggestions?: Suggestion[];
  clarification_questions?: string[];
  templates?: Template[];
  sections?: Section[];
  framework?: ResearchFramework;
  parameters?: ParameterConfig;
  summary?: ResearchSummary;
  final_plan?: ResearchPlan;
  status?: 'running' | 'executing' | 'cancelled' | 'processing';
}

/** Suggestion option (chat mode) */
export interface Suggestion {
  id: string;
  label: string;
  example?: string;
  description?: string;
}

/** POST /api/v1/research/interact request */
export interface InteractRequest {
  session_id: string;
  step: number;
  response: Record<string, any>;
}

// ============ Step-Specific Request Types ============

export interface Step1Request {
  output_type: string;
}

export interface Step2Request {
  template_id: string;
}

export interface Step3Request {
  selected_sections: string[];
}

// Dynamic parameter item (backend returned parameter structure)
export interface DynamicParameterOption {
  value: string;
  label: string;
}

export interface DynamicParameter {
  id: string;
  type: 'text' | 'select' | 'multi_select' | 'date';
  label: string;
  default?: string | string[];
  required?: boolean;
  options?: DynamicParameterOption[];
  placeholder?: string;
}

// Step4Request changed to dynamic (accepts any key-value pair)
export interface Step4Request {
  [key: string]: any;
}

export interface Step5Request {
  confirmed: boolean;
}

// ============ Common Types ============

export interface SelectOption {
  id: string;
  label: string;
  description?: string;
  icon?: string;
  disabled?: boolean;
  selected?: boolean;
  required?: boolean;
  example?: string;  // Example text for chat mode
}

export interface Template {
  id: string;
  name: string;
  description: string;
  preview_image?: string;
}

export interface Section {
  id: string;
  title: string;
  description?: string;
  required: boolean;
  selected: boolean;
}

// Legacy ParameterConfig has been replaced by DynamicParameter[]
// Backend returned parameterConfig format:
// { "parameters": DynamicParameter[] }
// Or backward compatible: { "region": {...}, "time_range": {...}, "depth": {...} }
export type ParameterConfig = DynamicParameter[];

export interface ResearchSummary {
  topic: string;
  title?: string;
  output_type: string;
  template: string;
  sections: string[];
  parameters: Record<string, string>;
  estimated_read_time?: string;
}

export interface ResearchPlan {
  topic: string;
  phases: Phase[];
  estimated_time: string;
}

export interface Phase {
  id: string;
  name: string;
  description?: string;
  tasks: string[];
  estimated_time: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  progress: number;
}

// ============ SSE Types ============

export interface SSEMessage {
  event: 'progress' | 'phase_start' | 'phase_complete' | 'error' | 'complete' | 'chat_response' | 'agent_message' | 'heartbeat' | 'connected' | 'message' | 'cancelled' | 'quality_result' | 'section_quality' | 'preview_refresh' | 'quality_confirmed';
  data: ProgressData | PhaseData | ErrorData | CompleteData | ChatResponseData | AgentMessageData | QualityResultEventData | SectionQualityEventData | PreviewRefreshEventData | QualityConfirmedEventData;
}

export interface AgentMessageData {
  session_id: string;
  agent_id: string;
  agent_name: string;
  action: string; // "searching" | "analyzing" | "writing" | "completed"
  content: string;
  timestamp: string;
}

export interface ChatResponseData {
  session_id: string;
  message: string;
  action: string;
  topic?: string;
  directions?: string[];
  suggestions?: Array<{ id: string; label: string; example: string }>;
  timestamp: string;
}

export interface QualityIssueData {
  id: string;
  section: string;
  type: string;
  message: string;
  severity: 'high' | 'medium' | 'low';
  state: 'open' | 'dismissed' | 'revising' | 'resolved' | 'max_retries_reached' | 'accepted';
  revision_count?: number;
}

export interface SectionScoreData {
  score: number;
  status: 'passed' | 'warning' | 'empty';
  issues: QualityIssueData[];
}

export interface QualityResultEventData {
  session_id: string;
  overall_score: number;
  overall_status: 'passed' | 'warning';
  section_scores: Record<string, SectionScoreData>;
  phase: 'reviewing' | 'revising' | 'confirmed';
  version_stack?: Array<{
    id: string;
    created_at: string;
    html_path: string;
    overall_score: number;
    label: string;
  }>;
  current_version?: string;
}

export interface SectionQualityEventData {
  session_id: string;
  section_name: string;
  data: SectionScoreData;
}

export interface PreviewRefreshEventData {
  session_id: string;
  preview_url: string;
  version_id: string;
  timestamp: string;
}

export interface QualityConfirmedEventData {
  session_id: string;
  final_document_path: string;
  timestamp: string;
}

export interface QualityStateData {
  overall_score: number;
  overall_status: 'passed' | 'warning';
  section_scores: Record<string, SectionScoreData>;
  phase: 'reviewing' | 'revising' | 'confirmed';
  version_stack: Array<{
    id: string;
    created_at: string;
    html_path: string;
    overall_score: number;
    label: string;
  }>;
  current_version?: string;
}

export interface PendingInputData {
  text: string;
  issueId?: string;
  sectionName?: string;
}

export interface ProgressData {
  task_id: string;
  phase_id: string;
  progress: number;
  message: string;
  timestamp: string;
}

export interface PhaseData {
  task_id: string;
  phase_id: string;
  phase_name: string;
  status: 'running' | 'completed' | 'error';
  timestamp: string;
}

export interface ErrorData {
  task_id: string;
  code: string;
  message: string;
  details?: any;
}

export interface CompleteData {
  task_id: string;
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

// ============ Document API Types ============

export interface GenerateDocumentRequest {
  task_id: string;
  output_format: 'docx' | 'pptx' | 'pdf' | 'html';
  template: 'consulting' | 'academic' | 'business' | 'minimal';
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

// ============ History Types ============

export interface ResearchResultMeta {
  id?: string; // Alias for task_id
  task_id: string;
  title: string;
  topic: string;
  query?: string; // Original user query
  status: 'analyzing' | 'collecting' | 'reporting' | 'completed' | 'paused' | 'document_pending' | 'document_generated';
  created_at: string | null;
  completed_at: string | null;
  output_format?: string;
  output_type?: string; // Alias
  generated_formats?: string[];
  user_id?: string;
}

// ============ Chat Types ============

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'agent' | 'system';
  content: string;
  timestamp: string;
  metadata?: Record<string, any>;
  agent?: {
    id: string;
    name: string;
    action: string;
  };
}
