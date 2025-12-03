import os
import sys
import asyncio
from dotenv import load_dotenv

from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, SseConnectionParams

from src.bitemate.utils.params import load_params
from src.bitemate.core.logger import setup_logger
from src.bitemate.core.exception import AppException

CONFIG_REL_PATH = "src/bitemate/config/params.yaml"

params = load_params(CONFIG_REL_PATH)
mcp_client_params = params.get("mcp_client", {})
file_path = mcp_client_params.get("file_path", "mcp_client.log")

logger = setup_logger(name="MCPClient", log_file_name=file_path)

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

        logger.info("Creating MCP Toolset...")
        _mcp_toolset_instance = McpToolset(
            connection_params=SseConnectionParams(
                url=os.getenv("MCP_SERVER_URL", "http://localhost:8000/sse"),
                timeout=60,
            )
        )

        logger.info("MCP Toolset created successfully.")
        return _mcp_toolset_instance
    except Exception as e:
        logger.error(f"❌ Failed to create MCP Toolset: {e}")
        raise AppException(e, sys)
