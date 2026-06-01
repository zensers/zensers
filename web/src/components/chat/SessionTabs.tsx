// components/chat/SessionTabs.tsx
// Multi-session tab bar — shows all open sessions, supports instant switching

'use client';

import { useCallback } from 'react';
import { useSessionStore } from '@/store/useSessionStore';
import { useResearchStore } from '@/store/useResearchStore';
import { useChatStore } from '@/store/useChatStore';
import { cn } from '@/lib/utils';
import { Plus, X } from 'lucide-react';
import { nanoid } from 'nanoid';

export function SessionTabs() {
  const activeId = useSessionStore((s) => s.activeId);
  const sessions = useSessionStore((s) => s.sessions);
  const switchTo = useSessionStore((s) => s.switchTo);
  const createSession = useSessionStore((s) => s.createSession);
  const closeSession = useSessionStore((s) => s.closeSession);
  const syncActive = useSessionStore((s) => s.syncActive);

  // Read current state from Research/Chat store (more up-to-date than registry cache)
  const { status, currentStep } = useResearchStore();

  const handleNew = useCallback(() => {
    const id = nanoid();
    createSession(id);
  }, [createSession]);

  const handleClose = useCallback((e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    closeSession(id);
  }, [closeSession]);

  // Filter meaningful sessions: active + has backend task + has message history, max 7 shown
  const entries = Object.entries(sessions)
    .filter(([id, s]) => id === activeId || s.taskId || s.messages.length > 0)
    .slice(-7);
  if (entries.length === 0) return null;

  return (
    <div className="flex items-center gap-0.5 px-3 pt-2 overflow-x-auto shrink-0 border-b bg-muted/10">
      {entries.map(([id, session]) => (
        <button
          key={id}
          onClick={() => {
            // Sync current active session state to cache before switching
            syncActive({
              status,
              currentStep,
              messages: useChatStore.getState().messages,
            });
            switchTo(id);
          }}
          className={cn(
            'group flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-t-lg border border-b-0 transition-colors whitespace-nowrap',
            id === activeId
              ? 'bg-background border-border text-foreground font-medium'
              : 'border-transparent text-muted-foreground hover:text-foreground hover:bg-secondary/50'
          )}
        >
          <span
            className={cn(
              'h-1.5 w-1.5 rounded-full shrink-0',
              session.status === 'running' ? 'bg-green-500 animate-pulse' :
              session.status === 'completed' ? 'bg-green-500' :
              'bg-muted-foreground/30'
            )}
          />
          <span className="max-w-[120px] truncate">{session.title || 'New Chat'}</span>
          <span
            role="button"
            onClick={(e) => handleClose(e, id)}
            className="ml-1 rounded-full p-0.5 opacity-0 group-hover:opacity-60 hover:opacity-100 hover:bg-secondary transition-opacity"
          >
            <X className="h-3 w-3" />
          </span>
        </button>
      ))}
      <button
        onClick={handleNew}
        className="flex items-center justify-center h-7 w-7 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary/50 transition-colors shrink-0"
        title="New Session"
      >
        <Plus className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
