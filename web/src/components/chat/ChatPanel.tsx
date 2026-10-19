// components/chat/ChatPanel.tsx

'use client';

import { useRef, useEffect, useState, useCallback } from 'react';
import type { ReactNode } from 'react';
import type { AgentMessageData, ChatMessage as ChatMessageType, ChatTokenData, ChatThinkingData, SelectOption } from '@/types/api';
import { nanoid } from 'nanoid';
import { useChatStore } from '@/store/useChatStore';
import { useResearchStore } from '@/store/useResearchStore';
import { useSessionStore } from '@/store/useSessionStore';
import { useResearch } from '@/hooks/useResearch';
import { useProgress, useSessionStream } from '@/hooks/useProgress';
import type { ChatResponseData } from '@/types/api';
import { ChatInput } from './ChatInput';
import { OptionSelector } from './OptionSelector';
import { SectionSelector } from './SectionSelector';
import { DynamicParameterForm } from './DynamicParameterForm';
// ProgressPanel removed — agent progress shown via inline agent_message events
import { SearchIndicator } from './SearchIndicator';
// ResearchStatusBar removed — 进度/框架信息与对话流重复且挤压对话区（用户裁决移除）；
// 生命周期事件仍以系统消息形式存在于对话历史，实时活动见 AgentActivityBar。
import { VirtualMessageList } from './VirtualMessageList';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';
import { ArrowDown, Brain, CheckCircle2, ChevronDown, Loader2, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { parseTemplateCommand, RESEARCH_TEMPLATES, formatTemplateMessage, formatTemplateList, formatTemplateNotFound, extractTemplateKeyword } from '@/lib/templates';
import { normalizeChatMessage, isStructuredMessagePrefix } from '@/lib/normalize-message';
import { isInternalChatMessage } from '@/lib/chat-message-utils';
import { hasMeaningfulChatResponse, shouldClearWaitingForStatus, shouldTrackResponseId } from '@/lib/chat-response-utils';

type AgentActivity = AgentMessageData & { completedCount?: number; totalCount?: number };

function cleanAgentActivityText(content: string) {
  return content
    .replace(/&#x([0-9a-f]+);/gi, (_, code) => String.fromCodePoint(parseInt(code, 16)))
    .replace(/^\*\*[^*]+\*\*:?\s*/i, '')
    .trim();
}

/**
 * 可折叠建议卡：默认展开，一键收起为细条，不再遮挡历史对话；
 * 展开时限高滚动（38vh），保证消息列表始终可见可翻。
 */
function CollapsibleSuggestionsCard({ title, optionsCount, children }: {
  title: string;
  optionsCount: number;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(true);
  return (
    <div className="apple-card overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-secondary/50 transition-colors"
      >
        <span className="text-xs font-semibold text-primary uppercase tracking-wider">
          {title}{optionsCount > 0 ? ` · ${optionsCount}` : ''}
        </span>
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          {open ? '收起' : '展开选项'}
          <ChevronDown className={cn('h-4 w-4 transition-transform duration-200', open && 'rotate-180')} />
        </span>
      </button>
      {open && (
        <div className="max-h-[38vh] overflow-y-auto px-1.5 pb-2">
          {children}
        </div>
      )}
    </div>
  );
}

function AgentActivityBar({ activities }: { activities: AgentActivity[] }) {
  const [showAll, setShowAll] = useState(false);
  if (activities.length === 0) return null;
  // 研究时 agent 活动随阶段增长，默认只展示最近 3 条，避免状态堆栈挤压对话区
  const VISIBLE = 3;
  const visible = showAll ? activities : activities.slice(-VISIBLE);
  const hidden = activities.length - visible.length;
  return (
    <div className="mx-4 mt-2 space-y-1.5" aria-live="polite" aria-label="Agent activity">
      {hidden > 0 && !showAll && (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="w-full text-left px-3 py-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
        >
          ↑ 还有 {hidden} 条更早的 Agent 活动，点击展开
        </button>
      )}
      {visible.map((activity) => {
        const Icon = activity.action === 'completed' ? CheckCircle2 : activity.action === 'error' ? XCircle : Loader2;
        const tone = activity.action === 'completed'
          ? 'text-green-600 border-green-200 bg-green-50'
          : activity.action === 'error'
            ? 'text-red-600 border-red-200 bg-red-50'
            : 'text-blue-600 border-blue-200 bg-blue-50';
        return (
          <div key={activity.agent_id} className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs ${tone}`}>
            <Icon className={`h-3.5 w-3.5 shrink-0 ${activity.action === 'searching' || activity.action === 'analyzing' ? 'animate-spin' : ''}`} />
            <span className="font-medium whitespace-nowrap">{activity.agent_name}：</span>
            <span className="min-w-0 truncate">{cleanAgentActivityText(activity.content)}</span>
          </div>
        );
      })}
      {activities.length > VISIBLE && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="w-full text-left px-3 py-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
        >
          {showAll ? '收起 Agent 活动' : `共 ${activities.length} 项 Agent 活动，点击展开全部`}
        </button>
      )}
    </div>
  );
}

export function ChatPanel() {
  const { messages, addMessage, updateMessage, appendStreamToken } = useChatStore();
  const {
    currentStep,
    stepOptions,
    parameterConfig,
    taskId,
    status,
    summary,
    framework,
    reset,
    phases,
    progress,
  } = useResearchStore();
  const {
    sessionId,
    startResearch,
    quickStartResearch,
    sendMessage,
    handleOptionSelect,
    selectSections,
    setParameters,
    confirmResearch,
    isProcessing,
    isNetworkBusy,
    isWaitingForReply,
    setIsWaitingForReply,
    stopCurrentResponse,
  } = useResearch();
  const activeSessionLanguage = useSessionStore((s) =>
    s.activeId ? s.sessions[s.activeId]?.language : undefined
  );
  const reportContext = useSessionStore((s) =>
    s.activeId ? s.sessions[s.activeId]?.reportContext : null
  );
  const isRestoringSession = useSessionStore((s) => s.isRestoring);

  // Research progress stream (closes on task complete)
  const sseId = sessionId || taskId;
  const { isConnected } = useProgress(sseId);

  // Tracks the currently streaming message ID for token-by-token updates
  const streamingMsgIdRef = useRef<string | null>(null);
  const streamingDoneRef = useRef(false);
  const streamingTokenBufferRef = useRef('');
  const handledResponseIdsRef = useRef<Set<string>>(new Set());

  const searchStateTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const [agentActivities, setAgentActivities] = useState<AgentActivity[]>([]);
  const [controlBusy, setControlBusy] = useState(false);

  // Persistent session stream (stays alive, unaffected by task complete)
  // Receives chat_response + chat_token + agent_message events
  useSessionStream(sessionId, {
    onChatToken: (data: ChatTokenData) => {
      const storeSessionId = useSessionStore.getState().activeId;
      const matches = !!storeSessionId && data.session_id === storeSessionId;
      if (!matches) return;
      if (streamingDoneRef.current) return;

      streamingTokenBufferRef.current += data.token;
      const tokenText = streamingTokenBufferRef.current.trimStart();
      if (isStructuredMessagePrefix(tokenText)) return;

      if (!streamingMsgIdRef.current) {
        streamingMsgIdRef.current = nanoid();
        addMessage({
          id: streamingMsgIdRef.current,
          role: 'assistant',
          content: data.token,
          timestamp: new Date().toISOString(),
          metadata: { status: 'streaming' },
        });
      } else {
        const currentMsg = useChatStore.getState().messages.find(m => m.id === streamingMsgIdRef.current);
        if (currentMsg?.metadata?.status === 'thinking') {
          updateMessage(streamingMsgIdRef.current, { metadata: { status: 'streaming' } });
        }
        appendStreamToken(streamingMsgIdRef.current, data.token, '');
      }
    },
    onChatThinking: (data: ChatThinkingData) => {
      const storeSessionId = useSessionStore.getState().activeId;
      const matches = !!storeSessionId && data.session_id === storeSessionId;
      if (!matches) return;
      if (streamingDoneRef.current) return;

      if (!streamingMsgIdRef.current) {
        streamingMsgIdRef.current = nanoid();
        addMessage({
          id: streamingMsgIdRef.current,
          role: 'assistant',
          content: '',
          thinkingContent: data.token,
          timestamp: new Date().toISOString(),
          metadata: { status: 'thinking' },
        });
      } else {
        const currentMsg = useChatStore.getState().messages.find(m => m.id === streamingMsgIdRef.current);
        if (currentMsg?.metadata?.status === 'streaming') {
          updateMessage(streamingMsgIdRef.current, { metadata: { status: 'thinking' } });
        }
        appendStreamToken(streamingMsgIdRef.current, '', data.token);
      }
    },
    onChatResponse: (data) => {
      const storeSessionId = useSessionStore.getState().activeId;
      const matches = !!storeSessionId && data.session_id === storeSessionId;
      if (!matches) return;

      if (streamingDoneRef.current) return;

      const existingAssistantMsg = useChatStore.getState().messages.find(
        m => m.role === 'assistant' && m.timestamp === data.timestamp
      );
      if (existingAssistantMsg) return;

      const finalContent = normalizeChatMessage(data.message);
      let finalThinking: string | undefined = data.thinking_content;

      // A transport/ack event can be labelled chat_response while carrying no
      // LLM text. It must not end the waiting indicator or finalize an empty
      // assistant bubble; keep the request visibly pending until real text,
      // an error, cancellation, or the existing timeout arrives.
      const currentStreamingMessage = streamingMsgIdRef.current
        ? useChatStore.getState().messages.find((message) => message.id === streamingMsgIdRef.current)
        : undefined;
      if (!hasMeaningfulChatResponse(finalContent)
        && !hasMeaningfulChatResponse(currentStreamingMessage?.content)) {
        useResearchStore.getState().setSearchState('searching');
        return;
      }

      // Do not let an empty transport acknowledgement reserve the id of the
      // real response that follows it.
      if (shouldTrackResponseId(data.response_id, finalContent, finalThinking, currentStreamingMessage?.content)) {
        if (handledResponseIdsRef.current.has(data.response_id)) return;
        handledResponseIdsRef.current.add(data.response_id);
      }

      // Do not replace a valid streamed answer with an empty terminal event.
      const resolvedContent = hasMeaningfulChatResponse(finalContent)
        ? finalContent
        : currentStreamingMessage?.content || '';

      if (streamingMsgIdRef.current) {
        updateMessage(streamingMsgIdRef.current, {
          content: resolvedContent,
          ...(finalThinking !== undefined ? { thinkingContent: finalThinking } : {}),
          metadata: {
            status: 'done',
            ...(data.response_id ? { responseId: data.response_id } : {}),
          },
        });
        streamingMsgIdRef.current = null;
        streamingDoneRef.current = true;
      } else {
        addMessage({
          id: nanoid(),
          role: 'assistant',
          content: finalContent,
          ...(finalThinking !== undefined ? { thinkingContent: finalThinking } : {}),
          timestamp: data.timestamp || new Date().toISOString(),
          ...(data.response_id ? { metadata: { responseId: data.response_id, status: 'done' } } : {}),
        });
        streamingDoneRef.current = true;
      }
      streamingTokenBufferRef.current = '';

      // Agent/tool notifications are transient UI state. They must never be
      // inserted into the persisted conversation timeline.
      setAgentActivities([]);

      setIsWaitingForReply(false);

      const mode = (data as any).mode || 'chat';
      const action = data.action || 'continue_chat';

      if (mode === 'framework') {
        useResearchStore.getState().setStatus('idle');
        useResearchStore.getState().setStep(0, data.suggestions || []);
        if ((data as any).framework) {
          useResearchStore.getState().setFramework((data as any).framework);
        } else {
          api.getResearchDetail(data.session_id).then((detail) => {
            if (detail.framework) {
              useResearchStore.getState().setFramework(detail.framework);
            }
          }).catch(() => {});
        }
      } else if (mode === 'research' && (data as any).step === 6) {
        useResearchStore.getState().setTaskId(data.session_id);
        useResearchStore.getState().setStatus('running');
        useResearchStore.getState().setStep(6, undefined);
      } else if (action === 'enter_framework') {
        useResearchStore.getState().setStatus('idle');
        useResearchStore.getState().setStep(0, data.suggestions || []);
        if ((data as any).framework) {
          useResearchStore.getState().setFramework((data as any).framework);
        } else {
          api.getResearchDetail(data.session_id).then((detail) => {
            if (detail.framework) {
              useResearchStore.getState().setFramework(detail.framework);
            }
          }).catch(() => {});
        }
      } else if (action === 'start_execution' || action === 'start_research') {
        useResearchStore.getState().setStatus('running');
        useResearchStore.getState().setStep(6, undefined);
      } else {
        if (data.suggestions && data.suggestions.length > 0) {
          useResearchStore.getState().setStep(0, data.suggestions);
        }
      }

      useResearchStore.getState().setSearchState('completed');
      const rs = useResearchStore.getState();
      if (rs.status !== 'running') {
        setIsWaitingForReply(false);
      }
      clearTimeout(searchStateTimerRef.current);
      searchStateTimerRef.current = setTimeout(() => {
        useResearchStore.getState().setSearchState('idle');
      }, 2000);
    },
    onAgentMessage: (data: AgentMessageData) => {
      const storeSessionId = useSessionStore.getState().activeId;
      if (storeSessionId && data.session_id === storeSessionId) {
        if (data.action === 'heartbeat') {
          const progressMatch = data.content.match(/\((\d+)%\s*complete\)/);
          if (progressMatch) {
            const pct = parseInt(progressMatch[1], 10) / 100;
            const rs = useResearchStore.getState();
            if (rs.status === 'running' && pct > rs.progress) {
              rs.setProgress(pct);
            }
          }
          return;
        }
        setAgentActivities((current) => {
          const isCompleted = data.action === 'completed';
          const existing = current.find((item) => item.agent_id === data.agent_id);
          const completedCount = (existing?.completedCount || 0) + (isCompleted ? 1 : 0);
          const totalCount = Math.max(existing?.totalCount || 0, completedCount);
          const next: AgentActivity = {
            ...data,
            completedCount,
            totalCount,
          };
          return existing
            ? current.map((item) => item.agent_id === data.agent_id ? next : item)
            : [...current, next];
        });
      }
    },
  });

  useEffect(() => {
    setAgentActivities([]);
  }, [sessionId]);

  // Cleanup timer on unmount (Oracle MAJOR)
  useEffect(() => {
    return () => {
      clearTimeout(searchStateTimerRef.current);
    };
  }, []);

  // Infinite scroll: load older messages on scroll-to-top
  const [hasMoreMessages, setHasMoreMessages] = useState(true);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const serverOffsetRef = useRef(0);

  const loadOlderMessages = useCallback(async () => {
    if (isLoadingMessages || !hasMoreMessages) return;
    const store = useSessionStore.getState();
    const activeId = store.activeId;
    if (!activeId) return;

    setIsLoadingMessages(true);
    try {
      const result = await api.getMessages(activeId, serverOffsetRef.current, 50);
      if (result.messages.length === 0) {
        setHasMoreMessages(false);
      } else {
        const currentIds = new Set(useChatStore.getState().messages.map(m => m.id));
          const olderMsgs: ChatMessageType[] = result.messages
            .filter((m: any) => !currentIds.has(m.id))
            .filter((m: any) => !isInternalChatMessage(m))
            .map((m: any) => ({
            id: m.id || nanoid(),
            role: (m.role === 'user' || m.role === 'assistant' || m.role === 'agent'
              ? m.role
              : 'system') as ChatMessageType['role'],
            content: normalizeChatMessage(m.content),
            timestamp: m.timestamp || new Date().toISOString(),
            ...(m.response_id ? { metadata: { responseId: m.response_id } } : {}),
            ...(m.agent_id || m.agent_name || m.action ? {
              agent: {
                id: m.agent_id || '',
                name: m.agent_name || '',
                action: m.action || '',
                completedCount: m.completedCount,
                totalCount: m.totalCount,
                provider: m.provider,
                quality_score: m.quality_score,
                cache_hit: m.cache_hit,
                stop_reason: m.stop_reason,
              },
            } : {}),
          }));
        if (olderMsgs.length > 0) {
          useChatStore.getState().prependMessages(olderMsgs);
        }
        serverOffsetRef.current = result.offset + result.messages.length;
        if (!result.has_more) {
          setHasMoreMessages(false);
        }
      }
    } catch (e) {
      console.error('Failed to load older messages:', e);
    } finally {
      setIsLoadingMessages(false);
    }
  }, [isLoadingMessages, hasMoreMessages]);

  const activeSessionId = useSessionStore((s) => s.activeId);

  useEffect(() => {
    streamingMsgIdRef.current = null;
    streamingDoneRef.current = false;
    streamingTokenBufferRef.current = '';
    // Response ids are scoped to a session; do not carry dedup state across
    // conversations and suppress a valid response in the new session.
    handledResponseIdsRef.current.clear();
  }, [activeSessionId]);

  useEffect(() => {
    const hasHeartbeat = messages.some(m => m.role === 'agent' && (m.agent?.action === 'heartbeat' || (m as any).action === 'heartbeat'));
    if (hasHeartbeat) {
      const cleaned = messages.filter(m => !(m.role === 'agent' && (m.agent?.action === 'heartbeat' || (m as any).action === 'heartbeat')));
      useChatStore.setState({ messages: cleaned });
      useSessionStore.getState().syncActive({ messages: cleaned });
    }
  }, [messages.length]);

  useEffect(() => {
    if (status === 'running' && !streamingMsgIdRef.current) {
      const hasAssistant = messages.some(m => m.role === 'assistant' && m.metadata?.status !== 'streaming' && m.metadata?.status !== 'thinking');
      if (!hasAssistant) {
        setIsWaitingForReply(true);
      }
    } else if (shouldClearWaitingForStatus(status)) {
      // `idle` is also the normal chat-mode status. Do not hide the waiting
      // indicator merely because the research state is idle while the LLM
      // response is still pending.
      setIsWaitingForReply(false);
    }
  }, [status, activeSessionId, messages.length]);

  useEffect(() => {
    const sessionMessages = useSessionStore.getState().sessions[activeSessionId ?? '']?.messages;
    if (sessionMessages) {
      serverOffsetRef.current = sessionMessages.length;
      setHasMoreMessages(sessionMessages.length > 0);
    } else {
      serverOffsetRef.current = 0;
      setHasMoreMessages(true);
    }
  }, [activeSessionId]);

  const scrollToBottomRef = useRef<(() => void) | null>(null);

  const [showScrollBtn, setShowScrollBtn] = useState(false);

  const handleAtBottomChange = useCallback((showButton: boolean) => {
    setShowScrollBtn(showButton);
  }, []);

  const scrollToBottom = useCallback(() => {
    scrollToBottomRef.current?.();
  }, []);

  useEffect(() => {
    const handleBeforeUnload = () => { useChatStore.getState().flushSyncNow(); };
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') useChatStore.getState().flushSyncNow();
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    window.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      window.removeEventListener('visibilitychange', handleVisibilityChange);
      useChatStore.getState().flushSyncNow();
    };
  }, []);

  // hasActiveResearch removed — ProgressPanel replaced by inline agent messages
  const isChatMode = currentStep === null || currentStep === 0;

  const handleSend = async (text: string, attachments?: File[], selectedModel?: string) => {
    // The visual input may not have re-rendered yet after a sidebar click.
    // Guard the command path with the authoritative store state as well.
    if (useSessionStore.getState().isRestoring) return;

    // Reset streaming state for new user message
    streamingMsgIdRef.current = null;
    streamingDoneRef.current = false;
    streamingTokenBufferRef.current = '';
    addMessage({
      id: nanoid(),
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    });

    // Parse /template command
    const { isTemplateCommand, templateId, remainingText } = parseTemplateCommand(text);

    if (isTemplateCommand) {
      // C6: template state cleanup inside the branch
      useResearchStore.getState().setActiveTemplate(null);
      useResearchStore.getState().setResearchTopic(null);

      if (!templateId) {
        // Bare /template — show available template list
        addMessage({
          id: nanoid(),
          role: 'assistant',
          content: formatTemplateList(),
          timestamp: new Date().toISOString(),
        });
        return;
      }

      const template = RESEARCH_TEMPLATES.find(t => t.id === templateId);
      if (template) {
        useResearchStore.getState().setActiveTemplate(template);

        if (remainingText) {
          useResearchStore.getState().setResearchTopic(remainingText);
          const msg = `我选择了 ${template.name} 模板研究：${remainingText}。模板章节包括：${template.sections.join('、')}。默认参数：${Object.entries(template.parameters).map(([k,v]) => `${k}=${v}`).join('，')}。请基于这个模板框架，用中文给出研究计划建议。`;
          const hasSession = !!(sessionId && useSessionStore.getState().sessions[sessionId]);
          try {
            if (hasSession) await sendMessage(msg);
            else await startResearch(msg);
          } catch (error) {
            console.error('Failed to start template chat:', error);
            useResearchStore.getState().setStep(0, []);
          }
        } else {
          addMessage({
            id: nanoid(), role: 'assistant',
            content: formatTemplateMessage(template),
            timestamp: new Date().toISOString(),
          });
          useResearchStore.getState().setStep(0, []);
        }
        return;
      }

      // Template not found
      const keyword = extractTemplateKeyword(text);
      addMessage({
        id: nanoid(),
        role: 'assistant',
        content: formatTemplateNotFound(keyword),
        timestamp: new Date().toISOString(),
      });
      return;
    }

    try {
      if (sessionId) {
        const data = await sendMessage(text);
        if (data && (data as any).status === 'processing') {
          const thinkingContent = (data as any).thinking_content;
          const processingMsg = (data as any).message;
          if (thinkingContent || processingMsg) {
            const msgId = nanoid();
            streamingMsgIdRef.current = msgId;
            addMessage({
              id: msgId,
              role: 'assistant',
              content: normalizeChatMessage(processingMsg || ''),
              ...(thinkingContent ? { thinkingContent } : {}),
              timestamp: new Date().toISOString(),
              metadata: { status: thinkingContent ? 'thinking' : 'streaming' },
            });
          }
          useResearchStore.getState().setSearchState('searching');
          return;
        }
      } else {
        const data = await startResearch(text, attachments, selectedModel);
        if (data && (data as any).status === 'processing') {
          const thinkingContent = (data as any).thinking_content;
          const processingMsg = (data as any).message;
          if (thinkingContent || processingMsg) {
            const msgId = nanoid();
            streamingMsgIdRef.current = msgId;
            addMessage({
              id: msgId,
              role: 'assistant',
              content: normalizeChatMessage(processingMsg || ''),
              ...(thinkingContent ? { thinkingContent } : {}),
              timestamp: new Date().toISOString(),
              metadata: { status: thinkingContent ? 'thinking' : 'streaming' },
            });
          }
          useResearchStore.getState().setSearchState('searching');
          return;
        }
      }
    } catch (error) {
      console.error('Failed to send message:', error);
      setIsWaitingForReply(false);
      addMessage({
        id: nanoid(),
        role: 'assistant',
        content: 'Sorry, failed to send message. Please check if the backend service is running properly.',
        timestamp: new Date().toISOString(),
      });
    }
  };

  const handlePauseResearch = async () => {
    if (!taskId || status !== 'running' || controlBusy) return;
    setControlBusy(true);
    try {
      const result = await api.pauseResearch(taskId);
      if (result.status === 'paused' || result.status === 'pausing') {
        // Preserve the server's intermediate state. Mapping `pausing` back to
        // `running` makes the UI suggest that the pause failed or never began.
        // Keep the public UI state deliberately binary: pausing is shown as
        // paused until the backend confirms the checkpoint is available.
        useResearchStore.getState().setStatus('paused');
        setIsWaitingForReply(false);
        if (result.status === 'paused') {
          addMessage({
            id: nanoid(),
            role: 'assistant',
            content: result.message || 'Research paused. Progress has been saved.',
            timestamp: new Date().toISOString(),
          });
        }
      } else {
        throw new Error(result.message || 'Pause request was not accepted');
      }
    } catch (e) {
      console.error('Failed to pause research:', e);
      addMessage({
        id: nanoid(),
        role: 'assistant',
        content: '暂停研究失败，任务仍在原状态运行，请稍后重试。',
        timestamp: new Date().toISOString(),
      });
    } finally {
      setControlBusy(false);
    }
  };

  const handleStopCurrentResponse = () => {
    stopCurrentResponse();
    useResearchStore.getState().setSearchState('idle');
    addMessage({
      id: nanoid(),
      role: 'assistant',
      content: '当前回复已停止。研究任务状态未改变。',
      timestamp: new Date().toISOString(),
    });
  };

  // Render step content (framework interaction steps 1-5)
  const renderStepContent = () => {
    if (isProcessing && !currentStep) {
      return (
        <div className="flex items-center justify-center py-8">
          <div className="flex items-center gap-3">
            <Brain className="h-5 w-5 animate-pulse text-purple-600" />
            <span className="text-sm text-purple-700">AI 正在思考...</span>
          </div>
        </div>
      );
    }

    if (isChatMode) {
      const tpl = useResearchStore.getState().activeTemplate;
      const topic = useResearchStore.getState().researchTopic;
      const baseOptions = stepOptions || [];
      const isZh = activeSessionLanguage
        ? activeSessionLanguage.toLowerCase().startsWith('zh')
        : /[\u4e00-\u9fff]/.test(topic || framework?.topic || '');

      if (framework && framework.sections && framework.sections.length > 0 && status === 'idle') {
        const frameworkOptions: SelectOption[] = framework.sections.map((s, i) => ({
          id: `section-${i}`,
          label: s,
          description: '',
          selected: true,
        }));

        return (
          <div className="space-y-3">
            <SectionSelector
              title={isZh ? '研究框架章节' : 'Research Framework Sections'}
              description={isZh
                ? `研究主题: ${framework.topic} — 选择要包含的章节`
                : `Topic: ${framework.topic} — Select sections to include`}
              sections={frameworkOptions}
              frameworkTree={framework.sections_tree}
              onConfirm={handleFrameworkSectionConfirm}
              disabled={isProcessing}
            />
            {baseOptions.length > 0 && (
              <div className="grid grid-cols-2 gap-2">
                {baseOptions.map((option) => (
                  <button
                    key={option.id}
                    onClick={() => handleOptionSelect(option.id, option.example)}
                    disabled={isProcessing}
                    className="bg-card border rounded-xl shadow-sm p-3 text-left hover:border-primary/50 transition-colors disabled:opacity-50"
                  >
                    <div className="font-medium text-sm text-foreground">{option.label}</div>
                    {option.example && (
                      <div className="text-xs text-muted-foreground mt-1">{option.example}</div>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        );
      }

      const enhancedOptions = (tpl && topic)
        ? [...baseOptions, {
            id: 'start_research',
            label: isZh ? '开始研究' : 'Start Research',
            example: isZh
              ? `使用定制后的 ${tpl.name} 开始研究`
              : `Start research with customized ${tpl.name}`,
            description: isZh ? '使用定制框架开始研究' : 'Use customized framework to start research',
          }]
        : baseOptions;

      if (enhancedOptions.length > 0) {
        return (
          <CollapsibleSuggestionsCard
            title={isZh ? '你可以选择' : 'You can choose'}
            optionsCount={enhancedOptions.length}
          >
            <div className="grid grid-cols-2 gap-2 pt-1">
              {enhancedOptions.map((option) => (
                <button
                  key={option.id}
                  onClick={() => handleOptionSelect(option.id, option.example)}
                  disabled={isProcessing}
                  className="bg-card border rounded-xl shadow-sm p-3 text-left hover:border-primary/50 transition-colors disabled:opacity-50"
                >
                  <div className="font-medium text-sm text-foreground">{option.label}</div>
                  {option.example && (
                    <div className="text-xs text-muted-foreground mt-1">{option.example}</div>
                  )}
                </button>
              ))}
            </div>
          </CollapsibleSuggestionsCard>
        );
      }
    }

    // ProgressPanel removed — agent progress shown via inline agent_message events

    if (stepOptions && !stepOptions.some((o) => o.required !== undefined) && currentStep !== 3 && currentStep !== 4) {
      if (currentStep === 5) {
        return (
          <OptionSelector
            title="Confirm Research Plan"
            description="Please confirm whether to start the research task"
            options={stepOptions}
            onSelect={(id) => handleConfirm(id === 'confirm')}
            disabled={isProcessing}
          />
        );
      }
      return (
        <OptionSelector
          title={currentStep === 1 ? 'Select Output Type' : 'Select Template'}
          options={stepOptions}
          onSelect={handleOptionSelect}
          disabled={isProcessing}
        />
      );
    }

    if (currentStep === 3 && stepOptions) {
      return (
        <SectionSelector
          sections={stepOptions}
          onConfirm={handleSectionConfirm}
          disabled={isProcessing}
        />
      );
    }

    if (currentStep === 4 && parameterConfig) {
      const params = Array.isArray(parameterConfig)
        ? parameterConfig
        : (parameterConfig as any)?.parameters || [];
      return (
        <DynamicParameterForm
          parameters={params}
          onSubmit={handleParameterSubmit}
          disabled={isProcessing}
        />
      );
    }

    return null;
  };

  const handleSectionConfirm = async (selectedIds: string[]) => {
    try { await selectSections(selectedIds); } catch (error) { console.error('Failed to select sections:', error); }
  };

  const handleFrameworkSectionConfirm = async (selectedIds: string[], outputFormat?: string) => {
    if (!framework) return;
    const sectionMap = new Map(framework.sections.map((s, i) => [`section-${i}`, s]));
    const selectedLabels = selectedIds
      .map(id => sectionMap.get(id))
      .filter((label): label is string => label !== undefined);
    if (selectedLabels.length === 0) return;
    const isZh = /[\u4e00-\u9fff]/.test(framework.topic || '');
    const fmt = outputFormat || 'docx';
    const fmtLabel = fmt === 'pptx' ? 'PPT' : fmt === 'html' ? 'HTML' : 'Word';
    const sectionsJson = JSON.stringify(selectedLabels);
    const exampleText = isZh
      ? `确认开始研究，包含章节：${selectedLabels.join('、')}\n__SELECTED_SECTIONS__:${sectionsJson}\n__OUTPUT_FORMAT__:${fmt}`
      : `Confirm and start research with sections: ${selectedLabels.join(', ')}\n__SELECTED_SECTIONS__:${sectionsJson}\n__OUTPUT_FORMAT__:${fmt}`;
    try {
      await handleOptionSelect('confirm_start', exampleText);
      const confirmContent = isZh
        ? `✅ 已确认研究框架\n\n**文档格式**：${fmtLabel}\n\n**研究章节**：\n${selectedLabels.map((s, i) => `${i + 1}. ${s}`).join('\n')}`
        : `✅ Research Framework Confirmed\n\n**Format**: ${fmtLabel}\n\n**Sections**:\n${selectedLabels.map((s, i) => `${i + 1}. ${s}`).join('\n')}`;
      addMessage({
        id: nanoid(),
        role: 'assistant',
        content: confirmContent,
        timestamp: new Date().toISOString(),
      });
    } catch (error) { console.error('Failed to confirm framework:', error); }
  };

  const handleParameterSubmit = async (params: Record<string, any>) => {
    try { await setParameters(params); } catch (error) { console.error('Failed to set parameters:', error); }
  };

  const handleConfirm = async (confirmed: boolean) => {
    try { await confirmResearch(confirmed); } catch (error) { console.error('Failed to confirm research:', error); }
  };

  return (
    <div className="relative flex h-full flex-col bg-background">
      {/* Message list — status bars are sticky headers inside the scroll container */}
      <VirtualMessageList
        messages={messages}
        loadOlderMessages={loadOlderMessages}
        hasMoreMessages={hasMoreMessages}
        isLoadingMessages={isLoadingMessages}
        onAtBottomChange={handleAtBottomChange}
        scrollToBottomRef={scrollToBottomRef}
        stickyHeader={
          <>
            <SearchIndicator isWaitingForReply={isWaitingForReply} />
            <AgentActivityBar activities={agentActivities} />
            {reportContext && (
              <div className="mx-4 mt-2 rounded-lg border border-border/60 bg-card/80 px-3 py-2 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">报告状态：{reportContext.report_phase}</span>
                  <span className="text-muted-foreground">v{reportContext.report_version}</span>
                </div>
                <div className="mt-1 text-muted-foreground">
                  {reportContext.sections.length} 个章节 · 质检 {reportContext.quality.overall_status}
                  {reportContext.quality.open_issue_count > 0
                    ? ` · ${reportContext.quality.open_issue_count} 个待处理问题`
                    : ''}
                </div>
                {reportContext.pending_decision && (
                  <div className="mt-1 text-amber-600 dark:text-amber-400">等待你的报告决策</div>
                )}
                {Boolean(reportContext.last_revision?.status) && reportContext.last_revision.status !== 'none' && (
                  <div className="mt-1 text-muted-foreground">
                    最近修订：{String(reportContext.last_revision.status)}
                  </div>
                )}
              </div>
            )}
          </>
        }
      />

      {/* Step content and paused status rendered below virtual list */}
      {(() => {
        const stepContent = currentStep !== null ? renderStepContent() : null;
        return stepContent ? (
          <div className="px-4 pb-2">
            <div className="mt-2">
              {stepContent}
            </div>
          </div>
        ) : null;
      })()}

      {/* 暂停/停止等任务状态已作为系统消息写入对话历史，此处不再单独占位展示 */}
      {/* Scroll to bottom */}
      {showScrollBtn && (
        <div className="absolute bottom-24 left-1/2 -translate-x-1/2 z-10">
          <button
            onClick={scrollToBottom}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-card/95 backdrop-blur-sm shadow-lg border border-border/50 text-xs text-foreground hover:bg-secondary transition-all duration-200"
          >
            <ArrowDown className="h-3 w-3" />
            <span>New messages</span>
          </button>
        </div>
      )}

      {/* Input area */}
      <div className="border-t border-border/50 p-3 pb-5 bg-background">
        <ChatInput
          onSend={handleSend}
          onCancel={isProcessing ? handleStopCurrentResponse : handlePauseResearch}
          disabled={controlBusy || isRestoringSession}
          isLoading={isProcessing}
          isNetworkBusy={isNetworkBusy}
          isWaitingForReply={isWaitingForReply}
          isRunning={status === 'running' || status === 'pausing' || status === 'cancelling'}
          isPaused={status === 'paused' || status === 'cancelled'}
          placeholder="Describe research needs or /template &lt;name&gt;"
        />
      </div>
    </div>
  );
}
