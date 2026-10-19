// app/surveys/page.tsx
'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Plus, ClipboardList, Loader2 } from 'lucide-react';
import type { SurveySummary } from '@/types/survey';

export default function SurveyListPage() {
  const [surveys, setSurveys] = useState<SurveySummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listSurveys().then(setSurveys).catch(console.error).finally(() => setLoading(false));
  }, []);

  return (
    <div className="flex flex-col h-screen">
      <header className="flex h-[52px] items-center justify-between border-b px-4 shrink-0">
        <div className="flex items-center gap-2">
          <ClipboardList className="h-5 w-5 text-primary" />
          <h1 className="font-semibold text-sm">Survey</h1>
        </div>
        <Link href="/surveys/new">
          <Button size="sm" className="h-8 gap-1.5">
            <Plus className="h-4 w-4" /> New Survey
          </Button>
        </Link>
      </header>

      <div className="flex-1 overflow-auto p-4">
        {loading ? (
          <div className="flex items-center justify-center h-32 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading...
          </div>
        ) : surveys.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-muted-foreground gap-3">
            <ClipboardList className="h-12 w-12 opacity-30" />
            <p className="text-sm">No surveys yet</p>
            <Link href="/surveys/new">
              <Button variant="outline" size="sm">Create your first survey</Button>
            </Link>
          </div>
        ) : (
          <div className="grid gap-3 max-w-3xl">
            {surveys.map((s) => (
              <Link key={s.survey_id} href={`/surveys/${s.survey_id}`}>
                <div className="border rounded-lg p-4 hover:bg-accent/50 transition-colors cursor-pointer">
                  <div className="flex items-center justify-between">
                    <h3 className="font-medium text-sm">{s.title || 'Untitled'}</h3>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      s.status === 'completed' ? 'bg-green-100 text-green-700' :
                      s.status === 'running' ? 'bg-blue-100 text-blue-700' :
                      'bg-gray-100 text-gray-600'
                    }`}>{s.status}</span>
                  </div>
                  <div className="flex gap-4 mt-1.5 text-xs text-muted-foreground">
                    <span>{s.question_count} questions</span>
                    <span>{s.response_count} responses</span>
                    <span>{s.created_at?.slice(0, 10)}</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
