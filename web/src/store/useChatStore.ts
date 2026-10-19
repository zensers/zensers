import { create } from 'zustand';
import type { ChatMessage } from '@/types/api';
import { useSessionStore } from './useSessionStore';
import { isInternalChatMessage, upsertChatMessage, visibleChatMessages } from '@/lib/chat-message-utils';

interface ChatState {
  messages: ChatMessage[];
  addMessage: (msg: ChatMessage) => void;
  updateMessage: (id: string, updates: Partial<ChatMessage>) => void;
  appendStreamToken: (id: string, contentDelta: string, thinkingDelta: string) => void;
  prependMessages: (msgs: ChatMessage[]) => void;
  setMessages: (msgs: ChatMessage[]) => void;
  mergeServerMessages: (msgs: ChatMessage[]) => void;
  clearMessages: () => void;
  flushSyncNow: () => void;
}

interface TokenBuffer {
  id: string;
  contentDelta: string;
  thinkingDelta: string;
}

let tokenBuffer: TokenBuffer | null = null;
let flushRafId: number | null = null;
let syncDebounceTimer: ReturnType<typeof setTimeout> | null = null;
const SYNC_DEBOUNCE_MS = 500;

const safeRAF: (cb: () => void) => number =
  typeof requestAnimationFrame !== 'undefined'
    ? (cb) => requestAnimationFrame(cb)
    : (cb) => setTimeout(cb, 16) as unknown as number;

const safeCancelRAF = (id: number): void => {
  if (typeof cancelAnimationFrame !== 'undefined') {
    cancelAnimationFrame(id);
  } else {
    clearTimeout(id as unknown as NodeJS.Timeout);
  }
};

let _isSyncingFromChatStore = false;

function messageTimeValue(message: ChatMessage): number {
  const parsed = Date.parse(message.timestamp);
  return Number.isNaN(parsed) ? 0 : parsed;
}

// Single ordering authority: fold incoming first, then current, through the
// shared identity rules, and sort by timestamp ascending. Every write path
// (live adds, paged prepends, restore merges, cache<->store sync) funnels
// through here so both stores converge to the same order regardless of which
// side is written first.
function mergeAndSortMessages(current: ChatMessage[], incoming: ChatMessage[]): ChatMessage[] {
  let merged: ChatMessage[] = [];
  for (const message of [...incoming, ...current]) {
    merged = upsertChatMessage(merged, message);
  }
  return merged.sort((a, b) => messageTimeValue(a) - messageTimeValue(b));
}

function debouncedSyncActive(messages: ChatMessage[]) {
  if (syncDebounceTimer) clearTimeout(syncDebounceTimer);
  syncDebounceTimer = setTimeout(() => {
    _isSyncingFromChatStore = true;
    useSessionStore.getState().syncActive({ messages: mergeAndSortMessages([], messages) });
    _isSyncingFromChatStore = false;
    syncDebounceTimer = null;
  }, SYNC_DEBOUNCE_MS);
}

function flushSyncNowInternal(messages?: ChatMessage[]) {
  if (syncDebounceTimer) {
    clearTimeout(syncDebounceTimer);
    syncDebounceTimer = null;
  }
  if (messages) {
    _isSyncingFromChatStore = true;
    useSessionStore.getState().syncActive({ messages: mergeAndSortMessages([], messages) });
    _isSyncingFromChatStore = false;
  }
}

function flushTokenBuffer() {
  if (!tokenBuffer) return;
  const { id, contentDelta, thinkingDelta } = tokenBuffer;
  tokenBuffer = null;
  flushRafId = null;

  const messages = useChatStore.getState().messages.map((m: ChatMessage) => {
    if (m.id !== id) return m;
    return {
      ...m,
      ...(contentDelta ? { content: m.content + contentDelta } : {}),
      ...(thinkingDelta ? { thinkingContent: (m.thinkingContent || '') + thinkingDelta } : {}),
    };
  });
  useChatStore.setState({ messages });
  debouncedSyncActive(messages);
}

function filterHeartbeats(msgs: ChatMessage[]): ChatMessage[] {
  return visibleChatMessages(msgs).filter((m) => !isInternalChatMessage(m));
}

let _sessionSubUnsub: (() => void) | null = null;
let _prevActiveId: string | null | undefined = undefined;
let _prevSessionMessagesRef: ChatMessage[] | undefined = undefined;

export const useChatStore = create<ChatState>()((set, get) => {
  if (!_sessionSubUnsub) {
    _sessionSubUnsub = useSessionStore.subscribe((state) => {
      if (_prevActiveId === undefined) {
        _prevActiveId = state.activeId;
      }

      const active = state.activeId ? state.sessions[state.activeId] : undefined;
      const raw = active?.messages || [];

      if (state.activeId !== _prevActiveId) {
        _prevActiveId = state.activeId;
        _prevSessionMessagesRef = raw;
        set({ messages: mergeAndSortMessages([], filterHeartbeats(raw)) });
        return;
      }

      if (!_isSyncingFromChatStore && raw !== _prevSessionMessagesRef) {
        _prevSessionMessagesRef = raw;
        set({ messages: mergeAndSortMessages([], filterHeartbeats(raw)) });
      } else {
        _prevSessionMessagesRef = raw;
      }
    });
  }

  return {
    messages: [],

    addMessage: (msg) => {
      const messages = mergeAndSortMessages(get().messages, [msg]);
      set({ messages });
      flushSyncNowInternal(messages);
    },

    updateMessage: (id, updates) => {
      if (tokenBuffer) flushTokenBuffer();
      const messages = get().messages.map(m => {
        if (m.id !== id) return m;
        const merged = updates.metadata && m.metadata
          ? { ...m, ...updates, metadata: { ...m.metadata, ...updates.metadata } }
          : { ...m, ...updates };
        return merged;
      });
      set({ messages });
      flushSyncNowInternal(messages);
    },

    appendStreamToken: (id, contentDelta, thinkingDelta) => {
      if (tokenBuffer && tokenBuffer.id === id) {
        tokenBuffer.contentDelta += contentDelta || '';
        tokenBuffer.thinkingDelta += thinkingDelta || '';
      } else {
        if (tokenBuffer) flushTokenBuffer();
        tokenBuffer = { id, contentDelta: contentDelta || '', thinkingDelta: thinkingDelta || '' };
      }
      if (!flushRafId) {
        flushRafId = safeRAF(() => flushTokenBuffer());
      }
    },

    prependMessages: (msgs) => {
      if (tokenBuffer) flushTokenBuffer();
      // Use the same identity/merge rules as live messages. A paged response
      // can have a different local id for an already-loaded message.
      const merged = mergeAndSortMessages(get().messages, msgs);
      set({ messages: merged });
      flushSyncNowInternal(merged);
    },

    setMessages: (msgs) => {
      if (tokenBuffer) flushTokenBuffer();
      const messages = mergeAndSortMessages(get().messages, msgs);
      set({ messages });
      flushSyncNowInternal(messages);
    },

    mergeServerMessages: (msgs) => {
      get().setMessages(msgs);
    },

    clearMessages: () => {
      if (tokenBuffer) { tokenBuffer = null; }
      if (flushRafId) { safeCancelRAF(flushRafId); flushRafId = null; }
      set({ messages: [] });
      flushSyncNowInternal([]);
    },

    flushSyncNow: () => {
      if (tokenBuffer) flushTokenBuffer();
      flushSyncNowInternal(get().messages);
    },
  };
});
