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
from src.bitemate.utils.callbacks import clean_after_model_callback

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
    - Creates Agent instances with MCP tools for external API access
    - Integrates all 7 MCP tools: Pinecone, PostgreSQL, Nutritionix, Spoonacular, USDA

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
            self.model_name: str = self.agent_config.get("model_name", "gemini-2.0-flash")
            self._validate_model_name(self.model_name)

            # Load prompts once (fail fast if missing)
            self.meal_instructions = self._load_prompt_checked("src/bitemate/prompts/generate_meal_prompt.txt")
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
        Lazy-loading wrapper for the MCP toolset.

        This provides access to all 7 MCP tools:
        1. save_user_preference (Pinecone)
        2. get_recent_conversation (Chat history)
        3. save_information_to_postgre (PostgreSQL)
        4. recall_user_profile (Pinecone)
        5. search_nutrition_info (Nutritionix API)
        6. search_recipes (Spoonacular API)
        7. search_usda_database (USDA Food Database)

        Using lazy loading avoids early failures when tools depend on network/DB 
        that isn't available in unit tests.
        """
        if self._toolset is None:
            try:
                LOGGER.debug("Fetching MCP toolset using get_mcp_toolset()")
                self._toolset = get_mcp_toolset()
                LOGGER.info("✅ MCP toolset loaded successfully with 7 tools")
            except Exception as exc:
                LOGGER.exception("❌ Failed to load MCP toolset: %s", exc)
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
            extra_tools: Additional tools (beyond standard MCP toolset) to provide.

        Returns:
            An Agent instance configured with Gemini and MCP tools.
        """
        LOGGER.debug("Creating agent '%s' with output_key='%s'", name, output_key)
        try:
            model = self._create_gemini_model()
            
            # Get MCP toolset (all 7 tools)
            mcp_toolset = self.tools
            
            # Combine MCP tools with any extras passed in
            tools_list = [mcp_toolset]
            if extra_tools:
                tools_list.extend(list(extra_tools))
                LOGGER.debug("Agent '%s' configured with %d extra tools", name, len(extra_tools))
            
            agent = Agent(
                name=name,
                model=model,
                description=description,
                instruction=instruction,
                tools=tools_list,
                output_key=output_key,
                after_model_callback=clean_after_model_callback,
            )

            LOGGER.info("✅ Agent '%s' created successfully with MCP tools", name)
            return agent
        except Exception as exc:
            LOGGER.exception("❌ Error creating agent '%s': %s", name, exc)
            raise AppException(f"Agent Creation Failed: {exc}", sys) from exc

    # -----------------------
    # Public API
    # -----------------------
    def create_profiler_agent(self) -> Agent:
        """
        Create an Agent responsible for user profiling.
        
        This agent has access to:
        - recall_user_profile (retrieve user data from Pinecone)
        - save_user_preference (save preferences to Pinecone)
        - get_recent_conversation (fetch chat history)
        - search_nutrition_info (Nutritionix for nutrition calculations)
        - search_usda_database (USDA for food data)

        Returns:
            An Agent instance configured as the UnifiedProfileManager.
        """
        LOGGER.debug("Creating UnifiedProfileManager agent for user profiling")
        return self._create_agent(
            name="UnifiedProfileManager",
            instruction=self.user_profile_instructions,
            description="Handles profile extraction, nutrition calculation, and variety checks using MCP tools.",
            output_key="profiling_summary",
        )

    def create_meal_generator_agent(self) -> Agent:
        """
        Create an Agent responsible for meal generation.
        
        This agent has access to:
        - search_recipes (Spoonacular for recipe search)
        - search_nutrition_info (Nutritionix for nutrition data)
        - search_usda_database (USDA for ingredient info)
        - save_information_to_postgre (save meal plans to PostgreSQL)
        - recall_user_profile (access user preferences)

        Returns:
            An Agent instance configured as the UnifiedMealChef.
        """
        LOGGER.debug("Creating UnifiedMealChef agent for meal generation")
        return self._create_agent(
            name="UnifiedMealChef",
            instruction=self.meal_instructions,
            description="Generates recipes, cooking instructions, and day plans using MCP tools.",
            output_key="meal_plan_result",
        )

    def create_pipeline(self) -> tuple[Agent, Agent]:
        """
        Convenience method to create both agents at once.
        
        Returns:
            Tuple of (profiler_agent, meal_generator_agent)
        """
        LOGGER.info("Creating complete meal planning pipeline with both agents")
        profiler = self.create_profiler_agent()
        meal_gen = self.create_meal_generator_agent()
        LOGGER.info("✅ Pipeline created successfully with MCP tools integrated")
        return profiler, meal_gen


# Example usage for testing
if __name__ == "__main__":
    try:
        LOGGER.info("=" * 60)
        LOGGER.info("Testing MealPlannerPipeline with MCP Integration")
        LOGGER.info("=" * 60)
        
        pipeline = MealPlannerPipeline()
        
        # Create both agents
        profiler, meal_gen = pipeline.create_pipeline()
        
        print("\n✅ Pipeline initialized successfully!")
        print(f"\n📋 Profiler Agent: {profiler.name}")
        print(f"   Description: {profiler.description}")
        print(f"   Output Key: {profiler.output_key}")
        
        print(f"\n🍳 Meal Generator Agent: {meal_gen.name}")
        print(f"   Description: {meal_gen.description}")
        print(f"   Output Key: {meal_gen.output_key}")
        
        print("\n🔧 Both agents have access to all 7 MCP tools:")
        print("   1. save_user_preference (Pinecone)")
        print("   2. get_recent_conversation (Chat history)")
        print("   3. save_information_to_postgre (PostgreSQL)")
        print("   4. recall_user_profile (Pinecone)")
        print("   5. search_nutrition_info (Nutritionix)")
        print("   6. search_recipes (Spoonacular)")
        print("   7. search_usda_database (USDA)")
        
    except Exception as e:
        LOGGER.exception("Failed to initialize pipeline: %s", e)
        print(f"\n❌ Error: {e}")
        sys.exit(1)