"""
MCP remote connection test for local BRAIN Alpha data server.
Tests stdio-based MCP server connection and tool execution.
"""

import asyncio
import json

MCP_SERVER_PATH = r"E:/worldquantV4/data_download/mcp_server.py"
MCP_PYTHON = r"C:/Users/Administrator/.conda/envs/worldquent/python.exe"


async def test_stdio_connection():
    import subprocess

    print(f"Server: {MCP_SERVER_PATH}")
    print(f"Python: {MCP_PYTHON}")
    print()

    proc = await asyncio.create_subprocess_exec(
        MCP_PYTHON,
        MCP_SERVER_PATH,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=r"E:/worldquantV4/data_download",
    )

    async def send(request: dict) -> dict:
        line = json.dumps(request) + "\n"
        proc.stdin.write(line.encode())
        await proc.stdin.drain()
        if "id" not in request:
            return {}
        resp = await asyncio.wait_for(proc.stdout.readline(), timeout=30.0)
        return json.loads(resp.decode())

    async def stderr_snapshot():
        await asyncio.sleep(0.3)
        try:
            while True:
                line = await asyncio.wait_for(proc.stderr.readline(), timeout=0.5)
                if not line:
                    break
                print(f"  [stderr] {line.decode().strip()}")
        except (asyncio.TimeoutError, ValueError):
            pass

    try:
        # Initialize
        print("1. initialize...")
        r = await send({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        })
        print(f"   server: {r.get('result', {}).get('serverInfo', {})}")
        await stderr_snapshot()
        print()

        # Notify initialized
        print("2. notifications/initialized...")
        await send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        await asyncio.sleep(1)
        await stderr_snapshot()
        print()

        # List tools
        print("3. tools/list...")
        r = await send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = r.get("result", {}).get("tools", [])
        print(f"   {len(tools)} tools:")
        for t in tools:
            print(f"   - {t['name']}")
        await stderr_snapshot()
        print()

        # Query alphas
        print("4. local_query_alphas (top 3)...")
        r = await send({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {
                "name": "local_query_alphas",
                "arguments": {"limit": 3, "region": "USA"},
            },
        })
        result_data = r.get("result", {})
        content = result_data.get("content", [])
        if content:
            data = json.loads(content[0].get("text", "{}"))
            results = data.get("results", [])
            for a in results[:3]:
                print(f"   id={a.get('id','?')} sharpe={a.get('is_sharpe',0):.2f} region={a.get('region','?')}")
        else:
            print(f"   empty (isError={result_data.get('isError')})")
        await stderr_snapshot()
        print()

        # Statistics
        print("5. local_get_statistics...")
        r = await send({
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "local_get_statistics", "arguments": {}},
        })
        content = r.get("result", {}).get("content", [])
        if content:
            stats = json.loads(content[0]["text"])
            print(f"   total: {stats.get('total_alphas', '?')}")
            print(f"   by_region: {stats.get('by_region', {})}")
        await stderr_snapshot()
        print()

        print("=== ALL TESTS PASSED ===")

    except Exception as e:
        print(f"ERROR: {e}")
        await stderr_snapshot()
        import traceback
        traceback.print_exc()

    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            proc.kill()


if __name__ == "__main__":
    asyncio.run(test_stdio_connection())
