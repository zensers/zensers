import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useSessionStream } from '../useProgress';
import { sseManager } from '@/lib/sse';
import { useSessionStore } from '@/store/useSessionStore';

describe('useSessionStream session ownership', () => {
  let callbacks: any[];
  let unsubscribe: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    callbacks = [];
    unsubscribe = vi.fn();
    useSessionStore.setState({ activeId: 'ses-current', sessions: {} });
    vi.spyOn(sseManager, 'subscribeSession').mockImplementation((...args: any[]) => {
      callbacks = args;
      return unsubscribe as unknown as () => void;
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('drops events for another session even when the subscription is still alive', () => {
    const onResponse = vi.fn();
    renderHook(() => useSessionStream('ses-current', { onChatResponse: onResponse }));

    callbacks[1]({
      session_id: 'ses-old', message: 'old', action: 'continue_chat', timestamp: 't1',
    });
    expect(onResponse).not.toHaveBeenCalled();

    callbacks[1]({
      session_id: 'ses-current', message: 'current', action: 'continue_chat', timestamp: 't2',
    });
    expect(onResponse).toHaveBeenCalledTimes(1);
  });

  it('drops queued events after the active session changes', () => {
    const onResponse = vi.fn();
    const { unmount } = renderHook(() => useSessionStream('ses-current', { onChatResponse: onResponse }));

    useSessionStore.setState({ activeId: 'ses-new' });
    callbacks[1]({
      session_id: 'ses-current', message: 'late', action: 'continue_chat', timestamp: 't3',
    });

    expect(onResponse).not.toHaveBeenCalled();
    unmount();
    expect(unsubscribe).toHaveBeenCalled();
  });
});
