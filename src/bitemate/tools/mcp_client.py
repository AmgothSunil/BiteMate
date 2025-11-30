import os
import sys
from dotenv import load_dotenv

# Google ADK Imports - Corrected per documentation
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPServerParams,
    StdioServerParameters,
    StdioConnectionParams
)
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

load_dotenv()

_mcp_toolset_instance = None

def get_mcp_toolset() -> McpToolset:
    """
    Returns singleton MCP Toolset.
    
    IMPORTANT: Uses STDIO connection (recommended by Google ADK)
    instead of HTTP for better reliability and no server setup needed.
    
    Reference: google.adk.tools.mcp_tool documentation
    """
    global _mcp_toolset_instance
    
    if _mcp_toolset_instance is None:
        try:
            # ✅ OPTION 1: STDIO Connection (RECOMMENDED - No separate server needed)
            # This directly spawns the MCP server as a subprocess
            _mcp_toolset_instance = McpToolset(
                connection_params=StdioConnectionParams(
                    server_params=StdioServerParameters(
                        command="python",
                        args=["-m", "src.bitemate.tools.bitemate_tools"],
                        env=os.environ.copy()
                    ),
                    timeout=60  # Timeout in seconds
                )
            )
            print(f"✅ MCP Toolset singleton created (STDIO mode - embedded server)")
            
        except Exception as stdio_error:
            print(f"⚠️  STDIO connection failed: {stdio_error}")
            print("   Falling back to HTTP mode...")
            
            try:
                # ✅ OPTION 2: HTTP Connection (Fallback - requires server running)
                mcp_url = os.getenv("MCP_BASE_URL", "http://localhost:8000")
                timeout = int(os.getenv("MCP_TIMEOUT", "60"))
                
                _mcp_toolset_instance = McpToolset(
                    connection_params=StreamableHTTPServerParams(
                        url=mcp_url,
                        timeout=timeout
                    )
                )
                print(f"✅ MCP Toolset singleton created (HTTP mode): {mcp_url}")
                print("   ⚠️  Make sure MCP server is running:")
                print("       python -m src.bitemate.tools.bitemate_tools")
                
            except Exception as http_error:
                print(f"❌ Both STDIO and HTTP connections failed!")
                print(f"   STDIO error: {stdio_error}")
                print(f"   HTTP error: {http_error}")
                raise RuntimeError(
                    "Failed to establish MCP connection. Check that:\n"
                    "1. All dependencies are installed\n"
                    "2. GOOGLE_API_KEY is set in .env\n"
                    "3. Database connections are configured\n"
                    "4. For HTTP mode: MCP server is running on specified port"
                )
    
    return _mcp_toolset_instance


if __name__ == "__main__":
    # Test connection
    try:
        toolset = get_mcp_toolset()
        print(f"✅ Test successful: {toolset}")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        sys.exit(1)