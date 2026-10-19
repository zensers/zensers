import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ChatMessage } from '../ChatMessage';
import type { ChatMessage as ChatMessageType } from '@/types/api';

const h = React.createElement;

vi.mock('react-markdown', () => {
  return {
    default: ({ children }: { children: string }) =>
      h('div', { 'data-testid': 'markdown-rendered' }, children),
  };
});

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

describe('ChatMessage Markdown Rendering', () => {
  it('assistant message renders content through ReactMarkdown', () => {
    const msg = makeMessage({ role: 'assistant', content: '# Hello World' });
    render(h(ChatMessage, { message: msg }));
    const md = screen.getByTestId('markdown-rendered');
    expect(md).toBeDefined();
    expect(md.textContent).toBe('# Hello World');
  });

  it('user message does NOT use ReactMarkdown', () => {
    const msg = makeMessage({ role: 'user', content: '# Hello World' });
    render(h(ChatMessage, { message: msg }));
    expect(screen.queryByTestId('markdown-rendered')).toBeNull();
    expect(screen.getByText('# Hello World')).toBeDefined();
  });

  it('user message renders **bold** as plain text', () => {
    const msg = makeMessage({ role: 'user', content: '**bold text**' });
    render(h(ChatMessage, { message: msg }));
    expect(screen.getByText('**bold text**')).toBeDefined();
  });

  it('assistant message with empty content renders without error', () => {
    const msg = makeMessage({ role: 'assistant', content: '' });
    const { container } = render(h(ChatMessage, { message: msg }));
    expect(container.querySelector('.prose')).toBeDefined();
  });

  it('assistant message with table markdown passes content to ReactMarkdown', () => {
    const tableMd = '| A | B |\n|---|---|\n| 1 | 2 |';
    const msg = makeMessage({ role: 'assistant', content: tableMd });
    render(h(ChatMessage, { message: msg }));
    const md = screen.getByTestId('markdown-rendered');
    expect(md.textContent).toContain('| A | B |');
  });

  it('assistant message with code block passes content to ReactMarkdown', () => {
    const codeMd = '```python\nprint("hello")\n```';
    const msg = makeMessage({ role: 'assistant', content: codeMd });
    render(h(ChatMessage, { message: msg }));
    const md = screen.getByTestId('markdown-rendered');
    expect(md.textContent).toContain('print("hello")');
  });

  it('assistant message with XSS script tag passes raw content safely', () => {
    const xssMd = '<script>alert(1)</script>';
    const msg = makeMessage({ role: 'assistant', content: xssMd });
    render(h(ChatMessage, { message: msg }));
    const md = screen.getByTestId('markdown-rendered');
    expect(md.textContent).toBe('<script>alert(1)</script>');
    expect(document.querySelector('script')).toBeNull();
  });

  it('assistant message with link markdown passes content to ReactMarkdown', () => {
    const linkMd = '[Click here](https://example.com)';
    const msg = makeMessage({ role: 'assistant', content: linkMd });
    render(h(ChatMessage, { message: msg }));
    const md = screen.getByTestId('markdown-rendered');
    expect(md.textContent).toContain('Click here');
  });

  it('assistant message with list markdown passes content to ReactMarkdown', () => {
    const listMd = '- Item 1\n- Item 2\n- Item 3';
    const msg = makeMessage({ role: 'assistant', content: listMd });
    render(h(ChatMessage, { message: msg }));
    const md = screen.getByTestId('markdown-rendered');
    expect(md.textContent).toContain('Item 1');
    expect(md.textContent).toContain('Item 2');
    expect(md.textContent).toContain('Item 3');
  });

  it('assistant message with Chinese content passes to ReactMarkdown', () => {
    const zhMd = '## 比亚迪市场分析\n\n比亚迪2024年营收达到**7771亿**元。';
    const msg = makeMessage({ role: 'assistant', content: zhMd });
    render(h(ChatMessage, { message: msg }));
    const md = screen.getByTestId('markdown-rendered');
    expect(md.textContent).toContain('比亚迪市场分析');
    expect(md.textContent).toContain('7771亿');
  });

  it('assistant message with mixed markdown passes content to ReactMarkdown', () => {
    const mixedMd = '# Title\n\nSome **bold** and *italic* text.\n\n- List item\n\n> Quote\n\n`code`';
    const msg = makeMessage({ role: 'assistant', content: mixedMd });
    render(h(ChatMessage, { message: msg }));
    const md = screen.getByTestId('markdown-rendered');
    expect(md.textContent).toContain('Title');
    expect(md.textContent).toContain('bold');
    expect(md.textContent).toContain('italic');
    expect(md.textContent).toContain('List item');
    expect(md.textContent).toContain('Quote');
    expect(md.textContent).toContain('code');
  });

  it('assistant message with streaming status renders markdown container', () => {
    const msg = makeMessage({
      role: 'assistant',
      content: 'Hello',
      metadata: { status: 'streaming' },
    });
    const { container } = render(h(ChatMessage, { message: msg }));
    expect(container.querySelector('.prose')).toBeDefined();
    expect(screen.getByTestId('markdown-rendered').textContent).toBe('Hello');
  });

  it('assistant message with processing status shows spinner', () => {
    const msg = makeMessage({
      role: 'assistant',
      content: '',
      metadata: { status: 'processing' },
    });
    const { container } = render(h(ChatMessage, { message: msg }));
    const spinner = container.querySelector('.animate-spin');
    expect(spinner).toBeDefined();
  });
});

describe('ChatMessage Agent Message Rendering', () => {
  it('agent message with heartbeat action renders compact', () => {
    const msg = makeMessage({
      role: 'agent',
      content: 'Research in progress... (50%)',
      agent: { id: 'system', name: 'System', action: 'heartbeat' },
    });
    const { container } = render(h(ChatMessage, { message: msg }));
    expect(container.querySelector('.animate-pulse')).toBeDefined();
    expect(screen.queryByTestId('markdown-rendered')).toBeNull();
  });

  it('agent message with searching action renders with spinning icon', () => {
    const msg = makeMessage({
      role: 'agent',
      content: 'Searching for: BYD',
      agent: { id: 'web_search', name: 'Web Search Agent', action: 'searching' },
    });
    const { container } = render(h(ChatMessage, { message: msg }));
    expect(container.querySelector('.animate-spin')).toBeDefined();
    expect(screen.getByText('Searching for: BYD')).toBeDefined();
  });

  it('agent message with completed count > 1 shows count display', () => {
    const msg = makeMessage({
      role: 'agent',
      content: 'Completed: web_search',
      agent: { id: 'web_search', name: 'Web Search Agent', action: 'completed', completedCount: 3, totalCount: 3 },
    });
    render(h(ChatMessage, { message: msg }));
    expect(screen.getByText('3/3 web_search completed')).toBeDefined();
  });

  it('agent message with completed count = 1 shows original content', () => {
    const msg = makeMessage({
      role: 'agent',
      content: 'Completed: web_search',
      agent: { id: 'web_search', name: 'Web Search Agent', action: 'completed', completedCount: 1, totalCount: 1 },
    });
    render(h(ChatMessage, { message: msg }));
    expect(screen.getByText('Completed: web_search')).toBeDefined();
  });

  it('agent message with error action renders with error styling', () => {
    const msg = makeMessage({
      role: 'agent',
      content: 'Search failed',
      agent: { id: 'web_search', name: 'Web Search Agent', action: 'error' },
    });
    const { container } = render(h(ChatMessage, { message: msg }));
    expect(container.querySelector('.text-red-600')).toBeDefined();
  });

  it('agent message with warning action renders with warning styling', () => {
    const msg = makeMessage({
      role: 'agent',
      content: 'Preview issues detected',
      agent: { id: 'system', name: 'System', action: 'warning' },
    });
    const { container } = render(h(ChatMessage, { message: msg }));
    expect(container.querySelector('.text-amber-600')).toBeDefined();
  });

  it('agent message does NOT use ReactMarkdown', () => {
    const msg = makeMessage({
      role: 'agent',
      content: '**bold** text',
      agent: { id: 'web_search', name: 'Web Search Agent', action: 'searching' },
    });
    render(h(ChatMessage, { message: msg }));
    expect(screen.queryByTestId('markdown-rendered')).toBeNull();
  });

  it('agent message with 2 completed + searching shows intermediate state', () => {
    const msg = makeMessage({
      role: 'agent',
      content: 'Searching for: BYD overseas',
      agent: { id: 'web_search', name: 'Web Search Agent', action: 'searching', completedCount: 2, totalCount: 2 },
    });
    render(h(ChatMessage, { message: msg }));
    expect(screen.getByText('2 web_search completed, Searching for: BYD overseas')).toBeDefined();
  });

  it('agent message with 6/6 web_search completed shows count', () => {
    const msg = makeMessage({
      role: 'agent',
      content: 'Completed: web_search',
      agent: { id: 'web_search', name: 'Web Search Agent', action: 'completed', completedCount: 6, totalCount: 6 },
    });
    render(h(ChatMessage, { message: msg }));
    expect(screen.getByText('6/6 web_search completed')).toBeDefined();
  });
});

describe('ChatMessage Thinking Content', () => {
  it('assistant message with thinkingContent renders details element', () => {
    const msg = makeMessage({
      role: 'assistant',
      content: 'Final answer',
      thinkingContent: 'I thought about this...',
    });
    const { container } = render(h(ChatMessage, { message: msg }));
    const details = container.querySelector('details');
    expect(details).toBeDefined();
    expect(screen.getByText('I thought about this...')).toBeDefined();
  });

  it('thinkingContent is plain text, not markdown rendered', () => {
    const msg = makeMessage({
      role: 'assistant',
      content: 'Answer',
      thinkingContent: '**bold** in thinking',
    });
    const { container } = render(h(ChatMessage, { message: msg }));
    const thinkingEl = container.querySelector('details p');
    expect(thinkingEl?.textContent).toBe('**bold** in thinking');
  });

  it('assistant without thinkingContent has no details element', () => {
    const msg = makeMessage({
      role: 'assistant',
      content: 'Just answer',
    });
    const { container } = render(h(ChatMessage, { message: msg }));
    expect(container.querySelector('details')).toBeNull();
  });
});
