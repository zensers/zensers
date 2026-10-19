// store/useSurveyStore.ts
// Survey state management

import { create } from 'zustand';
import type { SurveySummary, AnalysisReport, SurveyStatusResponse, TemplatesResponse } from '@/types/survey';

interface SurveyState {
  surveys: SurveySummary[];
  selectedId: string | null;
  analysis: AnalysisReport | null;
  status: SurveyStatusResponse | null;
  templates: TemplatesResponse | null;
  loading: boolean;
  error: string | null;

  setSurveys: (surveys: SurveySummary[]) => void;
  setSelectedId: (id: string | null) => void;
  setAnalysis: (report: AnalysisReport | null) => void;
  setStatus: (status: SurveyStatusResponse | null) => void;
  setTemplates: (templates: TemplatesResponse | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useSurveyStore = create<SurveyState>((set) => ({
  surveys: [],
  selectedId: null,
  analysis: null,
  status: null,
  templates: null,
  loading: false,
  error: null,

  setSurveys: (surveys) => set({ surveys }),
  setSelectedId: (id) => set({ selectedId: id }),
  setAnalysis: (report) => set({ analysis: report }),
  setStatus: (status) => set({ status }),
  setTemplates: (templates) => set({ templates }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
}));
