// components/layout/Header.tsx

'use client';

import { useState, useCallback, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { useResearchStore } from '@/store/useResearchStore';
import { useChatStore } from '@/store/useChatStore';
import { useSettingsStore } from '@/store/useSettingsStore';
import { UpdateBadge } from '@/components/layout/UpdateBadge';
import { Sidebar } from '@/components/history/Sidebar';
import { MCPSelector } from '@/components/mcp';
import { Menu, Plus, Clock, Settings, Sparkles, Eye, EyeOff } from 'lucide-react';

interface HeaderProps {
  onTogglePreview?: () => void;
  previewVisible?: boolean;
}

/**
 * Top navigation bar - Apple-style design
 */
export function Header({ onTogglePreview, previewVisible }: HeaderProps) {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const router = useRouter();
  const { status, reset, sessionId, setViewingResearch } = useResearchStore();
  const clearMessages = useChatStore((s) => s.clearMessages);
  const loadModels = useSettingsStore((s) => s.loadModels);

  useEffect(() => { loadModels(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleNewResearch = useCallback(() => {
    if (status === 'running') {
      if (confirm('A research task is currently running. Are you sure you want to start a new one?')) {
        reset();
        clearMessages();
        router.push('/');
      }
    } else {
      reset();
      clearMessages();
      router.push('/');
    }
  }, [status, reset, clearMessages, router]);

  return (
    <>
      <header className="flex h-[52px] items-center justify-between border-b bg-background px-4">
        {/* 左侧 */}
        <div className="flex items-center gap-2">
          {/* 菜单按钮 */}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setIsSidebarOpen(true)}
            className="h-9 w-9 rounded-xl hover:bg-secondary/80"
          >
            <Menu className="h-5 w-5" />
          </Button>

          {/* Logo */}
          <Link href="/" className="flex items-center gap-2.5 ml-1">
            <div className="h-8 w-8 rounded-xl bg-background border overflow-hidden">
              <img src="/logo.png" alt="Zensers" className="h-full w-full object-contain" />
            </div>
            <span className="font-semibold text-[15px] tracking-tight">Zensers</span>
          </Link>

          {/* 当前会话指示器 */}
          {sessionId && (
            <div className="hidden md:flex items-center gap-2 ml-3 pl-3 border-l border-border/50">
              <div className="h-2 w-2 rounded-full bg-primary animate-pulse" />
              <span className="text-xs text-muted-foreground">Researching</span>
            </div>
          )}
        </div>

        {/* 右侧导航 */}
        <nav className="flex items-center gap-1">
          <Button 
            variant="ghost" 
            size="sm" 
            onClick={handleNewResearch}
            className="h-9 rounded-xl gap-1.5 hover:bg-secondary/80"
          >
            <Plus className="h-4 w-4" />
            <span className="hidden sm:inline text-sm">New</span>
          </Button>
          
          <Link href="/history">
            <Button variant="ghost" size="sm" className="h-9 rounded-xl gap-1.5 hover:bg-secondary/80">
              <Clock className="h-4 w-4" />
              <span className="hidden sm:inline text-sm">History</span>
            </Button>
          </Link>
          
          {/* MCP 选择器 */}
          <MCPSelector />

          {/* 预览开关 */}
          {onTogglePreview && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onTogglePreview}
              className="h-9 w-9 rounded-xl hover:bg-secondary/80"
              title={previewVisible ? 'Close preview' : 'Open preview'}
            >
              {previewVisible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </Button>
          )}

          <UpdateBadge />

          <Link href="/settings">
            <Button variant="ghost" size="sm" className="h-9 rounded-xl gap-1.5 hover:bg-secondary/80">
              <Settings className="h-4 w-4" />
              <span className="hidden sm:inline text-sm">Settings</span>
            </Button>
          </Link>
        </nav>
      </header>

      {/* 侧边栏 */}
      <Sidebar isOpen={isSidebarOpen} onClose={() => setIsSidebarOpen(false)} onViewResearch={() => setViewingResearch(true)} />
    </>
  );
}
