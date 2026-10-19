'use client';

import { useSettingsStore } from '@/store/useSettingsStore';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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
import { LLMProvider, LLMProfile, LLMProviderInfo, DEFAULT_LLM_PROFILE, RoutingConfig } from '@/types/settings';
import { Eye, EyeOff, Loader2, Plus, Trash2, ChevronDown, ChevronRight, MoreVertical, AlertCircle, CheckCircle2 } from 'lucide-react';
import { useState, useEffect, useRef, useCallback } from 'react';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const PRIMARY_PROVIDERS = ['openai', 'deepseek', 'zhipu', 'qwen', 'kimi'];

export function LLMConfigPanel() {
  const {
    profiles,
    activeProfileName,
    routingConfig,
    isLoadingProfiles,
    isSaving,
    saveError,
    loadProfiles,
    createProfile,
    updateProfile,
    deleteProfile,
    switchProfile,
    updateRouting,
    availableProviders,
    availableModels,
    loadModels,
  } = useSettingsStore();

  const [mounted, setMounted] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [apiKeyValue, setApiKeyValue] = useState('');
  const [apiKeyModified, setApiKeyModified] = useState(false);
  const [newProfileName, setNewProfileName] = useState('');
  const [showNewProfileInput, setShowNewProfileInput] = useState(false);
  const [newProfileProvider, setNewProfileProvider] = useState<string>('openai');
  const [newProfileCustomProvider, setNewProfileCustomProvider] = useState('');
  const [routingExpanded, setRoutingExpanded] = useState(false);
  const [menuOpen, setMenuOpen] = useState<string | null>(null);
  const [addProviderOpen, setAddProviderOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [modifiedFields, setModifiedFields] = useState<Set<string>>(new Set());
  const debounceRef = useRef<NodeJS.Timeout | null>(null);
  const [customProviderEditing, setCustomProviderEditing] = useState(false);

  const activeProfile = profiles[activeProfileName] || null;
  const profileNames = Object.keys(profiles);
  const models = availableModels;
  const knownProviderIds = availableProviders.map(p => p.id);

  // 供应商下拉 = 固定目录 + 既有 profile 里的全部自定义供应商
  //（否则自定义供应商创建后无法在下拉中选回）
  const customProviderIds = Array.from(new Set(
    Object.values(profiles)
      .map(pf => (pf.provider || '').trim())
      .filter(pid => pid && !knownProviderIds.includes(pid))
  ));
  const providerOptions = [
    ...availableProviders.map(p => ({ id: p.id, name: p.name })),
    ...customProviderIds.map(id => ({
      id,
      name: availableProviders.find(p => p.id === id)?.name || id,
    })),
  ];

  const getProviderName = (providerId: string) => {
    return availableProviders.find(p => p.id === providerId)?.name || providerId;
  };

  const getProviderDefaultEndpoint = (providerId: string) => {
    return availableProviders.find(p => p.id === providerId)?.defaultEndpoint || '';
  };

  const getProviderDefaultModel = (providerId: string) => {
    return models.find(m => m.provider === providerId)?.id || '';
  };

  useEffect(() => { setMounted(true); }, []);

  useEffect(() => {
    if (mounted) {
      loadProfiles();
      loadModels();
    }
  }, [mounted]);

  useEffect(() => {
    if (activeProfile) {
      setApiKeyValue('');
      setApiKeyModified(false);
      setModifiedFields(new Set());
    }
  }, [activeProfileName]);

  const showSuccess = useCallback((msg: string) => {
    setSuccessMsg(msg);
    setTimeout(() => setSuccessMsg(null), 3000);
  }, []);

  const showError = useCallback((msg: string) => {
    setError(msg);
    setTimeout(() => setError(null), 5000);
  }, []);

  const scheduleSave = useCallback((fields: Record<string, any>) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        await updateProfile(activeProfileName, fields);
        setModifiedFields(new Set());
        showSuccess('已自动保存');
      } catch (e: any) {
        showError(e.message || '保存失败');
      }
    }, 800);
  }, [activeProfileName]);

  const handleFieldChange = (field: string, value: any) => {
    if (field === 'api_key') {
      setApiKeyValue(value);
      setApiKeyModified(true);
      setModifiedFields((prev) => new Set(prev).add('api_key'));
      return;
    }
    setModifiedFields((prev) => new Set(prev).add(field));
    scheduleSave({ [field]: value });
  };

  const handleSaveApiKey = async () => {
    if (!apiKeyModified) return;
    const fields: Record<string, any> = {};
    if (apiKeyValue === '') {
      fields.api_key = '';
    } else if (apiKeyValue !== '***') {
      fields.api_key = apiKeyValue;
    }
    try {
      await updateProfile(activeProfileName, fields);
      setApiKeyModified(false);
      setApiKeyValue('');
      setModifiedFields((prev) => { const n = new Set(prev); n.delete('api_key'); return n; });
      showSuccess('API Key 已保存');
    } catch (e: any) {
      showError(e.message || '保存失败');
    }
  };

  const handleProviderChange = (newProvider: string) => {
    const fields: Record<string, any> = { provider: newProvider };
    const endpoint = getProviderDefaultEndpoint(newProvider);
    const model = getProviderDefaultModel(newProvider);
    if (endpoint) fields.base_url = endpoint;
    if (model) fields.model = model;
    setModifiedFields((prev) => {
      const n = new Set(prev);
      n.add('provider');
      if (endpoint) n.add('base_url');
      if (model) n.add('model');
      return n;
    });
    scheduleSave(fields);
  };

  const handleCreateProfile = async () => {
    const name = newProfileName.trim();
    if (!name) return;
    if (!/^[a-zA-Z0-9_-]+$/.test(name)) {
      showError('Profile 名称只能包含字母、数字、下划线和连字符');
      return;
    }
    if (profiles[name]) {
      showError('Profile 名称已存在');
      return;
    }
    const provider = newProfileProvider === '__custom__' ? newProfileCustomProvider.trim() : newProfileProvider;
    if (!provider) {
      showError('请输入供应商名称');
      return;
    }
    const defaultEndpoint = getProviderDefaultEndpoint(provider);
    const defaultModel = getProviderDefaultModel(provider);
    try {
      await createProfile({
        name,
        provider,
        model: defaultModel,
        base_url: defaultEndpoint,
        max_tokens: 4096,
      });
      switchProfile(name);
      setNewProfileName('');
      setNewProfileCustomProvider('');
      setShowNewProfileInput(false);
      showSuccess('Profile 已创建');
    } catch (e: any) {
      showError(e.message || '创建失败');
    }
  };

  const handleDeleteProfile = async (name: string) => {
    if (!confirm(`确认删除 Profile "${name}"？`)) return;
    try {
      await deleteProfile(name);
      showSuccess('已删除');
    } catch (e: any) {
      showError(e.message || '删除失败');
    }
    setMenuOpen(null);
  };

  const handleQuickAddProvider = async (providerId: string) => {
    const pInfo = availableProviders.find(p => p.id === providerId);
    if (!pInfo) return;
    const profileName = providerId;
    if (profiles[profileName]) {
      switchProfile(profileName);
      return;
    }
    const defaultModel = getProviderDefaultModel(providerId);
    try {
      await createProfile({
        name: profileName,
        provider: providerId,
        model: defaultModel,
        base_url: pInfo.defaultEndpoint || '',
        max_tokens: 4096,
      });
      switchProfile(profileName);
      showSuccess('已添加');
    } catch (e: any) {
      showError(e.message || '添加失败');
    }
  };

  const handleRoutingChange = async (newConfig: RoutingConfig) => {
    const existingNames = Object.keys(profiles);
    for (const [, profileName] of Object.entries(newConfig.fixed_agent_routing)) {
      if (!existingNames.includes(profileName)) {
        showError(`Profile "${profileName}" 不存在`);
        return;
      }
    }
    for (const [, profileName] of Object.entries(newConfig.action_routing)) {
      if (!existingNames.includes(profileName)) {
        showError(`Profile "${profileName}" 不存在`);
        return;
      }
    }
    try {
      await updateRouting(newConfig);
      showSuccess('路由规则已保存');
    } catch (e: any) {
      showError(e.message || '保存失败');
    }
  };

  if (!mounted) return null;

  if (isLoadingProfiles && profileNames.length === 0) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          <span className="ml-2 text-muted-foreground">加载配置中...</span>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>LLM 配置</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex gap-6 min-h-[500px]">
          {/* Left sidebar */}
          <div className="w-52 flex-shrink-0 border-r pr-4 flex flex-col">
            {/* Primary providers - always visible */}
            <div className="space-y-0.5">
              {PRIMARY_PROVIDERS.map((pid) => {
                const pInfo = availableProviders.find(p => p.id === pid);
                const p = Object.values(profiles).find(pf => pf.provider === pid);
                const isActive = p ? profiles[activeProfileName]?.provider === pid : false;
                const providerLabel = pInfo?.name || pid;
                const isConfigured = !!p;

                return (
                  <div
                    key={pid}
                    className={`flex items-center justify-between group px-2 py-1.5 rounded cursor-pointer text-sm ${
                      isActive ? 'bg-primary/10 text-primary font-medium' : isConfigured ? 'hover:bg-muted' : 'hover:bg-muted/50 text-muted-foreground'
                    }`}
                    onClick={() => {
                      if (isConfigured && p) {
                        switchProfile(Object.keys(profiles).find(n => profiles[n].provider === pid) || '');
                      } else {
                        handleQuickAddProvider(pid);
                      }
                    }}
                  >
                    <div className="flex flex-col truncate min-w-0">
                      <span className="truncate font-medium">{providerLabel}</span>
                      {isConfigured && p ? (
                        <span className="text-[10px] text-muted-foreground truncate">{p.model || pid}</span>
                      ) : (
                        <span className="text-[10px] text-muted-foreground/60 truncate">未配置</span>
                      )}
                    </div>
                    {isConfigured && p ? (
                      <div className="relative">
                        <button
                          className="opacity-0 group-hover:opacity-100 p-0.5 hover:bg-muted rounded"
                          onClick={(e) => {
                            e.stopPropagation();
                            const name = Object.keys(profiles).find(n => profiles[n].provider === pid) || '';
                            setMenuOpen(menuOpen === name ? null : name);
                          }}
                        >
                          <MoreVertical className="h-3.5 w-3.5" />
                        </button>
                        {menuOpen === Object.keys(profiles).find(n => profiles[n].provider === pid) && (
                          <div className="absolute right-0 top-6 z-10 bg-background border rounded shadow-md py-1 min-w-[120px]">
                            <button
                              className="w-full text-left px-3 py-1.5 text-xs text-destructive hover:bg-muted"
                              onClick={(e) => {
                                e.stopPropagation();
                                const name = Object.keys(profiles).find(n => profiles[n].provider === pid) || '';
                                handleDeleteProfile(name);
                              }}
                            >
                              删除
                            </button>
                          </div>
                        )}
                      </div>
                    ) : (
                      <Plus className="h-3.5 w-3.5 text-muted-foreground/50 group-hover:text-primary" />
                    )}
                  </div>
                );
              })}
            </div>

            {/* Custom providers (profiles not in PRIMARY_PROVIDERS) */}
            {Object.entries(profiles).filter(([_, p]) => !PRIMARY_PROVIDERS.includes(p.provider)).length > 0 && (
              <>
                <div className="mt-3 mb-1 px-2">
                  <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">自定义</span>
                </div>
                <div className="space-y-0.5">
                  {Object.entries(profiles).filter(([_, p]) => !PRIMARY_PROVIDERS.includes(p.provider)).map(([name, p]) => {
                    const isActive = name === activeProfileName;
                    const providerLabel = getProviderName(p.provider);
                    return (
                      <div
                        key={name}
                        className={`flex items-center justify-between group px-2 py-1.5 rounded cursor-pointer text-sm ${
                          isActive ? 'bg-primary/10 text-primary font-medium' : 'hover:bg-muted'
                        }`}
                        onClick={() => switchProfile(name)}
                      >
                        <div className="flex flex-col truncate min-w-0">
                          <span className="truncate font-medium">{providerLabel}</span>
                          <span className="text-[10px] text-muted-foreground truncate">{p.model || name}</span>
                        </div>
                        <div className="relative">
                          <button
                            className="opacity-0 group-hover:opacity-100 p-0.5 hover:bg-muted rounded"
                            onClick={(e) => { e.stopPropagation(); setMenuOpen(menuOpen === name ? null : name); }}
                          >
                            <MoreVertical className="h-3.5 w-3.5" />
                          </button>
                          {menuOpen === name && (
                            <div className="absolute right-0 top-6 z-10 bg-background border rounded shadow-md py-1 min-w-[120px]">
                              <button
                                className="w-full text-left px-3 py-1.5 text-xs text-destructive hover:bg-muted"
                                onClick={(e) => { e.stopPropagation(); handleDeleteProfile(name); }}
                              >
                                删除
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            )}

            {/* Add more providers dropdown */}
            <div className="mt-4 pt-3 border-t">
              {availableProviders.filter(p => !PRIMARY_PROVIDERS.includes(p.id) && !Object.values(profiles).some(pf => pf.provider === p.id)).length > 0 ? (
                <div className="relative">
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full text-xs justify-start"
                    onClick={() => setAddProviderOpen(!addProviderOpen)}
                  >
                    <Plus className="h-3.5 w-3.5 mr-1.5" /> 添加供应商
                  </Button>
                  {addProviderOpen && (
                    <div className="absolute left-0 top-full mt-1 z-10 bg-background border rounded shadow-md py-1 min-w-[180px] max-h-48 overflow-y-auto">
                      {availableProviders
                        .filter(p => !PRIMARY_PROVIDERS.includes(p.id) && !Object.values(profiles).some(pf => pf.provider === p.id))
                        .map(p => (
                          <button
                            key={p.id}
                            className="w-full text-left px-3 py-1.5 text-xs hover:bg-muted flex items-center gap-2"
                            onClick={() => { handleQuickAddProvider(p.id); setAddProviderOpen(false); }}
                          >
                            <span>{p.name}</span>
                            {p.description && <span className="text-muted-foreground text-[10px] truncate">{p.description}</span>}
                          </button>
                        ))}
                    </div>
                  )}
                </div>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full text-xs"
                  onClick={() => setShowNewProfileInput(true)}
                >
                  <Plus className="h-3.5 w-3.5 mr-1" /> 自定义供应商
                </Button>
              )}

              {showNewProfileInput && (
                <div className="mt-2 space-y-2">
                  <Input
                    placeholder="profile-name"
                    value={newProfileName}
                    onChange={(e) => setNewProfileName(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleCreateProfile(); if (e.key === 'Escape') setShowNewProfileInput(false); }}
                    autoFocus
                    className="h-8 text-xs"
                  />
                  <Select value={newProfileProvider} onValueChange={setNewProfileProvider}>
                    <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {providerOptions.map((p) => (
                        <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                      ))}
                      <SelectItem value="__custom__">自定义供应商...</SelectItem>
                    </SelectContent>
                  </Select>
                  {newProfileProvider === '__custom__' && (
                    <Input
                      placeholder="供应商名称 (如 volcengine)"
                      value={newProfileCustomProvider}
                      onChange={(e) => setNewProfileCustomProvider(e.target.value)}
                      className="h-8 text-xs"
                    />
                  )}
                  <div className="flex gap-1">
                    <Button size="sm" variant="ghost" className="h-7 text-xs flex-1" onClick={handleCreateProfile}>创建</Button>
                    <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => { setShowNewProfileInput(false); setNewProfileName(''); setNewProfileCustomProvider(''); }}>取消</Button>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Right panel */}
          <div className="flex-1 min-w-0">
            {activeProfile ? (
              <div className="space-y-4">
                {/* Profile header */}
                <div className="flex items-center gap-2">
                  <h3 className="text-lg font-medium">{getProviderName(activeProfile.provider)}</h3>
                  <span className="text-xs text-muted-foreground">{activeProfile.model}</span>
                </div>

                {/* Provider */}
                <div className="space-y-1.5">
                  <Label>供应商</Label>
                  <Select
                    value={!customProviderEditing && providerOptions.some(p => p.id === activeProfile.provider)
                      ? activeProfile.provider
                      : '__custom__'}
                    onValueChange={(v) => {
                      if (v === '__custom__') {
                        setCustomProviderEditing(true);
                        return;
                      }
                      setCustomProviderEditing(false);
                      handleProviderChange(v);
                    }}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {providerOptions.map((p) => (
                        <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                      ))}
                      <SelectItem value="__custom__">自定义供应商...</SelectItem>
                    </SelectContent>
                  </Select>
                  {(customProviderEditing || !providerOptions.some(p => p.id === activeProfile.provider)) && (
                    <Input
                      value={activeProfile.provider}
                      onChange={(e) => handleFieldChange('provider', e.target.value)}
                      placeholder="自定义供应商名称"
                      className="h-8 text-xs"
                    />
                  )}
                </div>

                {/* API Endpoint */}
                <div className="space-y-1.5">
                  <Label>API 地址</Label>
                  <Input
                    value={activeProfile.base_url}
                    onChange={(e) => handleFieldChange('base_url', e.target.value)}
                    placeholder="https://api.openai.com/v1"
                  />
                </div>

                {/* API Key */}
                <div className="space-y-1.5">
                  <Label>API Key</Label>
                  <div className="flex gap-2">
                    <div className="relative flex-1">
                      <Input
                        type={showApiKey ? 'text' : 'password'}
                        value={apiKeyModified ? apiKeyValue : ''}
                        onChange={(e) => handleFieldChange('api_key', e.target.value)}
                        placeholder={activeProfile.hasApiKey ? '•••••••• (已设置)' : 'sk-...'}
                      />
                      <button
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                        onClick={() => setShowApiKey(!showApiKey)}
                        type="button"
                      >
                        {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                    {apiKeyModified && (
                      <Button size="sm" onClick={handleSaveApiKey} disabled={isSaving}>
                        {isSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : '保存 Key'}
                      </Button>
                    )}
                  </div>
                </div>

                {/* Model */}
                <div className="space-y-1.5">
                  <Label>模型</Label>
                  <ModelSelector
                    provider={activeProfile.provider}
                    model={activeProfile.model}
                    models={models}
                    onChange={(v) => handleFieldChange('model', v)}
                  />
                </div>

                {/* Temperature */}
                <div className="space-y-1.5">
                  <Label>Temperature 温度 ({activeProfile.temperature})</Label>
                  <Input
                    type="range"
                    min="0"
                    max="2"
                    step="0.1"
                    value={activeProfile.temperature}
                    onChange={(e) => handleFieldChange('temperature', parseFloat(e.target.value))}
                    className="cursor-pointer"
                  />
                </div>

                {/* Max Tokens */}
                <div className="space-y-1.5">
                  <Label>最大 Tokens</Label>
                  <Input
                    type="number"
                    min="100"
                    max="128000"
                    value={activeProfile.max_tokens}
                    onChange={(e) => handleFieldChange('max_tokens', parseInt(e.target.value) || 4096)}
                  />
                </div>

                {/* Top P */}
                <div className="space-y-1.5">
                  <Label>Top P ({activeProfile.top_p})</Label>
                  <Input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={activeProfile.top_p}
                    onChange={(e) => handleFieldChange('top_p', parseFloat(e.target.value))}
                    className="cursor-pointer"
                  />
                </div>

                {/* Frequency Penalty */}
                <div className="space-y-1.5">
                  <Label>频率惩罚 ({activeProfile.frequency_penalty})</Label>
                  <Input
                    type="range"
                    min="0"
                    max="2"
                    step="0.1"
                    value={activeProfile.frequency_penalty}
                    onChange={(e) => handleFieldChange('frequency_penalty', parseFloat(e.target.value))}
                    className="cursor-pointer"
                  />
                </div>

                {/* Presence Penalty */}
                <div className="space-y-1.5">
                  <Label>存在惩罚 ({activeProfile.presence_penalty})</Label>
                  <Input
                    type="range"
                    min="0"
                    max="2"
                    step="0.1"
                    value={activeProfile.presence_penalty}
                    onChange={(e) => handleFieldChange('presence_penalty', parseFloat(e.target.value))}
                    className="cursor-pointer"
                  />
                </div>

                {/* Save status */}
                <div className="flex items-center gap-2 h-5">
                  {isSaving && (
                    <span className="text-xs text-muted-foreground flex items-center gap-1">
                      <Loader2 className="h-3 w-3 animate-spin" /> 保存中...
                    </span>
                  )}
                  {saveError && (
                    <span className="text-xs text-destructive flex items-center gap-1">
                      <AlertCircle className="h-3 w-3" /> {saveError}
                    </span>
                  )}
                  {successMsg && (
                    <span className="text-xs text-green-600 flex items-center gap-1">
                      <CheckCircle2 className="h-3 w-3" /> {successMsg}
                    </span>
                  )}
                </div>

                {/* Routing section */}
                <div className="mt-6 border-t pt-4">
                  <button
                    className="flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground"
                    onClick={() => setRoutingExpanded(!routingExpanded)}
                  >
                    {routingExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                    路由规则
                  </button>

                  {routingExpanded && (
                    <RoutingEditor
                      config={routingConfig}
                      profileNames={profileNames}
                      profiles={profiles}
                      onChange={handleRoutingChange}
                    />
                  )}
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground">
                {profileNames.length === 0
                  ? '暂无 Profile，请点击左侧「新建 Profile」创建'
                  : '请选择一个 Profile'}
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ===== Model Selector Sub-component =====

function ModelSelector({
  provider,
  model,
  models,
  onChange,
}: {
  provider: string;
  model: string;
  models: { id: string; name: string; provider: string; key?: string }[];
  onChange: (value: string) => void;
}) {
  const [useCustom, setUseCustom] = useState(false);

  const providerModels = models.filter(m => m.provider === provider);
  const isPreset = providerModels.some(m => m.id === model);
  const modelKey = providerModels.find(m => m.id === model)?.key || model;
  const currentCustomValue = !isPreset && model ? model : '';
  const [customValue, setCustomValue] = useState(currentCustomValue);

  useEffect(() => {
    setUseCustom(false);
  }, [provider]);

  useEffect(() => {
    setCustomValue(currentCustomValue);
  }, [currentCustomValue]);

  if (useCustom) {
    return (
      <div className="flex gap-2">
        <Input
          value={customValue}
          onChange={(e) => setCustomValue(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && customValue.trim()) { onChange(customValue.trim()); setUseCustom(false); } }}
          placeholder="输入自定义模型名称"
          autoFocus
          className="h-9"
        />
        <Button size="sm" variant="outline" onClick={() => setUseCustom(false)}>取消</Button>
        <Button size="sm" onClick={() => { if (customValue.trim()) { onChange(customValue.trim()); setUseCustom(false); } }}>确定</Button>
      </div>
    );
  }

  return (
    <div className="flex gap-2">
      <Select
        value={modelKey}
        onValueChange={(key) => {
          const selected = providerModels.find(pm => (pm.key || pm.id) === key);
          onChange(selected ? selected.id : key);
        }}
      >
        <SelectTrigger className="flex-1"><SelectValue /></SelectTrigger>
        <SelectContent>
          {providerModels.map(m => (
            <SelectItem key={m.key || m.id} value={m.key || m.id}>{m.name}</SelectItem>
          ))}
          {!isPreset && model && (
            <SelectItem value={model}>{model} (自定义)</SelectItem>
          )}
        </SelectContent>
      </Select>
      <Button size="sm" variant="outline" onClick={() => { setCustomValue(currentCustomValue); setUseCustom(true); }}>
        自定义
      </Button>
    </div>
  );
}

// ===== Routing Editor Sub-component =====

function RoutingEditor({
  config,
  profileNames,
  profiles,
  onChange,
}: {
  config: RoutingConfig;
  profileNames: string[];
  profiles: Record<string, LLMProfile>;
  onChange: (config: RoutingConfig) => void;
}) {
  const { availableProviders } = useSettingsStore();

  const getProviderName = (providerId: string) => {
    return availableProviders.find(p => p.id === providerId)?.name || providerId;
  };

  const [localConfig, setLocalConfig] = useState<RoutingConfig>(config);

  useEffect(() => {
    setLocalConfig(config);
  }, [config]);

  const updateFixedAgent = (agent: string, profileName: string) => {
    const newConfig = {
      ...localConfig,
      fixed_agent_routing: { ...localConfig.fixed_agent_routing, [agent]: profileName },
    };
    setLocalConfig(newConfig);
  };

  const removeFixedAgent = (agent: string) => {
    const { [agent]: _, ...rest } = localConfig.fixed_agent_routing;
    const newConfig = { ...localConfig, fixed_agent_routing: rest };
    setLocalConfig(newConfig);
  };

  const updateAction = (action: string, profileName: string) => {
    const newConfig = {
      ...localConfig,
      action_routing: { ...localConfig.action_routing, [action]: profileName },
    };
    setLocalConfig(newConfig);
  };

  const removeAction = (action: string) => {
    const { [action]: _, ...rest } = localConfig.action_routing;
    const newConfig = { ...localConfig, action_routing: rest };
    setLocalConfig(newConfig);
  };

  const moveFallbackUp = (index: number) => {
    if (index <= 0) return;
    const chain = [...localConfig.fallback_chain];
    [chain[index - 1], chain[index]] = [chain[index], chain[index - 1]];
    setLocalConfig({ ...localConfig, fallback_chain: chain });
  };

  const moveFallbackDown = (index: number) => {
    if (index >= localConfig.fallback_chain.length - 1) return;
    const chain = [...localConfig.fallback_chain];
    [chain[index], chain[index + 1]] = [chain[index + 1], chain[index]];
    setLocalConfig({ ...localConfig, fallback_chain: chain });
  };

  const removeFallback = (index: number) => {
    const chain = localConfig.fallback_chain.filter((_, i) => i !== index);
    setLocalConfig({ ...localConfig, fallback_chain: chain });
  };

  const addFallback = (profileName: string) => {
    if (localConfig.fallback_chain.includes(profileName)) return;
    setLocalConfig({ ...localConfig, fallback_chain: [...localConfig.fallback_chain, profileName] });
  };

  const [newAgent, setNewAgent] = useState('');
  const [newAction, setNewAction] = useState('');
  const [newFallback, setNewFallback] = useState('');

  const handleSave = () => {
    onChange(localConfig);
  };

  const profileLabel = (n: string) => {
    const p = profiles[n];
    const providerLabel = p ? getProviderName(p.provider) : '';
    return `${providerLabel} · ${p?.model || n}`;
  };

  return (
    <div className="mt-3 space-y-4 text-sm">
      {/* Fixed Agent Routing */}
      <div className="space-y-2">
        <h4 className="font-medium">Agent → 模型 映射</h4>
        {Object.entries(localConfig.fixed_agent_routing).map(([agent, profileName]) => (
          <div key={agent} className="flex items-center gap-2">
            <span className="w-40 text-muted-foreground truncate" title={agent}>{agent}</span>
            <span className="text-muted-foreground">→</span>
            <Select value={profileName} onValueChange={(v) => updateFixedAgent(agent, v)}>
              <SelectTrigger className="w-56 h-8 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                {profileNames.map((n) => (
                  <SelectItem key={n} value={n}>{profileLabel(n)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => removeFixedAgent(agent)}>
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        ))}
        <div className="flex items-center gap-2">
          <Input
            placeholder="agent 名称"
            value={newAgent}
            onChange={(e) => setNewAgent(e.target.value)}
            className="w-40 h-8 text-xs"
          />
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs"
            onClick={() => {
              if (newAgent.trim()) {
                updateFixedAgent(newAgent.trim(), profileNames[0] || '');
                setNewAgent('');
              }
            }}
          >
            添加
          </Button>
        </div>
      </div>

      {/* Action Routing */}
      <div className="space-y-2">
        <h4 className="font-medium">Action → 模型 映射</h4>
        {Object.entries(localConfig.action_routing).map(([action, profileName]) => (
          <div key={action} className="flex items-center gap-2">
            <span className="w-40 text-muted-foreground truncate" title={action}>{action}</span>
            <span className="text-muted-foreground">→</span>
            <Select value={profileName} onValueChange={(v) => updateAction(action, v)}>
              <SelectTrigger className="w-56 h-8 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                {profileNames.map((n) => (
                  <SelectItem key={n} value={n}>{profileLabel(n)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => removeAction(action)}>
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        ))}
        <div className="flex items-center gap-2">
          <Input
            placeholder="action 名称"
            value={newAction}
            onChange={(e) => setNewAction(e.target.value)}
            className="w-40 h-8 text-xs"
          />
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs"
            onClick={() => {
              if (newAction.trim()) {
                updateAction(newAction.trim(), profileNames[0] || '');
                setNewAction('');
              }
            }}
          >
            添加
          </Button>
        </div>
      </div>

      {/* Fallback chain */}
      <div className="space-y-2">
        <h4 className="font-medium">Fallback Chain (回退顺序)</h4>
        <div className="space-y-1">
          {localConfig.fallback_chain.map((name, i) => {
            const p = profiles[name];
            const providerLabel = p ? getProviderName(p.provider) : '';
            return (
              <div key={i} className="flex items-center gap-1">
                <span className="text-muted-foreground text-xs w-4">{i + 1}.</span>
                <span className="bg-muted px-2 py-0.5 rounded text-xs flex-1">
                  {providerLabel} · {p?.model || name}
                </span>
                <button className="p-0.5 hover:bg-muted rounded text-muted-foreground" onClick={() => moveFallbackUp(i)} disabled={i === 0}>↑</button>
                <button className="p-0.5 hover:bg-muted rounded text-muted-foreground" onClick={() => moveFallbackDown(i)} disabled={i === localConfig.fallback_chain.length - 1}>↓</button>
                <button className="p-0.5 hover:bg-muted rounded text-destructive" onClick={() => removeFallback(i)}>×</button>
              </div>
            );
          })}
          {localConfig.fallback_chain.length === 0 && (
            <span className="text-xs text-muted-foreground">未设置</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Select value={newFallback} onValueChange={setNewFallback}>
            <SelectTrigger className="w-56 h-8 text-xs"><SelectValue placeholder="添加 Profile..." /></SelectTrigger>
            <SelectContent>
              {profileNames.filter(n => !localConfig.fallback_chain.includes(n)).map((n) => (
                <SelectItem key={n} value={n}>{profileLabel(n)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" className="h-8 text-xs" onClick={() => { if (newFallback) { addFallback(newFallback); setNewFallback(''); } }}>添加</Button>
        </div>
      </div>

      <Button size="sm" onClick={handleSave}>保存路由规则</Button>
    </div>
  );
}
