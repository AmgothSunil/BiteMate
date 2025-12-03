# src/bitemate/utils/callbacks.py

from typing import Optional, Dict
import logging

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse
from google.genai import types as genai_types

from src.bitemate.utils.params import load_params
from src.bitemate.core.logger import setup_logger
from src.bitemate.core.exception import AppException

CONFIG_REL_PATH = "src/bitemate/config/params.yaml"

params = load_params(CONFIG_REL_PATH)
callbacks_params = params.get("callbacks", {})
file_path = callbacks_params.get("file_path", "callbacks.log")

logger = setup_logger(name="Callbacks", log_file_name=file_path)

# Cache the last good user-facing response per agent
_CACHED_RESPONSE: Dict[str, str] = {}
# Track if we just made a tool call (to know when to suppress "I saved" messages)
_JUST_CALLED_TOOL: Dict[str, bool] = {}

def clean_after_model_callback(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> Optional[LlmResponse]:
    """
    TEMPORARILY DISABLED - Callback that does nothing.
    
    This is to verify that the callback is not interfering with tool execution.
    Once tools are working, we can re-enable the smart logic.
    
    Return:
      - None -> Always use original response
    """
    
    # Log what we see for debugging
    agent_name = callback_context.agent_name
    
    try:
        content = getattr(llm_response, "content", None)
        if content and hasattr(content, "parts") and content.parts:
            first_part = content.parts[0]
            
            if hasattr(first_part, "function_call") and first_part.function_call:
                logger.info(f"[{agent_name}] 🔧 Tool call: {first_part.function_call.name}")
            elif hasattr(first_part, "text") and first_part.text:
                text_preview = first_part.text[:80].replace('\n', ' ')
                logger.info(f"[{agent_name}] 💬 Text: {text_preview}...")
    except Exception as e:
        logger.warning(f"[{agent_name}] Callback logging error: {e}")
    
    # ALWAYS return None - let everything pass through naturally
    return None
