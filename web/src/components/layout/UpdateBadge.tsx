'use client';

import { useRouter } from 'next/navigation';
import { useVersionCheck } from '@/hooks/useVersionCheck';
import { Button } from '@/components/ui/button';

export function UpdateBadge() {
  const { hasUpdate } = useVersionCheck();
  const router = useRouter();

  if (!hasUpdate) return null;

  return (
    <Button
      variant="ghost"
      size="sm"
      className="h-9 rounded-xl gap-1.5 hover:bg-secondary/80 relative"
      onClick={() => router.push('/settings')}
      title="New version available"
    >
      <span className="relative">
        <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse absolute -top-1 -right-1" />
      </span>
      <span className="text-xs font-medium text-green-600 dark:text-green-400">New</span>
    </Button>
  );
}
