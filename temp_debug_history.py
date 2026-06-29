"""Debug: check why history not loading fully"""
from src.core.session_manager import SessionManager
sm = SessionManager.get_instance()
sm.recover_all()

for sid in list(sm._sessions.keys()):
    s = sm.get(sid)
    if not s:
        continue
    history = s.get('display_history') or s.get('conversation_history', [])
    if not history:
        continue
    print(f"\n=== Session {sid[:16]} ===")
    print(f"Total messages: {len(history)}")
    passed = 0
    for i, msg in enumerate(history):
        if not isinstance(msg, dict):
            print(f"  [{i}] NOT A DICT: {type(msg)}")
            continue
        has_role = 'role' in msg
        has_type = 'type' in msg
        has_content = 'content' in msg
        passes = (has_role or has_type) and has_content
        if passes:
            passed += 1
        else:
            print(f"  [{i}] FILTERED OUT: keys={list(msg.keys())}")
    print(f"Passed filter: {passed}/{len(history)}")
