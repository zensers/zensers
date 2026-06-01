// app/surveys/[id]/page.tsx
'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { ArrowLeft, Play, BarChart3, Loader2, CheckCircle2, XCircle } from 'lucide-react';
import type { SurveyDetail, SimulateResponse, TemplatesResponse, SurveyStatusResponse } from '@/types/survey';

export default function SurveyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [survey, setSurvey] = useState<SurveyDetail | null>(null);
  const [templates, setTemplates] = useState<TemplatesResponse | null>(null);
  const [status, setStatus] = useState<SurveyStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);

  // Simulation form
  const [template, setTemplate] = useState('white_collar');
  const [count, setCount] = useState(50);
  const [simulating, setSimulating] = useState(false);
  const [simResult, setSimResult] = useState<SimulateResponse | null>(null);

  useEffect(() => {
    if (!id) return;
    Promise.all([
      api.getSurvey(id).catch(() => null),
      api.listSurveyTemplates().catch(() => null),
      api.getSurveyStatus(id).catch(() => null),
    ]).then(([s, t, st]) => {
      setSurvey(s);
      setTemplates(t);
      setStatus(st);
    }).finally(() => setLoading(false));
  }, [id]);

  const handleSimulate = async () => {
    if (!id) return;
    setSimulating(true);
    setSimResult(null);
    try {
      const res = await api.simulateSurvey(id, { target_count: count, template, persona_type: 'consumer' });
      setSimResult(res);
      const st = await api.getSurveyStatus(id);
      setStatus(st);
    } catch (e: any) {
      alert(e?.response?.data?.detail || e.message || 'Simulation failed');
    } finally {
      setSimulating(false);
    }
  };

  if (loading) return (
    <div className="flex items-center justify-center h-screen text-muted-foreground">
      <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading...
    </div>
  );

  return (
    <div className="flex flex-col h-screen">
      <header className="flex h-[52px] items-center justify-between border-b px-4 shrink-0">
        <div className="flex items-center gap-2">
          <Link href="/surveys"><Button variant="ghost" size="icon" className="h-8 w-8"><ArrowLeft className="h-4 w-4" /></Button></Link>
          <h1 className="font-semibold text-sm truncate max-w-[300px]">{survey?.title || 'Survey'}</h1>
          {status && (
            <span className={`text-xs px-2 py-0.5 rounded-full ml-2 ${
              status.status === 'completed' ? 'bg-green-100 text-green-700' :
              status.status === 'running' ? 'bg-blue-100 text-blue-700' :
              'bg-gray-100 text-gray-600'
            }`}>{status.status}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="h-8 gap-1.5" onClick={() => router.push(`/surveys/${id}/analysis`)}>
            <BarChart3 className="h-4 w-4" /> Analyze
          </Button>
        </div>
      </header>

      <div className="flex-1 overflow-auto p-4 max-w-3xl space-y-6">
        {/* Status card */}
        {status && (
          <div className="border rounded-lg p-4 grid grid-cols-3 gap-4 text-center">
            <div>
              <p className="text-xs text-muted-foreground">Status</p>
              <p className="text-sm font-medium mt-0.5">{status.status}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Collected</p>
              <p className="text-sm font-medium mt-0.5">{status.collected}/{status.target}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Valid</p>
              <p className="text-sm font-medium mt-0.5">{status.valid}</p>
            </div>
          </div>
        )}

        {/* Simulation panel */}
        <div className="border rounded-lg p-4">
          <h2 className="text-sm font-medium mb-3">AI Simulation</h2>
          <div className="flex items-end gap-3">
            <div className="flex-1">
              <label className="text-xs text-muted-foreground mb-1 block">Template</label>
              <select className="w-full border rounded-lg px-3 py-2 text-sm bg-background" value={template} onChange={e => setTemplate(e.target.value)}>
                {templates?.consumer_templates.map(t => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </div>
            <div className="w-24">
              <label className="text-xs text-muted-foreground mb-1 block">Sample size</label>
              <input type="number" className="w-full border rounded-lg px-3 py-2 text-sm bg-background" value={count} onChange={e => setCount(Number(e.target.value))} min={1} max={500} />
            </div>
            <Button onClick={handleSimulate} disabled={simulating} className="h-9 gap-1.5">
              {simulating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              {simulating ? 'Running...' : 'Simulate'}
            </Button>
          </div>

          {simResult && (
            <div className="mt-3 p-3 bg-green-50 border border-green-200 rounded-lg text-sm">
              <p className="text-green-700 font-medium flex items-center gap-1.5">
                <CheckCircle2 className="h-4 w-4" /> Simulation complete
              </p>
              <div className="flex gap-4 mt-1 text-xs text-green-600">
                <span>{simResult.response_count} responses</span>
                <span>{simResult.persona_count} personas</span>
                <span>${simResult.cost.toFixed(4)} cost</span>
              </div>
            </div>
          )}
        </div>

        {/* Questions preview */}
        {survey?.questions && survey.questions.length > 0 && (
          <div className="border rounded-lg p-4">
            <h2 className="text-sm font-medium mb-3">Questions ({survey.questions.length})</h2>
            <div className="space-y-2">
              {survey.questions.map((q: any, i: number) => (
                <div key={i} className="text-sm p-2 bg-muted/30 rounded-lg">
                  <span className="text-muted-foreground mr-2">Q{i + 1}.</span>
                  <span>{q.text}</span>
                  <span className="text-xs text-muted-foreground ml-2">({q.type})</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
