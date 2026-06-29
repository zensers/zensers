// hooks/useProgress.ts

import { useEffect, useState, useRef, useCallback } from 'react';
import { useResearchStore } from '@/store/useResearchStore';
import { sseManager } from '@/lib/sse';
import { api } from '@/lib/api';
import type { SSEMessage, ProgressData, PhaseData, CompleteData, Phase, ChatResponseData, ChatTokenData, ChatThinkingData, AgentMessageData, QualityResultEventData, SectionQualityEventData, PreviewRefreshEventData, QualityConfirmedEventData } from '@/types/api';

export interface UseProgressOptions {
  onChatResponse?: (data: ChatResponseData) => void;
  onAgentMessage?: (data: AgentMessageData) => void;
}

const POLL_INTERVAL_MS = 5000;
const STUCK_TIMEOUT_MS = 60000;

function applyStatusToStore(
  status: string,
  progress: number,
  store: ReturnType<typeof useResearchStore.getState>,
  phases?: Array<{ id: string; name: string; status: string; progress: number }>
) {
  switch (status) {
    case 'completed':
      store.setStatus('completed');
      store.setProgress(100);
      if (phases) {
        phases.forEach((p) => store.updatePhase(p.id, { status: p.status as Phase['status'], progress: p.progress }));
      }
      break;
    case 'error':
      store.setStatus('error');
      break;
    case 'running':
      store.setProgress(progress);
      store.setStatus('running');
      if (phases) {
        phases.forEach((p) => store.updatePhase(p.id, { status: p.status as Phase['status'], progress: p.progress }));
      }
      break;
    case 'paused':
      // Paused: preserve phases, update progress only
      store.setStatus('paused');
      if (progress > 0) {
        store.setProgress(progress);
      }
      if (phases && phases.length > 0) {
        phases.forEach((p) => store.updatePhase(p.id, { status: p.status as Phase['status'], progress: p.progress }));
      }
      break;
  }
}

export function useProgress(taskId: string | null, options?: UseProgressOptions) {
  const { setProgress, updatePhase, setStatus, setStatistics } = useResearchStore();
  const [isConnected, setIsConnected] = useState(false);
  const { onChatResponse, onAgentMessage } = options || {};

  const onChatResponseRef = useRef(onChatResponse);
  onChatResponseRef.current = onChatResponse;
  const onAgentMessageRef = useRef(onAgentMessage);
  onAgentMessageRef.current = onAgentMessage;

  const lastProgressTimeRef = useRef<number>(Date.now());
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const stuckTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current !== null) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  // SSE subscription — stable by taskId only
  useEffect(() => {
    if (!taskId) {
      lastProgressTimeRef.current = Date.now();
      return;
    }

    const handleMessage = (message: SSEMessage) => {
      lastProgressTimeRef.current = Date.now();
      switch (message.event) {
        case 'chat_response':
          if (onChatResponseRef.current) {
            onChatResponseRef.current(message.data as unknown as ChatResponseData);
          }
          break;
        case 'progress': {
          const d = message.data as ProgressData;
          setProgress(d.progress);
          updatePhase(d.phase_id, { progress: d.progress });
          break;
        }
        case 'phase_start': {
          const d = message.data as PhaseData;
          updatePhase(d.phase_id, {
            status: 'running',
            name: d.phase_name || d.phase_id,
            description: d.description || '',
          });
          break;
        }
        case 'phase_complete':
          updatePhase((message.data as PhaseData).phase_id, { status: 'completed', progress: 100 });
          break;
        case 'complete': {
          const d = message.data as CompleteData;
          setStatus('completed');
          setProgress(100);
          setStatistics(d.statistics);
          break;
        }
        case 'error':
          // Guard against race: if status was already reset to 'idle' by handleSend,
          // don't override with 'error' from a late SSE event
          if (useResearchStore.getState().status !== 'idle') {
            setStatus('error');
          }
          break;
        case 'cancelled':
          setStatus('idle');
          break;
        case 'agent_message':
          if (onAgentMessageRef.current) {
            onAgentMessageRef.current(message.data as AgentMessageData);
          }
          break;
      }
    };

    const handleConnection = (connected: boolean) => {
      setIsConnected(connected);
    };

    const unsubscribe = sseManager.subscribe(taskId, handleMessage, handleConnection);

    return () => {
      stopPolling();
      unsubscribe();
      lastProgressTimeRef.current = Date.now();
    };
  }, [taskId, setProgress, updatePhase, setStatus, setStatistics, stopPolling]);

  // Polling fallback — activated when SSE disconnects and status is 'running'
  useEffect(() => {
    stopPolling();

    if (!taskId) return;
    if (isConnected) return; // SSE is alive, no need to poll

    const store = useResearchStore.getState();
    // Poll for running AND paused tasks (paused may turn back to running on resume)
    if (store.status !== 'running' && store.status !== 'paused') return;

    const doPoll = async (tid: string) => {
      try {
        const res = await api.getResearchStatus(tid);
        const s = useResearchStore.getState();
        if (s.taskId !== tid) return;
        applyStatusToStore(res.status, res.progress, s, res.phases);
      } catch {
        // Network error during polling — ignore
      }
    };

    doPoll(taskId);
    pollTimerRef.current = setInterval(() => doPoll(taskId!), POLL_INTERVAL_MS);

    return stopPolling;
  }, [taskId, isConnected, stopPolling]);

  // Stuck detection — SSE connected but no progress for STUCK_TIMEOUT_MS
  useEffect(() => {
    if (stuckTimerRef.current !== null) {
      clearInterval(stuckTimerRef.current);
      stuckTimerRef.current = null;
    }
    if (!taskId || !isConnected) return;

    stuckTimerRef.current = setInterval(() => {
      if (useResearchStore.getState().status !== 'running') return;
      if (Date.now() - lastProgressTimeRef.current <= STUCK_TIMEOUT_MS) return;

      api.getResearchStatus(taskId!).then((res) => {
        applyStatusToStore(res.status, res.progress, useResearchStore.getState(), res.phases);
      }).catch(() => {});
    }, POLL_INTERVAL_MS);

    return () => {
      if (stuckTimerRef.current !== null) {
        clearInterval(stuckTimerRef.current);
        stuckTimerRef.current = null;
      }
    };
  }, [taskId, isConnected]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopPolling();
      if (stuckTimerRef.current !== null) {
        clearInterval(stuckTimerRef.current);
      }
    };
  }, [stopPolling]);

  return { isConnected };
}


// ============ Session Stream Hook ============

/**
 * Subscribe to persistent session SSE stream.
 *
 * Unlike useProgress (which tracks task progress and closes on complete),
 * useSessionStream stays alive for the entire session.
 * Used for receiving chat_response and agent_message events.
 *
 * @param sessionId Session ID
 * @param onChatResponse Callback for chat_response events
 */
export interface UseSessionStreamOptions {
  onChatResponse?: (data: ChatResponseData) => void;
  onChatToken?: (data: ChatTokenData) => void;
  onChatThinking?: (data: ChatThinkingData) => void;
  onAgentMessage?: (data: AgentMessageData) => void;
  onQualityResult?: (data: QualityResultEventData) => void;
  onSectionQuality?: (data: SectionQualityEventData) => void;
  onPreviewRefresh?: (data: PreviewRefreshEventData) => void;
  onQualityConfirmed?: (data: QualityConfirmedEventData) => void;
}

export function useSessionStream(
  sessionId: string | null,
  options?: UseSessionStreamOptions | ((data: ChatResponseData) => void),
) {
  const onChatResponse = typeof options === 'function' ? options : options?.onChatResponse;
  const onChatToken = typeof options === 'function' ? undefined : options?.onChatToken;
  const onChatThinking = typeof options === 'function' ? undefined : options?.onChatThinking;
  const onAgentMessage = typeof options === 'function' ? undefined : options?.onAgentMessage;
  const onQualityResult = typeof options === 'function' ? undefined : options?.onQualityResult;
  const onSectionQuality = typeof options === 'function' ? undefined : options?.onSectionQuality;
  const onPreviewRefresh = typeof options === 'function' ? undefined : options?.onPreviewRefresh;
  const onQualityConfirmed = typeof options === 'function' ? undefined : options?.onQualityConfirmed;

  const onChatResponseRef = useRef(onChatResponse);
  onChatResponseRef.current = onChatResponse;
  const onChatTokenRef = useRef(onChatToken);
  onChatTokenRef.current = onChatToken;
  const onChatThinkingRef = useRef(onChatThinking);
  onChatThinkingRef.current = onChatThinking;
  const onAgentMessageRef = useRef(onAgentMessage);
  onAgentMessageRef.current = onAgentMessage;
  const onQualityResultRef = useRef(onQualityResult);
  onQualityResultRef.current = onQualityResult;
  const onSectionQualityRef = useRef(onSectionQuality);
  onSectionQualityRef.current = onSectionQuality;
  const onPreviewRefreshRef = useRef(onPreviewRefresh);
  onPreviewRefreshRef.current = onPreviewRefresh;
  const onQualityConfirmedRef = useRef(onQualityConfirmed);
  onQualityConfirmedRef.current = onQualityConfirmed;

  useEffect(() => {
    if (!sessionId) return;

    const unsub = sseManager.subscribeSession(
      sessionId,
      (data) => { if (onChatResponseRef.current) onChatResponseRef.current(data); },
      onAgentMessage ? (data) => { if (onAgentMessageRef.current) onAgentMessageRef.current(data); } : undefined,
      onChatToken ? (data) => { if (onChatTokenRef.current) onChatTokenRef.current(data); } : undefined,
      onChatThinking ? (data) => { if (onChatThinkingRef.current) onChatThinkingRef.current(data); } : undefined,
      onQualityResult ? (data) => { if (onQualityResultRef.current) onQualityResultRef.current(data); } : undefined,
      onSectionQuality ? (data) => { if (onSectionQualityRef.current) onSectionQualityRef.current(data); } : undefined,
      onPreviewRefresh ? (data) => { if (onPreviewRefreshRef.current) onPreviewRefreshRef.current(data); } : undefined,
      onQualityConfirmed ? (data) => { if (onQualityConfirmedRef.current) onQualityConfirmedRef.current(data); } : undefined,
    );

    return () => {
      unsub();
    };
  }, [sessionId]);
}
