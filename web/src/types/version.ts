export interface VersionInfo {
  local_version: string;
  remote_version: string;
  build_date: string;
  is_latest: boolean | null;
  check_error: string | null;
  changelog_url: string;
  release_url: string;
  release_notes: string;
  desktop_download_url: string;
  published_at: string;
}

export interface DismissedUpdate {
  version: string;
  dismissedAt: string;
  remindAfter: number;
}
