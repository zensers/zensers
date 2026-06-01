// types/survey.ts
// Survey module TypeScript types

export interface QuestionSchema {
  text: string;
  type: 'single_choice' | 'multiple_choice' | 'likert' | 'scale' | 'yes_no' | 'open_ended' | 'ranking' | 'matrix' | 'dropdown';
  options?: string[];
  required?: boolean;
  description?: string;
  skip_logic?: {
    depends_on: string;
    condition: 'equals' | 'not_equals' | 'in' | 'greater_than' | 'less_than';
    value: string | string[];
    effect: 'show' | 'hide';
  };
}

export interface CreateSurveyRequest {
  title: string;
  description?: string;
  questions: QuestionSchema[];
}

export interface CreateSurveyResponse {
  survey_id: string;
  title: string;
  question_count: number;
}

export interface SurveySummary {
  survey_id: string;
  title: string;
  status: string;
  question_count: number;
  response_count: number;
  created_at: string;
}

export interface SurveyStatusResponse {
  survey_id: string;
  status: string;
  collected: number;
  target: number;
  valid: number;
}

export interface SimulateRequest {
  target_count: number;
  template: string;
  persona_type: 'consumer' | 'expert';
}

export interface SimulateResponse {
  task_id: string;
  persona_count: number;
  response_count: number;
  cost: number;
  success: boolean;
}

export interface AnalysisReport {
  report: string;
  statistics: Record<string, any>;
  sentiment: Record<string, any>;
  wordcloud: Record<string, any>;
  cross_tabulations: any[];
  charts?: Record<string, string>;
  wordcloud_image?: string;
  generated_at: string;
}

export interface TemplateInfo {
  id: string;
  name: string;
  description: string;
}

export interface TemplatesResponse {
  consumer_templates: TemplateInfo[];
  expert_templates: TemplateInfo[];
}

export interface RegionInfo {
  name: string;
  source: string;
  source_url: string;
  dimensions: string[];
}

export interface RegionsResponse {
  regions: Record<string, RegionInfo>;
}

export interface SurveyDetail {
  survey_id: string;
  title: string;
  status: string;
  question_count: number;
  response_count: number;
  created_at: string;
  questions?: QuestionSchema[];
}
