// app/surveys/[id]/analysis/page.tsx
'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { ArrowLeft, Loader2 } from 'lucide-react';
import type { AnalysisReport } from '@/types/survey';

export default function AnalysisPage() {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<AnalysisReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!id) return;
    api.getSurveyAnalysis(id)
      .then(setReport)
      .catch((e: any) => setError(e?.response?.data?.detail || e.message || 'Analysis failed'))
      .finally(() => setLoading(false));
  }, [id]);

  return (
    <div className="flex flex-col h-screen">
      <header className="flex h-[52px] items-center justify-between border-b px-4 shrink-0">
        <div className="flex items-center gap-2">
          <Link href={`/surveys/${id}`}>
            <Button variant="ghost" size="icon" className="h-8 w-8">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <h1 className="font-semibold text-sm">Analysis Report</h1>
          {report && <span className="text-xs text-muted-foreground">{report.generated_at?.slice(0, 10)}</span>}
        </div>
      </header>

      <div className="flex-1 overflow-auto p-4">
        {loading ? (
          <div className="flex items-center justify-center h-32 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin mr-2" /> Generating analysis...
          </div>
        ) : error ? (
          <div className="text-sm text-red-500 p-4 border border-red-200 rounded-lg bg-red-50">
            {error}
            <p className="text-xs text-red-400 mt-2">Run simulation first, then analyze.</p>
            <Link href={`/surveys/${id}`}>
              <Button variant="outline" size="sm" className="mt-2">Back to survey</Button>
            </Link>
          </div>
        ) : report ? (
          <div className="max-w-4xl mx-auto space-y-6">
            {/* Markdown report */}
            <div className="prose prose-sm dark:prose-invert max-w-none"
              dangerouslySetInnerHTML={{ __html: renderMarkdown(report.report) }}
            />

            {/* Charts */}
            {report.charts && Object.keys(report.charts).length > 0 && (
              <div className="border-t pt-6">
                <h2 className="text-lg font-semibold mb-4">Charts</h2>
                <div className="grid grid-cols-2 gap-4">
                  {Object.entries(report.charts).map(([qid, path]) => (
                    <div key={qid} className="border rounded-lg p-2">
                      <p className="text-xs text-muted-foreground mb-2">{qid}</p>
                      <img src={path} alt={qid} className="w-full rounded" />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Wordcloud */}
            {report.wordcloud?.image_path && (
              <div className="border-t pt-6">
                <h2 className="text-lg font-semibold mb-4">Word Cloud</h2>
                <img src={report.wordcloud.image_path} alt="Word cloud" className="max-w-md rounded border" />
              </div>
            )}

            {/* Cross-tabulations summary */}
            {report.cross_tabulations && report.cross_tabulations.length > 0 && (
              <div className="border-t pt-6">
                <h2 className="text-lg font-semibold mb-4">Cross-Tabulations</h2>
                {report.cross_tabulations.map((ct: any, i: number) => (
                  <div key={i} className="mb-4 p-3 bg-muted/30 rounded-lg">
                    <p className="text-sm font-medium">{ct.row_question} x {ct.col_question}</p>
                    {ct.chi_square && (
                      <p className="text-xs text-muted-foreground mt-1">
                        Chi-square: {ct.chi_square.chi2_stat} (p={ct.chi_square.p_value})
                        {ct.chi_square.significant ? ' \u2713 significant' : ' \u2717 not significant'}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function escapeHtml(str: string): string {
  const map: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#x27;' };
  return str.replace(/[&<>"']/g, (c) => map[c]);
}

function renderMarkdown(md: string): string {
  if (!md) return '';
  const safe = escapeHtml(md);
  return safe
    .replace(/^### (.*$)/gm, '<h3>$1</h3>')
    .replace(/^## (.*$)/gm, '<h2>$1</h2>')
    .replace(/^# (.*$)/gm, '<h1>$1</h1>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/^- (.*$)/gm, '<li>$1</li>')
    .replace(/\|(.+)\|/g, (m) => {
      if (m.includes('---')) return '';
      const cells = m.split('|').filter(c => c.trim());
      return `<tr>${cells.map(c => `<td>${escapeHtml(c.trim())}</td>`).join('')}</tr>`;
    })
    .replace(/(<tr>.*<\/tr>)/g, '<table class="min-w-full text-xs border-collapse border border-gray-200">$1</table>')
    .replace(/\n\n/g, '</p><p class="text-sm">')
    .replace(/!\[(.*?)\]\((.*?)\)/g, '<img src="$2" alt="$1" class="max-w-md rounded border my-2" />');
}
