'use client';

import { useState } from 'react';
import { useSessionStore } from '@/store/useSessionStore';
import { api } from '@/lib/api';
import type { QualityIssueData, SectionScoreData, QualityStateData } from '@/types/api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { ChevronRight, AlertTriangle, CheckCircle2, RotateCcw, X } from 'lucide-react';

function severityColor(severity: string) {
  switch (severity) {
    case 'high': return 'text-red-500 bg-red-50 border-red-200';
    case 'medium': return 'text-yellow-600 bg-yellow-50 border-yellow-200';
    case 'low': return 'text-blue-500 bg-blue-50 border-blue-200';
    default: return 'text-gray-500 bg-gray-50 border-gray-200';
  }
}

function stateBadgeVariant(state: string) {
  switch (state) {
    case 'open': return 'destructive';
    case 'dismissed': return 'secondary';
    case 'revising': return 'default';
    case 'resolved': return 'outline';
    case 'max_retries_reached': return 'outline';
    case 'accepted': return 'secondary';
    default: return 'default';
  }
}

function IssueRow({ issue, onDismiss, onReopen, onStartRevision }: {
  issue: QualityIssueData;
  onDismiss: (id: string) => void;
  onReopen: (id: string) => void;
  onStartRevision: (issue: QualityIssueData) => void;
}) {
  return (
    <div className={cn(
      "flex items-start gap-2 p-2.5 rounded-lg border transition-all",
      severityColor(issue.severity),
      issue.state === 'dismissed' && "opacity-50",
      issue.state === 'revising' && "animate-pulse",
    )}>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 mb-0.5">
          <Badge variant={stateBadgeVariant(issue.state)} className="text-xs py-0">
            {issue.state === 'max_retries_reached' ? 'max' : issue.state}
          </Badge>
          <span className="text-xs font-medium text-muted-foreground">{issue.section}</span>
          {issue.revision_count && issue.revision_count > 0 && (
            <span className="text-xs text-muted-foreground">({issue.revision_count}x)</span>
          )}
        </div>
        <p className="text-sm">{issue.message}</p>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        {issue.state === 'open' && (
          <Button variant="ghost" size="sm" onClick={() => onStartRevision(issue)} className="h-7 px-2 text-xs">
            修订
          </Button>
        )}
        {issue.state === 'open' && (
          <Button variant="ghost" size="sm" onClick={() => onDismiss(issue.id)} className="h-7 px-2 text-xs text-muted-foreground">
            忽略
          </Button>
        )}
        {issue.state === 'dismissed' && (
          <Button variant="ghost" size="sm" onClick={() => onReopen(issue.id)} className="h-7 px-2 text-xs">
            恢复
          </Button>
        )}
      </div>
    </div>
  );
}

export function QualityPanel() {
  const activeId = useSessionStore((s) => s.activeId);
  const session = useSessionStore((s) => activeId ? s.sessions[activeId] : null);
  const qualityState = session?.qualityState;

  const [confirming, setConfirming] = useState(false);
  const [pendingIssues, setPendingIssues] = useState<QualityIssueData[]>([]);

  if (!qualityState) return null;
  if (qualityState.phase === 'confirmed') return null;

  const sessionId = activeId || '';

  const handleDismiss = async (issueId: string) => {
    try {
      await api.qualityAction(sessionId, 'quality_dismiss', { issue_id: issueId });
    } catch (e) { console.error('Dismiss failed:', e); }
  };

  const handleReopen = async (issueId: string) => {
    try {
      await api.qualityAction(sessionId, 'quality_reopen', { issue_id: issueId });
    } catch (e) { console.error('Reopen failed:', e); }
  };

  const handleStartRevision = async (issue: QualityIssueData) => {
    const input = `【质检问题】${issue.section}: ${issue.message}\n请帮我修订这部分内容。`;
    try {
      await api.qualityAction(sessionId, 'initiate_revision', { issue_id: issue.id });
    } catch (e) { console.error('Initiate revision failed:', e); }
    useSessionStore.getState().syncActive({ pendingInput: { text: input, issueId: issue.id, sectionName: issue.section } });
  };

  const handleRecheck = async (sectionName?: string) => {
    try {
      await api.qualityAction(sessionId, 'quality_recheck', { section_name: sectionName });
    } catch (e) { console.error('Recheck failed:', e); }
  };

  const handleConfirm = async (force = false) => {
    try {
      const result = await api.qualityAction(sessionId, 'quality_confirm', { data: { force } });
      if (result.status === 'pending_issues') {
        setPendingIssues(result.open_issues || []);
        setConfirming(true);
      } else {
        setConfirming(false);
        setPendingIssues([]);
      }
    } catch (e) { console.error('Confirm failed:', e); }
  };

  const allIssues: QualityIssueData[] = [];
  for (const [, secData] of Object.entries(qualityState.section_scores || {})) {
    for (const issue of secData.issues) {
      allIssues.push(issue);
    }
  }

  const openIssues = allIssues.filter(i => i.state === 'open');
  const totalIssues = allIssues.length;

  return (
    <div className="w-80 border-l bg-background overflow-y-auto">
      <div className="p-4 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">质检面板</h2>
          <Badge variant={qualityState.overall_status === 'passed' ? 'outline' : 'destructive'} className="text-xs">
            {qualityState.overall_status === 'passed' ? '✓ 通过' : '⚠ 待修订'}
          </Badge>
        </div>

        <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50 border">
          <div className="text-2xl font-bold">{qualityState.overall_score}</div>
          <div className="text-xs text-muted-foreground">综合评分</div>
          <div className="ml-auto text-xs text-muted-foreground">
            {openIssues.length}/{totalIssues} 问题
          </div>
        </div>

        {Object.entries(qualityState.section_scores || {}).map(([name, data]: [string, SectionScoreData]) => (
          <div key={name} className="flex items-center gap-2 p-2 rounded border text-xs">
            <div className={cn(
              "w-8 h-8 rounded flex items-center justify-center font-bold text-sm shrink-0",
              data.score >= 60 ? 'bg-green-50 text-green-600' : 'bg-red-50 text-red-600'
            )}>
              {data.score}
            </div>
            <div className="flex-1 min-w-0 truncate font-medium">{name}</div>
            <Badge variant={data.status === 'passed' ? 'outline' : 'destructive'} className="text-xs py-0">
              {data.status === 'passed' ? '✓' : '⚠'}
            </Badge>
          </div>
        ))}

        {allIssues.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs font-medium text-muted-foreground">
              <span>问题列表</span>
              <Button variant="ghost" size="sm" onClick={() => handleRecheck()} className="h-6 px-2 text-xs">
                重新检查
              </Button>
            </div>
            {allIssues.map(issue => (
              <IssueRow
                key={issue.id}
                issue={issue}
                onDismiss={handleDismiss}
                onReopen={handleReopen}
                onStartRevision={handleStartRevision}
              />
            ))}
          </div>
        )}

        <div className="pt-2 border-t space-y-2">
          <Button
            onClick={() => handleConfirm()}
            disabled={qualityState.phase === 'confirmed'}
            className="w-full h-9 text-sm"
          >
            确认交付
          </Button>
          {(qualityState.version_stack || []).length > 1 && (
            <div className="text-xs text-muted-foreground space-y-1">
              <span className="font-medium">版本历史</span>
              {(qualityState.version_stack || []).slice(-3).reverse().map(v => (
                <div key={v.id} className="flex items-center gap-1">
                  <span className="truncate">{v.label || v.id}</span>
                  <span>{v.overall_score}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {confirming && pendingIssues.length > 0 && (
          <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center">
            <Card className="w-96 p-6 space-y-4">
              <h3 className="text-lg font-semibold">仍有未解决的问题</h3>
              <div className="space-y-2 max-h-60 overflow-y-auto">
                {pendingIssues.map(issue => (
                  <div key={issue.id} className={cn("p-2 rounded border text-sm", severityColor(issue.severity))}>
                    <span className="font-medium">{issue.section}</span>: {issue.message}
                  </div>
                ))}
              </div>
              <div className="flex gap-2 justify-end">
                <Button variant="outline" onClick={() => { setConfirming(false); setPendingIssues([]); }}>
                  继续修订
                </Button>
                <Button onClick={() => { handleConfirm(true); setConfirming(false); }}>
                  仍要交付
                </Button>
              </div>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}