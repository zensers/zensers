import { describe, it, expect, beforeEach } from 'vitest';
import { useChatStore } from '../useChatStore';
import { useSessionStore } from '../useSessionStore';
import type { ChatMessage } from '@/types/api';

describe('addMessage deduplication', () => {
  beforeEach(() => {
    useSessionStore.setState({ activeId: null, sessions: {} });
    useChatStore.setState({ messages: [] });
  });

  it('addMessage skips duplicate message (same role+content+timestamp)', () => {
    const store = useChatStore.getState();
    const msg: ChatMessage = {
      id: 'msg1',
      role: 'assistant',
      content: 'Hello',
      timestamp: '2026-01-01T00:00:00.000Z',
    };
    store.addMessage(msg);
    expect(useChatStore.getState().messages).toHaveLength(1);

    const dup: ChatMessage = {
      id: 'msg2',
      role: 'assistant',
      content: 'Hello',
      timestamp: '2026-01-01T00:00:00.000Z',
    };
    store.addMessage(dup);
    expect(useChatStore.getState().messages).toHaveLength(1);
  });

  it('addMessage allows same content with different timestamp', () => {
    const store = useChatStore.getState();
    const msg1: ChatMessage = {
      id: 'msg1',
      role: 'assistant',
      content: 'Hello',
      timestamp: '2026-01-01T00:00:00.000Z',
    };
    store.addMessage(msg1);

    const msg2: ChatMessage = {
      id: 'msg2',
      role: 'assistant',
      content: 'Hello',
      timestamp: '2026-01-01T00:01:00.000Z',
    };
    store.addMessage(msg2);
    expect(useChatStore.getState().messages).toHaveLength(2);
  });

  it('addMessage allows same content with different role', () => {
    const store = useChatStore.getState();
    const userMsg: ChatMessage = {
      id: 'msg1',
      role: 'user',
      content: 'Hello',
      timestamp: '2026-01-01T00:00:00.000Z',
    };
    store.addMessage(userMsg);

    const assistantMsg: ChatMessage = {
      id: 'msg2',
      role: 'assistant',
      content: 'Hello',
      timestamp: '2026-01-01T00:00:00.000Z',
    };
    store.addMessage(assistantMsg);
    expect(useChatStore.getState().messages).toHaveLength(2);
  });

  it('prevents SSE replay duplicate when timestamps match backend', () => {
    const store = useChatStore.getState();
    const backendTimestamp = '2026-07-09T09:10:00.000Z';

    const httpMsg: ChatMessage = {
      id: 'http1',
      role: 'assistant',
      content: 'Research results found.',
      timestamp: backendTimestamp,
    };
    store.addMessage(httpMsg);
    expect(useChatStore.getState().messages).toHaveLength(1);

    const sseMsg: ChatMessage = {
      id: 'sse1',
      role: 'assistant',
      content: 'Research results found.',
      timestamp: backendTimestamp,
    };
    store.addMessage(sseMsg);
    expect(useChatStore.getState().messages).toHaveLength(1);
  });

  it('deduplicates paged messages when the backend changes the local id', () => {
    const store = useChatStore.getState();
    store.addMessage({
      id: 'live-1', role: 'assistant', content: 'Paged answer',
      timestamp: '2026-01-01T00:00:00.000Z',
    });

    store.prependMessages([{
      id: 'history-99', role: 'assistant', content: 'Paged answer',
      timestamp: '2026-01-01T00:00:00.000Z',
    }]);

    expect(useChatStore.getState().messages).toHaveLength(1);
    expect(useChatStore.getState().messages[0].id).toBe('live-1');
  });

  it('deduplicates paged messages by response id', () => {
    const store = useChatStore.getState();
    store.addMessage({
      id: 'live-2', role: 'assistant', content: 'Old answer',
      timestamp: '2026-01-01T00:00:00.000Z',
      metadata: { responseId: 'response-1', status: 'streaming' },
    });

    store.prependMessages([{
      id: 'history-100', role: 'assistant', content: 'Final answer',
      timestamp: '2026-01-01T00:00:01.000Z',
      metadata: { responseId: 'response-1', status: 'done' },
    }]);

    expect(useChatStore.getState().messages).toHaveLength(1);
    expect(useChatStore.getState().messages[0]).toMatchObject({
      id: 'live-2', content: 'Old answer', metadata: { responseId: 'response-1' },
    });
  });
});
