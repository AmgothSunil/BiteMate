from __future__ import annotations

import sys
import traceback
from typing import Optional

from dotenv import load_dotenv

from google.genai import types as genai_types
from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini

from src.bitemate.core.exception import AppException
from src.bitemate.core.logger import setup_logger
from src.bitemate.utils.params import load_params
from src.bitemate.utils.prompt import PromptManager

# Load environment for local/dev. In production use a secrets manager instead.
load_dotenv()

# Defaults (used if config file is missing or keys absent)
DEFAULT_CONFIG_PATH = "src/bitemate/config/params.yaml"
DEFAULT_PROMPT_PATH = "src/bitemate/prompts/orchestrator_prompt.txt"
DEFAULT_LOGFILE = "router_agent.log"
DEFAULT_MODEL = "gemini-2.0-flash"


def create_router_agent(
    *,
    config_path: str = DEFAULT_CONFIG_PATH,
    prompt_path: str = DEFAULT_PROMPT_PATH,
    prompt_manager: Optional[PromptManager] = None,
    logger = None,
    model_name: Optional[str] = None,
    retry_options: Optional[genai_types.HttpRetryOptions] = None,
) -> Agent:
    """
    Factory that builds and returns a lightweight Intent Router Agent.

    Behavior:
      - Inspects user input and returns one of: UPDATE_PROFILE, GENERATE_PLAN, FULL_FLOW.
      - The Agent is configured to output ONLY the uppercase keyword (no markdown). Caller must
        normalize/validate agent output.

    Args:
        config_path: Path to params.yaml containing router_agent configuration.
        prompt_path: Path to the prompt/instruction file for the router.
        prompt_manager: Optional PromptManager (injected for tests). If None, a new one is created.
        logger: Optional logger instance. If None, a logger is created using params or the default logfile.
        model_name: Optional model name override (takes precedence over config and default).
        retry_options: Optional genai HttpRetryOptions to pass into Gemini().

    Returns:
        google.adk.agents.Agent: configured IntentRouter agent.

    Raises:
        AppException: on any failure to load config, prompt, or create the agent.
    """
    try:
        # Prepare dependencies
        prompt_manager =PromptManager()

        # Load params (safe: load_params should raise its own errors if file is malformed)
        params = {}
        try:
            params = load_params(config_path) or {}
        except Exception as e:
            # Log but continue: we'll fall back to defaults if params can't be loaded.
            # In stricter setups you may want to fail-fast here.
            if logger:
                logger.warning("Could not load params from %s: %s. Falling back to defaults.", config_path, e)
            else:
                print(f"Warning: could not load params from {config_path}: {e}")

        router_cfg = params.get("router_agent", {}) if isinstance(params, dict) else {}
        cfg_file_path = router_cfg.get("file_path", DEFAULT_LOGFILE)
        cfg_model_name = router_cfg.get("model_name", DEFAULT_MODEL)

        # Setup logger if not injected
        logger = logger or setup_logger(name="RouterAgent", log_file_name=cfg_file_path)
        logger.debug("Initializing router agent factory (config_path=%s, prompt_path=%s)", config_path, prompt_path)

        # Determine final model name (explicit arg > config > default)
        final_model_name = model_name or cfg_model_name or DEFAULT_MODEL
        logger.debug("Using Gemini model: %s", final_model_name)

        # Load instruction prompt and validate
        instruction = prompt_manager.load_prompt(prompt_path)
        if not instruction or not instruction.strip():
            msg = f"Router prompt at '{prompt_path}' is empty or could not be loaded."
            logger.error(msg)
            raise AppException(msg, sys)

        # Build Gemini model instance (include retry options if provided)
        try:
            model = Gemini(model=final_model_name, retry_options=retry_options) if retry_options else Gemini(model=final_model_name)
        except Exception as exc:
            tb = traceback.format_exc()
            logger.exception("Failed to instantiate Gemini model '%s': %s\n%s", final_model_name, exc, tb)
            raise AppException(f"Gemini model instantiation failed: {exc}", sys) from exc

        # Create Agent
        agent = Agent(
            name="IntentRouter",
            model=model,
            description="Routes the user request to the correct BiteMate workflow (profile/plan/full).",
            instruction=instruction,
        )

        logger.info("Router agent created successfully using model: %s", final_model_name)
        return agent

    except AppException:
        # Preserve AppException semantics
        raise
    except Exception as exc:
        tb = traceback.format_exc()
        if 'logger' in locals() and logger:
            logger.exception("Error creating router agent: %s\n%s", exc, tb)
        else:
            print("Error creating router agent:", exc, tb)
        raise AppException(f"Router Agent Creation Failed: {exc}", sys) from exc
