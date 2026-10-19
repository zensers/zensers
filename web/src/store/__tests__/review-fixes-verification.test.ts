import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { useChatStore } from '../useChatStore';
import { useSessionStore } from '../useSessionStore';
import type { ChatMessage } from '@/types/api';

describe('useChatStore: review fixes verification', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useSessionStore.setState({ activeId: null, sessions: {} });
    useChatStore.setState({ messages: [] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  function makeMsg(overrides: Partial<ChatMessage> = {}): ChatMessage {
    return {
      id: 'msg-1',
      role: 'assistant',
      content: '',
      timestamp: '2026-01-01T00:00:00.000Z',
      ...overrides,
    };
  }

  describe('Critical #3: updateMessage deep-merges metadata', () => {
    it('preserves existing metadata keys when updating status', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({
        id: 'm1',
        content: 'hello',
        metadata: { status: 'streaming', source: 'sse', tokenCount: 5 },
      }));
      vi.advanceTimersByTime(32);

      store.updateMessage('m1', { metadata: { status: 'done' } });

      const msg = useChatStore.getState().messages.find(m => m.id === 'm1');
      expect(msg?.metadata?.status).toBe('done');
      expect(msg?.metadata?.source).toBe('sse');
      expect(msg?.metadata?.tokenCount).toBe(5);
    });

    it('preserves existing metadata when updating content only', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({
        id: 'm1',
        content: 'hello',
        metadata: { status: 'streaming', source: 'sse' },
      }));
      vi.advanceTimersByTime(32);

      store.updateMessage('m1', { content: 'hello world' });

      const msg = useChatStore.getState().messages.find(m => m.id === 'm1');
      expect(msg?.content).toBe('hello world');
      expect(msg?.metadata?.status).toBe('streaming');
      expect(msg?.metadata?.source).toBe('sse');
    });

    it('does not crash when message has no metadata and update provides metadata', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({ id: 'm1', content: 'hello' }));
      vi.advanceTimersByTime(32);

      store.updateMessage('m1', { metadata: { status: 'done' } });

      const msg = useChatStore.getState().messages.find(m => m.id === 'm1');
      expect(msg?.metadata?.status).toBe('done');
    });

    it('does not crash when message has metadata but update has none', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({
        id: 'm1',
        content: 'hello',
        metadata: { status: 'streaming' },
      }));
      vi.advanceTimersByTime(32);

      store.updateMessage('m1', { content: 'updated' });

      const msg = useChatStore.getState().messages.find(m => m.id === 'm1');
      expect(msg?.content).toBe('updated');
      expect(msg?.metadata?.status).toBe('streaming');
    });

    it('overwrites metadata value when both have same key', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({
        id: 'm1',
        content: 'hello',
        metadata: { status: 'thinking', source: 'sse' },
      }));
      vi.advanceTimersByTime(32);

      store.updateMessage('m1', { metadata: { status: 'streaming' } });

      const msg = useChatStore.getState().messages.find(m => m.id === 'm1');
      expect(msg?.metadata?.status).toBe('streaming');
      expect(msg?.metadata?.source).toBe('sse');
    });
  });

  describe('Critical #2: late tokens after streamingDoneRef are dropped', () => {
    it('appendStreamToken after clearMessages does not resurrect old message', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({ id: 'm1', content: 'hello' }));
      vi.advanceTimersByTime(32);

      store.clearMessages();
      expect(useChatStore.getState().messages).toHaveLength(0);

      store.appendStreamToken('m1', ' late token', '');
      vi.advanceTimersByTime(32);

      const msgs = useChatStore.getState().messages;
      expect(msgs).toHaveLength(0);
    });
  });

  describe('flushSyncNow: beforeunload/visibilitychange safety', () => {
    it('flushSyncNow flushes pending buffer then syncs', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({ id: 'm1', content: '' }));
      vi.advanceTimersByTime(32);

      store.appendStreamToken('m1', 'buffered content', '');

      const syncSpy = vi.spyOn(useSessionStore.getState(), 'syncActive');

      store.flushSyncNow();

      const msg = useChatStore.getState().messages.find(m => m.id === 'm1');
      expect(msg?.content).toBe('buffered content');
      expect(syncSpy).toHaveBeenCalled();

      syncSpy.mockRestore();
    });

    it('flushSyncNow is safe when no buffer exists', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({ id: 'm1', content: 'hello' }));
      vi.advanceTimersByTime(32);

      expect(() => store.flushSyncNow()).not.toThrow();
    });
  });

  describe('thinking/streaming state transitions', () => {
    it('thinking -> streaming transition preserves thinkingContent', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({
        id: 'm1',
        content: '',
        thinkingContent: 'I am thinking',
        metadata: { status: 'thinking' },
      }));
      vi.advanceTimersByTime(32);

      store.updateMessage('m1', { metadata: { status: 'streaming' } });

      const msg = useChatStore.getState().messages.find(m => m.id === 'm1');
      expect(msg?.metadata?.status).toBe('streaming');
      expect(msg?.thinkingContent).toBe('I am thinking');
    });

    it('streaming -> thinking transition preserves content', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({
        id: 'm1',
        content: 'Hello',
        metadata: { status: 'streaming' },
      }));
      vi.advanceTimersByTime(32);

      store.updateMessage('m1', { metadata: { status: 'thinking' } });

      const msg = useChatStore.getState().messages.find(m => m.id === 'm1');
      expect(msg?.metadata?.status).toBe('thinking');
      expect(msg?.content).toBe('Hello');
    });

    it('streaming -> done transition preserves thinkingContent', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({
        id: 'm1',
        content: 'Final answer',
        thinkingContent: 'My reasoning',
        metadata: { status: 'streaming', source: 'sse' },
      }));
      vi.advanceTimersByTime(32);

      store.updateMessage('m1', { metadata: { status: 'done' } });

      const msg = useChatStore.getState().messages.find(m => m.id === 'm1');
      expect(msg?.metadata?.status).toBe('done');
      expect(msg?.metadata?.source).toBe('sse');
      expect(msg?.thinkingContent).toBe('My reasoning');
      expect(msg?.content).toBe('Final answer');
    });
  });

  describe('addMessage dedup', () => {
    it('does not add duplicate message with same role+content+timestamp', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      const msg = makeMsg({ id: 'm1', content: 'hello', timestamp: '2026-01-01T00:00:00.000Z' });
      store.addMessage(msg);
      store.addMessage({ ...msg, id: 'm2' });

      expect(useChatStore.getState().messages).toHaveLength(1);
    });
  });
});
