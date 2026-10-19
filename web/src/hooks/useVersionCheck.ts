'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import api from '@/lib/api';
import type { VersionInfo, DismissedUpdate } from '@/types/version';

const POLL_INTERVAL = 30 * 60 * 1000;
const DISMISSED_KEY = 'zensers_dismissed_updates';
const MAX_DISMISSED = 10;
const CLEANUP_DAYS = 90;

export function useVersionCheck() {
  const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null);
  const [hasUpdate, setHasUpdate] = useState(false);
  const [bannerVisible, setBannerVisible] = useState(false);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const currentVersion = process.env.NEXT_PUBLIC_APP_VERSION || '0.0.0';

  const cleanupDismissed = (entries: DismissedUpdate[]): DismissedUpdate[] => {
    const cutoff = Date.now() - CLEANUP_DAYS * 24 * 60 * 60 * 1000;
    return entries
      .filter(e => new Date(e.dismissedAt).getTime() > cutoff)
      .slice(-MAX_DISMISSED);
  };

  const isVersionDismissed = useCallback((version: string): boolean => {
    try {
      const stored = localStorage.getItem(DISMISSED_KEY);
      if (!stored) return false;
      const dismissed: DismissedUpdate[] = JSON.parse(stored);
      const entry = dismissed.find(d => d.version === version);
      if (!entry) return false;

      const elapsed = Date.now() - new Date(entry.dismissedAt).getTime();
      return elapsed < entry.remindAfter * 24 * 60 * 60 * 1000;
    } catch {
      return false;
    }
  }, []);

  const dismissVersion = useCallback((version: string, remindAfter = 7) => {
    try {
      const stored = localStorage.getItem(DISMISSED_KEY);
      let dismissed: DismissedUpdate[] = stored ? JSON.parse(stored) : [];
      dismissed = dismissed.filter(d => d.version !== version);
      dismissed.push({ version, dismissedAt: new Date().toISOString(), remindAfter });
      localStorage.setItem(DISMISSED_KEY, JSON.stringify(cleanupDismissed(dismissed)));
      setBannerVisible(false);
    } catch {
      // 静默失败
    }
  }, []);

  const mountedRef = useRef(true);
  useEffect(() => {
    return () => { mountedRef.current = false; };
  }, []);

  const checkVersion = useCallback(async (showBanner = true) => {
    if (!mountedRef.current) return;
    setLoading(true);
    try {
      const info = await api.getVersion();
      if (!mountedRef.current) return;
      setVersionInfo(info);

      if (info.is_latest === false) {
        if (!mountedRef.current) return;
        setHasUpdate(true);
        setCheckError(null);

        if (showBanner && !isVersionDismissed(info.remote_version)) {
          if (!mountedRef.current) return;
          setBannerVisible(true);
        }
      } else if (info.is_latest === true) {
        if (!mountedRef.current) return;
        setHasUpdate(false);
        setCheckError(null);
      } else {
        if (!mountedRef.current) return;
        setHasUpdate(false);
        setCheckError(info.check_error || 'Update check failed');
      }
    } catch {
      if (!mountedRef.current) return;
      setCheckError('Unable to reach update server');
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, [isVersionDismissed]);

  useEffect(() => {
    checkVersion();
  }, [checkVersion]);

  useEffect(() => {
    const interval = setInterval(() => checkVersion(false), POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [checkVersion]);

  useEffect(() => {
    const handler = () => {
      if (document.visibilityState === 'visible') {
        checkVersion(false);
      }
    };
    document.addEventListener('visibilitychange', handler);
    window.addEventListener('focus', handler);
    return () => {
      document.removeEventListener('visibilitychange', handler);
      window.removeEventListener('focus', handler);
    };
  }, [checkVersion]);

  return {
    currentVersion,
    versionInfo,
    hasUpdate,
    bannerVisible,
    checkError,
    loading,
    checkVersion,
    dismissVersion,
  };
}
