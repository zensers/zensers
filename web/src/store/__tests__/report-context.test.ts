import { describe, it, expect, beforeEach } from 'vitest';
import { useSessionStore } from '../useSessionStore';
import type { ReportContextSnapshot } from '@/types/api';

function context(revision: number): ReportContextSnapshot {
  return {
    schema_version: 1,
    session_id: 'ctx-front',
    report_id: 'ctx-front',
    report_version: revision,
    report_phase: 'completed',
    document_type: 'docx',
    document_version: `v${revision}`,
    preview_url: null,
    download_url: null,
    topic: '测试报告',
    sections: [],
    quality: { overall_status: 'passed', open_issue_count: 0 },
    pending_decision: null,
    last_revision: { status: 'none' },
    updated_at: '2026-01-01T00:00:00Z',
    context_revision: revision,
  };
}

describe('report context version reconciliation', () => {
  beforeEach(() => {
    useSessionStore.setState({ activeId: null, sessions: {} });
    useSessionStore.getState().createSession('ctx-front');
  });

  it('accepts newer context and ignores stale context', () => {
    const store = useSessionStore.getState();
    store.applyReportContext(context(3));
    store.applyReportContext(context(2));
    expect(useSessionStore.getState().sessions['ctx-front'].reportContext?.context_revision).toBe(3);

    store.applyReportContext(context(4));
    expect(useSessionStore.getState().sessions['ctx-front'].reportContext?.document_version).toBe('v4');
  });

  it('rejects context from another session', () => {
    useSessionStore.getState().applyReportContext({ ...context(5), session_id: 'other-session' });
    expect(useSessionStore.getState().sessions['ctx-front'].reportContext).toBeNull();
  });
});
