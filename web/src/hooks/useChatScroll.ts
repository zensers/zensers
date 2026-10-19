import { useEffect, useRef, useCallback } from 'react';

export function useChatScroll(
  deps: unknown[],
  onScrollTop?: () => Promise<void>,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const isUserScrolling = useRef(false);
  const prevScrollTop = useRef(0);
  const isLoadingRef = useRef(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    return () => { mountedRef.current = false; };
  }, []);

  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;

    const { scrollTop, scrollHeight, clientHeight } = el;
    const atBottom = scrollHeight - scrollTop - clientHeight < 60;
    const atTop = scrollTop < 60;

    if (!atBottom && scrollTop < prevScrollTop.current) {
      isUserScrolling.current = true;
    }

    if (atBottom) {
      isUserScrolling.current = false;
    }

    if (atTop && onScrollTop && !isLoadingRef.current) {
      isLoadingRef.current = true;
      const prevHeight = el.scrollHeight;
      onScrollTop().finally(() => {
        requestAnimationFrame(() => {
          if (!mountedRef.current) return;
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

  useEffect(() => {
    if (isUserScrolling.current) return;

    const el = containerRef.current;
    if (el) {
      requestAnimationFrame(() => {
        if (!mountedRef.current) return;
        el.scrollTop = el.scrollHeight;
      });
    }
  }, deps);

  const scrollToBottom = useCallback(() => {
    const el = containerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
      isUserScrolling.current = false;
    }
  }, []);

  const isAtBottom = useCallback(() => {
    const el = containerRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight < 60;
  }, []);

  return { containerRef, handleScroll, scrollToBottom, isAtBottom };
}
