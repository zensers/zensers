import { describe, it, expect, beforeEach } from 'vitest';
import { useSessionStore } from '../useSessionStore';
import type { ChatMessage } from '@/types/api';

describe('Bug 1: createSession initialMessages', () => {
  beforeEach(() => {
    useSessionStore.setState({ activeId: null, sessions: {} });
  });

  it('createSession without initialMessages falls back to __pending__ messages', () => {
    const store = useSessionStore.getState();
    const userMsg: ChatMessage = {
      id: 'msg1',
      role: 'user',
      content: '比亚迪财务分析',
      timestamp: new Date().toISOString(),
    };
    store.syncActive({ messages: [userMsg] });
    expect(useSessionStore.getState().activeId).toBe('__pending__');
    expect(useSessionStore.getState().sessions['__pending__']?.messages).toHaveLength(1);

    store.createSession('ses_001', '比亚迪财务分析');
    expect(useSessionStore.getState().sessions['ses_001']?.messages).toHaveLength(1);
    expect(useSessionStore.getState().sessions['ses_001']?.messages[0].content).toBe('比亚迪财务分析');
    expect(useSessionStore.getState().sessions['__pending__']).toBeUndefined();
  });

  it('createSession with initialMessages uses provided messages directly', () => {
    const store = useSessionStore.getState();
    const userMsg: ChatMessage = {
      id: 'msg1',
      role: 'user',
      content: '比亚迪财务分析',
      timestamp: new Date().toISOString(),
    };
    const assistantMsg: ChatMessage = {
      id: 'msg2',
      role: 'assistant',
      content: '正在搜索...',
      timestamp: new Date().toISOString(),
    };

    store.createSession('ses_001', '比亚迪财务分析', [userMsg, assistantMsg]);
    expect(useSessionStore.getState().sessions['ses_001']?.messages).toHaveLength(2);
    expect(useSessionStore.getState().sessions['ses_001']?.messages[0].role).toBe('user');
    expect(useSessionStore.getState().sessions['ses_001']?.messages[1].role).toBe('assistant');
  });

  it('createSession with initialMessages overrides __pending__ messages', () => {
    const store = useSessionStore.getState();
    const pendingMsg: ChatMessage = {
      id: 'pending1',
      role: 'user',
      content: 'pending message',
      timestamp: new Date().toISOString(),
    };
    store.syncActive({ messages: [pendingMsg] });

    const initialMsg: ChatMessage = {
      id: 'init1',
      role: 'user',
      content: '比亚迪财务分析',
      timestamp: new Date().toISOString(),
    };

    store.createSession('ses_001', '比亚迪财务分析', [initialMsg]);
    expect(useSessionStore.getState().sessions['ses_001']?.messages).toHaveLength(1);
    expect(useSessionStore.getState().sessions['ses_001']?.messages[0].content).toBe('比亚迪财务分析');
  });

  it('createSession with empty initialMessages falls back to __pending__', () => {
    const store = useSessionStore.getState();
    const userMsg: ChatMessage = {
      id: 'msg1',
      role: 'user',
      content: 'test',
      timestamp: new Date().toISOString(),
    };
    store.syncActive({ messages: [userMsg] });

    store.createSession('ses_001', 'test', []);
    expect(useSessionStore.getState().sessions['ses_001']?.messages).toHaveLength(1);
    expect(useSessionStore.getState().sessions['ses_001']?.messages[0].content).toBe('test');
  });

  it('createSession with empty initialMessages and no __pending__ creates empty session', () => {
    const store = useSessionStore.getState();
    store.createSession('ses_001', 'new session', []);
    expect(useSessionStore.getState().sessions['ses_001']?.messages).toHaveLength(0);
  });

  it('createSession backward compat: no initialMessages param works like before', () => {
    const store = useSessionStore.getState();
    const userMsg: ChatMessage = {
      id: 'msg1',
      role: 'user',
      content: 'compat test',
      timestamp: new Date().toISOString(),
    };
    store.syncActive({ messages: [userMsg] });

    store.createSession('ses_001', 'compat test');
    expect(useSessionStore.getState().sessions['ses_001']?.messages).toHaveLength(1);
  });
});