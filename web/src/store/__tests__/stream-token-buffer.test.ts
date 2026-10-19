import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { useChatStore } from '../useChatStore';
import { useSessionStore } from '../useSessionStore';
import type { ChatMessage } from '@/types/api';

describe('useChatStore: appendStreamToken + debounced sync', () => {
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
      id: 'stream-1',
      role: 'assistant',
      content: '',
      timestamp: '2026-01-01T00:00:00.000Z',
      ...overrides,
    };
  }

  it('appendStreamToken adds content to existing message after flush', () => {
    const store = useChatStore.getState();
    const sid = 'ses_test';
    useSessionStore.getState().createSession(sid, 'test');

    store.addMessage(makeMsg({ id: 'm1', content: 'Hello' }));
    expect(useChatStore.getState().messages[0].content).toBe('Hello');

    store.appendStreamToken('m1', ' World', '');
    vi.advanceTimersByTime(32);
    expect(useChatStore.getState().messages[0].content).toBe('Hello World');
  });

  it('appendStreamToken adds thinkingContent to existing message after flush', () => {
    const store = useChatStore.getState();
    const sid = 'ses_test';
    useSessionStore.getState().createSession(sid, 'test');

    store.addMessage(makeMsg({ id: 'm1', content: '', thinkingContent: 'think' }));
    store.appendStreamToken('m1', '', ' more');
    vi.advanceTimersByTime(32);
    expect(useChatStore.getState().messages[0].thinkingContent).toBe('think more');
  });

  it('appendStreamToken batches multiple tokens into single update', () => {
    const store = useChatStore.getState();
    const sid = 'ses_test';
    useSessionStore.getState().createSession(sid, 'test');

    store.addMessage(makeMsg({ id: 'm1', content: '' }));

    let renderCount = 0;
    const unsub = useChatStore.subscribe(() => { renderCount++; });

    store.appendStreamToken('m1', 'a', '');
    store.appendStreamToken('m1', 'b', '');
    store.appendStreamToken('m1', 'c', '');

    expect(renderCount).toBe(0);

    vi.advanceTimersByTime(32);

    expect(useChatStore.getState().messages[0].content).toBe('abc');
    expect(renderCount).toBe(1);

    unsub();
  });

  it('appendStreamToken does not trigger syncActive on every call (debounced)', () => {
    const store = useChatStore.getState();
    const sid = 'ses_test';
    useSessionStore.getState().createSession(sid, 'test');

    store.addMessage(makeMsg({ id: 'm1', content: '' }));
    vi.advanceTimersByTime(32);

    const syncSpy = vi.spyOn(useSessionStore.getState(), 'syncActive');

    store.appendStreamToken('m1', 'x', '');
    store.appendStreamToken('m1', 'y', '');
    store.appendStreamToken('m1', 'z', '');
    vi.advanceTimersByTime(32);

    expect(syncSpy).toHaveBeenCalledTimes(0);

    vi.advanceTimersByTime(500);

    expect(syncSpy).toHaveBeenCalled();
    const calls = syncSpy.mock.calls.length;
    expect(calls).toBeGreaterThanOrEqual(1);
    expect(calls).toBeLessThanOrEqual(2);

    syncSpy.mockRestore();
  });

  it('flushSyncNow forces immediate sync bypassing debounce', () => {
    const store = useChatStore.getState();
    const sid = 'ses_test';
    useSessionStore.getState().createSession(sid, 'test');

    store.addMessage(makeMsg({ id: 'm1', content: '' }));
    vi.advanceTimersByTime(32);

    store.appendStreamToken('m1', 'urgent', '');
    vi.advanceTimersByTime(32);

    const syncSpy = vi.spyOn(useSessionStore.getState(), 'syncActive');

    store.flushSyncNow();

    expect(syncSpy.mock.calls.length).toBeGreaterThanOrEqual(1);

    syncSpy.mockRestore();
  });

  it('updateMessage flushes pending token buffer before applying update', () => {
    const store = useChatStore.getState();
    const sid = 'ses_test';
    useSessionStore.getState().createSession(sid, 'test');

    store.addMessage(makeMsg({ id: 'm1', content: '' }));
    vi.advanceTimersByTime(32);

    store.appendStreamToken('m1', 'partial ', '');
    store.updateMessage('m1', { content: 'FINAL', metadata: { status: 'done' } });

    expect(useChatStore.getState().messages[0].content).toBe('FINAL');
    expect(useChatStore.getState().messages[0].metadata?.status).toBe('done');
  });

  it('addMessage uses immediate sync (not debounced)', () => {
    const store = useChatStore.getState();
    const sid = 'ses_test';
    useSessionStore.getState().createSession(sid, 'test');

    const syncSpy = vi.spyOn(useSessionStore.getState(), 'syncActive');

    store.addMessage(makeMsg({ id: 'm1', content: 'hello' }));

    expect(syncSpy).toHaveBeenCalled();
    expect(syncSpy.mock.calls.length).toBeGreaterThanOrEqual(1);

    syncSpy.mockRestore();
  });

  it('clearMessages clears token buffer and uses immediate sync', () => {
    const store = useChatStore.getState();
    const sid = 'ses_test';
    useSessionStore.getState().createSession(sid, 'test');

    store.addMessage(makeMsg({ id: 'm1', content: '' }));
    vi.advanceTimersByTime(32);

    store.appendStreamToken('m1', 'buffered', '');

    store.clearMessages();

    expect(useChatStore.getState().messages).toHaveLength(0);
  });

  it('appendStreamToken with different id flushes previous buffer first', () => {
    const store = useChatStore.getState();
    const sid = 'ses_test';
    useSessionStore.getState().createSession(sid, 'test');

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

  it('appendStreamToken handles content + thinking simultaneously', () => {
    const store = useChatStore.getState();
    const sid = 'ses_test';
    useSessionStore.getState().createSession(sid, 'test');

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
