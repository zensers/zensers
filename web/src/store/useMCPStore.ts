// store/useMCPStore.ts

import { create } from 'zustand';
import { api } from '@/lib/api';
import type { 
  MCPServerInfo, 
  MCPServerListResponse, 
  MCPServerActionResponse,
  MCPServerStatus 
} from '@/types/mcp';

interface MCPState {
  // State
  servers: MCPServerInfo[];
  loading: boolean;
  error: string | null;
  lastFetched: number | null;
  
  // Operating servers (using array instead of Set for TypeScript compatibility)
  operatingServers: string[];
  
  // Actions
  fetchServers: () => Promise<void>;
  startServer: (name: string) => Promise<MCPServerActionResponse>;
  stopServer: (name: string) => Promise<MCPServerActionResponse>;
  refreshStatus: () => Promise<void>;
  clearError: () => void;
}

  // Helper: add to operating list
const addToOperating = (list: string[], name: string): string[] => {
  if (list.includes(name)) return list;
  return [...list, name];
};

// Helper: remove from operating list
const removeFromOperating = (list: string[], name: string): string[] => {
  return list.filter(n => n !== name);
};

export const useMCPStore = create<MCPState>((set, get) => ({
  // Initial state
  servers: [],
  loading: false,
  error: null,
  lastFetched: null,
  operatingServers: [],
  
  // Fetch server list
  fetchServers: async () => {
    set({ loading: true, error: null });
    
    try {
      const response: MCPServerListResponse = await api.getMCPServers();
      set({ 
        servers: response.servers,
        loading: false,
        lastFetched: Date.now(),
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch MCP server list';
      set({ error: message, loading: false });
    }
  },
  
  // Start server
  startServer: async (name: string) => {
    const { operatingServers } = get();
    
    // Prevent duplicate operations
    if (operatingServers.includes(name)) {
      return {
        success: false,
        message: 'Server is being operated on',
        server_name: name,
        new_status: 'running' as MCPServerStatus,
      };
    }
    
    // Add to operating list
    set({ 
      operatingServers: addToOperating(operatingServers, name),
      error: null,
    });
    
    // Optimistic state update
    set((state) => ({
      servers: state.servers.map(s => 
        s.name === name ? { ...s, status: 'starting' as MCPServerStatus } : s
      ),
    }));
    
    try {
      const response = await api.startMCPServer(name);
      
      // Update server status
      set((state) => ({
        servers: state.servers.map(s => 
          s.name === name ? { ...s, status: response.new_status } : s
        ),
        operatingServers: removeFromOperating(state.operatingServers, name),
      }));
      
      return response;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to start server';
      
      // Rollback state
      set((state) => ({
        servers: state.servers.map(s => 
          s.name === name ? { ...s, status: 'error' as MCPServerStatus, error: message } : s
        ),
        operatingServers: removeFromOperating(state.operatingServers, name),
        error: message,
      }));
      
      return {
        success: false,
        message,
        server_name: name,
        new_status: 'error' as MCPServerStatus,
      };
    }
  },
  
  // Stop server
  stopServer: async (name: string) => {
    const { operatingServers } = get();
    
    // Prevent duplicate operations
    if (operatingServers.includes(name)) {
      return {
        success: false,
        message: 'Server is being operated on',
        server_name: name,
        new_status: 'stopped' as MCPServerStatus,
      };
    }
    
    // Add to operating list
    set({ 
      operatingServers: addToOperating(operatingServers, name),
      error: null,
    });
    
    // Optimistic state update
    set((state) => ({
      servers: state.servers.map(s => 
        s.name === name ? { ...s, status: 'stopping' as MCPServerStatus } : s
      ),
    }));
    
    try {
      const response = await api.stopMCPServer(name);
      
      // Update server status
      set((state) => ({
        servers: state.servers.map(s => 
          s.name === name ? { ...s, status: response.new_status } : s
        ),
        operatingServers: removeFromOperating(state.operatingServers, name),
      }));
      
      return response;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to stop server';
      
      // Rollback state
      set((state) => ({
        servers: state.servers.map(s => 
          s.name === name ? { ...s, status: 'error' as MCPServerStatus, error: message } : s
        ),
        operatingServers: removeFromOperating(state.operatingServers, name),
        error: message,
      }));
      
      return {
        success: false,
        message,
        server_name: name,
        new_status: 'error' as MCPServerStatus,
      };
    }
  },
  
  // Refresh status
  refreshStatus: async () => {
    const { fetchServers } = get();
    await fetchServers();
  },
  
  // Clear error
  clearError: () => {
    set({ error: null });
  },
}));
