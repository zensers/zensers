// components/chat/ChatMessage.tsx

'use client';

import { cn } from '@/lib/utils';
import type { ChatMessage as ChatMessageType } from '@/types/api';
import { User, Bot, Search, Brain, FileText, CheckCircle2, Loader2 } from 'lucide-react';

interface ChatMessageProps {
  message: ChatMessageType;
}

const AGENT_ACTION_CONFIG: Record<string, { icon: typeof Search; color: string; bg: string }> = {
  searching: { icon: Search, color: 'text-blue-600', bg: 'bg-blue-50 border-blue-200' },
  analyzing: { icon: Brain, color: 'text-purple-600', bg: 'bg-purple-50 border-purple-200' },
  writing: { icon: FileText, color: 'text-amber-600', bg: 'bg-amber-50 border-amber-200' },
  completed: { icon: CheckCircle2, color: 'text-green-600', bg: 'bg-green-50 border-green-200' },
};

function AgentMessage({ message }: { message: ChatMessageType }) {
  const action = message.agent?.action || 'searching';
  const config = AGENT_ACTION_CONFIG[action] || AGENT_ACTION_CONFIG.searching;
  const Icon = config.icon;

  return (
    <div className="flex w-full gap-2 animate-slide-up">
      <div className={cn(
        'flex items-center gap-2.5 px-3.5 py-2.5 rounded-lg border w-full text-sm',
        config.bg,
      )}>
        <Icon className={cn('h-4 w-4 shrink-0', config.color)} />
        <div className="flex items-center gap-1.5 min-w-0">
          {message.agent?.name && (
            <span className="font-medium text-muted-foreground whitespace-nowrap text-xs">
              {message.agent.name}:
            </span>
          )}
          <span className="text-muted-foreground truncate">{message.content}</span>
        </div>
      </div>
    </div>
  );
}

/**
 * Single chat message component - Apple-style design
 */
export function ChatMessage({ message }: ChatMessageProps) {
  // Agent messages get their own compact rendering
  if (message.role === 'agent') {
    return <AgentMessage message={message} />;
  }

  const isUser = message.role === 'user';

  return (
    <div
      className={cn(
        'flex w-full gap-2.5 animate-slide-up',
        isUser ? 'flex-row-reverse' : 'flex-row'
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          'flex-shrink-0 h-7 w-7 rounded-full flex items-center justify-center',
          isUser
            ? 'bg-primary/10'
            : 'bg-gradient-to-br from-primary to-primary/60'
        )}
      >
        {isUser ? (
          <User className="h-3.5 w-3.5 text-primary" />
        ) : (
          <Bot className="h-3.5 w-3.5 text-primary-foreground" />
        )}
      </div>

      {/* Message bubble */}
      <div
        className={cn(
          'max-w-[80%] px-4 py-2.5 rounded-2xl',
          isUser
            ? 'bg-primary text-primary-foreground rounded-tr-md'
            : 'bg-secondary text-foreground rounded-tl-md'
        )}
      >
        <div className="flex items-start gap-2">
          {message.metadata?.status === 'processing' && (
            <span className="h-4 w-4 mt-0.5 animate-spin rounded-full border-2 border-primary border-t-transparent flex-shrink-0" />
          )}
          <p className="text-[14px] leading-relaxed whitespace-pre-wrap">
            {message.content}
          </p>
        </div>
        <p
          className={cn(
            'mt-1.5 text-[10px] opacity-50',
            isUser ? 'text-right' : 'text-left'
          )}
        >
          {new Date(message.timestamp).toLocaleTimeString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </p>
      </div>
    </div>
  );
}
