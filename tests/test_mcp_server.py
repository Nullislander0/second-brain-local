"""End-to-end test: start the MCP server as a subprocess, call all three tools via MCP client SDK."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Seed data directly before starting the server
from capture.embedder import generate_embedding
from db_client.client import close_pool, get_pool, insert_entry


async def seed_data():
    emb = await generate_embedding(
        "We decided to use Rust for the new CLI tool because it compiles to "
        "a single binary and has excellent error handling. Dave prototyped it."
    )
    eid = await insert_entry(
        raw_text=(
            "We decided to use Rust for the new CLI tool because it compiles to "
            "a single binary and has excellent error handling. Dave prototyped it."
        ),
        embedding=emb,
        entry_type="decision",
        topics=["Rust", "CLI", "tooling"],
        people=["Dave"],
        projects=["cli-tool"],
        action_items=[],
        source_client="mcp_test",
        relevance_score=0.92,
    )
    await close_pool()
    return str(eid)


async def cleanup():
    pool = await get_pool()
    await pool.execute("DELETE FROM brain_entries WHERE source_client = $1", "mcp_test")
    await close_pool()


async def run_test():
    entry_id = await seed_data()
    print(f"Seeded entry: {entry_id}\n")

    server_script = str(Path(__file__).resolve().parent.parent / "mcp_server" / "server.py")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[server_script],
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # 1. Initialize
            print("1. Initializing MCP session...")
            await session.initialize()
            print("   OK — session initialized")

            # 2. List tools
            print("2. Listing tools...")
            tools_result = await session.list_tools()
            tool_names = [t.name for t in tools_result.tools]
            print(f"   OK — tools: {tool_names}")
            assert "search_brain_tool" in tool_names
            assert "recent_entries" in tool_names
            assert "brain_stats" in tool_names

            # 3. Call search_brain_tool
            print("3. Calling search_brain_tool...")
            search_result = await session.call_tool(
                "search_brain_tool",
                arguments={"query": "Rust CLI single binary", "limit": 5},
            )
            search_data = json.loads(search_result.content[0].text)
            assert search_data["count"] >= 1
            assert "Rust" in search_data["results"][0]["raw_text"]
            print(f"   OK — {search_data['count']} results, top has 'Rust'")

            # 4. Call recent_entries
            print("4. Calling recent_entries...")
            recent_result = await session.call_tool(
                "recent_entries",
                arguments={"days": 1},
            )
            recent_data = json.loads(recent_result.content[0].text)
            assert recent_data["count"] >= 1
            print(f"   OK — {recent_data['count']} entries")

            # 5. Call brain_stats
            print("5. Calling brain_stats...")
            stats_result = await session.call_tool(
                "brain_stats",
                arguments={"days": 30},
            )
            stats_data = json.loads(stats_result.content[0].text)
            assert stats_data["total_all_time"] >= 1
            assert isinstance(stats_data["by_entry_type"], dict)
            assert isinstance(stats_data["top_topics"], dict)
            print(f"   OK — total_all_time={stats_data['total_all_time']}, "
                  f"by_type={stats_data['by_entry_type']}")

    # Cleanup
    print("\n6. Cleaning up...")
    await cleanup()
    print("   Done.")
    print("\nAll MCP server tests passed!")


if __name__ == "__main__":
    asyncio.run(run_test())
