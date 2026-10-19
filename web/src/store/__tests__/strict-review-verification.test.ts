import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { useChatStore } from '../../store/useChatStore';
import { useSessionStore } from '../../store/useSessionStore';
import type { ChatMessage as ChatMessageType } from '@/types/api';

function makeMsg(overrides: Partial<ChatMessageType> = {}): ChatMessageType {
  return {
    id: 'msg-1',
    role: 'assistant',
    content: '',
    timestamp: '2026-01-01T00:00:00.000Z',
    ...overrides,
  };
}

describe('Strict review: store-level correctness', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useSessionStore.setState({ activeId: null, sessions: {} });
    useChatStore.setState({ messages: [] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('flushTokenBuffer uses useChatStore.getState/setState (not stale closure)', () => {
    it('flushTokenBuffer works correctly after store state is reset', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({ id: 'm1', content: '' }));
      vi.advanceTimersByTime(32);

      store.appendStreamToken('m1', 'token1', '');
      vi.advanceTimersByTime(32);

      expect(useChatStore.getState().messages.find(m => m.id === 'm1')?.content).toBe('token1');

      useChatStore.setState({ messages: [] });
      vi.advanceTimersByTime(32);

      store.addMessage(makeMsg({ id: 'm2', content: '' }));
      vi.advanceTimersByTime(32);

      store.appendStreamToken('m2', 'token2', '');
      vi.advanceTimersByTime(32);

      expect(useChatStore.getState().messages.find(m => m.id === 'm2')?.content).toBe('token2');
    });

    it('appendStreamToken after updateMessage still flushes correctly', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({ id: 'm1', content: '', metadata: { status: 'thinking' } }));
      vi.advanceTimersByTime(32);

      store.updateMessage('m1', { metadata: { status: 'streaming' } });

      const msg = useChatStore.getState().messages.find(m => m.id === 'm1');
      expect(msg?.metadata?.status).toBe('streaming');

      store.appendStreamToken('m1', 'Hello', '');
      vi.advanceTimersByTime(32);

      const msg2 = useChatStore.getState().messages.find(m => m.id === 'm1');
      expect(msg2?.content).toBe('Hello');
      expect(msg2?.metadata?.status).toBe('streaming');
    });
  });

  describe('updateMessage deep merge: edge cases', () => {
    it('merges nested metadata keys correctly when both sides have unique keys', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({
        id: 'm1',
        content: 'hello',
        metadata: { status: 'streaming', source: 'sse', retryCount: 0 },
      }));
      vi.advanceTimersByTime(32);

      store.updateMessage('m1', { metadata: { status: 'done', finalTokenCount: 42 } });

      const msg = useChatStore.getState().messages.find(m => m.id === 'm1');
      expect(msg?.metadata?.status).toBe('done');
      expect(msg?.metadata?.source).toBe('sse');
      expect(msg?.metadata?.retryCount).toBe(0);
      expect(msg?.metadata?.finalTokenCount).toBe(42);
    });

    it('overwrites metadata values when keys conflict', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({
        id: 'm1',
        content: 'hello',
        metadata: { status: 'streaming', tokenCount: 5 },
      }));
      vi.advanceTimersByTime(32);

      store.updateMessage('m1', { metadata: { tokenCount: 10 } });

      const msg = useChatStore.getState().messages.find(m => m.id === 'm1');
      expect(msg?.metadata?.tokenCount).toBe(10);
      expect(msg?.metadata?.status).toBe('streaming');
    });
  });

  describe('concurrent token buffering scenarios', () => {
    it('appendStreamToken for different IDs flushes previous buffer first', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({ id: 'm1', content: 'A' }));
      store.addMessage(makeMsg({ id: 'm2', content: 'B' }));
      vi.advanceTimersByTime(32);

      store.appendStreamToken('m1', '+1', '');
      store.appendStreamToken('m2', '+2', '');
      vi.advanceTimersByTime(32);

      const msgs = useChatStore.getState().messages;
      expect(msgs.find(m => m.id === 'm1')?.content).toBe('A+1');
      expect(msgs.find(m => m.id === 'm2')?.content).toBe('B+2');
    });

    it('rapid appendStreamToken + updateMessage does not lose data', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({ id: 'm1', content: '', metadata: { status: 'streaming' } }));
      vi.advanceTimersByTime(32);

      store.appendStreamToken('m1', 'Hello ', '');
      store.appendStreamToken('m1', 'World', '');
      store.updateMessage('m1', { content: 'Hello World!', metadata: { status: 'done' } });

      const msg = useChatStore.getState().messages.find(m => m.id === 'm1');
      expect(msg?.content).toBe('Hello World!');
      expect(msg?.metadata?.status).toBe('done');
    });

    it('thinkingContent accumulates correctly via appendStreamToken', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({ id: 'm1', content: '', thinkingContent: '', metadata: { status: 'thinking' } }));
      vi.advanceTimersByTime(32);

      store.appendStreamToken('m1', '', 'Let me ');
      store.appendStreamToken('m1', '', 'think ');
      store.appendStreamToken('m1', '', 'about this');
      vi.advanceTimersByTime(32);

      const msg = useChatStore.getState().messages.find(m => m.id === 'm1');
      expect(msg?.thinkingContent).toBe('Let me think about this');
    });

    it('content and thinkingContent accumulate simultaneously', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({ id: 'm1', content: '', thinkingContent: '' }));
      vi.advanceTimersByTime(32);

      store.appendStreamToken('m1', 'text ', 'think ');
      store.appendStreamToken('m1', 'more', 'deep');
      vi.advanceTimersByTime(32);

      const msg = useChatStore.getState().messages.find(m => m.id === 'm1');
      expect(msg?.content).toBe('text more');
      expect(msg?.thinkingContent).toBe('think deep');
    });
  });

  describe('clearMessages clears all buffers', () => {
    it('clearMessages cancels pending RAF and clears token buffer', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({ id: 'm1', content: '' }));
      vi.advanceTimersByTime(32);

      store.appendStreamToken('m1', 'buffered', '');
      store.clearMessages();

      expect(useChatStore.getState().messages).toHaveLength(0);

      vi.advanceTimersByTime(32);
      expect(useChatStore.getState().messages).toHaveLength(0);
    });
  });

  describe('flushSyncNow edge cases', () => {
    it('flushSyncNow when both buffer and debounce timer are pending', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({ id: 'm1', content: '' }));
      vi.advanceTimersByTime(32);

      store.appendStreamToken('m1', 'data', '');
      vi.advanceTimersByTime(32);

      store.appendStreamToken('m1', ' more', '');
      store.flushSyncNow();

      const msg = useChatStore.getState().messages.find(m => m.id === 'm1');
      expect(msg?.content).toBe('data more');

      const syncSpy = vi.spyOn(useSessionStore.getState(), 'syncActive');
      vi.advanceTimersByTime(600);
      const syncCalls = syncSpy.mock.calls.length;
      expect(syncCalls).toBeLessThanOrEqual(1);
      syncSpy.mockRestore();
    });

    it('flushSyncNow is idempotent when called multiple times', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({ id: 'm1', content: '' }));
      vi.advanceTimersByTime(32);

      store.flushSyncNow();
      store.flushSyncNow();
      store.flushSyncNow();

      expect(useChatStore.getState().messages).toHaveLength(1);
    });
  });

  describe('prependMessages flushes buffer first', () => {
    it('prependMessages flushes pending token buffer before prepending', () => {
      const sid = 'ses_test';
      useSessionStore.getState().createSession(sid, 'test');

      const store = useChatStore.getState();
      store.addMessage(makeMsg({ id: 'm1', content: 'current' }));
      vi.advanceTimersByTime(32);

      store.appendStreamToken('m1', ' buffered', '');

      const olderMsg = makeMsg({ id: 'older', content: 'older message', timestamp: '2025-12-31T00:00:00.000Z' });
      store.prependMessages([olderMsg]);

      const msgs = useChatStore.getState().messages;
      expect(msgs.find(m => m.id === 'm1')?.content).toBe('current buffered');
      expect(msgs.find(m => m.id === 'older')).toBeDefined();
    });
  });
});
