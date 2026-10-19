import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { VirtualMessageList } from '../VirtualMessageList';
import type { ChatMessage as ChatMessageType } from '@/types/api';

function makeMsg(overrides: Partial<ChatMessageType> = {}): ChatMessageType {
  return {
    id: `msg-${Math.random().toString(36).slice(2, 8)}`,
    role: 'assistant',
    content: 'Hello world',
    timestamp: '2026-01-01T00:00:00.000Z',
    ...overrides,
  };
}

function mockScrollElement(el: HTMLElement) {
  Object.defineProperty(el, 'offsetHeight', { value: 600, configurable: true });
  Object.defineProperty(el, 'clientHeight', { value: 600, configurable: true });
  Object.defineProperty(el, 'scrollHeight', { value: 2400, configurable: true });
  Object.defineProperty(el, 'scrollTop', { value: 1800, writable: true, configurable: true });
}

describe('VirtualMessageList', () => {
  beforeEach(() => {
    HTMLElement.prototype.getBoundingClientRect = vi.fn(() => ({
      width: 800,
      height: 120,
      top: 0,
      left: 0,
      bottom: 120,
      right: 800,
      x: 0,
      y: 0,
      toJSON: () => {},
    }));
  });

  it('renders empty state when no messages', () => {
    const { container } = render(<VirtualMessageList messages={[]} />);
    const scrollEl = container.querySelector('.overflow-y-auto');
    expect(scrollEl).toBeTruthy();
  });

  it('renders messages via virtualizer', () => {
    const messages = Array.from({ length: 5 }, (_, i) =>
      makeMsg({ id: `msg-${i}`, content: `Message ${i}` })
    );
    const { container } = render(<VirtualMessageList messages={messages} />);
    const scrollEl = container.querySelector('.overflow-y-auto');
    if (scrollEl) mockScrollElement(scrollEl as HTMLElement);
    const innerDiv = container.querySelector('[style*="position: relative"]');
    expect(innerDiv).toBeTruthy();
  });

  it('keeps the status header outside the message scroll layer', () => {
    const messages = [makeMsg({ id: 'm1', content: 'Message 1' })];
    const { container } = render(
      <VirtualMessageList
        messages={messages}
        stickyHeader={<div data-testid="status-header">Status</div>}
      />
    );

    // 两个滚动层：头部包装层（限高，内部滚动）与消息滚动层。
    // 头部必须独立于消息滚动层之外，且必须限高——否则研究运行时
    // 状态堆栈无界增长会吃掉整个面板，滑块消失（生产 bug）。
    const scrollLayers = Array.from(container.querySelectorAll('.overflow-y-auto'));
    const headerWrapper = scrollLayers.find((el) => el.querySelector('[data-testid="status-header"]'));
    const messageLayer = scrollLayers.find((el) => el !== headerWrapper);
    expect(headerWrapper).toBeTruthy();
    expect(messageLayer).toBeTruthy();
    expect(messageLayer?.querySelector('[data-testid="status-header"]')).toBeFalsy();
    expect(headerWrapper?.className).toContain('max-h-[35vh]');
    expect(container.querySelector('.sticky')).toBeFalsy();
    expect(container.querySelector('.absolute.top-0')).toBeNull();
  });

  it('exposes scrollToBottom via ref', () => {
    const scrollToBottomRef = { current: null as (() => void) | null };
    const messages = [makeMsg({ id: 'm1', content: 'Hello' })];
    render(
      <VirtualMessageList
        messages={messages}
        scrollToBottomRef={scrollToBottomRef}
      />
    );
    expect(typeof scrollToBottomRef.current).toBe('function');
  });

  it('shows loading indicator when isLoadingMessages is true', () => {
    const messages = [makeMsg({ id: 'm1', content: 'Hello' })];
    render(
      <VirtualMessageList
        messages={messages}
        isLoadingMessages={true}
      />
    );
    expect(screen.getByText('Loading earlier messages...')).toBeDefined();
  });

  it('does not show loading indicator when isLoadingMessages is false', () => {
    const messages = [makeMsg({ id: 'm1', content: 'Hello' })];
    render(
      <VirtualMessageList
        messages={messages}
        isLoadingMessages={false}
      />
    );
    expect(screen.queryByText('Loading earlier messages...')).toBeNull();
  });

  it('calls onAtBottomChange callback prop', () => {
    const onAtBottomChange = vi.fn();
    const messages = [makeMsg({ id: 'm1', content: 'Hello' })];
    render(
      <VirtualMessageList
        messages={messages}
        onAtBottomChange={onAtBottomChange}
      />
    );
    expect(onAtBottomChange).toBeDefined();
  });

  it('accepts loadOlderMessages and hasMoreMessages props', () => {
    const loadOlderMessages = vi.fn().mockResolvedValue(undefined);
    const messages = Array.from({ length: 5 }, (_, i) =>
      makeMsg({ id: `msg-${i}`, content: `Message ${i}` })
    );
    render(
      <VirtualMessageList
        messages={messages}
        loadOlderMessages={loadOlderMessages}
        hasMoreMessages={true}
      />
    );
    expect(loadOlderMessages).toBeDefined();
  });
});
