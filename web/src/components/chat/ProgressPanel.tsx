// components/chat/ProgressPanel.tsx

'use client';

import { useState } from 'react';
import { useResearchStore } from '@/store/useResearchStore';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { ChevronRight, CheckCircle2, Loader2, XCircle, Circle, Bot } from 'lucide-react';

/** Friendly names for known phase IDs */
const AGENT_NAMES: Record<string, string> = {
  orchestrating: 'Orchestrator',
  data_collection: 'Data Collection Agent',
  deep_analysis: 'Deep Analysis Agent',
  synthesis_report: 'Report Synthesis Agent',
  requirement_analysis: 'Requirement Analysis',
  quality_check: 'Quality Check Agent',
};

function agentLabel(id: string, name: string): string {
  return AGENT_NAMES[id] || name || id;
}

function statusIcon(phaseStatus: string) {
  switch (phaseStatus) {
    case 'completed':
      return <CheckCircle2 className="h-4 w-4 text-green-500" />;
    case 'running':
      return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
    case 'error':
      return <XCircle className="h-4 w-4 text-red-500" />;
    default:
      return <Circle className="h-4 w-4 text-gray-300" />;
  }
}

/**
 * Research progress view — shows agents as sub-sessions.
 * Each agent (phase) is a clickable card showing status and progress.
 */
export function ProgressPanel() {
  const { progress, phases, status } = useResearchStore();
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const runningCount = phases.filter(p => p.status === 'running').length;
  const completedCount = phases.filter(p => p.status === 'completed').length;
  const totalCount = phases.length;

  return (
    <div className="space-y-3">
      {/* Overall status header */}
      <div className="flex items-center gap-3 px-1">
        <div className="flex items-center gap-2">
          <Bot className="h-4 w-4 text-primary" />
          <span className="text-sm font-semibold text-foreground">
            Agent Sessions
          </span>
        </div>
        <div className="flex items-center gap-2 ml-auto">
          {status === 'running' && (
            <span className="text-xs text-muted-foreground">
              {completedCount}/{totalCount} completed
            </span>
          )}
          <Badge variant={status === 'completed' ? 'success' : status === 'error' ? 'destructive' : status === 'paused' ? 'warning' : 'default'}>
            {status === 'completed' ? 'All Done' : status === 'error' ? 'Failed' : status === 'paused' ? 'Paused' : 'Running'}
          </Badge>
        </div>
      </div>

      {status === 'running' && (
        <Progress value={progress} className="h-1" />
      )}

      {/* Agent sub-session list */}
      {phases.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="p-6 text-center">
            <p className="text-sm text-muted-foreground">Waiting for agents to start...</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {phases.map((phase, index) => (
            <Card
              key={phase.id}
              className={cn(
                'cursor-pointer transition-colors hover:border-primary/30',
                phase.status === 'running' && 'border-blue-200 bg-blue-50/30',
                phase.status === 'completed' && 'border-green-100 bg-green-50/20',
                phase.status === 'error' && 'border-red-200 bg-red-50/30',
              )}
              onClick={() => setExpandedId(expandedId === phase.id ? null : phase.id)}
            >
              <CardContent className="p-3">
                <div className="flex items-center gap-3">
                  <div className={cn(
                    'flex h-8 w-8 shrink-0 items-center justify-center rounded-full border',
                    phase.status === 'running' && 'bg-blue-50 border-blue-200',
                    phase.status === 'completed' && 'bg-green-50 border-green-200',
                    phase.status === 'error' && 'bg-red-50 border-red-200',
                    phase.status === 'pending' && 'bg-gray-50 border-gray-200',
                  )}>
                    {statusIcon(phase.status)}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium truncate">
                        {agentLabel(phase.id, phase.name)}
                      </span>
                      <span className="text-[11px] text-muted-foreground shrink-0 ml-2">
                        {phase.status === 'running' && `${Math.round(phase.progress)}%`}
                        {phase.status === 'completed' && 'Done'}
                        {phase.status === 'error' && 'Error'}
                        {phase.status === 'pending' && 'Waiting'}
                      </span>
                    </div>
                    {phase.status === 'running' && (
                      <Progress value={phase.progress} className="h-1 mt-1.5" />
                    )}
                  </div>

                  <ChevronRight className={cn(
                    'h-4 w-4 text-muted-foreground transition-transform',
                    expandedId === phase.id && 'rotate-90'
                  )} />
                </div>

                {/* Expanded detail */}
                {expandedId === phase.id && (
                  <div className="mt-3 pt-3 border-t space-y-2">
                    {phase.description && (
                      <p className="text-xs text-muted-foreground">{phase.description}</p>
                    )}
                    <div className="flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                      <span>Session: {phase.id}</span>
                      <span>•</span>
                      <span>Status: {phase.status}</span>
                      {phase.progress > 0 && (
                        <>
                          <span>•</span>
                          <span>Progress: {Math.round(phase.progress)}%</span>
                        </>
                      )}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
