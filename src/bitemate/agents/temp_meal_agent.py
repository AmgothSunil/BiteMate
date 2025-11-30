import sys
import os
import datetime
from typing import Optional
from dotenv import load_dotenv

# --- Google ADK Imports ---
from google.genai import types
from google.adk.agents import Agent, SequentialAgent
from google.adk.models.google_llm import Gemini

# --- Internal Core Imports ---
from src.bitemate.utils.params import load_params
from src.bitemate.core.logger import setup_logger
from src.bitemate.core.exception import AppException
from src.bitemate.utils.prompt import PromptManager

# --- Tool Imports ---
from src.bitemate.tools.bitemate_tools import (
    recall_user_profile,
    save_generated_meal_plan,
    search_recipes,
    search_nutrition_info,
    search_usda_database,
)

# Load Env
load_dotenv()
os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")

# Constants
CONFIG_REL_PATH = "src/bitemate/config/params.yaml"

# Prompt Manager
prompt_manager = PromptManager()

# Retry Configuration
RETRY_CONFIG = types.HttpRetryOptions(
    initial_delay=1,
    attempts=5,
    max_delay=60,
    exp_base=2,
    jitter=0.2,
    http_status_codes=[429, 500, 503, 504]
)


class MealPlannerPipeline:
    """
    Orchestrates meal planning using Sequential Agents.
    This class ONLY defines the agent configuration - execution happens in the orchestrator.
    
    Agent Flow:
    1. RecipeFinderAgent: Recalls profile & finds recipes → outputs found_recipes
    2. DailyMealPlanner: Creates full day plan & saves → outputs daily_meal_plan
    3. MealGeneratingAgent: Generates cooking instructions → outputs cooking_instructions
    4. UserVarietyAgent: Checks variety & provides final response
    """
    
    def __init__(self, config_path: str = CONFIG_REL_PATH):
        try:
            # 1. Load Config
            self.params = load_params(config_path)
            self.agent_config = self.params.get("meal_planner_agent", {})
            
            # 2. Setup Logger
            log_file = self.agent_config.get("file_path", "meal_planner_agent.log")
            self.logger = setup_logger(name="MealPlannerPipeline", log_file_name=log_file)
            
            # 3. Model Configuration
            self.model_name = self.agent_config.get("model_name", "gemini-2.5-flash")
            
            # 4. Prepare Tools per Agent
            # Recipe Finder needs profile recall + search tools
            self.recipe_finder_tools = [
                recall_user_profile,
                search_recipes,
                search_nutrition_info,
                search_usda_database,
            ]
            
            # Daily Planner needs profile recall + save meal plan
            self.daily_planner_tools = [
                recall_user_profile,
                save_generated_meal_plan,
            ]
            
            # Meal Generator only needs profile recall
            self.meal_generator_tools = [
                recall_user_profile,
            ]
            
            # Variety Agent only needs profile recall
            self.variety_tools = [
                recall_user_profile,
            ]
            
            self.logger.info("MealPlannerPipeline initialized successfully.")
            
        except Exception as e:
            msg = f"Failed to initialize MealPlannerPipeline: {str( e)}"
            if hasattr(self, 'logger'):
                self.logger.critical(msg)
            else:
                print(f"CRITICAL: {msg}")
            raise AppException(msg, sys)

    def _create_recipe_finder_agent(self) -> Agent:
        """
        Agent 1: Recalls user profile and finds suitable recipes.
        Input: {user_input}, {current_time}
        Output: found_recipes
        """
        try:
            instruction = prompt_manager.load_prompt(
                "src/bitemate/prompts/meal_planner_prompts/recipe_finder_prompt.txt"
            )
        except Exception:
            self.logger.warning("Prompt file missing, using default.")
            instruction = """Find recipes based on user profile. 
            Use the recall_user_profile tool first to fetch the user's full profile data."""

        return Agent(
            name="RecipeFinderAgent",
            model=Gemini(model=self.model_name, retry_options=RETRY_CONFIG),
            description="Finds recipes matching dietary constraints and user preferences.",
            instruction=instruction,
            tools=self.recipe_finder_tools,
            output_key="found_recipes"
        )

    def _create_daily_meal_planner_agent(self) -> Agent:
        """
        Agent 2: Creates full day meal plan (breakfast, lunch, dinner) from found recipes.
        Input: {found_recipes}, {user_input}, {current_time}
        Output: daily_meal_plan
        """
        try:
            instruction = prompt_manager.load_prompt(
                "src/bitemate/prompts/meal_planner_prompts/daily_meal_planner_prompt.txt"
            )
        except Exception:
            instruction = "Plan meals based on found recipes: {found_recipes}."

        return Agent(
            name="DailyMealPlanner",
            model=Gemini(model=self.model_name, retry_options=RETRY_CONFIG),
            description="Schedules meals for the full day and saves the plan to DB.",
            instruction=instruction,
            tools=self.daily_planner_tools,
            output_key="daily_meal_plan"
        )

    def _create_meal_generator_agent(self) -> Agent:
        """
        Agent 3: Generates detailed cooking instructions from daily meal plan.
        Input: {daily_meal_plan}
        Output: cooking_instructions
        """
        try:
            instruction = prompt_manager.load_prompt(
                "src/bitemate/prompts/meal_planner_prompts/meal_preparation_prompt.txt"
            )
        except Exception:
            instruction = "Generate cooking instructions for: {daily_meal_plan}."

        return Agent(
            name="MealGeneratingAgent",
            model=Gemini(model=self.model_name, retry_options=RETRY_CONFIG),
            description="Generates step-by-step cooking instructions.",
            instruction=instruction,
            tools=self.meal_generator_tools,
            output_key="cooking_instructions"
        )

    def _create_variety_agent(self) -> Agent:
        """
        Agent 4: Checks variety and provides final encouraging response.
        Input: {cooking_instructions}
        Output: None (final agent)
        """
        try:
            instruction = prompt_manager.load_prompt(
                "src/bitemate/prompts/meal_planner_prompts/variety_check.txt"
            )
        except Exception:
            instruction = "Check for variety and finalize response."

        return Agent(
            name="UserVarietyAgent",
            model=Gemini(model=self.model_name, retry_options=RETRY_CONFIG),
            description="Ensures nutritional balance and variety.",
            instruction=instruction,
            tools=self.variety_tools
        )

    def create_sequential_agent(self) -> SequentialAgent:
        """
        Creates and returns the complete sequential agent chain.
        This method is called by the orchestrator to build the pipeline.
        
        Returns:
            SequentialAgent: The configured sequential agent chain
        """
        try:
            self.logger.info("Building Meal Planning Sequential Agent Chain...")
            
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
            
            self.logger.info("Meal Planning Sequential Agent Chain created successfully.")
            return root_agent
            
        except Exception as e:
            self.logger.error(f"Error creating sequential agent: {e}")
            raise AppException(f"Agent Creation Failed: {e}", sys)


#---------------- Example Usage (for testing agent creation only) ----------------
if __name__ == "__main__":
    try:
        pipeline = MealPlannerPipeline()
        agent_chain = pipeline.create_sequential_agent()
        print(f"✅ Meal Planning Agent Chain Created: {agent_chain.name}")
        print(f"   Sub-agents: {[agent.name for agent in agent_chain.sub_agents]}")
    except Exception as err:
        print(f"\n❌ SETUP FAILED: {err}")