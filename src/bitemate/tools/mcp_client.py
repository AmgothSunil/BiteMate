# src/bitemate/tools/mcp_client.py

import os
import sys
import asyncio
from dotenv import load_dotenv

from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, SseConnectionParams

load_dotenv()

_mcp_toolset_instance: McpToolset | None = None


def get_mcp_toolset() -> McpToolset:
    """
    Returns a singleton MCP Toolset instance for this process.
    """
    global _mcp_toolset_instance
    if _mcp_toolset_instance is not None:
        return _mcp_toolset_instance

    try:
        _mcp_toolset_instance = McpToolset(
            connection_params=SseConnectionParams(
                url=os.getenv("MCP_SERVER_URL", "http://localhost:8000/sse"),
                timeout=60,
            )
        )
        return _mcp_toolset_instance
    except Exception as e:
        print(f"❌ Failed to create MCP Toolset: {e}", file=sys.stderr)
        raise


async def cleanup_mcp_toolset():
    """Properly cleanup the MCP toolset instance."""
    global _mcp_toolset_instance
    if _mcp_toolset_instance is not None:
        try:
            # Close the session manager if it has a close method
            if hasattr(_mcp_toolset_instance, '_mcp_session_manager'):
                session_manager = _mcp_toolset_instance._mcp_session_manager
                if hasattr(session_manager, 'close'):
                    await session_manager.close()
        except Exception as e:
            print(f"Warning during cleanup: {e}", file=sys.stderr)
        finally:
            _mcp_toolset_instance = None


async def debug_list_tools():
    """Debug function to list all available MCP tools."""
    toolset = get_mcp_toolset()
    print("✅ MCP Toolset created:", type(toolset))

    try:
        if hasattr(toolset, "get_tools"):
            tools = await toolset.get_tools()
            print("\n📋 Available MCP Tools:")
            print("-" * 50)

            if isinstance(tools, (list, tuple)):
                for i, tool in enumerate(tools, 1):
                    name = getattr(tool, "name", getattr(tool, "tool_name", "unknown"))
                    description = getattr(tool, "description", "No description")
                    print(f"{i}. {name}")
                    if description and description != "No description":
                        print(f"   {description}")
                print("-" * 50)
                print(f"Total: {len(tools)} tools")
            elif isinstance(tools, dict):
                for name, tool in tools.items():
                    description = getattr(tool, "description", "")
                    print(f"• {name}")
                    if description:
                        print(f"  {description}")
                print("-" * 50)
                print(f"Total: {len(tools)} tools")
            else:
                print(f"Unexpected format: {type(tools)}")
                print(tools)
    finally:
        # Cleanup to avoid the async generator error
        await cleanup_mcp_toolset()


async def get_tool_details(tool_name: str):
    """Get detailed information about a specific tool."""
    toolset = get_mcp_toolset()
    
    try:
        tools = await toolset.get_tools()
        
        if isinstance(tools, (list, tuple)):
            for tool in tools:
                if getattr(tool, "name", None) == tool_name:
                    print(f"\n🔧 Tool: {tool.name}")
                    print(f"Description: {getattr(tool, 'description', 'N/A')}")
                    print(f"Schema: {getattr(tool, 'input_schema', 'N/A')}")
                    return tool
        
        print(f"❌ Tool '{tool_name}' not found")
        return None
    finally:
        await cleanup_mcp_toolset()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--tool":
        # Get details for specific tool: python -m src.bitemate.tools.mcp_client --tool search_recipes
        tool_name = sys.argv[2] if len(sys.argv) > 2 else "search_recipes"
        asyncio.run(get_tool_details(tool_name))
    else:
        # List all tools
        asyncio.run(debug_list_tools())