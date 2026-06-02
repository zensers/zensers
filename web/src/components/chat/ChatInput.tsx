// components/chat/ChatInput.tsx

'use client';

import { useState, useRef, KeyboardEvent, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useSettingsStore } from '@/store/useSettingsStore';
import { PRESET_MODELS, PROVIDER_INFO, LLMProvider } from '@/types/settings';
import { Paperclip, Send, Square, X, FileIcon, Sparkles, Loader2, Settings } from 'lucide-react';
import { cn } from '@/lib/utils';
import Link from 'next/link';

interface ChatInputProps {
  onSend: (text: string, attachments?: File[], model?: string) => void;
  onCancel?: () => void;
  disabled?: boolean;
  placeholder?: string;
  isLoading?: boolean;
  /** HTTP request in progress — blocks send (backward compat alias) */
  isNetworkBusy?: boolean;
  /** Waiting for async reply (SSE) — does NOT block send, user can keep typing */
  isWaitingForReply?: boolean;
  /** Show stop button without blocking send (e.g. during research) */
  isRunning?: boolean;
  /** Pre-filled input from quality panel issue action */
  pendingInput?: string;
}

/**
 * Chat input component
 * Supports: text input, file upload, model selection (synced with settings)
 */
export function ChatInput({
  onSend,
  onCancel,
  disabled = false,
  placeholder = 'Describe your research needs...',
  isLoading = false,
  isNetworkBusy = false,
  isWaitingForReply = false,
  isRunning = false,
  pendingInput,
}: ChatInputProps) {
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<File[]>([]);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    if (pendingInput !== undefined && pendingInput !== null && pendingInput !== '') {
      setText(pendingInput);
    }
  }, [pendingInput]);
  
  useEffect(() => {
    setMounted(true);
  }, []);
  
  const [isFocused, setIsFocused] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { llm, sendOnEnter, updateLLMConfig, switchProvider, availableModels: storeModels } = useSettingsStore();

  // Use store's dynamic models, fall back to PRESET_MODELS
  const availableModels = (storeModels.length > 0 ? storeModels : PRESET_MODELS).filter(
    (m) => m.provider === llm.provider || llm.provider === 'custom'
  );

  // Handle model selection change - directly update global settings
  const handleModelChange = (modelId: string) => {
    updateLLMConfig({ model: modelId });
  };

  // Handle provider change
  const handleProviderChange = (providerId: string) => {
    switchProvider(providerId as LLMProvider);
  };

  const handleSend = () => {
    // Block send only during active HTTP requests, not while waiting for SSE reply (Issue 4)
    const isBusy = isNetworkBusy ?? isLoading;
    if (isBusy && !isRunning) return;
    const trimmed = text.trim();
    if ((trimmed || attachments.length > 0) && !disabled) {
      onSend(trimmed, attachments, llm.model);
      setText('');
      setAttachments([]);
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && sendOnEnter) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    setAttachments((prev) => [...prev, ...files]);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleRemoveFile = (index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  };

  // Auto-resize textarea height
  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 180)}px`;
  };

  // Get provider list
  const providers = Object.entries(PROVIDER_INFO).map(([id, info]) => ({
    id,
    name: info.name,
  }));

  // show stop when API loading, or research running with no input
  const showStop = isLoading || (isRunning && !text.trim() && attachments.length === 0);
  const canSend = (text.trim() || attachments.length > 0) && !disabled;
  const currentModelName = availableModels.find(m => m.id === llm.model)?.name || PRESET_MODELS.find(m => m.id === llm.model)?.name || llm.model;
  const currentProviderName = PROVIDER_INFO[llm.provider]?.name || llm.provider;

  return (
    <div className="space-y-2 w-full">
      {/* File attachment list */}
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-1.5 p-2.5 bg-muted/40 rounded-xl border border-dashed border-muted-foreground/30">
          {attachments.map((file, index) => (
            <div
              key={`${file.name}-${index}`}
              className="flex items-center gap-2 bg-background px-2.5 py-1.5 rounded-lg border text-xs"
            >
              <FileIcon className="h-3.5 w-3.5 text-primary shrink-0" />
              <span className="truncate max-w-[120px]">{file.name}</span>
              <button
                onClick={() => handleRemoveFile(index)}
                className="text-muted-foreground hover:text-destructive transition-colors"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Input area */}
      <div
        className={cn(
          "relative rounded-2xl border bg-background shadow-sm transition-all",
          isFocused && "ring-2 ring-primary/20 border-primary/40 shadow-md",
          disabled && "opacity-60 cursor-not-allowed"
        )}
      >
        {/* Top toolbar */}
        <div className="flex items-center gap-2 px-3 py-2 border-b bg-muted/10 rounded-t-2xl">
          {/* File upload button */}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled}
            className="h-8 px-2.5 gap-1.5 text-muted-foreground hover:text-foreground"
          >
            <Paperclip className="h-4 w-4" />
            <span className="text-xs hidden sm:inline">Attach</span>
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.doc,.docx,.xls,.xlsx,.txt,.md,.csv"
            onChange={handleFileSelect}
            className="hidden"
          />

          <div className="h-4 w-px bg-border" />

          {/* Provider selection — delayed to avoid hydration mismatch */}
          {mounted ? (
            <Select
              value={llm.provider}
              onValueChange={handleProviderChange}
              disabled={disabled}
            >
              <SelectTrigger className="h-8 w-auto min-w-[100px] max-w-[140px] border-0 bg-transparent shadow-none text-xs">
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
          ) : (
            <span className="h-8 px-2 text-xs text-muted-foreground flex items-center">Loading...</span>
          )}

          <div className="h-4 w-px bg-border" />

          {/* Model selection - synced with settings — delayed to avoid hydration mismatch */}
          {mounted ? (
            llm.provider === 'custom' ? (
              <input
                type="text"
                value={llm.model}
                onChange={(e) => updateLLMConfig({ model: e.target.value })}
                placeholder="Model name"
                disabled={disabled}
                className="h-8 w-auto min-w-[120px] max-w-[180px] border-0 bg-transparent text-xs px-2 focus:outline-none"
              />
            ) : availableModels.length > 0 ? (
              <Select
                value={llm.model}
                onValueChange={handleModelChange}
                disabled={disabled}
              >
                <SelectTrigger className="h-8 w-auto min-w-[120px] max-w-[180px] border-0 bg-transparent shadow-none text-xs gap-1.5">
                  <Sparkles className="h-3.5 w-3.5 text-primary shrink-0" />
                  <SelectValue placeholder="Select model" />
                </SelectTrigger>
                <SelectContent>
                  {availableModels.map((model) => (
                    <SelectItem key={model.id} value={model.id}>
                      <div className="flex items-center justify-between w-full gap-2">
                        <span>{model.name}</span>
                        <span className="text-xs text-muted-foreground">
                          {Math.floor(model.maxTokens / 1000)}k
                        </span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : null
          ) : (
            <span className="h-8 px-2 text-xs text-muted-foreground flex items-center">Loading...</span>
          )}

          {/* Quick settings link */}
          <Link href="/settings" className="ml-auto">
            <Button
              variant="ghost"
              size="sm"
              disabled={disabled}
              className="h-8 px-2 gap-1.5 text-muted-foreground hover:text-foreground"
            >
              <Settings className="h-3.5 w-3.5" />
              <span className="text-xs hidden sm:inline">Settings</span>
            </Button>
          </Link>
        </div>

        {/* Text input area */}
        <div className="relative">
          <Textarea
            ref={textareaRef}
            value={text}
            onChange={handleTextareaChange}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder={isLoading ? 'Processing...' : isWaitingForReply ? 'System is responding... (you can still type a new question)' : isRunning ? 'Type query or click ■ to pause' : placeholder}
            disabled={disabled}
            className="min-h-[80px] max-h-[180px] resize-none border-0 focus-visible:ring-0 p-4 pr-14 text-sm leading-relaxed"
            rows={3}
          />

          {/* Send/Cancel button */}
          <Button
             onClick={showStop ? onCancel : handleSend}
            disabled={disabled || (!showStop && !text.trim() && attachments.length === 0)}
            size="icon"
            className={cn(
              "absolute right-3 bottom-3 transition-all",
              showStop
                ? "h-10 w-10 rounded-xl bg-card border shadow-sm hover:bg-red-50 hover:border-red-200 flex items-center justify-center"
                : canSend
                  ? "h-10 w-10 rounded-xl bg-primary hover:bg-primary/90 shadow-sm text-primary-foreground"
                  : "h-10 w-10 rounded-xl bg-muted text-muted-foreground"
            )}
          >
            {showStop ? (
              <span className="flex items-center justify-center h-3 w-3 rounded-sm bg-red-500" />
            ) : (
              <Send className="h-5 w-5" />
            )}
          </Button>
        </div>
      </div>

      {/* Bottom hint */}
      <div className="flex items-center justify-between px-1 gap-3 text-[11px] text-muted-foreground">
        {mounted ? (
          <span className="truncate">
            {currentProviderName} · {currentModelName} · <kbd className="px-1.5 py-0.5 bg-muted rounded-md text-[10px]">Enter</kbd> to send
          </span>
        ) : (
          <span className="truncate">Loading...</span>
        )}
        {text.length > 0 && (
          <span className="shrink-0 tabular-nums">{text.length} chars</span>
        )}
      </div>
    </div>
  );
}
