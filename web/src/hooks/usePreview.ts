// hooks/usePreview.ts

import { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import type { PreviewResponse } from '@/types/api';

interface UsePreviewOptions {
  taskId: string | null;
  enabled?: boolean;
  format?: 'html' | 'pdf' | 'png';
}

interface UsePreviewReturn {
  preview: PreviewResponse | null;
  isLoading: boolean;
  isPending: boolean;
  error: Error | null;
  refetch: () => void;
}

/**
 * Preview fetch Hook
 * Simple fetch implementation, no TanStack Query needed
 */
export function usePreview(options: UsePreviewOptions): UsePreviewReturn {
  const { taskId, enabled = true, format = 'html' } = options;

  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [hasFetched, setHasFetched] = useState(false);

  // Clear preview when taskId changes or becomes disabled
  useEffect(() => {
    setPreview(null);
    setError(null);
    setHasFetched(false);
  }, [taskId]);

  const fetchPreview = useCallback(async () => {
    if (!taskId || !enabled) return;

    setIsLoading(true);
    setError(null);
    setHasFetched(true);

    try {
      const data = await api.getResearchPreview(taskId, format);
      setPreview(data);
    } catch (e) {
      setError(e as Error);
    } finally {
      setIsLoading(false);
    }
  }, [taskId, enabled, format]);

  useEffect(() => {
    fetchPreview();
  }, [fetchPreview]);

  return {
    preview,
    isLoading,
    isPending: enabled && !hasFetched && !isLoading,
    error,
    refetch: fetchPreview,
  };
}
