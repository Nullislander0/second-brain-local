"""Test the capture_text MCP tool end-to-end."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from db_client.client import close_pool, get_pool


async def cleanup():
    pool = await get_pool()
    await pool.execute("DELETE FROM brain_entries WHERE source_client IN ($1, $2)", "claude_code", "mcp")
    await close_pool()


async def main():
    server_script = str(Path(__file__).resolve().parent.parent / "mcp_server" / "server.py")
    server_params = StdioServerParameters(command=sys.executable, args=[server_script])

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # Verify capture_text_tool is listed
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            assert "capture_text_tool" in names, f"capture_text_tool not found in {names}"
            print(f"Tools: {names}")

            # Capture something worth storing
            print("\n1. Capturing store-worthy text...")
            r = await session.call_tool("capture_text_tool", arguments={
                "text": (
                    "We decided to use Redis for session caching in the auth "
                    "service because it supports TTL natively and has sub-millisecond "
                    "reads. Marcus evaluated Memcached as well but Redis won on "
                    "feature set for the Gateway project."
                ),
            })
            data = json.loads(r.content[0].text)
            assert data["stored"] is True
            print(f"   Stored: id={data['id'][:8]}... reason={data['reason']}")

            # Capture junk — should be rejected
            print("2. Capturing junk (should reject)...")
            r2 = await session.call_tool("capture_text_tool", arguments={
                "text": "lol ok",
            })
            d2 = json.loads(r2.content[0].text)
            assert d2["stored"] is False
            print(f"   Rejected: {d2['reason'][:60]}")

            # Search for what we just stored
            print("3. Searching for the stored entry...")
            r3 = await session.call_tool("search_brain_tool", arguments={
                "query": "Redis session caching decision",
            })
            d3 = json.loads(r3.content[0].text)
            assert d3["count"] >= 1
            assert "Redis" in d3["results"][0]["raw_text"]
            print(f"   Found: {d3['count']} results, top has 'Redis'")

    # Cleanup
    print("\n4. Cleaning up...")
    await cleanup()
    print("   Done.")
    print("\nAll capture tool tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
