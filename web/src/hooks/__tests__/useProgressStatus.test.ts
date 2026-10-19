import { describe, expect, it, vi } from 'vitest';
import { applyStatusToStore } from '../useProgress';

function makeStore() {
  return {
    setStatus: vi.fn(),
    setProgress: vi.fn(),
    updatePhase: vi.fn(),
  } as any;
}

describe('progress status mapping', () => {
  it.each(['cancelled', 'paused'])('keeps %s recoverable as paused', (status) => {
    const store = makeStore();
    applyStatusToStore(status, 42, store);
    expect(store.setStatus).toHaveBeenCalledWith('paused');
    expect(store.setProgress).toHaveBeenCalledWith(0.42);
  });

  it('maps pausing to the single user-facing paused state', () => {
    const store = makeStore();
    applyStatusToStore('pausing', 21, store);
    expect(store.setStatus).toHaveBeenCalledWith('paused');
    expect(store.setProgress).toHaveBeenCalledWith(0.21);
  });

  it('keeps resuming as the running state', () => {
    const store = makeStore();
    applyStatusToStore('resuming', 21, store);
    expect(store.setStatus).toHaveBeenCalledWith('running');
    expect(store.setProgress).toHaveBeenCalledWith(0.21);
  });

  it('normalizes REST percentage progress before storing it', () => {
    const store = makeStore();
    applyStatusToStore('running', 42, store);
    expect(store.setProgress).toHaveBeenCalledWith(0.42);
  });
});
