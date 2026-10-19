// components/layout/ThemeProvider.tsx
// Listen to useSettingsStore theme config and apply to DOM in real-time

'use client';

import { useEffect } from 'react';
import { useSettingsStore } from '@/store/useSettingsStore';

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const { mode, primaryColor, fontSize, fontFamily } = useSettingsStore((s) => s.theme);

  useEffect(() => {
    const root = document.documentElement;

    // 1. Theme mode: toggle dark class on <html>
    if (mode === 'dark') {
      root.classList.add('dark');
    } else if (mode === 'light') {
      root.classList.remove('dark');
    } else {
      // system: follow system preference
      const mq = window.matchMedia('(prefers-color-scheme: dark)');
      if (mq.matches) {
        root.classList.add('dark');
      } else {
        root.classList.remove('dark');
      }
      const handler = (e: MediaQueryListEvent) => {
        if (e.matches) root.classList.add('dark');
        else root.classList.remove('dark');
      };
      mq.addEventListener('change', handler);
      return () => mq.removeEventListener('change', handler);
    }
  }, [mode]);

  useEffect(() => {
    // 2. Theme color: update CSS variable --primary
    const root = document.documentElement;
    // Convert hex to HSL and set to --primary
    root.style.setProperty('--primary', hexToHsl(primaryColor));
  }, [primaryColor]);

  useEffect(() => {
    // 3. Font size
    const sizes = { small: '14px', medium: '16px', large: '18px' };
    document.body.style.fontSize = sizes[fontSize] || '16px';
  }, [fontSize]);

  useEffect(() => {
    // 4. Font family
    document.body.style.fontFamily = fontFamily;
  }, [fontFamily]);

  return <>{children}</>;
}

/** Convert hex color to hsl string, e.g. "#3b82f6" → "217 91% 60%" */
function hexToHsl(hex: string): string {
  let r = 0, g = 0, b = 0;
  if (hex.length === 7) {
    r = parseInt(hex.slice(1, 3), 16) / 255;
    g = parseInt(hex.slice(3, 5), 16) / 255;
    b = parseInt(hex.slice(5, 7), 16) / 255;
  }
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0, s = 0, l = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
      case g: h = ((b - r) / d + 2) / 6; break;
      case b: h = ((r - g) / d + 4) / 6; break;
    }
  }
  return `${Math.round(h * 360)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%`;
}
