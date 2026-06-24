// components/chat/ChatPanel.tsx

'use client';

import { useRef, useEffect, useState, useCallback } from 'react';
import type { AgentMessageData, ChatMessage, SelectOption } from '@/types/api';
import { nanoid } from 'nanoid';
import { useChatStore } from '@/store/useChatStore';
import { useResearchStore } from '@/store/useResearchStore';
import { useSessionStore } from '@/store/useSessionStore';
import { useResearch } from '@/hooks/useResearch';
import { useProgress, useSessionStream } from '@/hooks/useProgress';
import type { ChatResponseData } from '@/types/api';
import { useChatScroll } from '@/hooks/useChatScroll';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { OptionSelector } from './OptionSelector';
import { SectionSelector } from './SectionSelector';
import { DynamicParameterForm } from './DynamicParameterForm';
// ProgressPanel removed — agent progress shown via inline agent_message events
import { SearchIndicator } from './SearchIndicator';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';
import { ArrowDown, Zap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { parseTemplateCommand, RESEARCH_TEMPLATES, formatTemplateMessage, formatTemplateList, formatTemplateNotFound, extractTemplateKeyword } from '@/lib/templates';

export function ChatPanel() {
  const { messages, addMessage } = useChatStore();
  const {
    currentStep,
    stepOptions,
    parameterConfig,
    taskId,
    status,
    summary,
    framework,
    reset,
    clearResearch,
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
  } = useResearch();

  // Research progress stream (closes on task complete)
  const sseId = sessionId || taskId;
  const { isConnected } = useProgress(sseId);

  // Timer ref to prevent stale setTimeout race (Issue 3 fix: Oracle CRITICAL)
  const searchStateTimerRef = useRef<ReturnType<typeof setTimeout>>();

  // Persistent session stream (stays alive, unaffected by task complete)
  // Receives chat_response + agent_message events (Issue 2, Issue 5)
  useSessionStream(sessionId, {
    onChatResponse: (data) => {
      // Match: direct equality, taskId, or fallback to store's active session
      const storeSessionId = useSessionStore.getState().activeId;
      const matches = data.session_id === sessionId
        || data.session_id === taskId
        || data.session_id === storeSessionId;
      if (matches) {
        addMessage({
          id: nanoid(),
          role: 'assistant',
          content: data.message,
          timestamp: data.timestamp || new Date().toISOString(),
        });
        if (data.suggestions && data.suggestions.length > 0) {
          useResearchStore.getState().setStep(0, data.suggestions);
        }
        // Clear search + waiting states on response (Issue 3, Issue 4)
        useResearchStore.getState().setSearchState('completed');
        setIsWaitingForReply(false);
        clearTimeout(searchStateTimerRef.current);
        searchStateTimerRef.current = setTimeout(() => {
          useResearchStore.getState().setSearchState('idle');
        }, 2000);
      }
    },
    onAgentMessage: (data: AgentMessageData) => {
      const storeSessionId = useSessionStore.getState().activeId;
      if (data.session_id === sessionId || data.session_id === storeSessionId) {
        addMessage({
          id: nanoid(),
          role: 'agent',
          content: data.content,
          timestamp: data.timestamp,
          agent: { id: data.agent_id, name: data.agent_name, action: data.action },
        });
      }
    },
  });

  // Cleanup timer on unmount (Oracle MAJOR)
  useEffect(() => {
    return () => clearTimeout(searchStateTimerRef.current);
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
        const olderMsgs: ChatMessage[] = result.messages
          .filter((m: any) => !currentIds.has(m.id))
          .map((m: any) => ({
            id: m.id || nanoid(),
            role: (m.role === 'user' || m.role === 'assistant' || m.role === 'agent'
              ? m.role
              : 'system') as ChatMessage['role'],
            content: m.content,
            timestamp: m.timestamp || new Date().toISOString(),
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
    serverOffsetRef.current = 0;
    setHasMoreMessages(true);
  }, [activeSessionId]);

  const { containerRef, handleScroll, scrollToBottom, isAtBottom } = useChatScroll(
    [messages],
    loadOlderMessages,
  );

  // hasActiveResearch removed — ProgressPanel replaced by inline agent messages
  const isChatMode = currentStep === null || currentStep === 0;

  const handleSend = async (text: string, attachments?: File[], selectedModel?: string) => {
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
          useResearchStore.getState().setSearchState('searching');
          return;
        }
      } else {
        const data = await startResearch(text, attachments, selectedModel);
        if (data && (data as any).status === 'processing') {
          useResearchStore.getState().setSearchState('searching');
          return;
        }
      }
    } catch (error) {
      console.error('Failed to send message:', error);
      addMessage({
        id: nanoid(),
        role: 'assistant',
        content: 'Sorry, failed to send message. Please check if the backend service is running properly.',
        timestamp: new Date().toISOString(),
      });
    }
  };

  const handleCancel = async () => {
    if (taskId && status === 'running') {
      try { await api.pauseResearch(taskId); } catch {}
      useResearchStore.getState().setStatus('idle');
      addMessage({
        id: nanoid(),
        role: 'assistant',
        content: 'Research paused. Progress has been saved. You can resume later or continue chatting.',
        timestamp: new Date().toISOString(),
      });
      return;
    }
    // Cancel background tool execution (chat processing/searching state)
    if (sessionId && isWaitingForReply) {
      try { await api.cancelResearch(sessionId); } catch {}
      setIsWaitingForReply(false);
      useResearchStore.getState().setSearchState('idle');
      addMessage({
        id: nanoid(),
        role: 'assistant',
        content: 'Search cancelled.',
        timestamp: new Date().toISOString(),
      });
      return;
    }
    if (taskId) {
      try { await api.cancelResearch(taskId); } catch {}
      clearResearch();  // Clear research state without creating a new session
    }
    addMessage({
      id: nanoid(),
      role: 'assistant',
      content: 'Task cancelled. You can continue with new requests.',
      timestamp: new Date().toISOString(),
    });
  };

  // Render step content (framework interaction steps 1-5)
  const renderStepContent = () => {
    if (isProcessing) {
      return (
        <div className="flex items-center justify-center py-8">
          <div className="flex items-center gap-3">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            <span className="text-sm text-muted-foreground">Processing...</span>
          </div>
        </div>
      );
    }

    if (isChatMode) {
      const tpl = useResearchStore.getState().activeTemplate;
      const topic = useResearchStore.getState().researchTopic;
      const baseOptions = stepOptions || [];
      const isZh = (topic || framework?.topic) ? /[\u4e00-\u9fff]/.test(topic || framework?.topic || '') : false;

      if (framework && framework.sections && framework.sections.length > 0) {
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
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground px-1">{isZh ? '你可以选择：' : 'You can choose:'}</p>
            <div className="grid grid-cols-2 gap-2">
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
          </div>
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

  const handleFrameworkSectionConfirm = async (selectedIds: string[]) => {
    if (!framework) return;
    const sectionMap = new Map(framework.sections.map((s, i) => [`section-${i}`, s]));
    const selectedLabels = selectedIds
      .map(id => sectionMap.get(id))
      .filter((label): label is string => label !== undefined);
    if (selectedLabels.length === 0) return;
    const isZh = /[\u4e00-\u9fff]/.test(framework.topic);
    const exampleText = isZh
      ? `确认开始研究，包含章节：${selectedLabels.join('、')}`
      : `Confirm and start research with sections: ${selectedLabels.join(', ')}`;
    try { await handleOptionSelect('confirm_start', exampleText); } catch (error) { console.error('Failed to confirm framework:', error); }
  };

  const handleParameterSubmit = async (params: Record<string, any>) => {
    try { await setParameters(params); } catch (error) { console.error('Failed to set parameters:', error); }
  };

  const handleConfirm = async (confirmed: boolean) => {
    try { await confirmResearch(confirmed); } catch (error) { console.error('Failed to confirm research:', error); }
  };

  const pendingInputData = useSessionStore((s) => {
    const sid = s.activeId;
    return sid ? s.sessions[sid]?.pendingInput : null;
  });
  const pendingInputText = pendingInputData?.text || undefined;

  const pendingInputConsumedRef = useRef<string | null>(null);
  const pendingInputTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (pendingInputData && pendingInputConsumedRef.current !== pendingInputData.text) {
      pendingInputConsumedRef.current = pendingInputData.text;
      if (pendingInputTimerRef.current) clearTimeout(pendingInputTimerRef.current);
      pendingInputTimerRef.current = setTimeout(() => {
        useSessionStore.getState().syncActive({ pendingInput: null });
        pendingInputConsumedRef.current = null;
        pendingInputTimerRef.current = null;
      }, 100);
    }
    return () => {
      if (pendingInputTimerRef.current) clearTimeout(pendingInputTimerRef.current);
    };
  }, [pendingInputData]);

  return (
    <div className="flex h-full flex-col bg-background">
      {/* Search/retrieval in-progress indicator (Issue 3) */}
      <SearchIndicator />

      {/* Message list */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto preview-scrollbar px-4 py-4 space-y-3"
      >
        {messages.length === 0 && (
          <div className="flex h-full items-center justify-center">
            <div className="text-center max-w-sm">
              <div className="mx-auto mb-5 h-16 w-16 rounded-2xl bg-background border overflow-hidden shadow-sm">
                <img src="/logo.png" alt="Zensers" className="h-full w-full object-contain p-1.5" />
              </div>
              <h2 className="text-lg font-semibold text-foreground tracking-tight">Zensers</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Describe your research needs to start smart research
              </p>
              <div className="mt-6 bg-card border rounded-xl shadow-sm p-4 text-left">
                <div className="flex items-center gap-2 mb-3">
                  <Zap className="h-3.5 w-3.5 text-primary" />
                  <span className="text-xs font-medium text-foreground">Quick Templates</span>
                </div>
                <div className="space-y-1.5">
                  {RESEARCH_TEMPLATES.slice(0, 4).map(t => (
                    <div key={t.id} className="flex items-center gap-2 text-xs">
                      <code className="px-1.5 py-0.5 bg-secondary rounded text-[11px]">
                        /template {t.id}
                      </code>
                      <span className="text-muted-foreground">{t.name}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {isLoadingMessages && (
          <div className="flex justify-center py-2">
            <span className="text-xs text-muted-foreground animate-pulse">Loading earlier messages...</span>
          </div>
        )}

        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}

        {currentStep !== null && (
          <div className="mt-2">
            {renderStepContent()}
          </div>
        )}
      </div>

      {/* Scroll to bottom */}
      {!isAtBottom() && (
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
          onCancel={handleCancel}
          disabled={false}
          isLoading={isProcessing}
          isNetworkBusy={isNetworkBusy}
          isWaitingForReply={isWaitingForReply}
          isRunning={status === 'running'}
          pendingInput={pendingInputText}
          placeholder="Describe research needs or /template &lt;name&gt;"
        />
      </div>
    </div>
  );
}
