# src/bitemate/pipeline/meal_planner_pipeline.py
from __future__ import annotations

import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from dotenv import load_dotenv

# --- Google ADK / genai imports ---
from google.genai import types as genai_types
from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini

# --- Internal imports (adjust paths as needed) ---
from src.bitemate.core.exception import AppException
from src.bitemate.core.logger import setup_logger
from src.bitemate.tools.mcp_client import get_mcp_toolset
from src.bitemate.utils.params import load_params
from src.bitemate.utils.prompt import PromptManager

# Load env variables from .env into os.environ (safe for local/dev; in prod use a secrets manager)
load_dotenv()

# Module-level logger. setup_logger returns a configured logging.Logger instance.
LOGGER = setup_logger(name="MealPlannerPipeline", log_file_name="meal_planner.log")


@dataclass
class RetryConfigSpec:
    """Simple wrapper for retry options so it's easier to validate / test."""
    initial_delay: float = 1.0
    attempts: int = 3
    max_delay: float = 30.0
    exp_base: float = 2.0
    jitter: float = 0.2
    http_status_codes: Sequence[int] = (429, 500, 503, 504)

    def to_genai(self) -> genai_types.HttpRetryOptions:
        """Convert to the Google genai types.HttpRetryOptions object expected by Gemini."""
        return genai_types.HttpRetryOptions(
            initial_delay=self.initial_delay,
            attempts=self.attempts,
            max_delay=self.max_delay,
            exp_base=self.exp_base,
            jitter=self.jitter,
            http_status_codes=list(self.http_status_codes),
        )


class MealPlannerPipeline:
    """
    MealPlannerPipeline coordinates the creation of Agents for user profiling and meal generation.

    Key features:
    - Loads configuration (yaml) using load_params
    - Loads prompts via PromptManager
    - Configures Gemini LLM with retry options
    - Creates Agent instances with clear responsibilities and tool access

    This class is designed for production:
    - dependency injection-friendly (prompts, params, toolset can be passed in)
    - explicit validation with helpful error messages
    - thorough logging including tracebacks
    """

    DEFAULT_CONFIG_PATH = "src/bitemate/config/params.yaml"

    def __init__(
        self,
        config_path: Optional[str] = None,
        prompt_manager: Optional[PromptManager] = None,
        toolset: Optional[Any] = None,
        retry_spec: Optional[RetryConfigSpec] = None,
        env_api_key_name: str = "GOOGLE_API_KEY",
    ) -> None:
        """
        Initialize the pipeline.

        Args:
            config_path: Path to the YAML parameter file.
            prompt_manager: Optional PromptManager instance (injected for easier testing).
            toolset: Optional toolset returned by get_mcp_toolset (injected for testing).
            retry_spec: Optional RetryConfigSpec to configure the LLM retry behavior.
            env_api_key_name: Name of environment variable for API key.
        """
        self.config_path = config_path or self.DEFAULT_CONFIG_PATH
        self.prompt_manager = prompt_manager or PromptManager()
        self.retry_spec = retry_spec or RetryConfigSpec()
        self._toolset = toolset  # may be None; lazily loaded
        self.env_api_key_name = env_api_key_name

        try:
            LOGGER.info("Initializing MealPlannerPipeline with config_path=%s", self.config_path)
            self._validate_and_setup_env()
            self.params = load_params(self.config_path)
            self.agent_config: Dict[str, Any] = self.params.get("meal_planner_agent", {})
            self.model_name: str = self.agent_config.get("model_name", "gemini-1.5-flash")
            self._validate_model_name(self.model_name)

            # Load prompts once (fail fast if missing)
            self.meal_instructions = self._load_prompt_checked("src/bitemate/prompts/meal_prompt_conso.txt")
            self.user_profile_instructions = self._load_prompt_checked("src/bitemate/prompts/user_profile_prompt.txt")

            LOGGER.info("MealPlannerPipeline initialized successfully using model: %s", self.model_name)

        except Exception as exc:  # broad except to convert into AppException with traceback
            tb = traceback.format_exc()
            LOGGER.error("Failed to initialize MealPlannerPipeline: %s\n%s", exc, tb)
            raise AppException(f"Init Failed: {exc}", sys) from exc

    # -----------------------
    # Internal helpers
    # -----------------------
    def _validate_and_setup_env(self) -> None:
        """Ensure required environment variables exist and set them in os.environ if needed."""
        api_key = os.getenv(self.env_api_key_name)
        if not api_key:
            # In production you might raise or integrate with a secrets manager
            msg = f"Missing required environment variable: {self.env_api_key_name}"
            LOGGER.error(msg)
            raise AppException(msg, sys)
        # Ensure env var appears in os.environ (load_dotenv already did this, but be explicit)
        os.environ[self.env_api_key_name] = api_key
        LOGGER.debug("Environment variable %s found and set.", self.env_api_key_name)

    def _validate_model_name(self, model_name: str) -> None:
        """Basic validation for model_name — keep this guard so catastrophic typos are caught early."""
        if not isinstance(model_name, str) or not model_name.strip():
            raise AppException("Invalid model_name in config (must be non-empty string).", sys)
        # Optionally: maintain an allow-list of supported model names and warn if unknown
        LOGGER.debug("Model name validated: %s", model_name)

    def _load_prompt_checked(self, prompt_path: str) -> str:
        """
        Load a prompt via the PromptManager and validate result.

        Raises AppException on missing file or empty prompt.
        """
        LOGGER.debug("Loading prompt from: %s", prompt_path)
        prompt_text = self.prompt_manager.load_prompt(prompt_path)
        if not prompt_text or not prompt_text.strip():
            raise AppException(f"Prompt at '{prompt_path}' is empty or could not be loaded.", sys)
        LOGGER.debug("Loaded prompt (length=%d) from %s", len(prompt_text), prompt_path)
        return prompt_text

    @property
    def tools(self) -> Any:
        """
        Lazy-loading wrapper for the toolset.

        Using lazy loading avoids early failures when tools depend on network/DB that isn't available in unit tests.
        """
        if self._toolset is None:
            try:
                LOGGER.debug("Fetching MCP toolset using get_mcp_toolset()")
                self._toolset = get_mcp_toolset()
                LOGGER.info("MCP toolset loaded successfully.")
            except Exception as exc:
                LOGGER.exception("Failed to load MCP toolset: %s", exc)
                raise AppException(f"Failed to load MCP toolset: {exc}", sys) from exc
        return self._toolset

    def _create_gemini_model(self) -> Gemini:
        """Create and return a configured Gemini model instance with retry options."""
        retry_options = self.retry_spec.to_genai()
        LOGGER.debug("Creating Gemini model with retry options: %s", self.retry_spec)
        try:
            model = Gemini(model=self.model_name, retry_options=retry_options)
            LOGGER.debug("Gemini model instance created: %s", self.model_name)
            return model
        except Exception as exc:
            LOGGER.exception("Failed to instantiate Gemini model: %s", exc)
            raise AppException(f"Gemini instantiation failed: {exc}", sys) from exc

    def _create_agent(
        self,
        name: str,
        instruction: str,
        description: str,
        output_key: str,
        extra_tools: Optional[Sequence[Any]] = None
    ) -> Agent:
        """
        Generic Agent factory to reduce duplication.

        Args:
            name: Name for the agent.
            instruction: Prompt/instruction text for the agent.
            description: Short description used for metadata/documentation.
            output_key: Key the agent writes its output to.
            extra_tools: Additional tools (beyond standard toolset) to provide.

        Returns:
            An Agent instance configured with Gemini.
        """
        LOGGER.debug("Creating agent '%s' with output_key='%s'", name, output_key)
        try:
            model = self._create_gemini_model()
            # Combine standard tools with any extras passed in
            tools_list = [self.tools]
            if extra_tools:
                tools_list.extend(list(extra_tools))
            agent = Agent(
                name=name,
                model=model,
                description=description,
                instruction=instruction,
                tools=tools_list,
                output_key=output_key,
            )
            LOGGER.info("Agent '%s' created successfully.", name)
            return agent
        except Exception as exc:
            LOGGER.exception("Error creating agent '%s': %s", name, exc)
            raise AppException(f"Agent Creation Failed: {exc}", sys) from exc

    # -----------------------
    # Public API
    # -----------------------
    def create_profiler_agent(self) -> Agent:
        """
        Create an Agent responsible for user profiling (profile extraction, nutrition calc, variety checks).

        Returns:
            An Agent instance configured as the UnifiedProfileManager.
        """
        return self._create_agent(
            name="UnifiedProfileManager",
            instruction=self.user_profile_instructions,
            description="Handles profile extraction, nutrition calculation, and variety checks.",
            output_key="profiling_summary",
        )

    def create_meal_generator_agent(self) -> Agent:
        """
        Create an Agent responsible for meal generation (recipes, cooking instructions, day plans).

        Returns:
            An Agent instance configured as the UnifiedMealChef.
        """
        return self._create_agent(
            name="UnifiedMealChef",
            instruction=self.meal_instructions,
            description="Generates recipes, cooking instructions, and day plans.",
            output_key="meal_plan_result",
        )


# -----------------------
# Example usage (module-level guard)
# -----------------------
if __name__ == "__main__":
    """
    This section demonstrates how to use MealPlannerPipeline in a script.
    For production you will import the class and call create_* functions where appropriate.
    """
    try:
        pipeline = MealPlannerPipeline()
        profiler_agent = pipeline.create_profiler_agent()
        meal_agent = pipeline.create_meal_generator_agent()
        LOGGER.info("Agents created: %s, %s", profiler_agent.name, meal_agent.name)
    except AppException as e:
        LOGGER.exception("Startup failed: %s", e)
        sys.exit(1)
