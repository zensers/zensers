// components/preview/DocumentPreview.tsx

'use client';

import { usePreview } from '@/hooks/usePreview';
import { useResearchStore } from '@/store/useResearchStore';
import { useDesktopStore } from '@/store/useDesktopStore';
import { api, buildDownloadUrl } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { 
  FileText, 
  RefreshCw, 
  Download, 
  Maximize2, 
  Minimize2,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  FileDown,
  Loader2,
  CheckCircle2,
} from 'lucide-react';
import { useState, useCallback, useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';

interface DocumentPreviewProps {
  /** Specify task ID (for history page) */
  taskIdOverride?: string;
}

// Zoom level range
const MIN_SCALE = 0.5;
const MAX_SCALE = 2.0;
const SCALE_STEP = 0.25;

/**
 * Document preview component
 * Apple-style design, supports HTML and PDF format preview
 */
export function DocumentPreview({ taskIdOverride }: DocumentPreviewProps) {
  const { taskId: storeTaskId, status, previewRefreshKey } = useResearchStore();
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [scale, setScale] = useState(1.0);
  
  // Use provided taskId or store taskId
  const taskId = taskIdOverride || storeTaskId;
  
  const { preview, isLoading, error, refetch } = usePreview({
    taskId,
    enabled: !!taskId && (status === 'completed' || !!taskIdOverride),
    format: 'html',
  });

  // P1 fix: Auto-refetch on completion - simplified and more reliable
  // Trigger when: status changes to 'completed' OR previewRefreshKey changes
  const prevStatusRef = useRef(status);
  const prevRefreshKeyRef = useRef(previewRefreshKey);
  
  useEffect(() => {
    // Detect completion transition
    const justCompleted = prevStatusRef.current !== 'completed' && status === 'completed';
    // Detect manual refresh request
    const refreshRequested = previewRefreshKey !== prevRefreshKeyRef.current;
    
    if ((justCompleted || refreshRequested) && taskId) {
      // Small delay to ensure backend has updated the document
      const timer = setTimeout(() => {
        refetch();
      }, 500);
      
      prevStatusRef.current = status;
      prevRefreshKeyRef.current = previewRefreshKey;
      return () => clearTimeout(timer);
    }
    
    prevStatusRef.current = status;
    prevRefreshKeyRef.current = previewRefreshKey;
  }, [status, taskId, refetch, previewRefreshKey]);

  // Auto-refetch when revision phase completes
  const phases = useResearchStore((s) => s.phases);
  const prevPhasesRef = useRef(phases);
  useEffect(() => {
    const prevRev = prevPhasesRef.current.find(p => p.id === 'revision');
    const currRev = phases.find(p => p.id === 'revision');
    const wasRunning = prevRev?.status === 'running';
    const isNowCompleted = currRev?.status === 'completed';
    if (wasRunning && isNowCompleted && taskId) {
      const timer = setTimeout(() => refetch(), 300);
      prevPhasesRef.current = phases;
      return () => clearTimeout(timer);
    }
    prevPhasesRef.current = phases;
  }, [phases, taskId, refetch]);

  // Zoom controls
  const handleZoomIn = useCallback(() => {
    setScale(prev => Math.min(prev + SCALE_STEP, MAX_SCALE));
  }, []);

  const handleZoomOut = useCallback(() => {
    setScale(prev => Math.max(prev - SCALE_STEP, MIN_SCALE));
  }, []);

  const handleZoomReset = useCallback(() => {
    setScale(1.0);
  }, []);

  // Zoom percentage display
  const scalePercent = Math.round(scale * 100);

  // Show empty state when no task ID
  if (!taskId) {
    return (
      <div className="flex h-full items-center justify-center bg-muted/5">
        <div className="text-center px-8">
          <div className="mx-auto mb-4 h-16 w-16 rounded-2xl bg-secondary/50 flex items-center justify-center">
            <FileText className="h-8 w-8 text-muted-foreground/60" />
          </div>
          <p className="text-sm font-medium text-foreground">No preview content</p>
          <p className="text-xs text-muted-foreground mt-1">Reports can be viewed here after research is complete</p>
        </div>
      </div>
    );
  }

  // Show waiting state during research execution
  if (status === 'running' && !taskIdOverride) {
    return (
      <div className="flex h-full items-center justify-center bg-muted/5">
        <div className="text-center px-8">
          <div className="relative mx-auto mb-4 h-12 w-12">
            <div className="absolute inset-0 rounded-full border-2 border-primary/20" />
            <div className="absolute inset-0 rounded-full border-2 border-primary border-t-transparent animate-spin" />
          </div>
          <p className="text-sm font-medium text-foreground">Research in progress</p>
          <p className="text-xs text-muted-foreground mt-1">Report will display automatically after completion</p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center bg-muted/5">
        <div className="text-center">
          <div className="relative mx-auto mb-4 h-10 w-10">
            <div className="absolute inset-0 rounded-full border-2 border-primary/20" />
            <div className="absolute inset-0 rounded-full border-2 border-primary border-t-transparent animate-spin" />
          </div>
          <p className="text-sm text-muted-foreground">Loading preview...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center bg-muted/5 p-6">
        <div className="text-center max-w-sm">
          <div className="mx-auto mb-4 h-12 w-12 rounded-full bg-destructive/10 flex items-center justify-center">
            <FileText className="h-6 w-6 text-destructive" />
          </div>
          <p className="text-sm font-medium text-foreground mb-1">Preview load failed</p>
          <p className="text-xs text-muted-foreground mb-4">{error.message}</p>
          <Button onClick={refetch} variant="secondary" size="sm" className="rounded-xl">
            <RefreshCw className="h-4 w-4 mr-2" />
            Retry
          </Button>
        </div>
      </div>
    );
  }

  if (!preview) {
    return (
      <div className="flex h-full items-center justify-center bg-muted/5">
        <div className="text-center">
          <div className="mx-auto mb-4 h-16 w-16 rounded-2xl bg-secondary/50 flex items-center justify-center">
            <FileText className="h-8 w-8 text-muted-foreground/60" />
          </div>
          <p className="text-sm text-muted-foreground">No preview content</p>
          <Button onClick={refetch} variant="ghost" size="sm" className="mt-3 rounded-xl">
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>
      </div>
    );
  }

  const format = preview.format || preview.preview_format;
  const title = preview.title || 'Research Report';

  return (
    <div className={cn(
      "flex h-full flex-col bg-background",
      isFullscreen && "fixed inset-0 z-50 bg-background"
    )}>
      {/* 工具栏 */}
      <div className="flex items-center justify-between border-b border-border/50 px-4 py-2 bg-muted/30">
        <div className="flex items-center gap-3">
          <Badge 
            variant="secondary" 
            className="rounded-lg text-[10px] font-medium px-2 py-0.5"
          >
            {(format || 'html').toUpperCase()}
          </Badge>
          <span className="text-sm font-medium text-foreground truncate max-w-[200px]">{title}</span>
        </div>
        
        <div className="flex items-center gap-2">
          {/* 缩放控制 */}
          <div className="flex items-center gap-1 px-2 py-1 rounded-lg bg-secondary/50">
            <Button 
              variant="ghost" 
              size="icon" 
              onClick={handleZoomOut}
              disabled={scale <= MIN_SCALE}
              className="h-6 w-6 rounded-md"
            >
              <ZoomOut className="h-3.5 w-3.5" />
            </Button>
            
            <span className="text-xs text-muted-foreground w-8 text-center tabular-nums">
              {scalePercent}%
            </span>
            
            <Button 
              variant="ghost" 
              size="icon" 
              onClick={handleZoomIn}
              disabled={scale >= MAX_SCALE}
              className="h-6 w-6 rounded-md"
            >
              <ZoomIn className="h-3.5 w-3.5" />
            </Button>
            
            <Button 
              variant="ghost" 
              size="icon" 
              onClick={handleZoomReset}
              disabled={scale === 1.0}
              className="h-6 w-6 rounded-md"
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </Button>
          </div>
          
          {/* 分隔线 */}
          <div className="h-4 w-px bg-border/50" />
          
          {/* 刷新按钮 - 更明显 */}
          <Button 
            variant="outline" 
            size="sm" 
            onClick={refetch}
            disabled={isLoading}
            className="h-8 gap-1.5 px-3 rounded-lg"
            title="刷新报告预览"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", isLoading && "animate-spin")} />
            <span className="text-xs">刷新</span>
          </Button>
          
          {preview.download_url && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 rounded-lg"
              onClick={() => {
                window.open(buildDownloadUrl(preview.download_url!), '_blank');
              }}
            >
              <Download className="h-4 w-4" />
            </Button>
          )}
          
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="h-8 w-8 rounded-lg"
          >
            {isFullscreen ? (
              <Minimize2 className="h-4 w-4" />
            ) : (
              <Maximize2 className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>

      {/* 预览内容 - 使用 CSS zoom 而非 transform:scale 避免空白区域 */}
      <div className="flex-1 overflow-auto bg-muted/5 p-3">
        <div className="min-h-full bg-white rounded-xl border border-border/50 shadow-sm overflow-hidden">
          {format === 'html' && preview.html_content ? (
            <div
              className="w-full h-full"
              style={{ zoom: scale, overflow: 'visible' }}
            >
              <iframe
                srcDoc={preview.html_content}
                className="w-full border-0"
                title="Document Preview"
                style={{ height: `${100 / scale}vh`, minHeight: '800px' }}
              />
            </div>
          ) : preview.preview_url ? (
            <div
              className="w-full h-full"
              style={{ zoom: scale, overflow: 'visible' }}
            >
              <iframe
                src={buildDownloadUrl(preview.preview_url)}
                className="w-full border-0"
                title="Document Preview"
                style={{ height: `${100 / scale}vh`, minHeight: '800px' }}
              />
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              <div className="text-center">
                <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p className="text-sm">Cannot preview this format</p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 底部: 定稿转换 → 下载（两步流程） */}
      {status === 'completed' && (
        <FinalizeToolbar taskId={taskId} />
      )}
    </div>
  );
}

/** 定稿工具栏: 先 Convert → 再 Download */
function FinalizeToolbar({ taskId }: { taskId: string | null }) {
  const isDesktop = useDesktopStore((s) => s.isDesktop);
  const [finalizing, setFinalizing] = useState(false);
  const [finalized, setFinalized] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const handleFinalize = async () => {
    if (!taskId) return;
    setFinalizing(true);
    setError(null);
    setInfo(null);
    try {
      const res = await api.exportDocument(taskId, 'latest', 'docx');
      if (res.status === 'success') {
        setFinalized(true);
        setDownloadUrl(res.download_url ?? null);
      } else {
        setError(res.error || 'Finalize failed');
      }
    } catch (e: any) {
      setError(e?.message || 'Finalize failed');
    } finally {
      setFinalizing(false);
    }
  };

  const handleDownload = useCallback(async () => {
    setError(null);
    setInfo(null);

    if (!taskId || !downloadUrl) {
      setError('请先转换文档');
      return;
    }
    
    const fileName = `${taskId}_report.docx`;
    
    // Layer 1: pywebview 原生保存对话框（桌面模式）
    if (isDesktop) {
      try {
        const pywebviewApi = (window as any).pywebview?.api;
        if (pywebviewApi?.download_and_save) {
          const result = await pywebviewApi.download_and_save(
            downloadUrl,
            fileName,
            'docx'
          );
          if (result.success) {
            return;
          }
          if (result.error === 'Cancelled by user') {
            return;
          }
          // 其他错误：降级到浏览器下载（不 return）
          console.warn('[DOWNLOAD] pywebview returned error, falling back:', result.error);
        }
      } catch (e: any) {
        // 异常：降级到浏览器下载（不 return）
        console.warn('[DOWNLOAD] pywebview threw, falling back:', e);
      }
    }
    
    // Layer 2: 浏览器下载
    try {
      const fetchUrl = buildDownloadUrl(downloadUrl);
      const response = await fetch(fetchUrl);
      if (!response.ok) {
        setError('下载失败: 文件不存在');
        return;
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      setInfo('文件已保存到浏览器默认下载目录');
    } catch (e: any) {
      setError(e?.message || '下载失败');
    }
  }, [taskId, downloadUrl, isDesktop]);

  return (
    <div className="flex items-center gap-2 border-t border-border/50 px-4 py-2 bg-muted/30">
      <span className="text-xs text-muted-foreground mr-2">
        Revision? Just tell me in the chat — I'll handle it.
      </span>
      <div className="flex-1" />
      {error && <span className="text-xs text-red-500 mr-2">{error}</span>}
      {info && <span className="text-xs text-blue-500 mr-2">{info}</span>}
      {!finalized ? (
        <Button
          variant="default"
          size="sm"
          className="rounded-lg text-xs h-7"
          onClick={handleFinalize}
          disabled={finalizing || !taskId}
        >
          {finalizing ? (
            <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
          ) : (
            <FileDown className="h-3.5 w-3.5 mr-1" />
          )}
          {finalizing ? 'Converting...' : 'Convert to DOCX'}
        </Button>
      ) : (
        <Button
          variant="default"
          size="sm"
          className="rounded-lg text-xs h-7"
          onClick={handleDownload}
        >
          <Download className="h-3.5 w-3.5 mr-1" />
          <CheckCircle2 className="h-3.5 w-3.5 mr-0.5 text-green-400" />
          {isDesktop ? 'Save As...' : 'Download DOCX'}
        </Button>
      )}
    </div>
  );
}
