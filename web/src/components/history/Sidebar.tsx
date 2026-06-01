// components/history/Sidebar.tsx

'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useResearchStore } from '@/store/useResearchStore';
import { useChatStore } from '@/store/useChatStore';
import { useHistorySessions } from '@/hooks/useHistorySessions';
import { restoreSession } from '@/store/useSessionStore';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { formatDistanceToNow } from '@/lib/utils';
import { BarChart3 } from 'lucide-react';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onViewResearch?: () => void;
}

export function Sidebar({ isOpen, onClose, onViewResearch }: SidebarProps) {
  const router = useRouter();
  const { sessions, isLoading, error, reload, loadMore, hasMore } = useHistorySessions();
  const { sessionId, reset, taskId, status, progress, phases } = useResearchStore();
  const clearMessages = useChatStore((s) => s.clearMessages);

  useEffect(() => {
    if (isOpen) {
      reload();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  const handleSelectSession = async (id: string) => {
    if (id === sessionId) {
      onClose();
      return;
    }
    onClose();
    reset();
    clearMessages();
    await restoreSession(id);
  };

  const handleNewResearch = () => {
    reset();
    clearMessages();
    onClose();
    router.push('/');
  };

  const handleViewResearch = () => {
    onClose();
    onViewResearch?.();
  };

  const hasActiveResearch = (status === 'running' || status === 'completed' || status === 'paused') && taskId;

  return (
    <>
      {isOpen && (
        <div className="fixed inset-0 z-40 bg-black/50 md:hidden" onClick={onClose} />
      )}

      <div
        className={cn(
          'fixed left-0 z-50 w-72 bg-background border-r transition-transform duration-300 ease-in-out',
          isOpen ? 'translate-x-0' : '-translate-x-full'
        )}
        style={{ top: '52px', height: 'calc(100dvh - 52px)' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b px-4" style={{ height: '52px' }}>
          <h2 className="font-semibold text-sm">History</h2>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </Button>
        </div>

        {/* New research button */}
        <div className="px-3 flex items-center" style={{ height: '56px' }}>
          <Button className="w-full text-sm" size="sm" onClick={handleNewResearch}>
            <svg className="mr-2 h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New Research
          </Button>
        </div>

        {/* Content area */}
        <div className="overflow-y-auto px-3 pb-3" style={{ height: 'calc(100dvh - 52px - 52px - 56px)' }}>
          {/* Active research task — agent sub-session list */}
          {hasActiveResearch && (
            <div className="mb-3">
              <div className="flex items-center gap-1.5 mb-1.5 px-1">
                <BarChart3 className="h-3 w-3 text-primary" />
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">
                  Active Research
                </span>
                <span className="text-[10px] text-muted-foreground ml-auto">
                  {status === 'running' || status === 'paused'
                    ? `${phases.filter(p => p.status !== 'pending').length}/${phases.length || '?'} agents`
                    : 'Completed'}
                </span>
              </div>
              <button
                onClick={handleViewResearch}
                className="w-full rounded-lg border p-2.5 text-left transition-colors hover:bg-accent border-primary/30 bg-primary/5"
              >
                <Progress value={progress} className="h-1 mb-1.5" />
                <div className="flex items-center justify-between">
                <span className={cn(
                  'h-1.5 w-1.5 rounded-full',
                  status === 'running' ? 'bg-primary animate-pulse' :
                  status === 'paused' ? 'bg-amber-500' : 'bg-green-500'
                )} />
                <span className="text-[10px] text-muted-foreground">
                  {status === 'running' || status === 'paused' ? `${Math.round(progress)}%` : 'Done'}
                </span>
                </div>
                {/* Mini agent list */}
                {phases.length > 0 && (
                  <div className="mt-1.5 space-y-0.5">
                    {phases.filter(p => p.status !== 'pending').slice(0, 3).map(p => (
                      <div key={p.id} className="flex items-center gap-1 text-[10px] text-muted-foreground">
                        <span className={cn(
                          'w-1 h-1 rounded-full',
                          p.status === 'running' ? 'bg-blue-500 animate-pulse' : 'bg-green-500'
                        )} />
                        <span className="truncate">{p.name}</span>
                      </div>
                    ))}
                    {phases.filter(p => p.status !== 'pending').length > 3 && (
                      <span className="text-[10px] text-muted-foreground pl-2">
                        +{phases.filter(p => p.status !== 'pending').length - 3} more
                      </span>
                    )}
                  </div>
                )}
              </button>
            </div>
          )}

          {/* Session history list */}
          {isLoading ? (
            <div className="flex items-center justify-center p-4">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            </div>
          ) : error ? (
            <div className="p-4 text-center text-sm text-muted-foreground">
              <p className="text-destructive">Failed to load</p>
              <Button variant="ghost" size="sm" onClick={reload} className="mt-2">Retry</Button>
            </div>
          ) : sessions.length === 0 && !hasActiveResearch ? (
            <div className="p-4 text-center text-sm text-muted-foreground">No history</div>
          ) : (
            <div className="space-y-2">
              {sessions.map((session) => (
                <button
                  key={session.task_id}
                  onClick={() => handleSelectSession(session.task_id)}
                  className={cn(
                    'w-full rounded-lg border p-3 text-left transition-colors hover:bg-accent',
                    session.task_id === sessionId && 'bg-accent border-primary'
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <p className="truncate text-sm font-medium">
                        {session.title || 'Unnamed Research'}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {session.query || session.topic}
                      </p>
                    </div>
                    {(() => {
                      const dispStatus = session.task_id === sessionId ? 'active' : session.status;
                      return (
                        <Badge
                          variant={dispStatus === 'completed' ? 'success' : 'secondary'}
                          className="shrink-0 text-xs"
                        >
                          {dispStatus === 'active' ? 'Active'
                            : dispStatus === 'completed' ? 'Completed'
                            : dispStatus === 'reporting' ? 'Running'
                            : dispStatus === 'collecting' ? 'Collecting'
                            : dispStatus === 'analyzing' ? 'Configuring'
                            : dispStatus === 'paused' ? 'Paused'
                            : 'Paused'}
                        </Badge>
                      );
                    })()}
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {session.created_at
                      ? formatDistanceToNow(new Date(session.created_at))
                      : 'Unknown time'}
                  </p>
                </button>
              ))}
              {hasMore && (
                <div className="flex justify-center py-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={loadMore}
                    disabled={isLoading}
                    className="text-xs w-full"
                  >
                    {isLoading ? 'Loading...' : 'Load More'}
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
