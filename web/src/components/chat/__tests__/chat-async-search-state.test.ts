import { describe, it, expect, beforeEach, vi } from 'vitest';
import type { ChatMessage, ChatResponseData, SelectOption } from '@/types/api';

function createResearchStore() {
  let state: Record<string, any> = {
    currentStep: null,
    stepOptions: null,
    status: 'idle',
    sessionId: null,
    searchState: 'idle',
    framework: null,
  };

  const listeners: Array<() => void> = [];

  return {
    getState: () => state,
    setState: (patch: Record<string, any>) => {
      state = { ...state, ...patch };
      listeners.forEach((l) => l());
    },
    subscribe: (l: () => void) => {
      listeners.push(l);
      return () => {
        const idx = listeners.indexOf(l);
        if (idx >= 0) listeners.splice(idx, 1);
      };
    },
    setStep: (step: number | null, options?: Array<SelectOption | string> | null) => {
      state = { ...state, currentStep: step, stepOptions: options ?? null };
    },
    setStatus: (s: string) => {
      state = { ...state, status: s };
    },
    setSearchState: (s: string) => {
      state = { ...state, searchState: s };
    },
    setFramework: (fw: any) => {
      state = { ...state, framework: fw };
    },
  };
}

function createChatStore() {
  let messages: ChatMessage[] = [];
  let nextId = 1;

  return {
    getMessages: () => messages,
    addMessage: (msg: ChatMessage) => {
      const newMsg = { ...msg, id: msg.id || `msg-${nextId++}` };
      messages = [...messages, newMsg];
      return messages;
    },
    updateMessage: (id: string, updates: Partial<ChatMessage>) => {
      messages = messages.map((m) => (m.id === id ? { ...m, ...updates } : m));
      return messages;
    },
    findMessage: (predicate: (m: ChatMessage) => boolean) =>
      messages.find(predicate),
  };
}

function makeChatResponseData(
  overrides: Partial<ChatResponseData> & { session_id: string },
): ChatResponseData {
  return {
    message: overrides.message ?? '搜索完成',
    action: overrides.action ?? 'continue_chat',
    session_id: overrides.session_id,
    timestamp: overrides.timestamp ?? new Date().toISOString(),
    ...(overrides.topic !== undefined ? { topic: overrides.topic } : {}),
    ...(overrides.directions !== undefined
      ? { directions: overrides.directions }
      : {}),
    ...(overrides.suggestions !== undefined
      ? { suggestions: overrides.suggestions }
      : {}),
    ...(overrides.thinking_content !== undefined
      ? { thinking_content: overrides.thinking_content }
      : {}),
    ...(overrides.mode !== undefined ? { mode: overrides.mode } : {}),
    ...(overrides.step !== undefined ? { step: overrides.step } : {}),
  };
}

function simulateOnChatResponse(
  data: ChatResponseData,
  chatStore: ReturnType<typeof createChatStore>,
  researchStore: ReturnType<typeof createResearchStore>,
  streamingDoneRef: { current: boolean },
  streamingMsgIdRef: { current: string | null },
) {
  const sessionId = data.session_id;
  const matches = true;

  if (!matches) return;

  let finalContent = data.message;
  let finalThinking: string | undefined = data.thinking_content;

  const trimmed = finalContent.trim();
  if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
    try {
      const parsed = JSON.parse(trimmed);
      if (parsed.message && typeof parsed.message === 'string') {
        finalContent = parsed.message;
      }
    } catch {}
  }

  if (streamingMsgIdRef.current) {
    chatStore.updateMessage(streamingMsgIdRef.current, {
      content: finalContent,
      ...(finalThinking !== undefined
        ? { thinkingContent: finalThinking }
        : {}),
      metadata: { status: 'done' },
    });
    streamingMsgIdRef.current = null;
    streamingDoneRef.current = true;
  } else {
    chatStore.addMessage({
      id: `sse-${Date.now()}`,
      role: 'assistant',
      content: finalContent,
      ...(finalThinking !== undefined
        ? { thinkingContent: finalThinking }
        : {}),
      timestamp: data.timestamp || new Date().toISOString(),
    });
  }

  if (data.suggestions && data.suggestions.length > 0) {
    researchStore.setStep(0, data.suggestions);
  }

  researchStore.setSearchState('completed');

  if (researchStore.getState().status !== 'running') {
    // isWaitingForReply = false
  }
}

function isChatMode(currentStep: number | null): boolean {
  return currentStep === null || currentStep === 0;
}

function getStepContentTitle(currentStep: number | null): string | null {
  if (currentStep === null || currentStep === 0) return null;
  if (currentStep === 3 || currentStep === 4 || currentStep === 5) return null;
  if (currentStep === 1) return 'Select Output Type';
  return 'Select Template';
}

describe('Bug A: onChatResponse ignores action/mode', () => {
  let chatStore: ReturnType<typeof createChatStore>;
  let researchStore: ReturnType<typeof createResearchStore>;
  let streamingDoneRef: { current: boolean };
  let streamingMsgIdRef: { current: string | null };

  beforeEach(() => {
    chatStore = createChatStore();
    researchStore = createResearchStore();
    streamingDoneRef = { current: false };
    streamingMsgIdRef = { current: null };
  });

  it('action=enter_framework is ignored — framework not set', () => {
    const data = makeChatResponseData({
      session_id: 'ses-001',
      message: '我来帮你建立研究框架',
      action: 'enter_framework',
      suggestions: [
        { id: 'confirm', label: '确认框架', example: '确认' },
      ],
    });

    simulateOnChatResponse(
      data,
      chatStore,
      researchStore,
      streamingDoneRef,
      streamingMsgIdRef,
    );

    expect(researchStore.getState().currentStep).toBe(0);
    expect(researchStore.getState().framework).toBeNull();
  });

  it('action=start_research is ignored — status stays idle', () => {
    const data = makeChatResponseData({
      session_id: 'ses-001',
      message: '研究任务已启动',
      action: 'start_research',
    });

    simulateOnChatResponse(
      data,
      chatStore,
      researchStore,
      streamingDoneRef,
      streamingMsgIdRef,
    );

    expect(researchStore.getState().status).toBe('idle');
    expect(researchStore.getState().currentStep).toBeNull();
  });

  it('mode=framework is ignored — stays in chat mode', () => {
    const data = makeChatResponseData({
      session_id: 'ses-001',
      message: '框架已准备好',
      action: 'enter_framework',
      mode: 'framework',
      suggestions: [
        { id: 'confirm', label: '确认', example: '确认' },
      ],
    });

    simulateOnChatResponse(
      data,
      chatStore,
      researchStore,
      streamingDoneRef,
      streamingMsgIdRef,
    );

    expect(researchStore.getState().framework).toBeNull();
    expect(isChatMode(researchStore.getState().currentStep)).toBe(true);
  });

  it('compare: sync sendMessage would handle mode=framework correctly', () => {
    const syncResponse = {
      session_id: 'ses-001',
      step: 0,
      mode: 'framework',
      message: '框架已准备好',
      suggestions: [{ id: 'confirm', label: '确认', example: '确认' }],
      framework: { topic: 'BYD', sections: ['财务分析', '竞争格局'] },
    };

    const mode = syncResponse.mode || 'chat';
    if (mode === 'framework') {
      researchStore.setStep(0, syncResponse.suggestions);
      researchStore.setFramework(syncResponse.framework);
    }

    expect(researchStore.getState().framework).not.toBeNull();
    expect(researchStore.getState().currentStep).toBe(0);

    const asyncData = makeChatResponseData({
      session_id: 'ses-001',
      message: '框架已准备好',
      action: 'enter_framework',
      mode: 'framework',
      suggestions: [{ id: 'confirm', label: '确认', example: '确认' }],
    });

    const researchStore2 = createResearchStore();
    simulateOnChatResponse(
      asyncData,
      chatStore,
      researchStore2,
      streamingDoneRef,
      streamingMsgIdRef,
    );

    expect(researchStore2.getState().framework).toBeNull();
    expect(researchStore2.getState().currentStep).toBe(0);
  });
});

describe('Bug B/D: streamingDoneRef not set in else branch', () => {
  let chatStore: ReturnType<typeof createChatStore>;
  let researchStore: ReturnType<typeof createResearchStore>;
  let streamingDoneRef: { current: boolean };
  let streamingMsgIdRef: { current: string | null };

  beforeEach(() => {
    chatStore = createChatStore();
    researchStore = createResearchStore();
    streamingDoneRef = { current: false };
    streamingMsgIdRef = { current: null };
  });

  it('async search: streamingDoneRef stays false after onChatResponse', () => {
    const data = makeChatResponseData({
      session_id: 'ses-001',
      message: '搜索完成，以下是比亚迪毛利率数据...',
    });

    simulateOnChatResponse(
      data,
      chatStore,
      researchStore,
      streamingDoneRef,
      streamingMsgIdRef,
    );

    expect(streamingDoneRef.current).toBe(false);
  });

  it('streaming search: streamingDoneRef becomes true after onChatResponse', () => {
    streamingMsgIdRef.current = 'msg-streaming-1';
    chatStore.addMessage({
      id: 'msg-streaming-1',
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
    });

    const data = makeChatResponseData({
      session_id: 'ses-001',
      message: '比亚迪近年毛利率...',
    });

    simulateOnChatResponse(
      data,
      chatStore,
      researchStore,
      streamingDoneRef,
      streamingMsgIdRef,
    );

    expect(streamingDoneRef.current).toBe(true);
  });

  it('replayed chat_response is NOT blocked when streamingDoneRef is false (BUG)', () => {
    const data1 = makeChatResponseData({
      session_id: 'ses-001',
      message: '搜索完成',
      timestamp: '2026-07-03T10:00:00',
    });

    simulateOnChatResponse(
      data1,
      chatStore,
      researchStore,
      streamingDoneRef,
      streamingMsgIdRef,
    );

    expect(chatStore.getMessages().filter((m) => m.role === 'assistant')).toHaveLength(1);
    expect(streamingDoneRef.current).toBe(false);

    const data2 = makeChatResponseData({
      session_id: 'ses-001',
      message: '搜索完成',
      timestamp: '2026-07-03T10:00:00',
    });

    simulateOnChatResponse(
      data2,
      chatStore,
      researchStore,
      streamingDoneRef,
      streamingMsgIdRef,
    );

    expect(chatStore.getMessages().filter((m) => m.role === 'assistant')).toHaveLength(2);
  });

  it('with fix: streamingDoneRef=true blocks replay', () => {
    const data1 = makeChatResponseData({
      session_id: 'ses-001',
      message: '搜索完成',
      timestamp: '2026-07-03T10:00:00',
    });

    simulateOnChatResponse(
      data1,
      chatStore,
      researchStore,
      streamingDoneRef,
      streamingMsgIdRef,
    );

    streamingDoneRef.current = true;

    const data2 = makeChatResponseData({
      session_id: 'ses-001',
      message: '搜索完成',
      timestamp: '2026-07-03T10:00:00',
    });

    if (streamingDoneRef.current) {
      // blocked
    } else {
      simulateOnChatResponse(
        data2,
        chatStore,
        researchStore,
        streamingDoneRef,
        streamingMsgIdRef,
      );
    }

    expect(chatStore.getMessages().filter((m) => m.role === 'assistant')).toHaveLength(1);
  });
});

describe('Bug C: useResearchStore subscription restores old currentStep', () => {
  it('status change alone does NOT trigger subscription with current code', () => {
    const researchStore = createResearchStore();

    let subscriptionTriggered = false;
    let restoredStep: number | null = null;

    const fakeSessionStore = {
      getState: () => ({
        activeId: 'ses-001',
        sessions: {
          'ses-001': {
            currentStep: 2,
            status: 'completed',
          } as any,
        },
      }),
      subscribe: (listener: () => void) => {
        return () => {};
      },
    };

    const currentResearch = {
      sessionId: 'ses-001',
      status: 'idle',
      currentStep: 0,
    };

    const nextResearch = {
      sessionId: 'ses-001',
      status: 'completed',
      currentStep: 2,
    };

    if (
      currentResearch.sessionId !== nextResearch.sessionId ||
      currentResearch.status !== nextResearch.status
    ) {
      subscriptionTriggered = true;
      restoredStep = nextResearch.currentStep;
    }

    expect(subscriptionTriggered).toBe(true);
    expect(restoredStep).toBe(2);
  });

  it('with fine-grained subscription: status change alone does NOT restore currentStep', () => {
    const currentResearch = {
      sessionId: 'ses-001',
      status: 'idle',
      currentStep: 0,
    };

    const nextResearch = {
      sessionId: 'ses-001',
      status: 'completed',
      currentStep: 2,
    };

    let restoredStep: number | null = null;

    if (currentResearch.sessionId !== nextResearch.sessionId) {
      restoredStep = nextResearch.currentStep;
    } else if (currentResearch.status !== nextResearch.status) {
      restoredStep = null;
    }

    expect(restoredStep).toBeNull();
  });

  it('page refresh from localStorage restores stale currentStep=2', () => {
    const storedSession = {
      'ses-001': {
        id: 'ses-001',
        title: 'BYD Research',
        currentStep: 2,
        stepOptions: [
          { id: 'tpl-detailed', label: 'Detailed' },
          { id: 'tpl-brief', label: 'Brief' },
        ],
        status: 'idle',
        messages: [],
      } as any,
    };

    const currentResearch = {
      sessionId: null,
      status: 'idle',
      currentStep: null,
    };

    const nextResearch = {
      sessionId: 'ses-001',
      status: 'idle',
      currentStep: 2,
    };

    let restoredStep: number | null = null;

    if (
      currentResearch.sessionId !== nextResearch.sessionId ||
      currentResearch.status !== nextResearch.status
    ) {
      restoredStep = nextResearch.currentStep;
    }

    expect(restoredStep).toBe(2);
    expect(isChatMode(restoredStep)).toBe(false);
    expect(getStepContentTitle(restoredStep)).toBe('Select Template');
  });
});

describe('Bug D: Backend chat_response missing mode/step', () => {
  it('sync response includes mode and step', () => {
    const syncResponse = {
      session_id: 'ses-001',
      step: 0,
      mode: 'chat',
      status: 'processing',
      message: 'Querying information...',
    };

    expect(syncResponse).toHaveProperty('mode');
    expect(syncResponse).toHaveProperty('step');
  });

  it('background tool chain response_data lacks mode and step', () => {
    const response_data = {
      message: '比亚迪近年毛利率...',
      action: 'continue_chat',
      topic: 'BYD',
      directions: ['财务分析'],
      suggestions: [{ id: 'deep_research', label: '深度研究', example: '开始深度研究' }],
    };

    expect(response_data).not.toHaveProperty('mode');
    expect(response_data).not.toHaveProperty('step');
  });

  it('ProgressStreamer.push_chat_response SSE data lacks mode and step', () => {
    const sseData = {
      session_id: 'ses-001',
      message: '比亚迪近年毛利率...',
      action: 'continue_chat',
      topic: 'BYD',
      directions: ['财务分析'],
      suggestions: [{ id: 'deep_research', label: '深度研究', example: '开始深度研究' }],
      timestamp: '2026-07-03T10:00:00',
    };

    expect(sseData).not.toHaveProperty('mode');
    expect(sseData).not.toHaveProperty('step');
  });

  it('with fix: response_data includes mode and step', () => {
    const response_data = {
      message: '比亚迪近年毛利率...',
      action: 'continue_chat',
      topic: 'BYD',
      directions: ['财务分析'],
      suggestions: [{ id: 'deep_research', label: '深度研究', example: '开始深度研究' }],
      mode: 'chat',
      step: 0,
    };

    expect(response_data).toHaveProperty('mode', 'chat');
    expect(response_data).toHaveProperty('step', 0);
  });
});

describe('Bug E: "Select Template" trigger path analysis', () => {
  it('renderStepContent shows "Select Template" when currentStep=2', () => {
    expect(isChatMode(2)).toBe(false);
    expect(getStepContentTitle(2)).toBe('Select Template');
  });

  it('renderStepContent shows "Select Template" when currentStep=6 with stepOptions', () => {
    expect(isChatMode(6)).toBe(false);
    expect(getStepContentTitle(6)).toBe('Select Template');
  });

  it('renderStepContent shows chat mode when currentStep=0', () => {
    expect(isChatMode(0)).toBe(true);
    expect(getStepContentTitle(0)).toBeNull();
  });

  it('renderStepContent shows chat mode when currentStep=null', () => {
    expect(isChatMode(null)).toBe(true);
    expect(getStepContentTitle(null)).toBeNull();
  });

  it('chat search flow: sendMessage setStep(0,undefined) → currentStep stays 0', () => {
    const researchStore = createResearchStore();

    researchStore.setStep(0, undefined);

    expect(researchStore.getState().currentStep).toBe(0);
    expect(isChatMode(researchStore.getState().currentStep)).toBe(true);
  });

  it('chat search flow: onChatResponse with suggestions → setStep(0,suggestions)', () => {
    const researchStore = createResearchStore();
    const suggestions = [
      { id: 'deep_research', label: '深度研究', example: '开始深度研究' },
    ];

    researchStore.setStep(0, suggestions);

    expect(researchStore.getState().currentStep).toBe(0);
    expect(researchStore.getState().stepOptions).toHaveLength(1);
    expect(isChatMode(researchStore.getState().currentStep)).toBe(true);
  });

  it('stale cache overwrite: status change triggers subscription → currentStep=2 restored', () => {
    const researchStore = createResearchStore();

    researchStore.setStep(0, [{ id: 'deep', label: 'Deep', example: 'go' }]);

    expect(researchStore.getState().currentStep).toBe(0);

    const staleCache = { currentStep: 2, stepOptions: [{ id: 'tpl', label: 'TPL' }], status: 'completed' };

    if (researchStore.getState().status !== staleCache.status) {
      researchStore.setState(staleCache);
    }

    expect(researchStore.getState().currentStep).toBe(2);
    expect(isChatMode(researchStore.getState().currentStep)).toBe(false);
    expect(getStepContentTitle(researchStore.getState().currentStep)).toBe('Select Template');
  });

  it('with fine-grained fix: status change does NOT restore stale currentStep', () => {
    const researchStore = createResearchStore();

    researchStore.setStep(0, [{ id: 'deep', label: 'Deep', example: 'go' }]);

    expect(researchStore.getState().currentStep).toBe(0);

    const staleCache = { currentStep: 2, stepOptions: [{ id: 'tpl', label: 'TPL' }], status: 'completed' };

    if (researchStore.getState().sessionId !== 'different-session') {
      // session switch: full restore (not triggered)
    } else if (researchStore.getState().status !== staleCache.status) {
      // fine-grained: only status, progress, phases
      researchStore.setState({
        status: staleCache.status,
      });
    }

    expect(researchStore.getState().currentStep).toBe(0);
    expect(isChatMode(researchStore.getState().currentStep)).toBe(true);
  });
});

describe('End-to-end chat search scenario', () => {
  it('full happy path: sendMessage → processing → SSE chat_response', () => {
    const chatStore = createChatStore();
    const researchStore = createResearchStore();
    const streamingDoneRef = { current: false };
    const streamingMsgIdRef = { current: null as string | null };

    researchStore.setStep(0, undefined);

    expect(researchStore.getState().currentStep).toBe(0);
    expect(isChatMode(researchStore.getState().currentStep)).toBe(true);

    const chatResponse = makeChatResponseData({
      session_id: 'ses-001',
      message: '比亚迪2021-2024年毛利率分别为13.0%、17.0%、20.2%、22.3%...',
      suggestions: [
        { id: 'deep_research', label: '深度研究', example: '开始深度研究' },
      ],
    });

    simulateOnChatResponse(
      chatResponse,
      chatStore,
      researchStore,
      streamingDoneRef,
      streamingMsgIdRef,
    );

    expect(researchStore.getState().currentStep).toBe(0);
    expect(isChatMode(researchStore.getState().currentStep)).toBe(true);
    expect(streamingDoneRef.current).toBe(false);
    expect(chatStore.getMessages().filter((m) => m.role === 'assistant')).toHaveLength(1);
  });

  it('SSE replay after search completion: creates duplicate message (BUG)', () => {
    const chatStore = createChatStore();
    const researchStore = createResearchStore();
    const streamingDoneRef = { current: false };
    const streamingMsgIdRef = { current: null as string | null };

    const chatResponse = makeChatResponseData({
      session_id: 'ses-001',
      message: '比亚迪毛利率数据',
      timestamp: '2026-07-03T10:00:00',
    });

    simulateOnChatResponse(
      chatResponse,
      chatStore,
      researchStore,
      streamingDoneRef,
      streamingMsgIdRef,
    );

    expect(chatStore.getMessages().filter((m) => m.role === 'assistant')).toHaveLength(1);

    simulateOnChatResponse(
      chatResponse,
      chatStore,
      researchStore,
      streamingDoneRef,
      streamingMsgIdRef,
    );

    expect(chatStore.getMessages().filter((m) => m.role === 'assistant')).toHaveLength(2);
  });

  it('enter_framework from background: framework not set (BUG)', () => {
    const chatStore = createChatStore();
    const researchStore = createResearchStore();
    const streamingDoneRef = { current: false };
    const streamingMsgIdRef = { current: null as string | null };

    const chatResponse = makeChatResponseData({
      session_id: 'ses-001',
      message: '根据讨论，我整理了研究框架',
      action: 'enter_framework',
      mode: 'framework',
      suggestions: [{ id: 'confirm', label: '确认', example: '确认框架' }],
    });

    simulateOnChatResponse(
      chatResponse,
      chatStore,
      researchStore,
      streamingDoneRef,
      streamingMsgIdRef,
    );

    expect(researchStore.getState().currentStep).toBe(0);
    expect(researchStore.getState().framework).toBeNull();
    expect(isChatMode(researchStore.getState().currentStep)).toBe(true);

    expect(researchStore.getState().stepOptions).toHaveLength(1);
  });

  it('multiple searches in sequence: status accumulates correctly', () => {
    const chatStore = createChatStore();
    const researchStore = createResearchStore();
    const streamingDoneRef = { current: false };
    const streamingMsgIdRef = { current: null as string | null };

    researchStore.setStep(0, undefined);

    const response1 = makeChatResponseData({
      session_id: 'ses-001',
      message: '第一次搜索结果',
      suggestions: [{ id: 's1', label: '继续搜索', example: '继续' }],
    });

    simulateOnChatResponse(
      response1,
      chatStore,
      researchStore,
      streamingDoneRef,
      streamingMsgIdRef,
    );

    streamingDoneRef.current = false;

    const response2 = makeChatResponseData({
      session_id: 'ses-001',
      message: '第二次搜索结果',
      suggestions: [{ id: 's2', label: '深度研究', example: '开始研究' }],
    });

    simulateOnChatResponse(
      response2,
      chatStore,
      researchStore,
      streamingDoneRef,
      streamingMsgIdRef,
    );

    expect(researchStore.getState().currentStep).toBe(0);
    expect(isChatMode(researchStore.getState().currentStep)).toBe(true);
    expect(chatStore.getMessages().filter((m) => m.role === 'assistant')).toHaveLength(2);
  });
});
