// components/history/SessionList.tsx

'use client';

import { useRouter } from 'next/navigation';
import { useHistorySessions } from '@/hooks/useHistorySessions';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { formatDistanceToNow } from '@/lib/utils';
import {
  FileText,
  Presentation,
  FileSpreadsheet,
  Clock,
  ChevronRight,
  RefreshCw,
  AlertCircle,
  Inbox,
  Loader2,
} from 'lucide-react';
import type { ResearchResultMeta } from '@/types/api';

/**
 * Get output type icon
 */
function getOutputIcon(format?: string) {
  switch (format) {
    case 'pptx':
      return <Presentation className="h-4 w-4" />;
    case 'xlsx':
    case 'csv':
      return <FileSpreadsheet className="h-4 w-4" />;
    default:
      return <FileText className="h-4 w-4" />;
  }
}

/**
 * Get status color
 */
function getStatusColor(status: string) {
  switch (status) {
    case 'completed':
      return 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400';
    case 'reporting':
      return 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400';
    case 'collecting':
      return 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400';
    case 'analyzing':
      return 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400';
    case 'paused':
      return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400';
    case 'document_pending':
    case 'document_generated':
      return 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400';
    default:
      return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400';
  }
}

/**
 * Get status text
 */
function getStatusText(status: string) {
  switch (status) {
    case 'completed':
      return 'Completed';
    case 'analyzing':
      return 'Configuring';
    case 'collecting':
      return 'Collecting';
    case 'reporting':
      return 'In Progress';
    case 'paused':
      return 'Paused';
    case 'document_pending':
      return 'Pending';
    case 'document_generated':
      return 'Generated';
    default:
      return status;
  }
}

/**
 * History session list
 */
export function SessionList() {
  const router = useRouter();
  const { sessions, isLoading, error, reload, loadMore, hasMore } = useHistorySessions();

  if (isLoading && sessions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-12 space-y-4">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-primary/30 border-t-primary" />
        <p className="text-sm text-muted-foreground">Loading history...</p>
      </div>
    );
  }

  if (error) {
    return (
      <Card className="border-destructive/50 bg-destructive/5">
        <CardContent className="p-6">
          <div className="flex items-center gap-4">
            <AlertCircle className="h-10 w-10 text-destructive" />
            <div className="flex-1">
              <p className="font-medium text-destructive">Failed to load</p>
              <p className="text-sm text-muted-foreground">{error.message}</p>
            </div>
            <Button onClick={reload} variant="outline" size="sm">
              <RefreshCw className="h-4 w-4 mr-2" />
              Retry
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (sessions.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="p-12">
          <div className="flex flex-col items-center text-center space-y-4">
            <div className="h-16 w-16 rounded-full bg-muted flex items-center justify-center">
              <Inbox className="h-8 w-8 text-muted-foreground" />
            </div>
            <div>
              <p className="font-medium">No research history</p>
              <p className="text-sm text-muted-foreground mt-1">
                Start your research journey, all studies will be saved automatically
              </p>
            </div>
            <Button onClick={() => router.push('/')} className="mt-2">
              Start New Research
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3 overflow-y-auto">
      {sessions.map((session) => (
        <Card
          key={session.task_id}
          className="group cursor-pointer hover:shadow-md hover:border-primary/30 transition-all duration-200"
          onClick={() => router.push(`/history/${session.task_id}`)}
        >
          <CardContent className="p-4">
            <div className="flex items-start gap-4">
              {/* Icon */}
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                {getOutputIcon(session.output_format)}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-medium text-foreground line-clamp-1 group-hover:text-primary transition-colors">
                    {session.title || session.topic || 'Unnamed Research'}
                  </h3>
                  <Badge className={cn('shrink-0', getStatusColor(session.status))}>
                    {getStatusText(session.status)}
                  </Badge>
                </div>
                
                <p className="text-sm text-muted-foreground line-clamp-2 mt-1">
                  {session.query || session.topic}
                </p>

                <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground">
                  <div className="flex items-center gap-1.5">
                    <Clock className="h-3.5 w-3.5" />
                    <span>
                      {session.created_at
                        ? formatDistanceToNow(new Date(session.created_at))
                        : 'Unknown time'}
                    </span>
                  </div>
                  {session.output_format && (
                    <>
                      <span>•</span>
                      <span className="uppercase">{session.output_format}</span>
                    </>
                  )}
                  {session.generated_formats && session.generated_formats.length > 0 && (
                    <>
                      <span>•</span>
                      <span>{session.generated_formats.length} versions</span>
                    </>
                  )}
                </div>
              </div>

              {/* Arrow */}
              <ChevronRight className="h-5 w-5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
          </CardContent>
        </Card>
      ))}

      {hasMore && (
        <div className="flex justify-center py-4">
          <Button
            variant="outline"
            size="sm"
            onClick={loadMore}
            disabled={isLoading}
            className="text-sm"
          >
            {isLoading ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Loading...
              </>
            ) : (
              'Load More'
            )}
          </Button>
        </div>
      )}
    </div>
  );
}

// Helper function
function cn(...classes: (string | boolean | undefined)[]) {
  return classes.filter(Boolean).join(' ');
}
