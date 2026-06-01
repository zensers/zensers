// app/history/[id]/page.tsx

'use client';

import { useState, useEffect } from 'react';
import { api, ApiError } from '@/lib/api';
import { DocumentPreview } from '@/components/preview/DocumentPreview';
import { RevisionPanel } from '@/components/preview/RevisionPanel';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useRouter, useParams } from 'next/navigation';
import type { ResearchResultMeta } from '@/types/api';
import { ArrowLeft, FileText, Download, Calendar, Clock, Edit3, ExternalLink } from 'lucide-react';

export default function HistoryDetailPage() {
  const params = useParams();
  const id = params?.id as string;
  const router = useRouter();
  const [meta, setMeta] = useState<ResearchResultMeta | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isRevisionPanelOpen, setIsRevisionPanelOpen] = useState(false);
  const [previewKey, setPreviewKey] = useState(0);

  useEffect(() => {
    if (!id) return;
    
    const load = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const detail = await api.getResearchDetail(id);
        setMeta(detail);
      } catch (e) {
        setError((e as ApiError).message || 'Failed to load');
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, [id]);

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'Unknown';
    return new Date(dateStr).toLocaleString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const handleRevisionComplete = () => {
    setPreviewKey((prev) => prev + 1);
    loadMeta();
  };

  const loadMeta = async () => {
    if (!id) return;
    try {
      const detail = await api.getResearchDetail(id);
      setMeta(detail);
    } catch (e) {
      console.error('Failed to reload meta:', e);
    }
  };

  // 恢复研究状态到聊天页面
  const handleResumeResearch = () => {
    if (!meta) return;
    sessionStorage.setItem('resume-session', meta.task_id);
    router.push('/');
  };

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-primary/30 border-t-primary" />
          <p className="text-sm text-muted-foreground">Loading research...</p>
        </div>
      </div>
    );
  }

  if (error || !meta) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <Card className="max-w-md border-destructive/50">
          <CardHeader>
            <CardTitle className="text-destructive">Load Failed</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground">{error || 'Research task not found'}</p>
            <div className="flex gap-2 mt-4">
              <Button onClick={() => router.push('/history')} variant="outline">
                Back to List
              </Button>
              <Button onClick={() => router.push('/')}>
                Back to Home
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur-sm">
        <div className="mx-auto max-w-7xl px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => router.push('/history')}
                className="h-9 w-9"
              >
                <ArrowLeft className="h-4 w-4" />
              </Button>
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                  <FileText className="h-5 w-5" />
                </div>
                <div>
                  <h1 className="text-lg font-bold text-foreground line-clamp-1">
                    {meta.title || meta.topic || 'Unnamed Research'}
                  </h1>
                  <p className="text-sm text-muted-foreground line-clamp-1">
                    {meta.query || meta.topic}
                  </p>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Badge className={
                meta.status === 'completed'
                  ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                  : meta.status === 'paused'
                  ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                  : 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
              }>
                {meta.status === 'completed' ? 'Completed' :
                 meta.status === 'paused' ? 'Paused' :
                 meta.status === 'reporting' ? 'In Progress' :
                 meta.status === 'collecting' ? 'Collecting' :
                 meta.status === 'analyzing' ? 'Configuring' : 'Paused'}
              </Badge>
              <Button
                variant="outline"
                size="sm"
                className="gap-2"
                onClick={handleResumeResearch}
              >
                <ExternalLink className="h-4 w-4" />
                Continue Research
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="gap-2"
                onClick={() => setIsRevisionPanelOpen(true)}
              >
                <Edit3 className="h-4 w-4" />
                Revise
              </Button>
              {meta.output_format && (
                <Button variant="default" size="sm" className="gap-2">
                  <Download className="h-4 w-4" />
                  Export
                </Button>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Meta Info Bar */}
      <div className="border-b bg-muted/30">
        <div className="mx-auto max-w-7xl px-6 py-3">
          <div className="flex items-center gap-6 text-sm text-muted-foreground">
            <div className="flex items-center gap-1.5">
              <Calendar className="h-4 w-4" />
              <span>Created: {formatDate(meta.created_at)}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Clock className="h-4 w-4" />
              <span>Completed: {formatDate(meta.completed_at)}</span>
            </div>
            {meta.generated_formats && meta.generated_formats.length > 0 && (
              <div className="flex items-center gap-2">
                <span>Format:</span>
                <div className="flex gap-1">
                  {meta.generated_formats.map((fmt) => (
                    <Badge key={fmt} variant="secondary" className="text-xs">
                      {fmt.toUpperCase()}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Preview */}
      <div className="h-[calc(100vh-140px)]">
        <DocumentPreview key={previewKey} taskIdOverride={id} />
      </div>

      {/* Revision Panel */}
      <RevisionPanel
        taskId={id}
        isOpen={isRevisionPanelOpen}
        onClose={() => setIsRevisionPanelOpen(false)}
        onRevisionComplete={handleRevisionComplete}
      />
    </div>
  );
}