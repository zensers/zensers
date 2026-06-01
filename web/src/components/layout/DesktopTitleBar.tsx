// components/layout/DesktopTitleBar.tsx

'use client';

import { useCallback, useRef, useEffect } from 'react';
import { useDesktopStore } from '@/store/useDesktopStore';

/**
 * Desktop window title bar - traffic light buttons
 * Only rendered when URL contains ?desktop=1 (persisted via Zustand + localStorage)
 * Implements window dragging via JS mousedown/mousemove + pywebview API
 */
export function DesktopTitleBar() {
  const isDesktop = useDesktopStore((s) => s.isDesktop);
  const dragging = useRef(false);
  const offsetRef = useRef({ x: 0, y: 0 });

  const callApi = useCallback((method: string, ...args: any[]) => {
    try {
      const api = (window as any).pywebview?.api;
      if (api && api[method]) return api[method](...args);
    } catch {}
  }, []);

  useEffect(() => {
    if (!isDesktop) return;

    const onMouseMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      callApi('move_window', e.screenX - offsetRef.current.x, e.screenY - offsetRef.current.y);
    };

    const onMouseUp = () => { dragging.current = false; };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, [isDesktop, callApi]);

  const handleMouseDown = (e: React.MouseEvent) => {
    // Left mouse button only
    if (e.button !== 0) return;
    dragging.current = true;
    offsetRef.current = { x: e.screenX - window.screenX, y: e.screenY - window.screenY };
  };

  if (!isDesktop) return null;

  return (
    <div
      className="flex items-center justify-between shrink-0 select-none"
      style={{
        height: 38,
        padding: '0 14px',
        background: 'linear-gradient(180deg, rgba(28,28,30,0.98) 0%, rgba(28,28,30,0.95) 100%)',
        borderBottom: '0.5px solid rgba(255,255,255,0.06)',
      }}
      onDoubleClick={() => callApi('maximize')}
      onMouseDown={handleMouseDown}
    >
      {/* 左侧标题 */}
      <div className="flex items-center gap-2">
        <img src="/logo.png" alt="Zensers" className="h-4 w-4 rounded object-contain" style={{ filter: 'brightness(10)' }} />
        <span style={{ color: 'rgba(255,255,255,0.85)', fontSize: 13, fontWeight: 500, letterSpacing: '-0.2px' }}>Zensers</span>
      </div>

      {/* 右侧按钮 */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => callApi('minimize')}
          className="flex items-center justify-center rounded-full border-none cursor-pointer transition-all duration-150 hover:scale-110 active:scale-95"
          title="Minimize"
          style={{
            width: 12,
            height: 12,
            background: '#FFBD2E',
            boxShadow: '0 0 0 0.5px rgba(0,0,0,0.12), inset 0 0.5px 0 rgba(255,255,255,0.25)',
          }}
        />
        <button
          onClick={() => callApi('maximize')}
          className="flex items-center justify-center rounded-full border-none cursor-pointer transition-all duration-150 hover:scale-110 active:scale-95"
          title="Maximize"
          style={{
            width: 12,
            height: 12,
            background: '#28CA41',
            boxShadow: '0 0 0 0.5px rgba(0,0,0,0.12), inset 0 0.5px 0 rgba(255,255,255,0.25)',
          }}
        />
        <button
          onClick={() => callApi('close')}
          className="flex items-center justify-center rounded-full border-none cursor-pointer transition-all duration-150 hover:scale-110 active:scale-95"
          title="Close"
          style={{
            width: 12,
            height: 12,
            background: '#FF5F57',
            boxShadow: '0 0 0 0.5px rgba(0,0,0,0.12), inset 0 0.5px 0 rgba(255,255,255,0.25)',
          }}
        />
      </div>
    </div>
  );
}
