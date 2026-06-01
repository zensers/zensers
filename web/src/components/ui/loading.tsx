// components/ui/loading.tsx

import { Spinner } from './spinner';
import { cn } from '@/lib/utils';

interface LoadingProps {
  text?: string;
  className?: string;
}

export function Loading({ text = 'Loading...', className }: LoadingProps) {
  return (
    <div className={cn('flex items-center justify-center gap-2 p-4', className)}>
      <Spinner />
      <span className="text-sm text-muted-foreground">{text}</span>
    </div>
  );
}
