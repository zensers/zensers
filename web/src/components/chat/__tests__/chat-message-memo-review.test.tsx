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

describe('Strict review: ChatMessage correctness', () => {
  it('re-renders when metadata.status changes from thinking to streaming', () => {
    const { rerender } = render(
      <ChatMessage message={makeMessage({ metadata: { status: 'thinking' }, thinkingContent: 'hmm' })} />
    );
    expect(screen.getByText('思考中')).toBeDefined();

    rerender(
      <ChatMessage message={makeMessage({ metadata: { status: 'streaming' }, thinkingContent: 'hmm', content: 'Hello' })} />
    );
    expect(screen.queryByText('思考中')).toBeNull();
    expect(screen.getByText('思考过程')).toBeDefined();
  });

  it('shows streaming indicator when status is streaming and content is empty', () => {
    render(
      <ChatMessage message={makeMessage({ metadata: { status: 'streaming' }, content: '' })} />
    );
    expect(screen.getByText('生成中...')).toBeDefined();
  });

  it('does not show streaming indicator when status is streaming but content exists', () => {
    render(
      <ChatMessage message={makeMessage({ metadata: { status: 'streaming' }, content: 'Hello' })} />
    );
    expect(screen.queryByText('生成中...')).toBeNull();
  });

  it('shows thinking preview with last 200 chars', () => {
    const longThinking = 'A'.repeat(300);
    render(
      <ChatMessage message={makeMessage({ metadata: { status: 'thinking' }, thinkingContent: longThinking })} />
    );
    const preview = screen.getByTestId('thinking-preview');
    expect(preview.textContent).toBe('A'.repeat(200));
  });

  it('shows thinking preview when thinkingContent is short', () => {
    render(
      <ChatMessage message={makeMessage({ metadata: { status: 'thinking' }, thinkingContent: 'short' })} />
    );
    const preview = screen.getByTestId('thinking-preview');
    expect(preview.textContent).toBe('short');
  });

  it('memo blocks re-render when only metadata non-status key changes', () => {
    const renderSpy = vi.fn();
    const OriginalChatMessage = ChatMessage;

    const { rerender } = render(
      <OriginalChatMessage message={makeMessage({
        id: 'm1',
        content: 'hello',
        metadata: { status: 'streaming', source: 'sse' },
      })} />
    );

    const firstRenderCount = screen.queryAllByText('hello').length;

    rerender(
      <OriginalChatMessage message={makeMessage({
        id: 'm1',
        content: 'hello',
        metadata: { status: 'streaming', source: 'websocket' },
      })} />
    );

    expect(screen.getAllByText('hello').length).toBe(firstRenderCount);
  });

  it('memo allows re-render when role changes', () => {
    const { rerender } = render(
      <ChatMessage message={makeMessage({ id: 'm1', role: 'assistant', content: 'hello' })} />
    );
    expect(screen.getByText('hello')).toBeDefined();

    rerender(
      <ChatMessage message={makeMessage({ id: 'm1', role: 'user', content: 'hello' })} />
    );
    expect(screen.getByText('hello')).toBeDefined();
  });

  it('renders agent message with searching action', () => {
    render(
      <ChatMessage message={makeMessage({
        role: 'agent',
        content: 'Searching web...',
        agent: { id: 'search-1', name: 'WebSearch', action: 'searching' },
      })} />
    );
    expect(screen.getByText('WebSearch:')).toBeDefined();
    expect(screen.getByText('Searching web...')).toBeDefined();
  });

  it('renders agent heartbeat message as null', () => {
    render(
      <ChatMessage message={makeMessage({
        role: 'agent',
        content: 'still working...',
        agent: { id: 'hb', name: '', action: 'heartbeat' },
      })} />
    );
    expect(screen.queryByText('still working...')).toBeNull();
  });

  it('shows completed thinking in details when status is not thinking', () => {
    render(
      <ChatMessage message={makeMessage({
        content: 'Final answer',
        thinkingContent: 'My reasoning process',
        metadata: { status: 'done' },
      })} />
    );
    expect(screen.getByText('思考过程')).toBeDefined();
    expect(screen.getByText('My reasoning process')).toBeDefined();
  });

  it('does not show thinking indicator when status is done with thinkingContent', () => {
    render(
      <ChatMessage message={makeMessage({
        content: 'Final answer',
        thinkingContent: 'My reasoning',
        metadata: { status: 'done' },
      })} />
    );
    expect(screen.queryByText('思考中')).toBeNull();
  });
});
