'use client';

import React from 'react';
import { cn } from '@/lib/utils';
import type { ChatMessage as ChatMessageType } from '@/types/api';
import { User, Bot, Search, Brain, FileText, CheckCircle2, Loader2, XCircle } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const REMARK_PLUGINS = [remarkGfm];

interface ChatMessageProps {
  message: ChatMessageType;
}

const AGENT_ACTION_CONFIG: Record<string, { icon: typeof Search; color: string; bg: string }> = {
  searching: { icon: Loader2, color: 'text-blue-600', bg: 'bg-blue-50 border-blue-200' },
  analyzing: { icon: Loader2, color: 'text-purple-600', bg: 'bg-purple-50 border-purple-200' },
  writing:   { icon: FileText, color: 'text-amber-600', bg: 'bg-amber-50 border-amber-200' },
  completed: { icon: CheckCircle2, color: 'text-green-600', bg: 'bg-green-50 border-green-200' },
  error:     { icon: XCircle, color: 'text-red-600', bg: 'bg-red-50 border-red-200' },
  warning:   { icon: XCircle, color: 'text-amber-600', bg: 'bg-amber-50 border-amber-200' },
};

function AgentMessage({ message }: { message: ChatMessageType }) {
  const action = message.agent?.action || 'searching';
  const config = AGENT_ACTION_CONFIG[action] || AGENT_ACTION_CONFIG.searching;
  const Icon = config.icon;
  const isActive = action === 'searching' || action === 'analyzing';
  const completedCount = message.agent?.completedCount || 0;
  const totalCount = message.agent?.totalCount || 0;
  const showCount = totalCount > 1;

  if (action === 'heartbeat') {
    return null;
  }

  let displayText = message.content;
  if (showCount) {
    const taskName = message.agent?.id || message.content.replace(/^Completed:\s*/, '').replace(/^completed\.?/i, '').trim() || 'tasks';
    if (action === 'completed') {
      displayText = `${completedCount}/${totalCount} ${taskName} completed`;
    } else {
      displayText = `${completedCount} ${taskName} completed, ${message.content}`;
    }
  }

  const searchMeta = message.agent?.provider
    ? ` · ${message.agent.provider}${message.agent.quality_score != null ? ` · quality ${message.agent.quality_score}` : ''}${message.agent.cache_hit ? ' · cache' : ''}`
    : '';

  return (
    <div className="flex w-full gap-2 animate-slide-up">
      <div className={cn(
        'flex items-center gap-2.5 px-3.5 py-2.5 rounded-lg border w-full text-sm',
        config.bg,
      )}>
        <Icon className={cn('h-4 w-4 shrink-0', config.color, isActive && 'animate-spin')} />
        <div className="flex items-center gap-1.5 min-w-0">
          {message.agent?.name && (
            <span className="font-medium text-muted-foreground whitespace-nowrap text-xs">
              {message.agent.name}:
            </span>
          )}
          <span className="text-muted-foreground truncate">{displayText}{searchMeta}</span>
        </div>
      </div>
    </div>
  );
}

export const ChatMessage = React.memo(function ChatMessage({ message }: ChatMessageProps) {
  if (message.role === 'agent') {
    return <AgentMessage message={message} />;
  }

  // Lifecycle status notes（暂停/停止/恢复）: centered, low-emphasis, non-blocking
  if (message.role === 'system') {
    return (
      <div className="flex w-full justify-center py-1.5 animate-slide-up" data-testid="system-note">
        <div className="max-w-[90%] rounded-full border border-border/50 bg-muted/50 px-3.5 py-1.5 text-xs text-muted-foreground text-center leading-relaxed whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    );
  }

  const isUser = message.role === 'user';
  const isThinking = message.metadata?.status === 'thinking';
  const isStreamingEmpty = message.metadata?.status === 'streaming' && !message.content;

  return (
    <div
      className={cn(
        'flex w-full gap-2.5 animate-slide-up',
        isUser ? 'flex-row-reverse' : 'flex-row'
      )}
    >
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

      <div
        className={cn(
          'max-w-[80%] px-4 py-2.5 rounded-2xl',
          isUser
            ? 'bg-primary text-primary-foreground rounded-tr-md'
            : 'bg-secondary text-foreground rounded-tl-md'
        )}
      >
        {isThinking && (
          <div className="mb-2 rounded-lg bg-muted/50 border border-border/50 px-3 py-2">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Brain className="h-3 w-3 animate-pulse" />
              <span>思考中</span>
              <span className="animate-pulse">...</span>
            </div>
            {message.thinkingContent && (
              <p data-testid="thinking-preview" className="mt-1 text-xs text-muted-foreground/70 leading-relaxed whitespace-pre-wrap line-clamp-3">
                {message.thinkingContent.slice(-200)}
              </p>
            )}
          </div>
        )}
        {!isThinking && message.thinkingContent && (
          <details className="mb-2 rounded-lg bg-muted/50 border border-border/50 px-3 py-2">
            <summary className="text-xs text-muted-foreground cursor-pointer select-none flex items-center gap-1.5">
              <Brain className="h-3 w-3" />
              思考过程
            </summary>
            <p className="mt-2 text-xs text-muted-foreground leading-relaxed whitespace-pre-wrap max-h-[300px] overflow-y-auto">
              {message.thinkingContent}
            </p>
          </details>
        )}
        <div className="flex items-start gap-2">
          {isStreamingEmpty && (
            <div className="flex items-center gap-2">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
              <span className="text-xs text-muted-foreground">生成中...</span>
            </div>
          )}
          {isUser ? (
            <p className="text-[14px] leading-relaxed whitespace-pre-wrap">
              {message.content}
            </p>
          ) : (
            <div className="prose prose-sm prose-chat max-w-none text-[14px] leading-relaxed
              prose-p:my-1 prose-p:first:mt-0 prose-p:last:mb-0
              prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5
              prose-headings:font-semibold
            ">
              <ReactMarkdown remarkPlugins={REMARK_PLUGINS}>{message.content}</ReactMarkdown>
            </div>
          )}
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
}, (prev, next) => {
  const p = prev.message, n = next.message;
  return p.id === n.id
    && p.role === n.role
    && p.content === n.content
    && p.thinkingContent === n.thinkingContent
    && p.metadata?.status === n.metadata?.status
    && p.agent?.action === n.agent?.action
    && p.agent?.completedCount === n.agent?.completedCount
    && p.agent?.totalCount === n.agent?.totalCount;
});
