// components/mcp/MCPServerItem.tsx

'use client';

import { Switch } from '@/components/ui/switch';
import { MCPServerInfo } from '@/types/mcp';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface MCPServerItemProps {
  server: MCPServerInfo;
  onToggle: (name: string, checked: boolean) => void;
  isOperating?: boolean;
}

/**
 * MCP server item component - Apple-style simplified design
 * Only shows name and toggle
 */
export function MCPServerItem({ 
  server, 
  onToggle, 
  isOperating = false 
}: MCPServerItemProps) {
  const isRunning = server.status === 'running';
  const isDisabled = server.status === 'disabled' || !server.enabled;
  const isTransitioning = server.status === 'starting' || server.status === 'stopping';
  
  const handleToggle = (checked: boolean) => {
    if (isOperating || isTransitioning) return;
    onToggle(server.name, checked);
  };

  return (
    <div className={cn(
      "flex items-center justify-between py-2.5 px-1",
      isDisabled && "opacity-50"
    )}>
      {/* 服务器名称 */}
      <div className="flex items-center gap-2 min-w-0">
        {(isOperating || isTransitioning) ? (
          <Loader2 className="h-3.5 w-3.5 text-muted-foreground animate-spin flex-shrink-0" />
        ) : (
          <div className={cn(
            "h-2 w-2 rounded-full flex-shrink-0",
            isRunning ? "bg-emerald-500" : "bg-gray-400"
          )} />
        )}
        <span className="text-sm font-medium truncate">
          {server.name}
        </span>
      </div>
      
      {/* 开关 */}
      <Switch
        checked={isRunning}
        disabled={isDisabled || isOperating || isTransitioning}
        onCheckedChange={handleToggle}
        className="data-[state=checked]:bg-emerald-500"
      />
    </div>
  );
}
