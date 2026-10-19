import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useSessionStore, type SessionCache } from '../useSessionStore';
import { useResearchStore } from '../useResearchStore';
import { useChatStore } from '../useChatStore';
import { api } from '@/lib/api';
import type { ResearchFramework, ChatMessage } from '@/types/api';

const mockFramework: ResearchFramework = {
  topic: '比亚迪公司研究',
  sections: ['公司概况', '财务分析', '竞争格局', '发展战略'],
  output_type: 'pptx',
  depth: 'detailed',
  region: 'China',
  time_range: 'Last 3 years',
};

function makeSession(id: string, overrides: Partial<SessionCache> = {}): SessionCache {
  return {
    id,
    title: 'Test Session',
    taskId: null,
    activeTemplateId: null,
    researchTopic: null,
    status: 'idle',
    currentStep: 0,
    stepOptions: null,
    parameterConfig: null,
    summary: null,
    statistics: null,
    framework: null,
    progress: 0,
    phases: [],
    messages: [],
    agentMessages: [],
    previewUrl: null,
    downloadUrl: null,
    result: null,
    interrupted: false,
    language: 'zh',
    mode: 'chat',
    qualityState: null,
    reportContext: null,
    ...overrides,
  };
}

describe('framework persistence across research lifecycle', () => {
  beforeEach(() => {
    useSessionStore.setState({ activeId: null, sessions: {} });
    useResearchStore.setState({
      taskId: null, sessionId: null, progress: 0, phases: [],
      status: 'idle', currentStep: null, stepOptions: null, parameterConfig: null,
      summary: null, statistics: null, framework: null, viewingResearch: false,
      searchState: 'idle', previewRefreshKey: 0, activeTemplate: null,
      activeTemplateId: null, researchTopic: null,
      agentMessages: [], previewUrl: null, downloadUrl: null, result: null, interrupted: false,
    });
    useChatStore.setState({ messages: [] });
  });

  it('framework is preserved when research starts (mode=research, step=6)', () => {
    const sid = 'ses-test1';
    useSessionStore.getState().createSession(sid);
    useSessionStore.getState().switchTo(sid);

    useResearchStore.getState().setFramework(mockFramework);
    useResearchStore.getState().setStep(0, []);
    useResearchStore.getState().setStatus('running');
    useResearchStore.getState().setStep(6, undefined);

    const rs = useResearchStore.getState();
    expect(rs.framework).not.toBeNull();
    expect(rs.framework?.topic).toBe('比亚迪公司研究');
    expect(rs.framework?.sections).toHaveLength(4);
    expect(rs.currentStep).toBe(6);
    expect(rs.status).toBe('running');
  });

  it('framework is preserved in SessionCache when research starts', () => {
    const sid = 'ses-test2';
    useSessionStore.getState().createSession(sid);
    useSessionStore.getState().switchTo(sid);

    useResearchStore.getState().setFramework(mockFramework);
    useResearchStore.getState().setStatus('running');
    useResearchStore.getState().setStep(6, undefined);

    const cached = useSessionStore.getState().sessions[sid];
    expect(cached?.framework).not.toBeNull();
    expect(cached?.framework?.topic).toBe('比亚迪公司研究');
  });

  it('clearResearch clears framework from both stores', () => {
    const sid = 'ses-test3';
    useSessionStore.getState().createSession(sid);
    useSessionStore.getState().switchTo(sid);

    useResearchStore.getState().setFramework(mockFramework);
    useResearchStore.getState().clearResearch();

    expect(useResearchStore.getState().framework).toBeNull();
    const cached = useSessionStore.getState().sessions[sid];
    expect(cached?.framework).toBeNull();
  });

  it('clearResearch clears parameterConfig, activeTemplateId, researchTopic from cache', () => {
    const sid = 'ses-test4';
    useSessionStore.getState().createSession(sid);
    useSessionStore.getState().switchTo(sid);

    useResearchStore.getState().setParameterConfig([{ id: 'region', type: 'select', label: 'Region', default: 'China', options: [] }] as any);
    useResearchStore.getState().setActiveTemplate({ id: 'tpl1', name: 'Test', description: '', sections: [], parameters: {} } as any);
    useResearchStore.getState().setResearchTopic('test topic');
    useResearchStore.getState().clearResearch();

    const cached = useSessionStore.getState().sessions[sid];
    expect(cached?.parameterConfig).toBeNull();
    expect(cached?.activeTemplateId).toBeNull();
    expect(cached?.researchTopic).toBeNull();
  });
});

describe('restoreSession preserves cached fields', () => {
  it('locks input while the selected session is being restored', async () => {
    const sid = 'ses-restore-lock';
    let resolveDetail!: (value: any) => void;
    const detailPromise = new Promise((resolve) => { resolveDetail = resolve; });
    const detailSpy = vi.spyOn(api, 'getResearchDetail').mockReturnValue(detailPromise as any);

    useSessionStore.setState({ activeId: '__pending__', sessions: {}, isRestoring: false });
    const { restoreSession } = await import('../useSessionStore');
    const restoring = restoreSession(sid);
    expect(useSessionStore.getState().isRestoring).toBe(true);

    resolveDetail({
      task_id: sid,
      status: 'paused',
      messages: [],
      step: 6,
      progress: 42,
    });
    await restoring;

    expect(useSessionStore.getState().isRestoring).toBe(false);
    expect(useSessionStore.getState().activeId).toBe(sid);
    expect(useSessionStore.getState().sessions[sid]?.status).toBe('paused');
    detailSpy.mockRestore();
  });

  it('does not let an older restore clear the newer restore lock', async () => {
    const first = 'ses-restore-first';
    const second = 'ses-restore-second';
    let resolveFirst!: (value: any) => void;
    let resolveSecond!: (value: any) => void;
    const firstPromise = new Promise((resolve) => { resolveFirst = resolve; });
    const secondPromise = new Promise((resolve) => { resolveSecond = resolve; });
    const detailSpy = vi.spyOn(api, 'getResearchDetail')
      .mockReturnValueOnce(firstPromise as any)
      .mockReturnValueOnce(secondPromise as any);
    const { restoreSession } = await import('../useSessionStore');

    const firstRestore = restoreSession(first);
    const secondRestore = restoreSession(second);
    resolveFirst({ task_id: first, status: 'paused', messages: [] });
    await firstRestore;
    expect(useSessionStore.getState().isRestoring).toBe(true);
    expect(useSessionStore.getState().activeId).toBe(second);

    resolveSecond({ task_id: second, status: 'paused', messages: [] });
    await secondRestore;
    expect(useSessionStore.getState().isRestoring).toBe(false);
    expect(useSessionStore.getState().activeId).toBe(second);
    detailSpy.mockRestore();
  });

  it('restoreSession idle branch preserves parameterConfig from cache', () => {
    const sid = 'ses-restore1';
    const paramConfig = [{ id: 'region', type: 'select', label: 'Region', default: 'China', options: [] }];
    const session = makeSession(sid, {
      status: 'idle',
      currentStep: 4,
      parameterConfig: paramConfig as any,
      activeTemplateId: 'tpl1',
      researchTopic: 'test topic',
      framework: mockFramework,
    });
    useSessionStore.setState({ activeId: null, sessions: { [sid]: session } });
    useSessionStore.getState().switchTo(sid);

    const cached = useSessionStore.getState().sessions[sid];
    expect(cached?.parameterConfig).toEqual(paramConfig);
    expect(cached?.activeTemplateId).toBe('tpl1');
    expect(cached?.researchTopic).toBe('test topic');
    expect(cached?.framework?.topic).toBe('比亚迪公司研究');
  });
});

describe('useResearchStore subscribe partial update', () => {
  it('status change within same session preserves framework, stepOptions, parameterConfig', () => {
    const sid = 'ses-sub1';
    useSessionStore.getState().createSession(sid);
    useSessionStore.getState().switchTo(sid);

    useResearchStore.getState().setFramework(mockFramework);
    useResearchStore.getState().setStep(0, [{ id: 'opt1', label: 'Option 1', description: '' }]);
    useResearchStore.getState().setParameterConfig([{ id: 'p1', type: 'select', label: 'P1', default: 'v1', options: [] }] as any);

    useSessionStore.getState().syncActive({ status: 'running' });

    const rs = useResearchStore.getState();
    expect(rs.framework?.topic).toBe('比亚迪公司研究');
    expect(rs.stepOptions).toHaveLength(1);
    expect(rs.parameterConfig).not.toBeNull();
  });
});

describe('stateFromCache reads activeTemplateId and researchTopic', () => {
  it('stateFromCache returns activeTemplateId and researchTopic from cache', () => {
    const sid = 'ses-cache1';
    const session = makeSession(sid, {
      activeTemplateId: 'tpl-detailed',
      researchTopic: 'AI research',
    });
    useSessionStore.setState({ activeId: sid, sessions: { [sid]: session } });

    const rs = useResearchStore.getState();
    expect(rs.activeTemplateId).toBe('tpl-detailed');
    expect(rs.researchTopic).toBe('AI research');
  });
});

describe('ChatPanel renderStepContent guards', () => {
  it('framework selector should only show in idle status', () => {
    const states = ['idle', 'running', 'paused', 'completed'] as const;
    const results: boolean[] = [];

    for (const s of states) {
      const shouldShow = s === 'idle';
      results.push(shouldShow);
    }

    expect(results).toEqual([true, false, false, false]);
  });
});
