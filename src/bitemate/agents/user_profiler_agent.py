import sys
import os
import asyncio
import inspect
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
# --- Google ADK Imports ---
from google.genai import types
from google.adk.agents import Agent, SequentialAgent
from google.adk.models.google_llm import Gemini
from google.adk.tools import FunctionTool, google_search
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService
# --- Internal Core Imports ---
from src.bitemate.utils.params import load_params
from src.bitemate.core.logger import setup_logger
from src.bitemate.core.exception import AppException
from src.bitemate.utils.prompt import PromptManager
from src.bitemate.utils.run_sessions import SessionManager
# --- Tool Imports (Directly from your MCP module) ---
from src.bitemate.tools.bitemate_tools import (
    save_user_preference,
    recall_user_profile,
    search_nutrition_info,
    search_usda_database,
    search_scientific_papers
)
# Load Environment Variables
load_dotenv()
os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")
# Constants
CONFIG_REL_PATH = "src/bitemate/config/params.yaml"
# Prompt Manager + Services
prompt_manager = PromptManager()
session_service = InMemorySessionService()
memory_service = InMemoryMemoryService()
# IMPORTANT: Pass the same session_service instance to SessionManager
# so that both Runner and SessionManager use the same session store
session_manager = SessionManager(session_service=session_service)
# ========== FIX #1: DEFINE RETRY CONFIG AS AN OBJECT ==========
RETRY_CONFIG = types.HttpRetryOptions(
    initial_delay=1,        # Start with 1 second delay
    attempts=5,             # Retry up to 5 times
    max_delay=60,           # Cap delay at 60 seconds
    exp_base=2,             # Exponential backoff: delay *= 2 each attempt
    jitter=0.2,             # Add 20% random jitter to prevent thundering herd
    http_status_codes=[429, 500, 503, 504]  # Retry on these HTTP errors
)
# # ---------- Helper: Robust FunctionTool Creator ----------
# def _create_function_tool(func, name: Optional[str] = None, description: Optional[str] = None):
#     """
#     Flexible creator for ADK function tools:
#       - tries FunctionTool.from_function(func)
#       - tries common constructors like FunctionTool(func=...) or FunctionTool(name=..., func=...)
#       - falls back to a lightweight adapter object exposing `.name`, `.description`,
#         and callable behavior via __call__ and run().
#     This helps compatibility across google.adk versions.
#     """
#     # 1) Try convenience factory if present
#     try:
#         if hasattr(FunctionTool, "from_function") and inspect.isfunction(getattr(FunctionTool, "from_function")):
#             try:
#                 return FunctionTool.from_function(func)
#             except Exception:
#                 # Fall-through to other attempts
#                 pass
#     except Exception:
#         pass
#     # 2) Try common constructor signatures
#     try:
#         sig = inspect.signature(FunctionTool)
#         params = sig.parameters
#         # Common variant: FunctionTool(func=...)
#         if "func" in params:
#             try:
#                 return FunctionTool(func=func)
#             except Exception:
#                 pass
#         # Common variant: FunctionTool(name=..., func=...)
#         if "name" in params and ("func" in params or "fn" in params):
#             kwargs = {}
#             kwargs["name"] = name or func.__name__
#             if "func" in params:
#                 kwargs["func"] = func
#             elif "fn" in params:
#                 kwargs["fn"] = func
#             try:
#                 return FunctionTool(**kwargs)
#             except Exception:
#                 pass
#     except Exception:
#         # signature() may fail on some builtins; ignore and continue
#         pass
#     # 3) Fallback adapter
#     class _SimpleTool:
#         def __init__(self, fn, tool_name=None, desc=None):
#             self.fn = fn
#             self.name = tool_name or fn.__name__
#             self.description = desc or (fn.__doc__ or "")
#         def __call__(self, *args, **kwargs):
#             return self.fn(*args, **kwargs)
#         def run(self, *args, **kwargs):
#             return self.fn(*args, **kwargs)
#         def __repr__(self):
#             return f"<_SimpleTool name={self.name}>"
#     return _SimpleTool(func, tool_name=(name or func.__name__), desc=description or func.__doc__)
# ---------- Pipeline Class ----------
class UserProfilingPipeline:
    """
    Orchestrates the lifecycle of User Profiling using Sequential Agents.
    """
    def __init__(self, config_path: str = CONFIG_REL_PATH):
        try:
            # 1. Load Configuration
            self.params = load_params(config_path)
            self.agent_config = self.params.get("user_profiler_agent", {})
            # 2. Setup Logger
            log_file = self.agent_config.get("file_path", "user_profiling.log")
            self.logger = setup_logger(name="UserProfilingPipeline", log_file_name=log_file)
            # 3. Model Configuration
            self.model_name = self.agent_config.get("model_name", "gemini-2.0-flash-exp")
            # 4. Wrap MCP Functions as ADK Tools using the robust helper
            self.profiling_tools = [
                save_user_preference,
                recall_user_profile,
            ]
            self.calculation_tools = [
                search_nutrition_info,
                search_usda_database,
                search_scientific_papers,
                # google_search  # native ADK-provided tool
            ]
            self.logger.info("UserProfilingPipeline initialized successfully.")
        except Exception as e:
            msg = f"Failed to initialize UserProfilingPipeline: {str(e)}"
            if hasattr(self, 'logger'):
                self.logger.critical(msg)
            else:
                print(f"CRITICAL: {msg}")
            raise AppException(msg, sys)
    # ========== FIX #2: USE RETRY_CONFIG OBJECT IN AGENTS ==========
    def _create_profiler_agent(self) -> Agent:
        instruction = prompt_manager.load_prompt("src/bitemate/prompts/user_profiler_prompts/create_profiler_prompt.txt")
        return Agent(
            name="UserProfiler",
            model=Gemini(
                model=self.model_name, 
                retry_options=RETRY_CONFIG  # ✅ Pass the object, not a function
            ),
            description="Extracts bio-data and saves it to the vector database.",
            instruction=instruction,
            tools=self.profiling_tools,
            output_key="extracted_profile_json"
        )
    def _create_calculator_agent(self) -> Agent:
        instruction = prompt_manager.load_prompt("src/bitemate/prompts/user_profiler_prompts/create_calculator_prompt.txt")
        return Agent(
            name="NutritionCalculator",
            model=Gemini(
                model=self.model_name,
                retry_options=RETRY_CONFIG  # ✅ Pass the object, not a function
            ),
            description="Calculates nutritional needs based on extracted profile.",
            instruction=instruction,
            tools=self.calculation_tools,
            output_key="calculated_macros"
        )
    def _create_updater_agent(self) -> Agent:
        instruction = prompt_manager.load_prompt("src/bitemate/prompts/user_profiler_prompts/create_updater_prompt.txt")
        return Agent(
            name="ProfileUpdater",
            model=Gemini(
                model=self.model_name,
                retry_options=RETRY_CONFIG  # ✅ Pass the object, not a function
            ),
            description="Saves the final calculated goals back to memory.",
            instruction=instruction,
            tools=self.profiling_tools
        )
    # ---------------- Run Pipeline ----------------
    def run_pipeline(self, user_id: str, user_input: str, session_id: str = "default") -> Any:
        """
        Executes the sequential profiling chain and returns the final response(s).
        """
        try:
            self.logger.info(f"Starting Profiling Pipeline for User: {user_id}")
            # 1. Instantiate Agents
            profiler = self._create_profiler_agent()
            calculator = self._create_calculator_agent()
            updater = self._create_updater_agent()
            # 2. Define Sequential Chain
            root_agent = SequentialAgent(
                name="UserProfilingChain",
                sub_agents=[profiler, calculator, updater]
            )
            # 3. Build Runner (without initial_context - that's not supported)
            # Context variables are passed via session state in session_manager.run_session()
            runner = Runner(
                app_name="agents",
                agent=root_agent,
                session_service=session_service,
                memory_service=memory_service
            )
            
            # 4. Run via session manager with context variables
            # These will be stored in session state and available for template substitution
            # in agent prompts using {variable} syntax
            self.logger.info("Executing Sequential Chain...")
            responses = asyncio.run(
                session_manager.run_session(
                    runner_instance=runner,
                    user_queries=user_input,
                    session_id=session_id,
                    context_variables={"user_id": user_id, "user_input": user_input}
                )
            )
            self.logger.info("Pipeline execution completed successfully.")
            return responses
        except Exception as e:
            self.logger.error(f"Error during pipeline execution: {e}")
            raise AppException(f"User Profiling Failed: {e}", sys)
# ---------------- Example Usage ----------------
if __name__ == "__main__":
    try:
        pipeline = UserProfilingPipeline()
        mock_user_id = "test_user_alpha"
        mock_input = (
            "I want an recipe for pasta, i want to try it today give full process of making it"
        )
        result = pipeline.run_pipeline(user_id=mock_user_id, user_input=mock_input, session_id="test_session_1")
        print("\n\n✅ FINAL PIPELINE RESPONSE:")
        print(result)
    except Exception as err:
        print(f"\n❌ SETUP FAILED: {err}")