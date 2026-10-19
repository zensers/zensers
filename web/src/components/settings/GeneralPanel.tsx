// components/settings/GeneralPanel.tsx

'use client';

import { useSettingsStore } from '@/store/useSettingsStore';
import { useVersionCheck } from '@/hooks/useVersionCheck';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';

export function GeneralPanel() {
  const {
    sendOnEnter,
    showTokenCount,
    autoSaveDraft,
    updateSettings,
    resetSettings,
  } = useSettingsStore();

  const { versionInfo, checkError, loading, checkVersion, currentVersion } = useVersionCheck();
  const buildDate = versionInfo?.build_date || process.env.NEXT_PUBLIC_BUILD_DATE || '—';

  return (
    <Card>
      <CardHeader>
        <CardTitle>General Settings</CardTitle>
        <CardDescription>Basic configuration options</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Send settings */}
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <Label htmlFor="sendOnEnter">Enter to Send</Label>
            <p className="text-sm text-muted-foreground">
              Press Enter to send message, Shift + Enter for new line
            </p>
          </div>
          <Checkbox
            id="sendOnEnter"
            checked={sendOnEnter}
            onCheckedChange={(checked) => updateSettings({ sendOnEnter: checked as boolean })}
          />
        </div>

        {/* Token count */}
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <Label htmlFor="showTokenCount">Show Token Count</Label>
            <p className="text-sm text-muted-foreground">
              Show current token usage in conversation
            </p>
          </div>
          <Checkbox
            id="showTokenCount"
            checked={showTokenCount}
            onCheckedChange={(checked) => updateSettings({ showTokenCount: checked as boolean })}
          />
        </div>

        {/* Auto save draft */}
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <Label htmlFor="autoSaveDraft">Auto Save Draft</Label>
            <p className="text-sm text-muted-foreground">
              Auto-save unsent input content
            </p>
          </div>
          <Checkbox
            id="autoSaveDraft"
            checked={autoSaveDraft}
            onCheckedChange={(checked) => updateSettings({ autoSaveDraft: checked as boolean })}
          />
        </div>

        {/* Reset button */}
        <div className="pt-4 border-t">
          <Button variant="destructive" onClick={resetSettings}>
            Reset All Settings
          </Button>
          <p className="mt-2 text-xs text-muted-foreground">
            All settings will be reset to defaults
          </p>
        </div>

        {/* Version Information */}
        <div className="pt-4 border-t">
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="text-lg">📦</span>
              <h3 className="text-sm font-medium">Version Information</h3>
            </div>

            <div className="rounded-lg bg-muted/50 p-3 space-y-1.5 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Current Version</span>
                <span className="font-mono">{currentVersion}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Remote Version</span>
                <div className="flex items-center gap-2">
                  <span className="font-mono">
                    {loading && !versionInfo ? 'Checking...' : (versionInfo?.remote_version || '—')}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-xs"
                    onClick={() => checkVersion()}
                    disabled={loading}
                  >
                    {loading ? '...' : 'Refresh'}
                  </Button>
                </div>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Build Date</span>
                <span>{buildDate}</span>
              </div>
              {versionInfo?.published_at && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Published</span>
                  <span>{versionInfo.published_at}</span>
                </div>
              )}
            </div>

            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => checkVersion()}
                disabled={loading}
              >
                {loading ? 'Checking...' : 'Check for Updates'}
              </Button>
              {versionInfo?.release_url && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => window.open(versionInfo.release_url, '_blank')}
                >
                  View Changelog
                </Button>
              )}
            </div>

            {checkError && (
              <div className="rounded-lg bg-yellow-50 dark:bg-yellow-950/20 border border-yellow-200 dark:border-yellow-800 p-3 text-xs text-yellow-800 dark:text-yellow-200">
                ⚠️ Unable to check for updates.
                <br />
                Last error: {checkError}
                <br />
                Please check your network connection.
              </div>
            )}

            {versionInfo?.is_latest === true && checkError === null && (
              <div className="text-xs text-green-600 dark:text-green-400">
                ✅ You are running the latest version.
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
