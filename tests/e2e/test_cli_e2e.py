# -*- coding: utf-8 -*-
"""
End-to-end test for CLI module — real LLM environment.

Prerequisites:
  - API server running at http://127.0.0.1:8000
  - LLM configured in .env (LLM_API_KEY, LLM_BASE_URL, LLM_MODEL)
  - Network access to LLM API endpoint

Run:
  python -m pytest tests/e2e/test_cli_e2e.py -v -s
"""
import asyncio
import json
import os
import sys
import time
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

API_URL = os.environ.get("ZENSERS_API_URL", "http://127.0.0.1:8000")
CLI_PYTHON = sys.executable

REQUIREMENT = "中国新能源汽车市场概况"


def _skip_if_no_server():
    import httpx
    try:
        r = httpx.get(f"{API_URL}/api/v1/health", timeout=5)
        if r.status_code != 200:
            pytest.skip("API server not healthy")
    except Exception:
        pytest.skip("API server not reachable")


@pytest.fixture
def api_server():
    """Require the external API only for tests that actually call it."""
    _skip_if_no_server()


# =========================================================================
# Test 1: API health + version (no LLM needed)
# =========================================================================
class TestAPIBasic:
    def test_health(self, api_server):
        import httpx
        r = httpx.get(f"{API_URL}/api/v1/health", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"

    def test_version(self, api_server):
        import httpx
        r = httpx.get(f"{API_URL}/api/v1/version", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "local_version" in data or "version" in data

    def test_llm_models(self, api_server):
        import httpx
        r = httpx.get(f"{API_URL}/api/v1/llm/models", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "providers" in data or "models" in data

    def test_llm_config(self, api_server):
        import httpx
        r = httpx.get(f"{API_URL}/api/v1/llm/config", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "provider" in data or "model" in data

    def test_llm_health(self, api_server):
        import httpx
        r = httpx.get(f"{API_URL}/api/v1/llm/health", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "reachable" in data


# =========================================================================
# Test 2: ZensersClient against real API
# =========================================================================
class TestClientE2E:
    @pytest.mark.asyncio
    async def test_client_health(self, api_server):
        from cli.client import ZensersClient
        async with ZensersClient(base_url=API_URL) as client:
            result = await client.version_info()
            assert "local_version" in result or "version" in result

    @pytest.mark.asyncio
    async def test_client_llm_models(self, api_server):
        from cli.client import ZensersClient
        async with ZensersClient(base_url=API_URL) as client:
            result = await client.llm_models()
            assert "providers" in result or "models" in result

    @pytest.mark.asyncio
    async def test_client_research_sessions_empty(self, api_server):
        from cli.client import ZensersClient
        async with ZensersClient(base_url=API_URL) as client:
            result = await client.research_sessions(limit=5)
            assert "sessions" in result


# =========================================================================
# Test 3: Start research session with real LLM — full dialogue flow
# =========================================================================
class TestResearchSessionE2E:
    @pytest.mark.asyncio
    async def test_start_session_and_interact(self, api_server):
        """
        Full E2E: start a research session via API, verify LLM responds,
        then check session status and message history.
        """
        from cli.client import ZensersClient, ZensersError

        async with ZensersClient(base_url=API_URL) as client:
            # Step 1: Start research
            start_result = await client.research_start(
                user_input=REQUIREMENT,
                user_id="e2e_test",
            )

            session_id = start_result.get("session_id") or start_result.get("task_id")
            assert session_id, f"No session_id in start result: {start_result}"

            print(f"\n[1] Session started: {session_id}")

            # Step 2: Verify the LLM actually responded
            response = start_result.get("response", start_result.get("message", ""))
            assert response, f"No response from LLM in start result: {start_result}"
            print(f"[2] LLM responded: {str(response)[:100]}...")

            # Step 3: Send an interact message to continue the dialogue
            await asyncio.sleep(1)
            interact_result = await client.research_interact(
                session_id=session_id,
                user_message="请帮我确认开始研究",
            )

            interact_response = interact_result.get("response", interact_result.get("message", ""))
            print(f"[3] Interact response: {str(interact_response)[:100]}...")

            # Step 4: Check session status
            await asyncio.sleep(1)
            status_result = await client.research_status(session_id)
            status = status_result.get("status", "unknown")
            print(f"[4] Session status: {status}")
            assert status != "unknown", f"Status should not be unknown: {status_result}"

            # Step 5: Check message history
            messages_result = await client.research_messages(session_id, limit=10)
            messages = messages_result.get("messages", [])
            assert len(messages) >= 2, f"Expected at least 2 messages, got {len(messages)}"
            print(f"[5] Message count: {len(messages)}")

            # Step 6: List sessions — should include our session
            sessions_result = await client.research_sessions(limit=10)
            sessions = sessions_result.get("sessions", [])
            found = any(
                s.get("session_id", s.get("task_id", "")) == session_id
                for s in sessions
            )
            assert found, f"Our session {session_id} not found in sessions list"
            print(f"[6] Session found in list")

            # Step 7: Get session detail
            detail_result = await client.research_detail(session_id)
            assert detail_result.get("session_id") or detail_result.get("task_id"), \
                f"Detail result missing ID: {detail_result}"
            print(f"[7] Session detail retrieved")

            print(f"\n[PASS] Full E2E session flow passed for session {session_id}")


# =========================================================================
# Test 4: CLI commands via subprocess (real server)
# =========================================================================
class TestCLISubprocessE2E:
    def test_cli_version(self):
        import subprocess
        result = subprocess.run(
            [CLI_PYTHON, "-m", "src.cli.main", "version"],
            capture_output=True, text=True, timeout=15,
            cwd=str(Path(__file__).parent.parent.parent),
        )
        assert result.returncode == 0, f"CLI version failed: {result.stderr}"
        assert "Zensers" in result.stdout or "Version" in result.stdout

    def test_cli_config_show(self):
        import subprocess
        result = subprocess.run(
            [CLI_PYTHON, "-m", "src.cli.main", "config", "--show"],
            capture_output=True, text=True, timeout=15,
            cwd=str(Path(__file__).parent.parent.parent),
        )
        assert result.returncode == 0, f"CLI config show failed: {result.stderr}"

    def test_cli_session_list(self, api_server):
        import subprocess
        env = os.environ.copy()
        env["ZENSERS_API_URL"] = API_URL
        result = subprocess.run(
            [CLI_PYTHON, "-m", "src.cli.main", "--api-url", API_URL, "session", "list"],
            capture_output=True, text=True, timeout=15,
            cwd=str(Path(__file__).parent.parent.parent),
            env=env,
        )
        assert result.returncode == 0, f"CLI session list failed: {result.stderr}"

    def test_cli_llm_config(self, api_server):
        import subprocess
        env = os.environ.copy()
        env["ZENSERS_API_URL"] = API_URL
        result = subprocess.run(
            [CLI_PYTHON, "-m", "src.cli.main", "--api-url", API_URL, "llm", "config"],
            capture_output=True, text=True, timeout=15,
            cwd=str(Path(__file__).parent.parent.parent),
            env=env,
        )
        assert result.returncode == 0, f"CLI llm config failed: {result.stderr}"

    def test_cli_llm_health(self, api_server):
        import subprocess
        env = os.environ.copy()
        env["ZENSERS_API_URL"] = API_URL
        result = subprocess.run(
            [CLI_PYTHON, "-m", "src.cli.main", "--api-url", API_URL, "llm", "health"],
            capture_output=True, text=True, timeout=20,
            cwd=str(Path(__file__).parent.parent.parent),
            env=env,
        )
        assert result.returncode == 0, f"CLI llm health failed: {result.stderr}"

    def test_cli_task_status_no_args(self, api_server):
        import subprocess
        env = os.environ.copy()
        env["ZENSERS_API_URL"] = API_URL
        result = subprocess.run(
            [CLI_PYTHON, "-m", "src.cli.main", "--api-url", API_URL, "status"],
            capture_output=True, text=True, timeout=15,
            cwd=str(Path(__file__).parent.parent.parent),
            env=env,
        )
        assert result.returncode == 0, f"CLI status (no args) failed: {result.stderr}"


# =========================================================================
# Test 5: Research start via CLI subprocess (real LLM)
# =========================================================================
class TestCLIResearchE2E:
    def test_cli_research_no_interactive(self, api_server):
        """
        Start a research session via CLI with --no-interactive.
        In non-interactive mode, the CLI starts the session and prints the session ID,
        then exits (since research needs dialogue confirmation).
        """
        import subprocess
        env = os.environ.copy()
        env["ZENSERS_API_URL"] = API_URL
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        result = subprocess.run(
            [CLI_PYTHON, "-m", "src.cli.main", "--api-url", API_URL,
             "research", REQUIREMENT, "--no-interactive"],
            capture_output=True, timeout=60,
            cwd=str(Path(__file__).parent.parent.parent),
            env=env,
        )
        stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
        stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
        output = stdout + stderr
        safe_output = output.encode("ascii", errors="replace").decode("ascii")
        print(f"Research output:\n{safe_output[:2000]}")
        assert result.returncode == 0, f"CLI research failed: {output[:500]}"
        assert "session" in output.lower() or "Session" in output, \
            f"Research didn't start properly: {output[:500]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
