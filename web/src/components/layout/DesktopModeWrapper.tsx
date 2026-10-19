// components/layout/DesktopModeWrapper.tsx
// Root layout wrapper: detects ?desktop=1 mode + renders DesktopTitleBar

'use client';

import { useEffect } from 'react';
import { useDesktopStore } from '@/store/useDesktopStore';
import { DesktopTitleBar } from './DesktopTitleBar';

export function DesktopModeWrapper({ children }: { children: React.ReactNode }) {
  const setDesktop = useDesktopStore((s) => s.setDesktop);

  useEffect(() => {
    // Check ?desktop=1 on page load, persist to localStorage
    if (window.location.search.includes('desktop=1')) {
      setDesktop(true);
    }
  }, [setDesktop]);

  return (
    <>
      <DesktopTitleBar />
      {children}
    </>
  );
}
