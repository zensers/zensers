'use client';

import { useSettingsStore } from '@/store/useSettingsStore';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { PRESET_MODELS, PROVIDER_INFO, LLMProvider, BackendLLMConfig } from '@/types/settings';
import { Eye, EyeOff, RefreshCw, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import { useState, useEffect, useRef, useMemo } from 'react';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const STORAGE_KEY = 'Zensers-settings-v2';

export function LLMConfigPanel() {
  const { llm, savedLlm, isSaving, saveError, updateLLMConfig, switchProvider, persistLLMConfig, applyBackendConfig, syncConfigToBackend } = useSettingsStore();
  const [mounted, setMounted] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [backendConfig, setBackendConfig] = useState<BackendLLMConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);

  const hasUnsavedChanges = useMemo(
    () => JSON.stringify(llm) !== JSON.stringify(savedLlm),
    [llm, savedLlm]
  );

  const hasUnsavedChangesRef = useRef(hasUnsavedChanges);
  hasUnsavedChangesRef.current = hasUnsavedChanges;

  useEffect(() => { setMounted(true); }, []);

  useEffect(() => {
    return () => {
      if (hasUnsavedChangesRef.current) {
        console.warn('[LLMConfigPanel] Unsaved LLM config changes discarded on unmount');
      }
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadBackendConfig() {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 8000);
        const response = await fetch(`${API_BASE_URL}/api/v1/llm/config`, { signal: controller.signal });
        clearTimeout(timeoutId);
        if (!response.ok) throw new Error('Failed to fetch backend config');
        const config: BackendLLMConfig = await response.json();
        if (cancelled) return;
        setBackendConfig(config);
        setError(null);

        try {
          if (typeof localStorage !== 'undefined') {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) {
              applyBackendConfig(config);
            } else {
              syncConfigToBackend();
            }
          }
        } catch {}
      } catch (err) {
        if (cancelled) return;
        console.error('Failed to load backend config:', err);
        setError('Unable to load backend config, please check if backend service is running');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadBackendConfig();
    return () => { cancelled = true; };
  }, []);

  if (!mounted) {
    return <div className="space-y-6"><div className="min-h-[52px]" /></div>;
  }

  const handleResetToBackendDefault = async () => {
    setResetting(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/llm/config/reset`, {
        method: 'POST',
      });
      if (!response.ok) throw new Error('Failed to reset backend config');
      const config: BackendLLMConfig = await response.json();
      setBackendConfig(config);
      applyBackendConfig(config);
      persistLLMConfig();
      setError(null);
    } catch {
      setError('Unable to reset backend config');
    } finally {
      setResetting(false);
    }
  };

  const handleSave = async () => {
    await persistLLMConfig();
  };

  const providers = Object.entries(PROVIDER_INFO).map(([id, info]) => ({
    id,
    ...info,
  }));

  const filteredModels = PRESET_MODELS.filter(
    (m) => m.provider === llm.provider || llm.provider === 'custom'
  );

  return (
    <div className="space-y-6">
      <div className="min-h-[52px]">
        {loading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground p-4 bg-muted/50 rounded-lg">
            <RefreshCw className="h-4 w-4 animate-spin" />
            <span>Loading backend config...</span>
          </div>
        )}

        {error && !loading && (
          <div className="flex items-center gap-2 text-sm text-amber-600 dark:text-amber-400 p-4 bg-amber-50 dark:bg-amber-950/20 rounded-lg">
            <AlertCircle className="h-4 w-4" />
            <span>{error} · Using local config</span>
          </div>
        )}

        {!loading && !error && backendConfig && (
          <div className="flex items-center justify-between p-4 bg-muted/30 rounded-lg">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <CheckCircle2 className="h-4 w-4" />
              <span>
                Backend env: <span className="font-medium">{backendConfig.model}</span> ({PROVIDER_INFO[backendConfig.provider as LLMProvider]?.name || backendConfig.provider})
              </span>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleResetToBackendDefault}
              disabled={resetting}
            >
              {resetting ? <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
              Reset to Default
            </Button>
          </div>
        )}

        {!loading && !error && !backendConfig && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground p-4 bg-muted/30 rounded-lg">
            <CheckCircle2 className="h-4 w-4" />
            <span>Using local config</span>
          </div>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>LLM Configuration</CardTitle>
          <CardDescription>Configure your LLM API</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <Label htmlFor="provider">Provider</Label>
            <Select
              value={llm.provider}
              onValueChange={(v) => switchProvider(v as LLMProvider)}
            >
              <SelectTrigger id="provider">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {providers.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="endpoint">API Endpoint</Label>
            <Input
              id="endpoint"
              value={llm.apiEndpoint}
              onChange={(e) => updateLLMConfig({ apiEndpoint: e.target.value })}
              placeholder="https://api.example.com/v1"
            />
            {llm.provider === 'local' && (
              <p className="text-xs text-muted-foreground">
                Default ports: Ollama (11434), LocalAI (8080)
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="apiKey">API Key</Label>
            <div className="relative">
              <Input
                id="apiKey"
                type={showApiKey ? 'text' : 'password'}
                value={llm.apiKey}
                onChange={(e) => updateLLMConfig({ apiKey: e.target.value })}
                placeholder="sk-..."
                className="pr-10"
              />
              <button
                type="button"
                onClick={() => setShowApiKey(!showApiKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            <p className="text-xs text-muted-foreground">
              API Key is stored locally in the browser only, not uploaded to server
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="model">Model</Label>
            {llm.provider === 'custom' ? (
              <Input
                id="model"
                value={llm.model}
                onChange={(e) => updateLLMConfig({ model: e.target.value })}
                placeholder="Enter model name"
              />
            ) : (
              <Select
                value={llm.model}
                onValueChange={(v) => updateLLMConfig({ model: v })}
              >
                <SelectTrigger id="model">
                  <SelectValue placeholder="Select model" />
                </SelectTrigger>
                <SelectContent>
                  {filteredModels.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.name} ({Math.floor(m.maxTokens / 1000)}k)
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <div className="flex items-center justify-between pt-4 border-t">
            <div>
              <Button
                onClick={handleSave}
                disabled={!hasUnsavedChanges || isSaving}
                variant={hasUnsavedChanges ? 'default' : 'outline'}
              >
                {isSaving ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Saving...
                  </>
                ) : hasUnsavedChanges ? (
                  'Save'
                ) : (
                  <>
                    <CheckCircle2 className="mr-2 h-4 w-4" />
                    Saved
                  </>
                )}
              </Button>
            </div>
            {saveError && (
              <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
                <AlertCircle className="h-4 w-4" />
                <span>{saveError}</span>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Model Parameters</CardTitle>
          <CardDescription>Adjust generation parameters</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label htmlFor="temperature">Temperature</Label>
              <span className="text-sm font-medium tabular-nums">{llm.temperature}</span>
            </div>
            <input
              id="temperature"
              type="range"
              min="0"
              max="2"
              step="0.1"
              value={llm.temperature}
              onChange={(e) => updateLLMConfig({ temperature: parseFloat(e.target.value) })}
              className="w-full accent-primary h-2 bg-secondary rounded-lg appearance-none cursor-pointer"
            />
            <p className="text-xs text-muted-foreground">
              Lower values are more deterministic, higher values are more creative
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="maxTokens">Max Output Tokens</Label>
            <Input
              id="maxTokens"
              type="number"
              value={llm.maxTokens}
              onChange={(e) => updateLLMConfig({ maxTokens: parseInt(e.target.value) || 4096 })}
              min={100}
              max={128000}
            />
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label htmlFor="topP">Top P</Label>
              <span className="text-sm font-medium tabular-nums">{llm.topP}</span>
            </div>
            <input
              id="topP"
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={llm.topP}
              onChange={(e) => updateLLMConfig({ topP: parseFloat(e.target.value) })}
              className="w-full accent-primary h-2 bg-secondary rounded-lg appearance-none cursor-pointer"
            />
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label htmlFor="frequencyPenalty">Frequency Penalty</Label>
              <span className="text-sm font-medium tabular-nums">{llm.frequencyPenalty}</span>
            </div>
            <input
              id="frequencyPenalty"
              type="range"
              min="0"
              max="2"
              step="0.1"
              value={llm.frequencyPenalty}
              onChange={(e) => updateLLMConfig({ frequencyPenalty: parseFloat(e.target.value) })}
              className="w-full accent-primary h-2 bg-secondary rounded-lg appearance-none cursor-pointer"
            />
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label htmlFor="presencePenalty">Presence Penalty</Label>
              <span className="text-sm font-medium tabular-nums">{llm.presencePenalty}</span>
            </div>
            <input
              id="presencePenalty"
              type="range"
              min="0"
              max="2"
              step="0.1"
              value={llm.presencePenalty}
              onChange={(e) => updateLLMConfig({ presencePenalty: parseFloat(e.target.value) })}
              className="w-full accent-primary h-2 bg-secondary rounded-lg appearance-none cursor-pointer"
            />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}