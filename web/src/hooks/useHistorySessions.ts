// hooks/useHistorySessions.ts

import { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import type { ResearchResultMeta } from '@/types/api';

const INITIAL_SIZE = 5;   // First page: latest 5 sessions
const PAGE_SIZE = 10;      // Each "Load More": 10 more sessions

export function useHistorySessions() {
  const [sessions, setSessions] = useState<ResearchResultMeta[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [offset, setOffset] = useState(0);

  // Stable reload — resets pagination and reloads from offset 0 (latest 5)
  const reload = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const { sessions: newSessions, has_more } = await api.listAllSessions(INITIAL_SIZE, 0);
      setSessions(newSessions);
      setHasMore(has_more);
      setOffset(newSessions.length);
    } catch (e) {
      setError(e as Error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Append next page
  const loadMore = useCallback(async () => {
    if (isLoading || !hasMore) return;
    setIsLoading(true);
    setError(null);
    try {
      const { sessions: newSessions, has_more: more } = await api.listAllSessions(PAGE_SIZE, offset);
      setSessions(prev => [...prev, ...newSessions]);
      setHasMore(more);
      setOffset(prev => prev + newSessions.length);
    } catch (e) {
      setError(e as Error);
    } finally {
      setIsLoading(false);
    }
  }, [offset, isLoading, hasMore]);

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { sessions, isLoading, error, reload, loadMore, hasMore };
}
