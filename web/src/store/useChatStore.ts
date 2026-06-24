// store/useChatStore.ts
// Delegation layer — message state driven by useSessionStore

import { create } from 'zustand';
import type { ChatMessage } from '@/types/api';
import { useSessionStore } from './useSessionStore';

interface ChatState {
  messages: ChatMessage[];
  addMessage: (msg: ChatMessage) => void;
  prependMessages: (msgs: ChatMessage[]) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatState>()((set, get) => {
  useSessionStore.subscribe((state) => {
    const active = state.activeId ? state.sessions[state.activeId] : undefined;
    const current = get();
    const next = active?.messages || [];
    if (current.messages !== next) {
      set({ messages: next });
    }
  });

  return {
    messages: [],

    addMessage: (msg) => {
      const messages = [...get().messages, msg];
      set({ messages });
      useSessionStore.getState().syncActive({ messages });
    },

    prependMessages: (msgs) => {
      const messages = [...msgs, ...get().messages];
      const seen = new Set<string>();
      const deduped = messages.filter(m => {
        if (seen.has(m.id)) return false;
        seen.add(m.id);
        return true;
      });
      set({ messages: deduped });
      useSessionStore.getState().syncActive({ messages: deduped });
    },

    clearMessages: () => {
      set({ messages: [] });
      useSessionStore.getState().syncActive({ messages: [] });
    },
  };
});
