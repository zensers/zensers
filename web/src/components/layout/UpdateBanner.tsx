'use client';

import { X, ExternalLink, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useVersionCheck } from '@/hooks/useVersionCheck';
import { useDesktopStore } from '@/store/useDesktopStore';

export function UpdateBanner() {
  const { bannerVisible, versionInfo, dismissVersion } = useVersionCheck();
  const isDesktop = useDesktopStore((s) => s.isDesktop);

  if (!bannerVisible || !versionInfo) return null;

  const handleUpdate = () => {
    if (isDesktop && versionInfo.desktop_download_url) {
      window.open(versionInfo.desktop_download_url, '_blank');
    } else {
      window.location.reload();
    }
  };

  return (
    <div className="relative bg-gradient-to-r from-blue-600/10 via-primary/10 to-purple-600/10 border-b border-primary/20">
      <div className="mx-auto max-w-7xl px-4 py-3 sm:px-6">
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 mt-0.5">
            <span className="inline-flex items-center justify-center h-8 w-8 rounded-full bg-primary/20">
              <span className="text-lg">🚀</span>
            </span>
          </div>

          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-foreground">
              Zensers <strong>v{versionInfo.remote_version}</strong> is now available
              <span className="text-muted-foreground font-normal">
                {' '}(you are on v{versionInfo.local_version})
              </span>
            </p>

            {versionInfo.release_notes && (
              <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
                {versionInfo.release_notes}
              </p>
            )}
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            {versionInfo.release_url && (
              <Button
                variant="ghost"
                size="sm"
                className="h-8 text-xs gap-1"
                onClick={() => window.open(versionInfo.release_url, '_blank')}
              >
                <ExternalLink className="h-3 w-3" />
                Changelog
              </Button>
            )}

            <Button
              size="sm"
              className="h-8 text-xs gap-1"
              onClick={handleUpdate}
            >
              <RefreshCw className="h-3 w-3" />
              {isDesktop ? 'Download' : 'Refresh'}
            </Button>

            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => dismissVersion(versionInfo.remote_version)}
              title="Dismiss"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
