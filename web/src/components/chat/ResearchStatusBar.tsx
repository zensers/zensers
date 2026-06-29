'use client';

import { Loader2 } from 'lucide-react';
import { useResearchStore } from '@/store/useResearchStore';
import { Progress } from '@/components/ui/progress';

export function ResearchStatusBar() {
  const status = useResearchStore((s) => s.status);
  const progress = useResearchStore((s) => s.progress);
  const phases = useResearchStore((s) => s.phases);

  if (status !== 'running') return null;

  const currentPhase = phases.find(p => p.status === 'running');
  const completedCount = phases.filter(p => p.status === 'completed').length;

  return (
    <div className="sticky top-0 z-10 bg-background/95 backdrop-blur border-b px-4 py-2">
      <div className="flex items-center gap-3">
        <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
        <span className="text-sm font-medium">
          {currentPhase?.name || 'Processing...'}
        </span>
        <span className="text-xs text-muted-foreground ml-auto">
          {completedCount}/{phases.length} phases completed
        </span>
      </div>
      <Progress value={progress * 100} className="h-1 mt-1" />
    </div>
  );
}
