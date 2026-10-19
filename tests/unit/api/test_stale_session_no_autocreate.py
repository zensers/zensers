import pytest
from unittest.mock import patch


@pytest.mark.asyncio
async def test_invalid_nonempty_session_id_does_not_create_new_session():
    from src.api.research_api import ResearchAPI

    api = ResearchAPI.__new__(ResearchAPI)
    with patch('src.api.research_api.session_manager') as manager:
        manager.get.return_value = None
        result = await api.handle_interact(
            'ses_stale',
            step=0,
            response={'text': '你好'},
        )

    assert result == {'error': 'Session not found', 'error_code': 'SESSION_NOT_FOUND'}
    manager.create.assert_not_called()
