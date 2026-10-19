import { describe, it, expect, beforeEach, vi } from 'vitest';
import type { AgentMessageData, ChatMessage } from '@/types/api';

const MERGEABLE_IDS = ['web_search', 'news_search', 'scrape_url'];

function simulateOnAgentMessage(
  data: AgentMessageData,
  messages: ChatMessage[],
  addMessage: (msg: ChatMessage) => ChatMessage[],
  updateMessage: (id: string, updates: Partial<ChatMessage>) => ChatMessage[],
): ChatMessage[] {
  if (data.action === 'heartbeat') {
    const lastHb = [...messages].reverse().find(m => m.role === 'agent' && m.agent?.action === 'heartbeat');
    if (lastHb) {
      return updateMessage(lastHb.id, { content: data.content, timestamp: data.timestamp });
    }
  }

  if (MERGEABLE_IDS.includes(data.agent_id) && data.action !== 'error') {
    const existing = [...messages].reverse().find(
      m => m.role === 'agent' && m.agent?.id === data.agent_id && m.agent?.action !== 'heartbeat' && m.agent?.action !== 'error'
    );
    if (existing) {
      const prevCompleted = existing.agent?.completedCount || 0;
      const prevTotal = existing.agent?.totalCount || 0;
      const isCompleted = data.action === 'completed';
      const newCompleted = isCompleted ? prevCompleted + 1 : prevCompleted;
      const newTotal = isCompleted ? Math.max(prevTotal, newCompleted) : prevTotal;
      const displayAction = (isCompleted && newCompleted < newTotal) ? existing.agent!.action : data.action;
      return updateMessage(existing.id, {
        content: data.content,
        timestamp: data.timestamp,
        agent: {
          ...existing.agent!,
          action: displayAction,
          completedCount: newCompleted,
          totalCount: newTotal,
        },
      });
    }
    const isCompleted = data.action === 'completed';
    return addMessage({
      id: `msg-${Date.now()}-${Math.random()}`,
      role: 'agent',
      content: data.content,
      timestamp: data.timestamp,
      agent: {
        id: data.agent_id,
        name: data.agent_name,
        action: data.action,
        completedCount: isCompleted ? 1 : 0,
        totalCount: isCompleted ? 1 : 0,
      },
    });
  }

  const updatableActions = ['searching', 'writing'] as const;
  if (updatableActions.includes(data.action as any)) {
    const lastSame = [...messages].reverse().find(
      m => m.role === 'agent' && m.agent?.id === data.agent_id && m.agent?.action === data.action
    );
    if (lastSame) {
      return updateMessage(lastSame.id, { content: data.content, timestamp: data.timestamp });
    }
  }

  return addMessage({
    id: `msg-${Date.now()}-${Math.random()}`,
    role: 'agent',
    content: data.content,
    timestamp: data.timestamp,
    agent: { id: data.agent_id, name: data.agent_name, action: data.action },
  });
}

function createMessageStore() {
  let messages: ChatMessage[] = [];
  let nextId = 1;
  return {
    getMessages: () => messages,
    addMessage: (msg: ChatMessage): ChatMessage[] => {
      const newMsg = { ...msg, id: msg.id || `msg-${nextId++}` };
      messages = [...messages, newMsg];
      return messages;
    },
    updateMessage: (id: string, updates: Partial<ChatMessage>): ChatMessage[] => {
      messages = messages.map(m => m.id === id ? { ...m, ...updates } : m);
      return messages;
    },
  };
}

function makeAgentData(overrides: Partial<AgentMessageData> & { agent_id: string; agent_name: string; action: AgentMessageData['action']; content: string }): AgentMessageData {
  return {
    session_id: 'test-session',
    timestamp: new Date().toISOString(),
    ...overrides,
  };
}

describe('Agent Message Merging Logic', () => {
  let store: ReturnType<typeof createMessageStore>;

  beforeEach(() => {
    store = createMessageStore();
  });

  describe('Mergeable tools (web_search, news_search, scrape_url)', () => {
    it('single web_search: searching then completed → 1 message', () => {
      const data1 = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'searching', content: 'Searching for: BYD' });
      let msgs = simulateOnAgentMessage(data1, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);
      expect(msgs[0].agent?.action).toBe('searching');
      expect(msgs[0].agent?.completedCount).toBe(0);
      expect(msgs[0].agent?.totalCount).toBe(0);

      const data2 = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'completed', content: 'Completed: web_search' });
      msgs = simulateOnAgentMessage(data2, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);
      expect(msgs[0].agent?.action).toBe('completed');
      expect(msgs[0].agent?.completedCount).toBe(1);
      expect(msgs[0].agent?.totalCount).toBe(1);
    });

    it('3 web_search calls → 1 message with count 3/3', () => {
      const search1 = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'searching', content: 'Searching for: BYD revenue' });
      let msgs = simulateOnAgentMessage(search1, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);

      const complete1 = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'completed', content: 'Completed: web_search' });
      msgs = simulateOnAgentMessage(complete1, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);
      expect(msgs[0].agent?.completedCount).toBe(1);
      expect(msgs[0].agent?.totalCount).toBe(1);
      expect(msgs[0].agent?.action).toBe('completed');

      const search2 = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'searching', content: 'Searching for: BYD profit' });
      msgs = simulateOnAgentMessage(search2, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);
      expect(msgs[0].agent?.action).toBe('searching');

      const complete2 = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'completed', content: 'Completed: web_search' });
      msgs = simulateOnAgentMessage(complete2, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);
      expect(msgs[0].agent?.completedCount).toBe(2);
      expect(msgs[0].agent?.totalCount).toBe(2);
      expect(msgs[0].agent?.action).toBe('completed');

      const search3 = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'searching', content: 'Searching for: BYD overseas' });
      msgs = simulateOnAgentMessage(search3, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);
      expect(msgs[0].agent?.action).toBe('searching');

      const complete3 = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'completed', content: 'Completed: web_search' });
      msgs = simulateOnAgentMessage(complete3, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);
      expect(msgs[0].agent?.completedCount).toBe(3);
      expect(msgs[0].agent?.totalCount).toBe(3);
      expect(msgs[0].agent?.action).toBe('completed');
    });

    it('6 web_search calls → 1 message with count 6/6', () => {
      for (let i = 1; i <= 6; i++) {
        const search = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'searching', content: `Searching for: query ${i}` });
        let msgs = simulateOnAgentMessage(search, store.getMessages(), store.addMessage, store.updateMessage);
        expect(msgs).toHaveLength(1);

        const complete = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'completed', content: 'Completed: web_search' });
        msgs = simulateOnAgentMessage(complete, store.getMessages(), store.addMessage, store.updateMessage);
        expect(msgs).toHaveLength(1);
        expect(msgs[0].agent?.completedCount).toBe(i);
        expect(msgs[0].agent?.totalCount).toBe(i);
      }
      const final = store.getMessages();
      expect(final).toHaveLength(1);
      expect(final[0].agent?.completedCount).toBe(6);
      expect(final[0].agent?.totalCount).toBe(6);
    });

    it('web_search and news_search are separate messages (different agent_id)', () => {
      const search1 = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'searching', content: 'Searching for: BYD' });
      let msgs = simulateOnAgentMessage(search1, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);

      const search2 = makeAgentData({ agent_id: 'news_search', agent_name: 'News Search Agent', action: 'searching', content: 'Searching for: BYD news' });
      msgs = simulateOnAgentMessage(search2, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(2);

      const complete1 = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'completed', content: 'Completed: web_search' });
      msgs = simulateOnAgentMessage(complete1, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(2);

      const complete2 = makeAgentData({ agent_id: 'news_search', agent_name: 'News Search Agent', action: 'completed', content: 'Completed: news_search' });
      msgs = simulateOnAgentMessage(complete2, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(2);

      const webMsg = msgs.find(m => m.agent?.id === 'web_search');
      const newsMsg = msgs.find(m => m.agent?.id === 'news_search');
      expect(webMsg?.agent?.completedCount).toBe(1);
      expect(newsMsg?.agent?.completedCount).toBe(1);
    });

    it('interleaved web_search and news_search maintain separate counts', () => {
      const events = [
        makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'searching', content: 'Searching for: BYD' }),
        makeAgentData({ agent_id: 'news_search', agent_name: 'News Search Agent', action: 'searching', content: 'Searching for: BYD news' }),
        makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'completed', content: 'Completed: web_search' }),
        makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'searching', content: 'Searching for: BYD profit' }),
        makeAgentData({ agent_id: 'news_search', agent_name: 'News Search Agent', action: 'completed', content: 'Completed: news_search' }),
        makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'completed', content: 'Completed: web_search' }),
      ];

      let msgs: ChatMessage[] = [];
      for (const event of events) {
        msgs = simulateOnAgentMessage(event, store.getMessages(), store.addMessage, store.updateMessage);
      }

      expect(msgs).toHaveLength(2);
      const webMsg = msgs.find(m => m.agent?.id === 'web_search');
      const newsMsg = msgs.find(m => m.agent?.id === 'news_search');
      expect(webMsg?.agent?.completedCount).toBe(2);
      expect(webMsg?.agent?.totalCount).toBe(2);
      expect(newsMsg?.agent?.completedCount).toBe(1);
      expect(newsMsg?.agent?.totalCount).toBe(1);
    });

    it('first event is completed (no prior searching) → creates message with count 1/1', () => {
      const complete = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'completed', content: 'Completed: web_search' });
      const msgs = simulateOnAgentMessage(complete, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);
      expect(msgs[0].agent?.completedCount).toBe(1);
      expect(msgs[0].agent?.totalCount).toBe(1);
    });

    it('completed while still in progress (2/3) keeps searching action', () => {
      const search1 = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'searching', content: 'Searching for: BYD' });
      simulateOnAgentMessage(search1, store.getMessages(), store.addMessage, store.updateMessage);

      const complete1 = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'completed', content: 'Completed: web_search' });
      let msgs = simulateOnAgentMessage(complete1, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs[0].agent?.completedCount).toBe(1);
      expect(msgs[0].agent?.totalCount).toBe(1);
      expect(msgs[0].agent?.action).toBe('completed');

      const search2 = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'searching', content: 'Searching for: BYD profit' });
      msgs = simulateOnAgentMessage(search2, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs[0].agent?.action).toBe('searching');

      const complete2 = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'completed', content: 'Completed: web_search' });
      msgs = simulateOnAgentMessage(complete2, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs[0].agent?.completedCount).toBe(2);
      expect(msgs[0].agent?.totalCount).toBe(2);
      expect(msgs[0].agent?.action).toBe('completed');

      const search3 = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'searching', content: 'Searching for: BYD overseas' });
      msgs = simulateOnAgentMessage(search3, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs[0].agent?.action).toBe('searching');

      const complete3 = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'completed', content: 'Completed: web_search' });
      msgs = simulateOnAgentMessage(complete3, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs[0].agent?.completedCount).toBe(3);
      expect(msgs[0].agent?.totalCount).toBe(3);
      expect(msgs[0].agent?.action).toBe('completed');
    });
  });

  describe('Non-mergeable agents (orchestrator, research agents, phases)', () => {
    it('orchestrator: 4 different messages → 4 separate messages (NOT merged)', () => {
      const events = [
        makeAgentData({ agent_id: 'orchestrator', agent_name: 'Research Orchestrator', action: 'analyzing', content: 'Starting research on 「BYD」...' }),
        makeAgentData({ agent_id: 'orchestrator', agent_name: 'Research Orchestrator', action: 'analyzing', content: 'Requirement analysis complete' }),
        makeAgentData({ agent_id: 'orchestrator', agent_name: 'Research Orchestrator', action: 'analyzing', content: 'Intelligent routing: 3 phases planned' }),
        makeAgentData({ agent_id: 'orchestrator', agent_name: 'Research Orchestrator', action: 'completed', content: 'Research completed! 3 stages completed.' }),
      ];

      let msgs: ChatMessage[] = [];
      for (const event of events) {
        msgs = simulateOnAgentMessage(event, store.getMessages(), store.addMessage, store.updateMessage);
      }

      expect(msgs).toHaveLength(4);
      expect(msgs[0].content).toBe('Starting research on 「BYD」...');
      expect(msgs[1].content).toBe('Requirement analysis complete');
      expect(msgs[2].content).toBe('Intelligent routing: 3 phases planned');
      expect(msgs[3].content).toBe('Research completed! 3 stages completed.');
    });

    it('orchestrator: searching action updates last same-agent_id+action message', () => {
      const event1 = makeAgentData({ agent_id: 'orchestrator', agent_name: 'Research Orchestrator', action: 'searching', content: 'Searching step 1...' });
      let msgs = simulateOnAgentMessage(event1, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);

      const event2 = makeAgentData({ agent_id: 'orchestrator', agent_name: 'Research Orchestrator', action: 'searching', content: 'Searching step 2...' });
      msgs = simulateOnAgentMessage(event2, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);
      expect(msgs[0].content).toBe('Searching step 2...');
    });

    it('phase messages: execution start + complete → 2 separate messages', () => {
      const start = makeAgentData({ agent_id: 'execution', agent_name: 'Agent Execution', action: 'analyzing', content: 'Starting Agent Execution...' });
      let msgs = simulateOnAgentMessage(start, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);

      const complete = makeAgentData({ agent_id: 'execution', agent_name: 'Agent Execution', action: 'completed', content: 'Agent Execution completed.' });
      msgs = simulateOnAgentMessage(complete, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(2);
    });

    it('research agent: analyzing + completed → 2 separate messages', () => {
      const start = makeAgentData({ agent_id: 'research_market_size_1', agent_name: '市场规模', action: 'analyzing', content: 'Starting 市场规模...' });
      let msgs = simulateOnAgentMessage(start, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);

      const complete = makeAgentData({ agent_id: 'research_market_size_1', agent_name: '市场规模', action: 'completed', content: '市场规模 completed.' });
      msgs = simulateOnAgentMessage(complete, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(2);
    });

    it('system warning: NOT merged with heartbeat', () => {
      const hb = makeAgentData({ agent_id: 'system', agent_name: 'System', action: 'heartbeat', content: 'Research in progress... (50% complete)' });
      let msgs = simulateOnAgentMessage(hb, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);

      const warning = makeAgentData({ agent_id: 'system', agent_name: '系统', action: 'warning', content: '修订完成但预览可能存在排版问题' });
      msgs = simulateOnAgentMessage(warning, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(2);

      const hb2 = makeAgentData({ agent_id: 'system', agent_name: 'System', action: 'heartbeat', content: 'Research in progress... (75% complete)' });
      msgs = simulateOnAgentMessage(hb2, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(2);
      const hbMsg = msgs.find(m => m.agent?.action === 'heartbeat');
      expect(hbMsg?.content).toBe('Research in progress... (75% complete)');
      const warnMsg = msgs.find(m => m.agent?.action === 'warning');
      expect(warnMsg?.content).toBe('修订完成但预览可能存在排版问题');
    });

    it('plan modification: completed → separate message', () => {
      const modify = makeAgentData({ agent_id: 'modify', agent_name: 'Plan Modification', action: 'completed', content: 'Plan updated. Added: 竞争分析' });
      const msgs = simulateOnAgentMessage(modify, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);
      expect(msgs[0].agent?.id).toBe('modify');
      expect(msgs[0].agent?.completedCount).toBeUndefined();
    });
  });

  describe('Heartbeat handling', () => {
    it('heartbeat updates existing heartbeat message in-place', () => {
      const hb1 = makeAgentData({ agent_id: 'system', agent_name: 'System', action: 'heartbeat', content: 'Research in progress... (10% complete)' });
      let msgs = simulateOnAgentMessage(hb1, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);

      const hb2 = makeAgentData({ agent_id: 'system', agent_name: 'System', action: 'heartbeat', content: 'Research in progress... (30% complete)' });
      msgs = simulateOnAgentMessage(hb2, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);
      expect(msgs[0].content).toBe('Research in progress... (30% complete)');
    });

    it('heartbeat does not merge with non-heartbeat messages', () => {
      const analyzing = makeAgentData({ agent_id: 'execution', agent_name: 'Agent Execution', action: 'analyzing', content: 'Starting Agent Execution...' });
      let msgs = simulateOnAgentMessage(analyzing, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);

      const hb = makeAgentData({ agent_id: 'system', agent_name: 'System', action: 'heartbeat', content: 'Research in progress...' });
      msgs = simulateOnAgentMessage(hb, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(2);
    });
  });

  describe('Error handling', () => {
    it('error action for non-mergeable agent → new message', () => {
      const error = makeAgentData({ agent_id: 'research_market_size_1', agent_name: '市场规模', action: 'error', content: '市场规模 analysis failed.' });
      const msgs = simulateOnAgentMessage(error, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);
      expect(msgs[0].agent?.action).toBe('error');
    });

    it('error action for mergeable agent → new message (not merged)', () => {
      const search = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'searching', content: 'Searching for: BYD' });
      let msgs = simulateOnAgentMessage(search, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);

      const error = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'error', content: 'Search failed' });
      msgs = simulateOnAgentMessage(error, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(2);
      const errorMsg = msgs.find(m => m.agent?.action === 'error');
      expect(errorMsg?.content).toBe('Search failed');
    });
  });

  describe('Edge cases', () => {
    it('scrape_url is mergeable', () => {
      const search = makeAgentData({ agent_id: 'scrape_url', agent_name: 'Content Scraper Agent', action: 'searching', content: 'Scraping: https://example.com' });
      let msgs = simulateOnAgentMessage(search, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);

      const complete = makeAgentData({ agent_id: 'scrape_url', agent_name: 'Content Scraper Agent', action: 'completed', content: 'Completed: scrape_url' });
      msgs = simulateOnAgentMessage(complete, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);
      expect(msgs[0].agent?.completedCount).toBe(1);
    });

    it('get_current_datetime is NOT mergeable', () => {
      const dt = makeAgentData({ agent_id: 'get_current_datetime', agent_name: 'Date/Time Agent', action: 'completed', content: 'Completed: get_current_datetime' });
      const msgs = simulateOnAgentMessage(dt, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);
      expect(msgs[0].agent?.completedCount).toBeUndefined();
    });

    it('unknown agent_id is NOT mergeable', () => {
      const unknown = makeAgentData({ agent_id: 'custom_tool', agent_name: 'Custom Tool', action: 'completed', content: 'Completed: custom_tool' });
      const msgs = simulateOnAgentMessage(unknown, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);
      expect(msgs[0].agent?.completedCount).toBeUndefined();
    });

    it('web_search: error then resume → error stays separate, resume continues merge', () => {
      const search1 = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'searching', content: 'Searching for: BYD' });
      let msgs = simulateOnAgentMessage(search1, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);

      const error = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'error', content: 'Network error' });
      msgs = simulateOnAgentMessage(error, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(2);

      const search2 = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'searching', content: 'Searching for: BYD revenue' });
      msgs = simulateOnAgentMessage(search2, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(2);
      const mergeMsg = msgs.find(m => m.agent?.action !== 'error');
      expect(mergeMsg?.content).toBe('Searching for: BYD revenue');
      expect(mergeMsg?.agent?.completedCount).toBe(0);

      const complete2 = makeAgentData({ agent_id: 'web_search', agent_name: 'Web Search Agent', action: 'completed', content: 'Completed: web_search' });
      msgs = simulateOnAgentMessage(complete2, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(2);
      const completedMsg = msgs.find(m => m.agent?.action !== 'error');
      expect(completedMsg?.agent?.completedCount).toBe(1);
    });

    it('warning action is NOT mergeable', () => {
      const warning = makeAgentData({ agent_id: 'system', agent_name: '系统', action: 'warning', content: 'Preview issues detected' });
      const msgs = simulateOnAgentMessage(warning, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);
      expect(msgs[0].agent?.completedCount).toBeUndefined();
    });

    it('non-mergeable writing action updates in-place', () => {
      const write1 = makeAgentData({ agent_id: 'research_market_size_1', agent_name: '市场规模', action: 'writing', content: 'Writing section: 30%' });
      let msgs = simulateOnAgentMessage(write1, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);

      const write2 = makeAgentData({ agent_id: 'research_market_size_1', agent_name: '市场规模', action: 'writing', content: 'Writing section: 70%' });
      msgs = simulateOnAgentMessage(write2, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);
      expect(msgs[0].content).toBe('Writing section: 70%');
    });

    it('non-mergeable agent: different actions → separate messages', () => {
      const searching = makeAgentData({ agent_id: 'research_market_size_1', agent_name: '市场规模', action: 'searching', content: 'Searching for data...' });
      let msgs = simulateOnAgentMessage(searching, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(1);

      const analyzing = makeAgentData({ agent_id: 'research_market_size_1', agent_name: '市场规模', action: 'analyzing', content: 'Analyzing data...' });
      msgs = simulateOnAgentMessage(analyzing, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(2);

      const writing = makeAgentData({ agent_id: 'research_market_size_1', agent_name: '市场规模', action: 'writing', content: 'Writing report...' });
      msgs = simulateOnAgentMessage(writing, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(3);

      const completed = makeAgentData({ agent_id: 'research_market_size_1', agent_name: '市场规模', action: 'completed', content: '市场规模 completed.' });
      msgs = simulateOnAgentMessage(completed, store.getMessages(), store.addMessage, store.updateMessage);
      expect(msgs).toHaveLength(4);
    });
  });
});

describe('AgentMessage Display Logic', () => {
  function getDisplayText(message: ChatMessage): string {
    const action = message.agent?.action || 'searching';
    const completedCount = message.agent?.completedCount || 0;
    const totalCount = message.agent?.totalCount || 0;
    const showCount = totalCount > 1;

    if (!showCount) return message.content;

    const taskName = message.agent?.id || message.content.replace(/^Completed:\s*/, '').replace(/^completed\.?/i, '').trim() || 'tasks';
    if (action === 'completed') {
      return `${completedCount}/${totalCount} ${taskName} completed`;
    }
    return `${completedCount} ${taskName} completed, ${message.content}`;
  }

  it('single web_search completed → shows original content', () => {
    const msg: ChatMessage = {
      id: '1', role: 'agent', content: 'Completed: web_search', timestamp: '',
      agent: { id: 'web_search', name: 'Web Search Agent', action: 'completed', completedCount: 1, totalCount: 1 },
    };
    expect(getDisplayText(msg)).toBe('Completed: web_search');
  });

  it('3 web_search completed → shows "3/3 web_search completed"', () => {
    const msg: ChatMessage = {
      id: '1', role: 'agent', content: 'Completed: web_search', timestamp: '',
      agent: { id: 'web_search', name: 'Web Search Agent', action: 'completed', completedCount: 3, totalCount: 3 },
    };
    expect(getDisplayText(msg)).toBe('3/3 web_search completed');
  });

  it('searching with 2 completed → shows "2 web_search completed, Searching for: ..."', () => {
    const msg: ChatMessage = {
      id: '1', role: 'agent', content: 'Searching for: BYD overseas', timestamp: '',
      agent: { id: 'web_search', name: 'Web Search Agent', action: 'searching', completedCount: 2, totalCount: 2 },
    };
    expect(getDisplayText(msg)).toBe('2 web_search completed, Searching for: BYD overseas');
  });

  it('non-mergeable agent → shows original content', () => {
    const msg: ChatMessage = {
      id: '1', role: 'agent', content: 'Starting research on 「BYD」...', timestamp: '',
      agent: { id: 'orchestrator', name: 'Research Orchestrator', action: 'analyzing' },
    };
    expect(getDisplayText(msg)).toBe('Starting research on 「BYD」...');
  });

  it('6/6 web_search completed → shows "6/6 web_search completed"', () => {
    const msg: ChatMessage = {
      id: '1', role: 'agent', content: 'Completed: web_search', timestamp: '',
      agent: { id: 'web_search', name: 'Web Search Agent', action: 'completed', completedCount: 6, totalCount: 6 },
    };
    expect(getDisplayText(msg)).toBe('6/6 web_search completed');
  });

  it('news_search completed with count → shows "2/2 news_search completed"', () => {
    const msg: ChatMessage = {
      id: '1', role: 'agent', content: 'Completed: news_search', timestamp: '',
      agent: { id: 'news_search', name: 'News Search Agent', action: 'completed', completedCount: 2, totalCount: 2 },
    };
    expect(getDisplayText(msg)).toBe('2/2 news_search completed');
  });

  it('scrape_url with count → shows "1/1 scrape_url completed" but totalCount=1 so shows original', () => {
    const msg: ChatMessage = {
      id: '1', role: 'agent', content: 'Completed: scrape_url', timestamp: '',
      agent: { id: 'scrape_url', name: 'Content Scraper Agent', action: 'completed', completedCount: 1, totalCount: 1 },
    };
    expect(getDisplayText(msg)).toBe('Completed: scrape_url');
  });

  it('warning action → shows original content', () => {
    const msg: ChatMessage = {
      id: '1', role: 'agent', content: '修订完成但预览可能存在排版问题', timestamp: '',
      agent: { id: 'system', name: '系统', action: 'warning' },
    };
    expect(getDisplayText(msg)).toBe('修订完成但预览可能存在排版问题');
  });

  it('error action → shows original content', () => {
    const msg: ChatMessage = {
      id: '1', role: 'agent', content: 'Search failed', timestamp: '',
      agent: { id: 'web_search', name: 'Web Search Agent', action: 'error' },
    };
    expect(getDisplayText(msg)).toBe('Search failed');
  });

  it('agent without agent field → shows content with searching fallback', () => {
    const msg: ChatMessage = {
      id: '1', role: 'agent', content: 'Some message', timestamp: '',
    };
    expect(getDisplayText(msg)).toBe('Some message');
  });
});
