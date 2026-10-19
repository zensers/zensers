// types/mcp.ts

/**
 * MCP server transport type
 */
export type TransportType = 'stdio' | 'sse' | 'streamable_http';

/**
 * MCP server status
 */
export type MCPServerStatus = 
  | 'running' 
  | 'stopped' 
  | 'starting' 
  | 'stopping' 
  | 'error' 
  | 'disabled';

/**
 * MCP server info
 */
export interface MCPServerInfo {
  name: string;
  transport: TransportType;
  enabled: boolean;
  status: MCPServerStatus;
  description?: string;
  tools_count: number;
  latency_ms: number;
  error?: string;
  tags: string[];
}

/**
 * MCP server list response
 */
export interface MCPServerListResponse {
  servers: MCPServerInfo[];
  total: number;
  healthy_count: number;
  running_count: number;
}

/**
 * MCP server action response
 */
export interface MCPServerActionResponse {
  success: boolean;
  message: string;
  server_name: string;
  new_status: MCPServerStatus;
}

/**
 * MCP health check summary
 */
export interface MCPHealthSummary {
  total_servers: number;
  healthy: number;
  unhealthy: number;
  healthy_ratio: number;
  last_check: string;
}

/**
 * MCP health check response
 */
export interface MCPHealthResponse {
  summary: MCPHealthSummary;
  details: Record<string, Record<string, unknown>>;
}
