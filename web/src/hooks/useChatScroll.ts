// hooks/useChatScroll.ts

import { useEffect, useRef, useCallback } from 'react';

/**
 * Chat scroll behavior control Hook
 *
 * Scroll strategy:
 * - Auto-scroll to bottom on dependency change
 * - Pause auto-scroll when user scrolls up to view history
 * - Resume auto-scroll when user scrolls back to bottom
 * - Provide "scroll to latest" button state
 */
export function useChatScroll(deps: unknown[]) {
  const containerRef = useRef<HTMLDivElement>(null);
  const isUserScrolling = useRef(false);
  const prevScrollTop = useRef(0);

  /**
   * Scroll event handler
   */
  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;

    const { scrollTop, scrollHeight, clientHeight } = el;
    const atBottom = scrollHeight - scrollTop - clientHeight < 60;

    // User scrolls up → mark
    if (!atBottom && scrollTop < prevScrollTop.current) {
      isUserScrolling.current = true;
    }

    // User scrolls to bottom → resume auto-scroll
    if (atBottom) {
      isUserScrolling.current = false;
    }

    prevScrollTop.current = scrollTop;
  }, []);

  // Deps change → auto-scroll (unless user is scrolling up)
  useEffect(() => {
    if (isUserScrolling.current) return;

    const el = containerRef.current;
    if (el) {
      requestAnimationFrame(() => {
        el.scrollTop = el.scrollHeight;
      });
    }
  }, deps);

  /**
   * Scroll to bottom
   */
  const scrollToBottom = useCallback(() => {
    const el = containerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
      isUserScrolling.current = false;
    }
  }, []);

  /**
   * Check if at bottom
   */
  const isAtBottom = useCallback(() => {
    const el = containerRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight < 60;
  }, []);

  return { containerRef, handleScroll, scrollToBottom, isAtBottom };
}
