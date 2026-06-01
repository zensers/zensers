// components/mcp/MCPSelector.tsx

'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { MCPServerItem } from './MCPServerItem';
import { useMCPStore } from '@/store/useMCPStore';
import { Server, ChevronDown, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * MCP selector component - Apple-style simplified design
 * Only shows name and toggle
 */
export function MCPSelector() {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  
  const {
    servers,
    loading,
    operatingServers,
    fetchServers,
    startServer,
    stopServer,
  } = useMCPStore();
  
  // Initial load
  useEffect(() => {
    fetchServers();
  }, [fetchServers]);
  
  // Click outside to close
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);
  
  // Toggle server status
  const handleToggle = useCallback((name: string, checked: boolean) => {
    if (checked) {
      startServer(name);
    } else {
      stopServer(name);
    }
  }, [startServer, stopServer]);
  
  // Check if server is operating
  const isOperating = (name: string) => operatingServers.includes(name);
  
  // Running count
  const runningCount = servers.filter(s => s.status === 'running').length;
  
  return (
    <div ref={containerRef} className="relative">
      {/* 触发按钮 */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          "h-9 rounded-xl gap-1.5 px-3",
          "hover:bg-secondary/80 transition-all duration-200",
          isOpen && "bg-secondary/80"
        )}
      >
        {loading && servers.length === 0 ? (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        ) : (
          <Server className="h-4 w-4 text-muted-foreground" />
        )}
        <span className="hidden sm:inline text-sm">MCP</span>
        {runningCount > 0 && (
          <span className="text-xs text-emerald-500 font-medium">
            {runningCount}
          </span>
        )}
        <ChevronDown className={cn(
          "h-3.5 w-3.5 text-muted-foreground transition-transform duration-200",
          isOpen && "rotate-180"
        )} />
      </Button>
      
      {/* 下拉面板 */}
      {isOpen && (
        <div className={cn(
          "absolute right-0 top-full mt-2 z-50",
          "w-56 p-3",
          "bg-background/95 backdrop-blur-xl",
          "border border-border/50 rounded-2xl",
          "shadow-xl shadow-black/5"
        )}>
          {/* Title */}
          <div className="text-xs text-muted-foreground mb-2 px-1">
            MCP Servers
          </div>
          
          {/* 服务器列表 */}
          <div className="space-y-1">
            {loading && servers.length === 0 ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : servers.length === 0 ? (
              <div className="text-center py-4 text-muted-foreground text-xs">
                No configuration
              </div>
            ) : (
              servers.map((server) => (
                <MCPServerItem
                  key={server.name}
                  server={server}
                  onToggle={handleToggle}
                  isOperating={isOperating(server.name)}
                />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
