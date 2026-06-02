// components/layout/MainLayout.tsx

'use client';

import { useState, useCallback } from 'react';
import { Header } from './Header';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { DocumentPreview } from '@/components/preview/DocumentPreview';
import { QualityPanel } from '@/components/quality/QualityPanel';
import { Eye, EyeOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useSessionStore } from '@/store/useSessionStore';
import { useSessionStream } from '@/hooks/useProgress';
import type { QualityResultEventData, QualityConfirmedEventData, QualityStateData } from '@/types/api';

export function MainLayout() {
  const [previewVisible, setPreviewVisible] = useState(true);

  const activeId = useSessionStore((s) => s.activeId);
  const session = useSessionStore((s) => activeId ? s.sessions[activeId] : null);
  const showQualityPanel = !!session?.qualityState && session.qualityState.phase !== 'confirmed';

  // Always subscribe to quality_result SSE so qualityState updates
  // even when DocumentPreview is not mounted (preview hidden)
  useSessionStream(activeId, {
    onQualityResult: (data: QualityResultEventData) => {
      if (data.session_id === activeId) {
        useSessionStore.getState().syncActive({
          qualityState: {
            ...data,
            phase: (data.phase as QualityStateData['phase']) || 'reviewing',
            version_stack: data.version_stack || [],
            current_version: data.current_version,
          },
        });
      }
    },
    onQualityConfirmed: (data: QualityConfirmedEventData) => {
      if (data.session_id === activeId) {
        const current = useSessionStore.getState().sessions[activeId!]?.qualityState;
        if (current) {
          useSessionStore.getState().syncActive({
            qualityState: { ...current, phase: 'confirmed' },
          });
        }
      }
    },
  });

  const onTogglePreview = useCallback(() => {
    setPreviewVisible(v => !v);
  }, []);

  return (
    <div className="flex flex-1 flex-col bg-background overflow-hidden min-h-0">
      <Header onTogglePreview={onTogglePreview} previewVisible={previewVisible} />

      <div className="flex flex-1 min-h-0">
        <div className={`${previewVisible ? '' : 'flex-1'} min-w-0 overflow-hidden ${previewVisible ? 'flex-1 w-1/2' : ''}`}>
          <ChatPanel />
        </div>

        {previewVisible && <div className="w-px bg-border shrink-0" />}

        {previewVisible && (
          <div className="flex-1 w-1/2 min-w-0 overflow-hidden relative">
            <DocumentPreview />
            <Button
              variant="ghost"
              size="sm"
              onClick={onTogglePreview}
              className="absolute top-2 right-2 h-7 w-7 p-0 rounded-lg z-10 opacity-60 hover:opacity-100"
              title="Close preview"
            >
              <EyeOff className="h-3.5 w-3.5" />
            </Button>
          </div>
        )}

        {showQualityPanel && <div className="w-px bg-border shrink-0" />}
        {showQualityPanel && <QualityPanel />}
      </div>
    </div>
  );
}
