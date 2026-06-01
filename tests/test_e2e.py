"""Test v2 revision end-to-end via direct method call."""
import sys, os
test_dir = os.path.dirname(__file__)
project_root = os.path.dirname(test_dir)
src_dir = os.path.join(project_root, 'src')
sys.path.insert(0, src_dir)
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

from unittest.mock import MagicMock
import asyncio
import json

from src.api.research_api import ResearchAPI
import src.api.research_api as ra

async def test():
    session = {
        'session_id': 'test_v2',
        'mode': 'chat',
        'state_machine': MagicMock(),
        'research_result': {
            'report': {
                'sections': [
                    {'id': 's1', 'title': '市场规模', 'content': 'data1'},
                    {'id': 's2', 'title': '竞争格局', 'content': 'data2'},
                    {'id': 's3', 'title': '发展趋势', 'content': 'data3'},
                ]
            }
        },
        'research_context': {},
        'conversation_history': [],
    }

    api = ResearchAPI.__new__(ResearchAPI)
    api._revision_task = None
    api._v2_lock_manager = None
    api._chat_response = MagicMock(return_value={'status': 'ok', 'message': 'mock'})

    ra.session_manager = MagicMock()
    ra.session_manager.get.return_value = session
    ra.logger = MagicMock()

    conv_result = {
        'adjustment': 'delete the third section',
        'aspects': [],
        'revision_type': 'section',
    }

    result = await api._handle_v2_revision('test_v2', conv_result)
    print('result:', json.dumps(result, ensure_ascii=False))

    pending = session.get('_pending_v2_revision')
    if pending:
        flow = pending['flow']
        print('snapshot_id:', pending['snapshot_id'])
        print('flow.status:', flow.status.value)
        print('PASS: _pending_v2_revision stored correctly')
    else:
        print('FAIL: no _pending_v2_revision in session')

if __name__ == '__main__':
    asyncio.run(test())
