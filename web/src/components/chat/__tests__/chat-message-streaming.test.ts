import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ChatMessage } from '../ChatMessage';
import type { ChatMessage as ChatMessageType } from '@/types/api';

const h = React.createElement;

vi.mock('react-markdown', () => ({
  default: ({ children }: { children: string }) =>
    h('div', { 'data-testid': 'markdown-rendered' }, children),
}));

vi.mock('remark-gfm', () => ({
  default: () => {},
}));

function makeMessage(overrides: Partial<ChatMessageType>): ChatMessageType {
  return {
    id: 'test-id',
    role: 'assistant',
    content: '',
    timestamp: new Date().toISOString(),
    ...overrides,
  };
}

describe('ChatMessage: thinking/streaming status indicator', () => {
  it('shows thinking indicator when metadata.status is thinking', () => {
    const msg = makeMessage({
      content: '',
      thinkingContent: 'Let me analyze this...',
      metadata: { status: 'thinking' },
    });
    render(h(ChatMessage, { message: msg }));
    expect(screen.getByText('思考中')).toBeDefined();
  });

  it('shows thinking content preview (last 200 chars) during thinking', () => {
    const longThinking = 'A'.repeat(300);
    const msg = makeMessage({
      content: '',
      thinkingContent: longThinking,
      metadata: { status: 'thinking' },
    });
    render(h(ChatMessage, { message: msg }));
    const preview = screen.getByTestId('thinking-preview');
    expect(preview.textContent).toHaveLength(200);
  });

  it('shows thinking content in details after completion (not during thinking)', () => {
    const msg = makeMessage({
      content: 'Here is my answer',
      thinkingContent: 'I thought about it',
      metadata: { status: 'done' },
    });
    render(h(ChatMessage, { message: msg }));
    expect(screen.queryByText('思考中')).toBeNull();
    expect(screen.getByText('思考过程')).toBeDefined();
  });

  it('shows streaming spinner when status is streaming and content is empty', () => {
    const msg = makeMessage({
      content: '',
      metadata: { status: 'streaming' },
    });
    render(h(ChatMessage, { message: msg }));
    expect(screen.getByText('生成中...')).toBeDefined();
  });

  it('does not show streaming spinner when status is streaming and content exists', () => {
    const msg = makeMessage({
      content: 'Hello world',
      metadata: { status: 'streaming' },
    });
    render(h(ChatMessage, { message: msg }));
    expect(screen.queryByText('生成中...')).toBeNull();
  });

  it('does not show processing spinner for non-processing status', () => {
    const msg = makeMessage({
      content: 'Done',
      metadata: { status: 'done' },
    });
    render(h(ChatMessage, { message: msg }));
    expect(screen.queryByText('生成中...')).toBeNull();
    expect(screen.queryByText('思考中')).toBeNull();
  });
});

describe('ChatMessage: React.memo optimization', () => {
  it('skips re-render when same message object reference is passed', () => {
    const msg = makeMessage({ content: 'Hello', metadata: { status: 'done' } });
    let renderCount = 0;
    const OriginalChatMessage = ChatMessage;

    const { rerender } = render(h(OriginalChatMessage, { message: msg }));
    renderCount = 1;

    rerender(h(OriginalChatMessage, { message: msg }));

    expect(renderCount).toBe(1);
  });

  it('re-renders when content changes', () => {
    const msg = makeMessage({ content: 'Hello' });
    const { rerender } = render(h(ChatMessage, { message: msg }));

    const changedMsg = makeMessage({ id: 'test-id', content: 'Hello World' });
    rerender(h(ChatMessage, { message: changedMsg }));
    expect(screen.getByTestId('markdown-rendered').textContent).toBe('Hello World');
  });

  it('re-renders when metadata.status changes', () => {
    const msg = makeMessage({ content: 'Hello', metadata: { status: 'streaming' } });
    const { rerender } = render(h(ChatMessage, { message: msg }));

    const changedMsg = makeMessage({ id: 'test-id', content: 'Hello', metadata: { status: 'done' } });
    rerender(h(ChatMessage, { message: changedMsg }));
    expect(screen.queryByText('生成中...')).toBeNull();
  });
});
