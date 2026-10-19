'use client';

import { useResearchStore } from '@/store/useResearchStore';
import type { SearchState } from '@/store/useResearchStore';
import { cn } from '@/lib/utils';
import { Loader2, Search, CheckCircle2, XCircle, Brain } from 'lucide-react';

interface SearchIndicatorProps {
  isWaitingForReply?: boolean;
}

const STATE_CONFIG: Record<SearchState, {
  icon: typeof Loader2;
  text: string;
  bg: string;
  border: string;
  textColor: string;
} | null> = {
  idle: null,
  searching: {
    icon: Loader2,
    text: 'Searching the web for information...',
    bg: 'bg-blue-50/50',
    border: 'border-blue-200/30',
    textColor: 'text-blue-700',
  },
  completed: {
    icon: CheckCircle2,
    text: 'Search completed, generating response...',
    bg: 'bg-green-50/50',
    border: 'border-green-200/30',
    textColor: 'text-green-700',
  },
  error: {
    icon: XCircle,
    text: 'Search encountered an issue',
    bg: 'bg-red-50/50',
    border: 'border-red-200/30',
    textColor: 'text-red-700',
  },
};

export function SearchIndicator({ isWaitingForReply }: SearchIndicatorProps) {
  const searchState = useResearchStore((s) => s.searchState);

  if (searchState === 'idle' && isWaitingForReply) {
    return (
      <div className="flex items-center gap-2 px-4 py-2 border-b bg-purple-50/50 border-purple-200/30">
        <Brain className="h-4 w-4 animate-pulse text-purple-700" />
        <span className="text-sm text-purple-700">AI 正在思考...</span>
      </div>
    );
  }

  const config = STATE_CONFIG[searchState];
  if (!config) return null;

  const Icon = config.icon;

  return (
    <div className={cn(
      'flex items-center gap-2 px-4 py-2 border-b transition-all duration-300',
      config.bg,
      config.border,
      searchState === 'searching' && 'animate-pulse',
    )}>
      <Icon className={cn(
        'h-4 w-4',
        config.textColor,
        searchState === 'searching' && 'animate-spin',
      )} />
      <span className={cn('text-sm', config.textColor)}>{config.text}</span>
    </div>
  );
}
