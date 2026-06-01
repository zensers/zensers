# Survey Module Frontend Integration Plan

## Overview

Integrate the survey module's 10 REST API endpoints into the Next.js frontend to enable full survey lifecycle management: create, simulate, collect responses, analyze, and merge into research reports.

## Current State

| Layer | Status |
|-------|--------|
| Backend REST API | ✅ 10 endpoints at `/api/v1/surveys/` |
| CLI | ✅ 8 commands via `src/cli/main.py` |
| Python API | ✅ `from src.survey import SurveyClient` |
| Web Frontend | ❌ No survey pages or API calls exist |

## Pages

### P0 — Survey List & Creation

| Page | Route | Purpose |
|------|-------|---------|
| Survey List | `/surveys` | List all surveys with status badges. Actions: create, view, delete |
| Create Survey | `/surveys/new` | JSON editor + form to define questions with skip logic |
| Survey Detail | `/surveys/[id]` | Overview: status, question list, response count. Actions: simulate, view results |

### P1 — Simulation & Results

| Page | Route | Purpose |
|------|-------|---------|
| Survey Results | `/surveys/[id]/results` | Response table, export CSV, per-question distribution charts |
| Survey Analysis | `/surveys/[id]/analysis` | Full report: charts, cross-tabs, chi-square, sentiment, significance tests |
| Compare Surveys | `/surveys/compare` | Side-by-side comparison of two surveys |

### P2 — Integration

| Page | Route | Purpose |
|------|-------|---------|
| Research + Survey | `/research/[id]/survey` | Attach survey to a research task, cross-synthesis view |

## API Integration

### Type Definitions (`types/survey.ts`)

```typescript
// Question definition
interface QuestionSchema {
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

// API request/response types
interface CreateSurveyRequest {
  title: string;
  description?: string;
  questions: QuestionSchema[];
}

interface SurveySummary {
  survey_id: string;
  title: string;
  status: string;
  question_count: number;
  response_count: number;
  created_at: string;
}

interface SimulateRequest {
  target_count: number;
  template: string;
  persona_type: 'consumer' | 'expert';
}

interface SimulateResponse {
  task_id: string;
  persona_count: number;
  response_count: number;
  cost: number;
  success: boolean;
}

interface AnalysisReport {
  report: string;           // Markdown
  statistics: object;
  sentiment: object;
  cross_tabulations: array;
  charts: Record<string, string>;  // question_id → image URL
  wordcloud_image?: string;
  generated_at: string;
}

interface TemplateInfo {
  id: string;
  name: string;
  description: string;
}

interface RegionInfo {
  name: string;
  source: string;
  dimensions: string[];
}
```

### API Client Methods (`lib/api.ts` additions)

```typescript
class SurveyAPI {
  // List all surveys
  async listSurveys(): Promise<SurveySummary[]>
  // GET /api/v1/surveys

  // Create survey
  async createSurvey(req: CreateSurveyRequest): Promise<{survey_id: string}>
  // POST /api/v1/surveys

  // Get survey detail
  async getSurvey(surveyId: string): Promise<SurveyDetail>
  // GET /api/v1/surveys/{survey_id}

  // Run AI simulation
  async simulateSurvey(surveyId: string, req: SimulateRequest): Promise<SimulateResponse>
  // POST /api/v1/surveys/{survey_id}/simulate

  // Get simulation status
  async getSurveyStatus(surveyId: string): Promise<StatusResponse>
  // GET /api/v1/surveys/{survey_id}/status

  // Get results
  async getSurveyResults(surveyId: string, limit?: number): Promise<ResultsResponse>
  // GET /api/v1/surveys/{survey_id}/results

  // Get analysis report
  async getSurveyAnalysis(surveyId: string): Promise<AnalysisReport>
  // GET /api/v1/surveys/{survey_id}/analysis

  // List templates
  async listSurveyTemplates(): Promise<{consumer_templates: TemplateInfo[], expert_templates: TemplateInfo[]}>
  // GET /api/v1/surveys/templates

  // List regions
  async listSurveyRegions(): Promise<RegionsResponse>
  // GET /api/v1/surveys/regions
}
```

## Component Tree

```
app/
├── surveys/                          # Survey section
│   ├── page.tsx                      # Survey list (P0)
│   ├── new/
│   │   └── page.tsx                  # Create survey (P0)
│   └── [id]/
│       ├── page.tsx                  # Survey dashboard (P0)
│       ├── results/
│       │   └── page.tsx              # Response browser (P1)
│       └── analysis/
│           └── page.tsx              # Full analysis report (P1)

components/
├── survey/
│   ├── SurveyList.tsx                # Survey table with status
│   ├── SurveyCreateForm.tsx          # Question builder form
│   ├── SurveyCard.tsx                # Summary card with actions
│   ├── QuestionEditor.tsx            # Single question editor (with skip_logic config)
│   ├── QuestionList.tsx              # List of questions (reorderable)
│   ├── JsonEditor.tsx                # JSON editor for advanced users
│   ├── SimulationPanel.tsx           # Simulation config + trigger
│   ├── ResultsTable.tsx              # Tabular response viewer
│   ├── DistributionChart.tsx         # Per-question bar chart
│   ├── CrossTabViewer.tsx            # Cross-tabulation table with chi-square
│   ├── SentimentViewer.tsx           # Sentiment analysis display
│   └── AnalysisReport.tsx            # Full report renderer

store/
├── useSurveyStore.ts                # Survey state management
```

## Data Flow

### Survey Creation Flow
```
User fills form / pastes JSON → POST /api/v1/surveys → Redirect to /surveys/[id]
```

### Simulation Flow
```
User clicks "Simulate" → Select template + count → 
POST /api/v1/surveys/{id}/simulate → 
Poll GET /api/v1/surveys/{id}/status → Show progress → 
GET /api/v1/surveys/{id}/results → Display
```

### Analysis Flow
```
User clicks "Analyze" → 
GET /api/v1/surveys/{id}/analysis → 
Render Markdown report + charts (bar charts per question) +
cross-tabulations with chi-square p-values +
sentiment analysis +
statistical significance indicators
```

## Navigation

Add survey section to the sidebar/nav:

```
Research          (existing)
├── New Research
├── History
└── Settings

Survey            (new)
├── My Surveys
├── Create Survey
├── Templates
└── Regions

Knowledge Bank    (existing)
Chat              (existing)
```

## Integration with Existing Report System

The analysis report API returns structured data that can be:
1. Rendered as a standalone survey report page
2. Injected into the existing Markdown report preview system
3. Used in cross-synthesis with research data

The orchestrator already supports `PhaseType.CROSS_SYNTHESIS` which merges survey + desk research. The frontend should show a combined view when both exist.

## Implementation Order

| Phase | Items | Dependencies |
|-------|-------|-------------|
| **Phase 1** (Backend API ready) | Types, API client, Survey list page, Create page, Survey detail page | None |
| **Phase 2** | Simulation panel, Results page, Result table, Distribution chart | Phase 1 |
| **Phase 3** | Analysis report page, Cross-tab viewer, Sentiment viewer, Chi-square display | Phase 2 |
| **Phase 4** | Navigation integration, Survey store, Chart integration | Phase 1-3 |
| **Phase 5** | Research+survey integration, Cross-synthesis view, Compare surveys | Phase 4 |
