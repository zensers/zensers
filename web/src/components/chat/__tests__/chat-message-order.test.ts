import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { useChatStore } from '@/store/useChatStore';
import { useSessionStore, restoreSession } from '@/store/useSessionStore';
import { upsertChatMessage } from '@/lib/chat-message-utils';
import { api } from '@/lib/api';
import type { ChatMessage } from '@/types/api';

function msg(
  id: string,
  role: ChatMessage['role'],
  content: string,
  timestamp: string,
  extra: Partial<ChatMessage> = {},
): ChatMessage {
  return { id, role, content, timestamp, ...extra };
}

describe('chat message ordering (timestamp-sorted authority)', () => {
  beforeEach(() => {
    useSessionStore.setState({ activeId: null, sessions: {}, isRestoring: false });
    useChatStore.setState({ messages: [] });
  });

  it('addMessage keeps the array sorted when an older message is appended after a newer one', () => {
    const store = useChatStore.getState();
    store.addMessage(msg('a1', 'assistant', 'answer', '2026-10-17T19:25:00.000Z'));
    store.addMessage(msg('u0', 'user', 'older question', '2026-10-17T19:22:00.000Z'));
    store.addMessage(msg('u1', 'user', 'newer question', '2026-10-17T19:26:00.000Z'));

    expect(useChatStore.getState().messages.map((m) => m.id)).toEqual(['u0', 'a1', 'u1']);
  });

  it('prependMessages merges an older page into sorted position', () => {
    const store = useChatStore.getState();
    store.addMessage(msg('u2', 'user', 'q2', '2026-10-17T19:26:00.000Z'));
    store.addMessage(msg('a2', 'assistant', 'r2', '2026-10-17T19:26:30.000Z'));

    store.prependMessages([
      msg('u0', 'user', 'q0', '2026-10-17T19:22:00.000Z'),
      msg('a0', 'assistant', 'r0', '2026-10-17T19:23:00.000Z'),
    ]);

    expect(useChatStore.getState().messages.map((m) => m.id)).toEqual(['u0', 'a0', 'u2', 'a2']);
  });

  it('restore-merge: server history merges with local messages without duplicating window matches', () => {
    useChatStore.setState({
      messages: [
        msg('u1', 'user', '飞行汽车', '2026-10-17T19:25:10.000Z'),
        msg('a1', 'assistant', 'summary', '2026-10-17T19:25:30.000Z'),
      ],
    });

    useChatStore.getState().mergeServerMessages([
      msg('srv-u0', 'user', '你好', '2026-10-17T19:22:00.000Z'),
      msg('srv-a0', 'assistant', 'greeting', '2026-10-17T19:23:00.000Z'),
      // Server-persisted copy of u1 with a slightly different (server) timestamp.
      msg('srv-u1', 'user', '飞行汽车', '2026-10-17T19:25:10.400Z'),
    ]);

    const messages = useChatStore.getState().messages;
    expect(messages).toHaveLength(4);
    expect(messages.map((m) => m.id)).toEqual(['srv-u0', 'srv-a0', 'srv-u1', 'a1']);
    expect(messages[2].timestamp).toBe('2026-10-17T19:25:10.000Z');
  });

  it('restoreSession routes server messages through the chat-store merge (cache gets the merged array)', async () => {
    const sid = 'ses-order-restore';
    useSessionStore.getState().createSession(sid, 'restored');
    useChatStore.setState({
      messages: [
        msg('u1', 'user', '飞行汽车', '2026-10-17T19:25:10.000Z'),
        msg('a1', 'assistant', 'summary', '2026-10-17T19:25:30.000Z'),
      ],
    });

    const detailSpy = vi.spyOn(api, 'getResearchDetail').mockResolvedValue({
      task_id: sid,
      status: 'paused',
      messages: [
        { id: 'srv-u0', role: 'user', content: '你好', timestamp: '2026-10-17T19:22:00.000Z' },
        { id: 'srv-a0', role: 'assistant', content: 'greeting', timestamp: '2026-10-17T19:23:00.000Z' },
        { id: 'srv-u1', role: 'user', content: '飞行汽车', timestamp: '2026-10-17T19:25:10.400Z' },
      ],
      step: 2,
      progress: 40,
    } as any);

    try {
      await restoreSession(sid);

      const messages = useChatStore.getState().messages;
      expect(messages.map((m) => m.id)).toEqual(['srv-u0', 'srv-a0', 'srv-u1', 'a1']);

      // The session cache must hold the merged array (via the chat-store
      // flush), not the raw 3-message server array.
      const cached = useSessionStore.getState().sessions[sid];
      expect(cached?.messages.map((m) => m.id)).toEqual(['srv-u0', 'srv-a0', 'srv-u1', 'a1']);
    } finally {
      detailSpy.mockRestore();
    }
  });

  it('streaming message keeps its position while content grows', () => {
    vi.useFakeTimers();
    try {
      const store = useChatStore.getState();
      store.addMessage(msg('m-old', 'assistant', 'old', '2026-10-17T19:20:00.000Z'));
      store.addMessage(
        msg('m-str', 'assistant', '', '2026-10-17T19:25:00.000Z', { metadata: { status: 'streaming' } }),
      );
      vi.advanceTimersByTime(32);

      store.appendStreamToken('m-str', 'partial ', '');
      vi.advanceTimersByTime(32);
      expect(useChatStore.getState().messages.map((m) => m.id)).toEqual(['m-old', 'm-str']);

      // An older message arriving mid-stream must sort below the streaming one.
      store.addMessage(msg('m-mid', 'user', 'q', '2026-10-17T19:22:00.000Z'));

      store.updateMessage('m-str', { content: 'partial final', metadata: { status: 'done' } });

      const messages = useChatStore.getState().messages;
      expect(messages.map((m) => m.id)).toEqual(['m-old', 'm-mid', 'm-str']);
      expect(messages[2].content).toBe('partial final');
      expect(messages[2].metadata?.status).toBe('done');
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('upsertChatMessage time-window identity', () => {
  const base = '2026-10-17T19:25:00.000Z';

  it('same user content within 60s is the same message (id + earlier timestamp kept)', () => {
    const messages = upsertChatMessage([], msg('local-1', 'user', '飞行汽车', base));
    const merged = upsertChatMessage(messages, msg('srv-1', 'user', '飞行汽车', '2026-10-17T19:25:30.000Z'));

    expect(merged).toHaveLength(1);
    expect(merged[0].id).toBe('local-1');
    expect(merged[0].timestamp).toBe(base);
  });

  it('same content exactly 60s apart produces two messages (window is exclusive)', () => {
    let merged = upsertChatMessage([], msg('a', 'assistant', 'Hello', base));
    merged = upsertChatMessage(merged, msg('b', 'assistant', 'Hello', '2026-10-17T19:26:00.000Z'));
    expect(merged).toHaveLength(2);
  });

  it('same content 61s apart produces two messages', () => {
    let merged = upsertChatMessage([], msg('a', 'assistant', 'Hello', base));
    merged = upsertChatMessage(merged, msg('b', 'assistant', 'Hello', '2026-10-17T19:26:01.000Z'));
    expect(merged).toHaveLength(2);
  });

  it('exact timestamp match still merges and the incoming id wins (SSE replay)', () => {
    let merged = upsertChatMessage([], msg('http-1', 'assistant', 'done', base));
    merged = upsertChatMessage(merged, msg('sse-1', 'assistant', 'done', base));
    expect(merged).toHaveLength(1);
    expect(merged[0].id).toBe('sse-1');
  });

  it('system role is excluded from the window rule', () => {
    let merged = upsertChatMessage([], msg('s1', 'system', 'event', base));
    merged = upsertChatMessage(merged, msg('s2', 'system', 'event', '2026-10-17T19:25:10.000Z'));
    expect(merged).toHaveLength(2);
  });

  it('agent role repeated content is never merged into the visible list', () => {
    let merged = upsertChatMessage([], msg('g1', 'agent', 'Searching...', base, {
      agent: { id: 'web_search', name: 'Web Search', action: 'searching' },
    }));
    merged = upsertChatMessage(merged, msg('g2', 'agent', 'Searching...', base, {
      agent: { id: 'web_search', name: 'Web Search', action: 'completed' },
    }));
    expect(merged).toHaveLength(0);
  });

  it('unparseable timestamps never window-match', () => {
    let merged = upsertChatMessage([], msg('x1', 'user', 'dup?', 'not-a-date'));
    merged = upsertChatMessage(merged, msg('x2', 'user', 'dup?', 'also-not-a-date'));
    expect(merged).toHaveLength(2);
  });
});
