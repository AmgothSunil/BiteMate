# --- UPDATE FILE: src/bitemate/tools/mcp_client.py ---

import os
import sys
from dotenv import load_dotenv

from google.adk.tools.mcp_tool.mcp_session_manager import (
    StdioServerParameters,
    StdioConnectionParams
)
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

load_dotenv()

# REMOVED: global _mcp_toolset_instance

def get_mcp_toolset() -> McpToolset:
    """
    Returns a NEW MCP Toolset instance.
    Avoids Singleton pattern to prevent lifecycle conflicts in SequentialAgents.
    """
    try:
        # We create a fresh toolset instance for every agent that needs it.
        toolset = McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command="python", 
                    # Force unbuffered output
                    args=["-u", "-m", "src.bitemate.tools.bitemate_tools"],
                    env=os.environ.copy()
                ),
                timeout=60
            )
        )
        # print(f"✅ New MCP Toolset created.") # Avoid printing here if called frequently
        return toolset
        
    except Exception as e:
        print(f"❌ Failed to create MCP Toolset: {e}")
        raise e