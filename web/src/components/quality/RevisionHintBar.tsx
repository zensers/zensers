'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { cn } from '@/lib/utils';
import { RotateCcw, X, AlertTriangle, CheckCircle2 } from 'lucide-react';

interface RevisionHintBarProps {
  visible: boolean;
  scoreDelta?: number;
  hasLayoutIssue?: boolean;
  onRollback?: () => void;
  onDismiss?: () => void;
  autoHideMs?: number;
  className?: string;
}

export function RevisionHintBar({
  visible,
  scoreDelta,
  hasLayoutIssue = false,
  onRollback,
  onDismiss,
  autoHideMs = 5000,
  className,
}: RevisionHintBarProps) {
  const [show, setShow] = useState(false);
  const onDismissRef = useRef(onDismiss);
  onDismissRef.current = onDismiss;

  useEffect(() => {
    if (!visible) {
      setShow(false);
      return;
    }
    setShow(true);
    if (autoHideMs <= 0) return;
    const timer = setTimeout(() => {
      setShow(false);
      onDismissRef.current?.();
    }, autoHideMs);
    return () => clearTimeout(timer);
  }, [visible, autoHideMs]);

  const handleRollback = useCallback(() => {
    setShow(false);
    onRollback?.();
  }, [onRollback]);

  const handleDismiss = useCallback(() => {
    setShow(false);
    onDismiss?.();
  }, [onDismiss]);

  if (!show) return null;

  return (
    <div
      className={cn(
        'flex items-center gap-3 px-3 py-2 border-b text-xs animate-in slide-in-from-top-1 duration-200',
        hasLayoutIssue ? 'bg-destructive/5 border-destructive/20' : 'bg-emerald-500/5 border-emerald-500/20',
        className,
      )}
    >
      {hasLayoutIssue ? (
        <AlertTriangle className="h-3.5 w-3.5 text-destructive shrink-0" />
      ) : (
        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 shrink-0" />
      )}

      <span className={cn('flex-1', hasLayoutIssue ? 'text-destructive' : 'text-emerald-700')}>
        {hasLayoutIssue
          ? '修订完成但预览可能存在排版问题'
          : '修订完成，预览已更新'}
        {scoreDelta !== undefined && scoreDelta !== 0 && (
          <span className={cn('ml-1 font-medium', scoreDelta > 0 ? 'text-emerald-600' : 'text-destructive')}>
            评分{scoreDelta > 0 ? '+' : ''}{scoreDelta}
          </span>
        )}
      </span>

      {hasLayoutIssue && onRollback && (
        <button
          onClick={handleRollback}
          className="shrink-0 flex items-center gap-1 px-2 py-0.5 rounded-md bg-destructive/10 text-destructive hover:bg-destructive/20 transition-colors"
        >
          <RotateCcw className="h-3 w-3" />
          一键回滚
        </button>
      )}

      <button
        onClick={handleDismiss}
        className="shrink-0 p-0.5 rounded hover:bg-muted transition-colors"
      >
        <X className="h-3 w-3 text-muted-foreground" />
      </button>
    </div>
  );
}
