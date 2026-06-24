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
 * - Trigger onScrollTop when user scrolls to top (for infinite scroll)
 */
export function useChatScroll(
  deps: unknown[],
  onScrollTop?: () => Promise<void>,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const isUserScrolling = useRef(false);
  const prevScrollTop = useRef(0);
  const isLoadingRef = useRef(false);

  /**
   * Scroll event handler
   */
  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;

    const { scrollTop, scrollHeight, clientHeight } = el;
    const atBottom = scrollHeight - scrollTop - clientHeight < 60;
    const atTop = scrollTop < 60;

    // User scrolls up → mark
    if (!atBottom && scrollTop < prevScrollTop.current) {
      isUserScrolling.current = true;
    }

    // User scrolls to bottom → resume auto-scroll
    if (atBottom) {
      isUserScrolling.current = false;
    }

    // User scrolls to top → load older messages
    if (atTop && onScrollTop && !isLoadingRef.current) {
      isLoadingRef.current = true;
      const prevHeight = el.scrollHeight;
      onScrollTop().finally(() => {
        requestAnimationFrame(() => {
          const currentEl = containerRef.current;
          if (currentEl) {
            const newHeight = currentEl.scrollHeight;
            currentEl.scrollTop = newHeight - prevHeight;
          }
          isLoadingRef.current = false;
        });
      });
    }

    prevScrollTop.current = scrollTop;
  }, [onScrollTop]);

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
