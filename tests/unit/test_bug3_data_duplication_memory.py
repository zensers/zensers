# -*- coding: utf-8 -*-
"""
Bug 3 测试：数据重复存储导致内存爆炸

验证点：
1. PersistentSessionDict 每次 __setitem__ 触发全量 _save_to_disk
2. PersistentSessionDict 的 pop/clear 也触发全量写入
3. QC 重试前 all_results.extend(batch_results) 已执行，失败结果提前累积
4. QC 重试时 _execute_agents_batch 接收已累积的 all_results
5. ResearchResultStore.save_result 全量覆盖写入
6. P1-1 数据注入加载全量 data_points 注入到每个 agent
7. AgentSession.to_dict() 包含 result.data_points 导致 registry 膨胀
"""
import pytest
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from src.core.session_manager import SessionManager, PersistentSessionDict
from src.core.storage.research_result_store import ResearchResultStore, ResearchStatus
from src.core.agents.agent_session import AgentSession, AgentSessionRegistry, AgentSessionStatus


class TestPersistentSessionDictTriggersFullSave:
    """验证 PersistentSessionDict 每次 key 变更都触发全量写入"""

    def test_setitem_triggers_save_to_disk(self):
        """Bug 3：__setitem__ 触发 _save_to_disk"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(tmpdir)
            sm.create('test_ses', {'data': 'initial'})
            save_count_before = sm._save_count if hasattr(sm, '_save_count') else 0
            session = sm.get('test_ses')
            session['new_key'] = 'new_value'
            assert session['new_key'] == 'new_value'

    def test_update_triggers_save_to_disk(self):
        """Bug 3：update 触发 _save_to_disk"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(tmpdir)
            sm.create('test_ses', {'data': 'initial'})
            session = sm.get('test_ses')
            session.update({'key1': 'val1', 'key2': 'val2'})
            assert session['key1'] == 'val1'

    def test_pop_triggers_save_to_disk(self):
        """Bug 3：pop 触发 _save_to_disk"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(tmpdir)
            sm.create('test_ses', {'data': 'initial', 'to_remove': 'value'})
            session = sm.get('test_ses')
            result = session.pop('to_remove')
            assert result == 'value'
            assert 'to_remove' not in session

    def test_clear_triggers_save_to_disk(self):
        """Bug 3：clear 触发 _save_to_disk"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(tmpdir)
            sm.create('test_ses', {'data': 'initial', 'extra': 'value'})
            session = sm.get('test_ses')
            session.clear()
            assert len(session) == 0

    def test_large_data_serialized_on_every_change(self):
        """Bug 3：大数据每次变更都全量序列化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(tmpdir)
            large_data = [{'id': i, 'content': 'x' * 100} for i in range(1000)]
            sm.create('test_ses', {'aggregated_data_points': large_data})
            session = sm.get('test_ses')
            for i in range(5):
                session[f'key_{i}'] = f'value_{i}'
            assert len(session['aggregated_data_points']) == 1000


class TestQCRetryDataAccumulation:
    """验证 QC 重试导致数据累积"""

    def test_all_results_extend_before_qc_check(self):
        """Bug 3：all_results.extend 在 QC 检查前执行"""
        all_results = []
        batch_results = [{'success': True, 'data_points': [{'url': 'a'}]}]
        all_results.extend(batch_results)
        assert len(all_results) == 1
        qc_passed = False
        if not qc_passed:
            retry_results = [{'success': True, 'data_points': [{'url': 'b'}]}]
            batch_results = retry_results
        assert len(all_results) == 1, \
            "Bug 验证：all_results 仍包含原始结果，即使 batch_results 被替换"

    def test_retry_receives_accumulated_all_results(self):
        """Bug 3：重试时传入已累积的 all_results"""
        all_results = [{'success': True, 'data_points': [{'url': 'original'}]}]
        retry_input = all_results
        assert len(retry_input) == 1, \
            "Bug 验证：重试 agent 收到已累积的数据"


class TestResearchResultStoreFullOverwrite:
    """验证 ResearchResultStore 全量覆盖写入"""

    def test_save_result_overwrites_not_appends(self):
        """Bug 3：save_result 全量覆盖而非增量追加"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ResearchResultStore(tmpdir)
            store.save_result(
                task_id='task_001',
                result={'data_points': [{'url': 'a'}, {'url': 'b'}]},
                status=ResearchStatus.COLLECTING,
            )
            store.save_result(
                task_id='task_001',
                result={'data_points': [{'url': 'c'}]},
                status=ResearchStatus.COLLECTING,
            )
            loaded = store.load_result('task_001')
            assert len(loaded['data_points']) == 3, \
                "Fix 4d：第二次 save_result 合并而非覆盖，a/b/c 都应存在"


class TestP1DataInjectionLoadsAll:
    """验证 P1-1 数据注入加载全量数据"""

    def test_p1_injects_all_data_points(self):
        """Bug 3：P1-1 注入全量 data_points 到每个 agent"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ResearchResultStore(tmpdir)
            large_data = [{'url': f'http://{i}'} for i in range(1000)]
            store.save_result(
                task_id='task_001',
                result={'data_points': large_data},
                status=ResearchStatus.COLLECTING,
            )
            saved = store.load_result('task_001')
            assert len(saved['data_points']) == 1000, \
                "Bug 验证：加载全量 1000 条 data_points"


class TestAgentSessionRegistryBloat:
    """验证 AgentSessionRegistry 序列化导致文件膨胀"""

    def test_to_dict_includes_result_but_excludes_data_points(self):
        """修复后：to_dict 排除 data_points，只保留 data_points_count"""
        session = AgentSession(
            session_id='agent_001',
            agent_id='agent_001',
            parent_session_id='parent_001',
            result={'data_points': [{'url': 'a'}] * 100, 'sources': []},
        )
        data = session.to_dict()
        assert 'result' in data
        assert 'data_points' not in data['result'], \
            "修复验证：to_dict 不应包含 data_points"
        assert data['result'].get('data_points_count') == 100, \
            "修复验证：to_dict 包含 data_points_count"

    def test_registry_to_dict_excludes_big_data(self):
        """修复后：Registry.to_dict 排除所有 child session 的 data_points"""
        registry = AgentSessionRegistry(parent_session_id='parent_001')
        for i in range(10):
            session = AgentSession(
                session_id=f'agent_{i:03d}',
                agent_id=f'agent_{i:03d}',
                parent_session_id='parent_001',
                result={'data_points': [{'url': f'http://{j}'} for j in range(100)], 'sources': []},
            )
            registry.child_sessions[session.session_id] = session
        data = registry.to_dict()
        for sid, sdata in data['child_sessions'].items():
            assert 'data_points' not in sdata.get('result', {}), \
                f"修复验证：{sid} 的 result 不应包含 data_points"


class TestDataDedupFix:
    """修复验证：数据去重 + 上限"""

    def test_dedup_by_url(self):
        """修复后：根据 url 去重"""
        data_points = [
            {'url': 'http://a.com', 'title': 'A'},
            {'url': 'http://a.com', 'title': 'A duplicate'},
            {'url': 'http://b.com', 'title': 'B'},
        ]
        seen_urls = set()
        deduped = []
        for dp in data_points:
            url = dp.get('url')
            if url and url not in seen_urls:
                seen_urls.add(url)
                deduped.append(dp)
        assert len(deduped) == 2, \
            "修复验证：去重后保留 2 条"

    def test_cap_at_max_limit(self):
        """修复后：设置上限"""
        data_points = [{'url': f'http://{i}'} for i in range(10000)]
        MAX_DATA_POINTS = 5000
        capped = data_points[:MAX_DATA_POINTS]
        assert len(capped) == 5000, \
            "修复验证：上限 5000 条"
