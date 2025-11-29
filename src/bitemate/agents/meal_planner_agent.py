import sys
import os
import asyncio
import inspect
import datetime
from typing import Any, List, Optional
from dotenv import load_dotenv
# from google.adk.tools.google_search_tool import google_search
# --- Google ADK Imports ---
from google.genai import types
from google.adk.agents import Agent, SequentialAgent
from google.adk.models.google_llm import Gemini
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService

# --- Internal Core Imports ---
from src.bitemate.utils.params import load_params
from src.bitemate.core.logger import setup_logger
from src.bitemate.core.exception import AppException
from src.bitemate.utils.prompt import PromptManager
from src.bitemate.utils.run_sessions import SessionManager

# --- Tool Imports ---
from src.bitemate.tools.bitemate_tools import (
    recall_user_profile, 
    save_generated_meal_plan,
    search_recipes,
    search_nutrition_info,
    search_usda_database,
)
from src.bitemate.db.pinecone_memory_db import UserProfileMemory

# Load Env
load_dotenv()
os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")

# Constants
CONFIG_REL_PATH = "src/bitemate/config/params.yaml"

# Services
session_service = InMemorySessionService()
memory_service = InMemoryMemoryService()
session_manager = SessionManager(session_service=session_service)
prompt_manager = PromptManager()

# Tool Instances
pinecone = UserProfileMemory()

# Retry Configuration
RETRY_CONFIG = types.HttpRetryOptions(
    initial_delay=1,
    attempts=5,
    max_delay=60,
    exp_base=2,
    jitter=0.2,
    http_status_codes=[429, 500, 503, 504]
)

# # ---------- Helper: Robust FunctionTool Creator ----------
# def _create_function_tool(func, name: Optional[str] = None, description: Optional[str] = None):
#     """Robustly converts a Python function/method into a Google ADK FunctionTool."""
#     # 1. Try standard factory
#     try:
#         if hasattr(FunctionTool, "from_function"):
#             return FunctionTool.from_function(func)
#     except Exception:
#         pass

#     # 2. Try constructor injection
#     try:
#         tool_name = name or getattr(func, "__name__", "tool")
#         tool_desc = description or getattr(func, "__doc__", "")
#         return FunctionTool(name=tool_name, fn=func, description=tool_desc)
#     except Exception:
#         pass

#     # 3. Fallback Wrapper with __name__ attribute
#     class _SimpleTool:
#         def __init__(self, fn, tool_name, desc):
#             self.fn = fn
#             self.name = tool_name
#             self.__name__ = tool_name  # ← FIX: Add __name__ attribute
#             self.description = desc
#         def __call__(self, *args, **kwargs):
#             return self.fn(*args, **kwargs)
#         def run(self, *args, **kwargs):
#             return self.fn(*args, **kwargs)
#         def __repr__(self):
#             return f"<_SimpleTool name={self.name}>"
            
#     return _SimpleTool(func, name or getattr(func, "__name__", "tool"), description or getattr(func, "__doc__", ""))


class MealPlannerPipeline:
    """Orchestrates meal planning using Sequential Agents."""
    
    def __init__(self, config_path: str = CONFIG_REL_PATH):
        try:
            # 1. Load Config
            self.params = load_params(config_path)
            self.agent_config = self.params.get("meal_planner_agent", {})
            
            # 2. Setup Logger
            log_file = self.agent_config.get("file_path", "meal_planner_agent.log")
            self.logger = setup_logger(name="MealPlannerPipeline", log_file_name=log_file)
            
            # 3. Model Configuration
            # IMPORTANT: Using same default as user_profiler_agent.py for consistency
            # gemini-2.0-flash-exp supports function calling with FunctionTool
            # Config says gemini-2.5-flash but user_profiler defaults to 2.0-flash-exp
            self.model_name = self.agent_config.get("model_name", "gemini-2.5-flash")
            
            # # 4. Prepare Tools
            # self.research_tools = [
            #     _create_function_tool(search_recipes, name="search_recipes"),
            #     _create_function_tool(search_nutrition_info, name="search_nutrition_info"),
            #     _create_function_tool(search_usda_database, name="search_usda_database"),
            #     google_search
            # ]
            
            self.planning_tools = [
                save_generated_meal_plan,
                recall_user_profile,
                
            ]
            
            self.audit_tools = [
                recall_user_profile,
                
            ]
            
            self.logger.info("MealPlannerPipeline initialized successfully.")
            
        except Exception as e:
            msg = f"Failed to initialize MealPlannerPipeline: {str(e)}"
            if hasattr(self, 'logger'):
                self.logger.critical(msg)
            else:
                print(f"CRITICAL: {msg}")
            raise AppException(msg, sys)

    def _create_recipe_finder_agent(self) -> Agent:
        try:
            instruction = prompt_manager.load_prompt("src/bitemate/prompts/meal_planner_prompts/recipe_finder_prompt.txt")
        except Exception:
            self.logger.warning("Prompt file missing, using default.")
            instruction = """Find recipes based on nutritional needs: {user_nutritional_needs}.
            Use the recall_user_profile tool to fetch the user's full profile data first."""

        return Agent(
            name="RecipeFinderAgent",
            model=Gemini(model=self.model_name, retry_options=RETRY_CONFIG),
            description="Finds recipes matching dietary constraints.",
            instruction=instruction,
            tools=self.audit_tools,
            output_key="found_recipes"
        )

    def _create_daily_meal_planner_agent(self) -> Agent:
        try:
            instruction = prompt_manager.load_prompt("src/bitemate/prompts/meal_planner_prompts/daily_meal_planner_prompt.txt")
        except Exception:
            instruction = "Plan meals based on found recipes: {found_recipes}."

        return Agent(
            name="DailyMealPlanner",
            model=Gemini(model=self.model_name, retry_options=RETRY_CONFIG),
            description="Schedules meals and saves the plan to DB.",
            instruction=instruction,
            tools=self.planning_tools,
            output_key="daily_meal_plan"
        )

    def _create_meal_generator_agent(self) -> Agent:
        try:
            instruction = prompt_manager.load_prompt("src/bitemate/prompts/meal_planner_prompts/meal_preparation_prompt.txt")
        except Exception:
            instruction = "Generate cooking instructions for: {daily_meal_plan}."

        return Agent(
            name="MealGeneratingAgent",
            model=Gemini(model=self.model_name, retry_options=RETRY_CONFIG),
            description="Generates step-by-step cooking instructions.",
            instruction=instruction,
            tools=self.planning_tools,
            output_key="cooking_instructions"
        )

    def _create_variety_agent(self) -> Agent:
        try:
            instruction = prompt_manager.load_prompt("src/bitemate/prompts/meal_planner_prompts/variety_check.txt")
        except Exception:
            instruction = "Check for variety and finalize response."

        return Agent(
            name="UserVarietyAgent",
            model=Gemini(model=self.model_name, retry_options=RETRY_CONFIG),
            description="Ensures nutritional balance and variety.",
            instruction=instruction,
            tools=self.audit_tools
        )

    def run_pipeline(self, user_id: str, user_input: str, 
                     user_nutritional_needs: str = "Standard balanced diet", 
                     session_id: str = "default") -> Any:
        """Executes the sequential meal planning chain."""
        try:
            self.logger.info(f"Starting Meal Planning Pipeline for User: {user_id}")
            
            # 1. Instantiate Agents
            recipe_finder = self._create_recipe_finder_agent()
            meal_planner = self._create_daily_meal_planner_agent()
            meal_generator = self._create_meal_generator_agent()
            variety_agent = self._create_variety_agent()
            
            # 2. Define Sequential Chain
            root_agent = SequentialAgent(
                name="MealPlanningChain",
                sub_agents=[recipe_finder, meal_planner, meal_generator, variety_agent]
            )
            
            # 3. Build Runner
            runner = Runner(
                app_name="agents",
                agent=root_agent,
                session_service=session_service,
                memory_service=memory_service
            )
            
            # 4. Context Variables
            context_vars = {
                "user_id": user_id,
                "user_input": user_input,
                "user_nutritional_needs": user_nutritional_needs,
                "current_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            self.logger.info("Executing Sequential Chain...")
            
            # 5. Run via Session Manager
            responses = asyncio.run(
                session_manager.run_session(
                    runner_instance=runner,
                    user_queries=user_input,
                    session_id=session_id,
                    context_variables=context_vars
                )
            )
            
            self.logger.info("Pipeline execution completed successfully.")
            return responses
            
        except Exception as e:
            self.logger.error(f"Error during meal planning pipeline execution: {e}")
            raise AppException(f"Meal Planning Failed: {e}", sys)


# ---------------- Example Usage ----------------
if __name__ == "__main__":
    try:
        pipeline = MealPlannerPipeline()
        
        # IMPORTANT: Use the same user_id from user_profiler_agent!
        mock_user_id = "test_user_alpha"  # ← Same as your user profiler
        mock_input = (
            "I need a healthy lunch plan for today. "
            "I'm vegetarian and trying to lose weight."
        )
        
        # The meal planner will fetch the user's profile from DB using recall_user_profile
        result = pipeline.run_pipeline(
            user_id=mock_user_id,
            user_input=mock_input,
            session_id="test_meal_session_1"
        )
        
        print("\n\n✅ FINAL MEAL PLANNING RESPONSE:")
        print(result)
        
    except Exception as err:
        print(f"\n❌ SETUP FAILED: {err}")
        import traceback
        traceback.print_exc()