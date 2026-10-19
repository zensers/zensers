'use client';

import { useEffect, useState } from 'react';
import { MainLayout } from '@/components/layout/MainLayout';
import { restoreSession } from '@/store/useSessionStore';

export default function HomePage() {
  const [isRestoring, setIsRestoring] = useState(false);

  useEffect(() => {
    const doRestore = async () => {
      const sessionId = sessionStorage.getItem('resume-session');
      sessionStorage.removeItem('resume-session');
      if (!sessionId) return;

      setIsRestoring(true);
      try {
        await restoreSession(sessionId);
      } catch (e) {
        console.error('Failed to restore session:', e);
      } finally {
        setIsRestoring(false);
      }
    };

    doRestore();
  }, []);

  if (isRestoring) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-primary/30 border-t-primary" />
          <p className="text-sm text-muted-foreground">Restoring session...</p>
        </div>
      </div>
    );
  }

  return <MainLayout />;
}
