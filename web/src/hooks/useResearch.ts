// hooks/useResearch.ts

import { useCallback, useState } from 'react';
import { useResearchStore } from '@/store/useResearchStore';
import { useChatStore } from '@/store/useChatStore';
import { useSettingsStore } from '@/store/useSettingsStore';
import { useSessionStore } from '@/store/useSessionStore';
import { api, ApiError } from '@/lib/api';
import { collectTemplateContext } from '@/lib/templates';
import { nanoid } from 'nanoid';

/**
 * Research task Hook
 * Handles all research step interactions
 */
export function useResearch() {
  const {
    sessionId,
    currentStep,
    setSessionId,
    setStep,
    setTaskId,
    setStatus,
    setSummary,
    setFramework: setFrameworkAction,
    reset,
  } = useResearchStore();

  const { addMessage } = useChatStore();
  const { llm } = useSettingsStore();

  const [isNetworkBusy, setIsNetworkBusy] = useState(false);
  const [isWaitingForReply, setIsWaitingForReply] = useState(false);
  const isProcessing = isNetworkBusy || isWaitingForReply; // backward compat
  const [error, setError] = useState<ApiError | null>(null);

  /**
   * Quick start research (using preset template)
   * v6: C4/I8/C8/S14 fixes applied
   */
  const quickStartResearch = useCallback(async (
    input: string,
    templateId: string,
    attachments?: File[],
    selectedModel?: string,
    customParams?: Record<string, any>
  ) => {
    setIsNetworkBusy(true);
    setError(null);

    try {
      const llmConfig = {
        provider: llm.provider,
        model: selectedModel || llm.model,
        apiKey: llm.apiKey,
        apiEndpoint: llm.apiEndpoint,
        temperature: llm.temperature,
        maxTokens: llm.maxTokens,
        topP: llm.topP,
        frequencyPenalty: llm.frequencyPenalty,
        presencePenalty: llm.presencePenalty,
      };

      // S14: strip control/context fields from parameters
      const { autoConfirm: _flag, templateContext: _ctx, ...paramValues } = customParams || {};
      const autoConfirm = !!_flag;

      const data = await api.quickStart(input, templateId, {
        llmConfig,
        parameters: paramValues,
        autoConfirm,
      });

      // I8: exclude __pending__ session from message merge
      const prevId = useSessionStore.getState().activeId;
      const isPending = prevId === '__pending__';
      const prevMessages = (!isPending && prevId)
        ? useSessionStore.getState().sessions[prevId]?.messages || []
        : [];

      // C8: setSessionId BEFORE createSession to avoid subscription recursion
      useResearchStore.getState().setSessionId(data.session_id);
      useSessionStore.getState().createSession(data.session_id, input);

      // C4: merge old session messages into new session
      if (prevMessages.length > 0) {
        const store = useSessionStore.getState();
        if (store.sessions[data.session_id]) {
          store.syncActive({ messages: prevMessages });
        }
      }

      setTaskId(data.task_id);

      if (autoConfirm && data.step === 6) {
        setStatus('running');
        setStep(6, undefined);
        addMessage({
          id: nanoid(),
          role: 'assistant',
          content: `Starting research with template **${templateId}**.`,
          timestamp: new Date().toISOString(),
        });
      } else if (data.step === 4) {
        setStatus('idle');
        setStep(data.step, undefined);
        if (data.parameters) {
          useResearchStore.getState().setParameterConfig(data.parameters);
        }
        addMessage({
          id: nanoid(),
          role: 'assistant',
          content: data.message || `Template loaded. Configure parameters to continue.`,
          timestamp: new Date().toISOString(),
        });
      } else {
        setStatus('running');
        setStep(6, undefined);
        addMessage({
          id: nanoid(),
          role: 'assistant',
          content: data.message || `Quick start successful.`,
          timestamp: new Date().toISOString(),
        });
      }

      return data;
    } catch (e) {
      setError(e as ApiError);
      throw e;
    } finally {
      setIsNetworkBusy(false);
    }
  }, [setSessionId, setTaskId, setStatus, setStep, addMessage, llm]);

  /**
   * Start research
   * Supports LLM config and file attachments
   */
  const startResearch = useCallback(async (
    input: string,
    attachments?: File[],
    selectedModel?: string
  ) => {
    setIsNetworkBusy(true);
    setError(null);

    try {
      // If there are files, upload first
      let fileIds: string[] | undefined;
      if (attachments && attachments.length > 0) {
        const uploadResult = await api.uploadFiles(attachments);
        fileIds = uploadResult.files.map(f => f.id);
      }

      // Build LLM config
      const llmConfig = {
        provider: llm.provider,
        model: selectedModel || llm.model,
        apiKey: llm.apiKey,
        apiEndpoint: llm.apiEndpoint,
        temperature: llm.temperature,
        maxTokens: llm.maxTokens,
        topP: llm.topP,
        frequencyPenalty: llm.frequencyPenalty,
        presencePenalty: llm.presencePenalty,
      };

      const data = await api.startResearch(input, undefined, llmConfig, fileIds);
      setSessionId(data.session_id);

      // createSession now auto-transfers messages from pending session (Issue 1 fix)
      useSessionStore.getState().createSession(data.session_id, input);
      setTaskId(data.session_id);  // Break isLocalOnly loop: without taskId, sendMessage redirects back to startResearch

        // Async tool execution path: returns processing status, SSE pushes results later
      if ((data as any).status === 'processing') {
        setStep(0, undefined);
        setIsNetworkBusy(false);
        setIsWaitingForReply(true); // Enter waiting-for-reply state (Issue 4)
        return data;
      }

      setStep(data.step, data.options);

      addMessage({
        id: nanoid(),
        role: 'assistant',
        content: data.message,
        timestamp: new Date().toISOString(),
      });

      return data;
    } catch (e) {
      setError(e as ApiError);
      setIsWaitingForReply(false); // Clear waiting state on error (Issue 4)
      throw e;
    } finally {
      setIsNetworkBusy(false);
    }
  }, [setSessionId, setStep, addMessage, llm]);

  /**
   * Step 1: Select output type
   */
  const selectOutputType = useCallback(async (outputType: string) => {
    if (!sessionId) return;

    setIsNetworkBusy(true);
    setError(null);

    try {
      const data = await api.selectOutputType(sessionId, outputType);
      setStep(
        data.step,
        data.options ||
          data.templates?.map((t) => ({
            id: t.id,
            label: t.name,
            description: t.description,
          }))
      );

      if (data.message) {
        addMessage({
          id: nanoid(),
          role: 'assistant',
          content: data.message,
          timestamp: new Date().toISOString(),
        });
      }

      return data;
    } catch (e) {
      setError(e as ApiError);
      throw e;
    } finally {
      setIsNetworkBusy(false);
    }
  }, [sessionId, setStep, addMessage]);

  /**
   * Step 2: Select template
   */
  const selectTemplate = useCallback(async (templateId: string) => {
    if (!sessionId) return;

    setIsNetworkBusy(true);
    setError(null);

    try {
      const data = await api.selectTemplate(sessionId, templateId);
      // Preserve required field for SectionSelector
      setStep(
        data.step,
        data.sections?.map((s) => ({
          id: s.id,
          label: s.title,
          description: s.description,
          selected: s.selected,
          disabled: s.required,
          required: s.required,
        }))
      );

      if (data.message) {
        addMessage({
          id: nanoid(),
          role: 'assistant',
          content: data.message,
          timestamp: new Date().toISOString(),
        });
      }

      return data;
    } catch (e) {
      setError(e as ApiError);
      throw e;
    } finally {
      setIsNetworkBusy(false);
    }
  }, [sessionId, setStep, addMessage]);

  /**
   * Step 3: Select sections (multi-select)
   */
  const selectSections = useCallback(async (sectionIds: string[]) => {
    if (!sessionId) return;

    setIsNetworkBusy(true);
    setError(null);

    try {
      const data = await api.selectSections(sessionId, sectionIds);

      if (data.parameters) {
        setStep(data.step, undefined);
        useResearchStore.getState().setParameterConfig(data.parameters);
      } else {
        setStep(data.step, data.options);
      }

      if (data.message) {
        addMessage({
          id: nanoid(),
          role: 'assistant',
          content: data.message,
          timestamp: new Date().toISOString(),
        });
      }

      return data;
    } catch (e) {
      setError(e as ApiError);
      throw e;
    } finally {
      setIsNetworkBusy(false);
    }
  }, [sessionId, setStep, addMessage]);

  /**
   * Step 4: Set parameters
   */
  const setParameters = useCallback(
    async (params: Record<string, any>) => {
      if (!sessionId) return;

      setIsNetworkBusy(true);
      setError(null);

      try {
        const data = await api.setParameters(sessionId, params);

        if (data.summary) {
          setSummary(data.summary);
        }

        setStep(data.step, [
          { id: 'confirm', label: 'Confirm Start', description: 'Start executing the research task' },
          { id: 'back', label: 'Go Back', description: 'Adjust parameter settings' },
        ]);

        if (data.message) {
          addMessage({
            id: nanoid(),
            role: 'assistant',
            content: data.message,
            timestamp: new Date().toISOString(),
          });
        }

        return data;
      } catch (e) {
        setError(e as ApiError);
        throw e;
      } finally {
        setIsNetworkBusy(false);
      }
    },
    [sessionId, setStep, setSummary, addMessage]
  );

  /**
   * Step 5: Confirm research
   */
  const confirmResearch = useCallback(async (confirmed: boolean) => {
    if (!sessionId) return;

    setIsNetworkBusy(true);
    setError(null);

    try {
      const data = await api.confirmResearch(sessionId, confirmed);

      if (confirmed && data.step === 6 && data.status === 'running') {
        setTaskId(data.session_id);
        setStatus('running');
      }

      // If user clicks "go back", restart
      if (!confirmed && data.step === 6 && data.status === 'cancelled') {
        reset();
        return data;
      }

      setStep(data.step, undefined);

      if (data.message) {
        addMessage({
          id: nanoid(),
          role: 'assistant',
          content: data.message,
          timestamp: new Date().toISOString(),
        });
      }

      return data;
    } catch (e) {
      setError(e as ApiError);
      throw e;
    } finally {
      setIsNetworkBusy(false);
    }
  }, [sessionId, setTaskId, setStatus, setStep, reset, addMessage]);

  /**
   * Start research from template customization flow
   */
  const handleStartResearch = useCallback(async () => {
    const active = useResearchStore.getState().activeTemplate;
    const topic = useResearchStore.getState().researchTopic || active?.name || '';
    if (!active) return;

    try {
      const allMessages = useChatStore.getState().messages;
      const context = collectTemplateContext(active, allMessages, topic);

      setIsNetworkBusy(true);
      await quickStartResearch(topic, active.id, undefined, undefined, {
        templateContext: context,
        ...active.parameters,
        autoConfirm: true,
      });

      useResearchStore.getState().setActiveTemplate(null);
      useResearchStore.getState().setResearchTopic(null);
    } catch (error) {
      setError(error as ApiError);
      addMessage({
        id: nanoid(),
        role: 'assistant',
        content: 'Failed to start research. Please try again.',
        timestamp: new Date().toISOString(),
      });
    } finally {
      setIsNetworkBusy(false);
    }
  }, [quickStartResearch, addMessage]);

  /**
   * Unified send message entry - for RuntimeProvider
   */
  const sendMessage = useCallback(async (text: string) => {
    if (!sessionId) {
      return startResearch(text);
    }

    // Locally created empty session (via "+" tab), no backend counterpart yet
    const cache = useSessionStore.getState().sessions[sessionId];
    const isLocalOnly = cache && !cache.taskId;
    if (isLocalOnly) {
      return startResearch(text);
    }

    // Existing session: send message (works for both chat mode and research mode)
    // In research mode (currentStep=6), backend _handle_user_message routes via _llm_converse
    if (currentStep === 0 || currentStep === 6) {
      // Chat mode: send message
      try {
        setIsNetworkBusy(true);
        const data = await api.sendChatMessage(sessionId, text);
        
      // Async tool execution path: returns processing status, SSE pushes results later
        if ((data as any).status === 'processing') {
          setStep(0, undefined);
          setIsNetworkBusy(false);
          setIsWaitingForReply(true); // Enter waiting-for-reply state (Issue 4)
          return data;
        }

        // Update state based on returned mode
        const mode = data.mode || 'chat';
        
        if (mode === 'framework') {
          setStep(0, data.suggestions || data.options);
          if (data.framework) {
            setFrameworkAction(data.framework);
          }
        } else if (mode === 'research' && data.step === 6) {
          setTaskId(data.session_id);
          setStatus('running');
          setStep(6, undefined);
          setFrameworkAction(null);
        } else {
          // Still in chat mode
          setStep(0, data.suggestions || data.options);
        }
        
        // D-1 fix: sync sessionId from backend response (handles auto-create path)
        if (data.session_id && data.session_id !== sessionId) {
          setSessionId(data.session_id);
        }
        
        addMessage({
          id: nanoid(),
          role: 'assistant',
          content: data.message,
          timestamp: new Date().toISOString(),
        });
        
        return data;
      } catch (e) {
        setError(e as ApiError);
        throw e;
      } finally {
        setIsNetworkBusy(false);
      }
    }
    
    console.warn('sendMessage called at unexpected step:', currentStep);
    return null;
  }, [sessionId, currentStep, startResearch, setSessionId, setStep, setTaskId, setStatus, addMessage]);

  /**
   * Generic option handler - dispatches based on currentStep
   */
  const handleOptionSelect = useCallback(async (optionId: string, exampleText?: string) => {
    // S11: start_research handled here, not in ChatPanel
    if (optionId === 'start_research') {
      return handleStartResearch();
    }

    // "view_report" — toggle preview panel, don't send message to LLM
    if (optionId === 'view_report') {
      const rs = useResearchStore.getState();
      if (rs.status !== 'completed') {
        rs.setStatus('completed');
      }
      // Ensure taskId is set (restored sessions may have taskId in sessionStore but not researchStore)
      if (!rs.taskId && sessionId) {
        rs.setTaskId(sessionId);
      }
      rs.triggerPreviewRefresh();
      return;
    }

    // Chat mode: click suggestion
    if (currentStep === 0) {
      try {
        setIsNetworkBusy(true);
        const data = await api.clickSuggestion(sessionId!, optionId, exampleText);
        
        // Update state based on returned mode
        const mode = data.mode || 'chat';
        
        if (mode === 'framework') {
          setStep(0, data.suggestions || data.options);
          if (data.framework) {
            setFrameworkAction(data.framework);
          }
        } else if (mode === 'research' && data.step === 6) {
          setTaskId(data.session_id);
          setStatus('running');
          setStep(6, undefined);
          setFrameworkAction(null);
        } else {
          setStep(0, data.suggestions || data.options);
        }
        
        if (data.message) {
          addMessage({
            id: nanoid(),
            role: 'assistant',
            content: data.message,
            timestamp: new Date().toISOString(),
          });
        }
        
        return data;
      } catch (e) {
        setError(e as ApiError);
        throw e;
      } finally {
        setIsNetworkBusy(false);
      }
    }
    
    switch (currentStep) {
      case 1:
        return selectOutputType(optionId);
      case 2:
        return selectTemplate(optionId);
      case 5:
        return confirmResearch(optionId === 'confirm');
      default:
        console.warn('handleOptionSelect called at unexpected step:', currentStep);
        return null;
    }
  }, [currentStep, sessionId, selectOutputType, selectTemplate, confirmResearch,
      handleStartResearch, setSessionId, setStep, setTaskId, setStatus, addMessage]);

  return {
    quickStartResearch,
    startResearch,
    selectOutputType,
    selectTemplate,
    selectSections,
    setParameters,
    confirmResearch,
    reset,
    sendMessage,
    handleOptionSelect,
    handleStartResearch,
    isProcessing,
    isNetworkBusy,
    isWaitingForReply,
    setIsWaitingForReply,
    error,
    sessionId,
    currentStep,
  };
}
