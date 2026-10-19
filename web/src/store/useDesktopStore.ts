// store/useDesktopStore.ts
// Desktop mode state: whether running in pywebview with ?desktop=1

'use client';

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

interface DesktopState {
  isDesktop: boolean;
  setDesktop: (v: boolean) => void;
}

export const useDesktopStore = create<DesktopState>()(
  persist(
    (set) => ({
      isDesktop: false,
      setDesktop: (v) => set({ isDesktop: v }),
    }),
    {
      name: 'zensers-desktop-mode',
      storage: createJSONStorage(() => localStorage),
    }
  )
);
