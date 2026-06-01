// store/useChatStore.ts
// Delegation layer — message state driven by useSessionStore

import { create } from 'zustand';
import type { ChatMessage } from '@/types/api';
import { useSessionStore } from './useSessionStore';

interface ChatState {
  messages: ChatMessage[];
  addMessage: (msg: ChatMessage) => void;
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

    clearMessages: () => {
      set({ messages: [] });
      useSessionStore.getState().syncActive({ messages: [] });
    },
  };
});
