// hooks/useProgress.ts

import { useEffect, useState, useRef, useCallback } from 'react';
import { useResearchStore } from '@/store/useResearchStore';
import { sseManager } from '@/lib/sse';
import { api } from '@/lib/api';
import type { SSEMessage, ProgressData, PhaseData, CompleteData, Phase, ChatResponseData, ChatTokenData, ChatThinkingData, AgentMessageData, QualityResultEventData, SectionQualityEventData, PreviewRefreshEventData, QualityConfirmedEventData, ReportContextEventData } from '@/types/api';
import { useSessionStore } from '@/store/useSessionStore';
import { normalizeProgress } from '@/lib/progress';

export interface UseProgressOptions {
  onChatResponse?: (data: ChatResponseData) => void;
  onAgentMessage?: (data: AgentMessageData) => void;
}

const POLL_INTERVAL_MS = 5000;
const STUCK_TIMEOUT_MS = 60000;

export function applyStatusToStore(
  status: string,
  progress: number,
  store: ReturnType<typeof useResearchStore.getState>,
  phases?: Array<{ id: string; name: string; status: string; progress: number }>
) {
  const normalizedProgress = normalizeProgress(progress);
  switch (status) {
    case 'completed':
      store.setStatus('completed');
      store.setProgress(1);
      if (phases) {
        phases.forEach((p) => store.updatePhase(p.id, { status: p.status as Phase['status'], progress: normalizeProgress(p.progress) }));
      }
      break;
    case 'error':
      store.setStatus('error');
      break;
    case 'running':
    case 'resuming':
      store.setProgress(normalizedProgress);
      store.setStatus('running');
      if (phases) {
        phases.forEach((p) => store.updatePhase(p.id, { status: p.status as Phase['status'], progress: normalizeProgress(p.progress) }));
      }
      break;
    case 'pausing':
      // The UI intentionally exposes only running/paused. Keep the
      // transitional backend state visible as paused instead of inventing a
      // third user-facing status.
      store.setStatus('paused');
      if (normalizedProgress > 0) {
        store.setProgress(normalizedProgress);
      }
      break;
    case 'paused':
    case 'cancelled':
      // Paused: preserve phases, update progress only
      store.setStatus('paused');
      if (normalizedProgress > 0) {
        store.setProgress(normalizedProgress);
      }
      if (phases && phases.length > 0) {
        phases.forEach((p) => store.updatePhase(p.id, { status: p.status as Phase['status'], progress: normalizeProgress(p.progress) }));
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
      // An old EventSource may deliver one final event after unsubscribe.
      // Never apply it after the user has switched to another session.
      const activeId = useSessionStore.getState().activeId;
      if (!activeId || activeId !== taskId) return;
      lastProgressTimeRef.current = Date.now();
      switch (message.event) {
        case 'chat_response':
          if (onChatResponseRef.current) {
            onChatResponseRef.current(message.data as unknown as ChatResponseData);
          }
          break;
        case 'progress': {
          const d = message.data as ProgressData;
          setProgress(normalizeProgress(d.progress));
          if (useResearchStore.getState().status !== 'paused') {
            updatePhase(d.phase_id, { progress: d.progress });
          }
          break;
        }
        case 'phase_start': {
          const d = message.data as PhaseData;
          if (useResearchStore.getState().status !== 'paused') {
            updatePhase(d.phase_id, {
              status: 'running',
              name: d.phase_name || d.phase_id,
              description: d.description || '',
            });
          }
          break;
        }
        case 'phase_complete':
          if (useResearchStore.getState().status !== 'paused') {
            updatePhase((message.data as PhaseData).phase_id, { status: 'completed', progress: 100 });
          }
          break;
        case 'complete': {
          const d = message.data as CompleteData;
          setStatus('completed');
          setProgress(1);
          setStatistics(d.statistics);
          break;
        }
        case 'error':
          if (useResearchStore.getState().status !== 'idle') {
            setStatus('error');
          }
          break;
        case 'cancelled':
          // A stopped research keeps its checkpoint and is recoverable. Do
          // not turn it into idle, which hides the resume affordance.
          setStatus('paused');
          break;
        case 'paused':
          setStatus('paused');
          break;
        case 'resumed':
          setStatus('running');
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
    const shouldPoll = store.status === 'running'
      || store.status === 'paused'
      || (store.status === 'idle' && !!taskId);

    if (!shouldPoll) return;

    const doPoll = async (tid: string) => {
      try {
        const res = await api.getResearchStatus(tid);
        const s = useResearchStore.getState();
        if (s.taskId !== tid || useSessionStore.getState().activeId !== tid) return;
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
        const activeId = useSessionStore.getState().activeId;
        const current = useResearchStore.getState();
        if (activeId !== taskId || current.taskId !== taskId) return;
        applyStatusToStore(res.status, res.progress, current, res.phases);
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
  onReportContext?: (data: ReportContextEventData) => void;
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
  const onReportContext = typeof options === 'function' ? undefined : options?.onReportContext;

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
  const onReportContextRef = useRef(onReportContext);
  onReportContextRef.current = onReportContext;

  useEffect(() => {
    if (!sessionId) return;

    // Protect every consumer from queued events arriving after a session
    // switch or unsubscribe.
    const isCurrentSessionEvent = (data: { session_id?: string }) =>
      data.session_id === sessionId && useSessionStore.getState().activeId === sessionId;

    const unsub = sseManager.subscribeSession(
      sessionId,
      (data) => { if (isCurrentSessionEvent(data) && onChatResponseRef.current) onChatResponseRef.current(data); },
      onAgentMessage ? (data) => { if (isCurrentSessionEvent(data) && onAgentMessageRef.current) onAgentMessageRef.current(data); } : undefined,
      onChatToken ? (data) => { if (isCurrentSessionEvent(data) && onChatTokenRef.current) onChatTokenRef.current(data); } : undefined,
      onChatThinking ? (data) => { if (isCurrentSessionEvent(data) && onChatThinkingRef.current) onChatThinkingRef.current(data); } : undefined,
      onQualityResult ? (data) => { if (isCurrentSessionEvent(data) && onQualityResultRef.current) onQualityResultRef.current(data); } : undefined,
      onSectionQuality ? (data) => { if (isCurrentSessionEvent(data) && onSectionQualityRef.current) onSectionQualityRef.current(data); } : undefined,
      onPreviewRefresh ? (data) => { if (isCurrentSessionEvent(data) && onPreviewRefreshRef.current) onPreviewRefreshRef.current(data); } : undefined,
      onQualityConfirmed ? (data) => { if (isCurrentSessionEvent(data) && onQualityConfirmedRef.current) onQualityConfirmedRef.current(data); } : undefined,
      onReportContext ? (data) => {
        if (!isCurrentSessionEvent(data)) return;
        useSessionStore.getState().applyReportContext(data.snapshot);
        if (onReportContextRef.current) onReportContextRef.current(data);
      } : (data) => {
        if (!isCurrentSessionEvent(data)) return;
        useSessionStore.getState().applyReportContext(data.snapshot);
      },
    );

    return () => {
      unsub();
    };
  }, [sessionId]);
}
