import os
import sys
import asyncio
import datetime
from typing import Any
from dotenv import load_dotenv
from google.genai import types
from google.adk.agents import Agent, SequentialAgent
from google.adk.models.google_llm import Gemini
from google.adk.tools import google_search
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService

from src.bitemate.utils.params import load_params
from src.bitemate.core.logger import setup_logger
from src.bitemate.core.exception import AppException
from src.bitemate.tools.bitemate_tools import NutritionMealFetchTools
from src.bitemate.utils.run_sessions import SessionManager
from src.bitemate.db.pinecone_memory_db import PineconeMemory

load_dotenv()

os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")

CONFIG_REL_PATH = "src/bitemate/config/params.yaml"

# Load Configuration
params = load_params(CONFIG_REL_PATH)

# Shared services and tools
tools = NutritionMealFetchTools()
pinecone = PineconeMemory()

# Session and Memory Services
session_service = InMemorySessionService()
memory_service = InMemoryMemoryService()
# IMPORTANT: Pass the same session_service instance to SessionManager
# so that both Runner and SessionManager use the same session store
session_manager = SessionManager(session_service=session_service)

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
    Orchestrates the lifecycle of Meal Planning using Sequential Agents.
    """
    
    def __init__(self, config_path: str = CONFIG_REL_PATH):
        try:
            # 1. Load Configuration
            self.params = load_params(config_path)
            self.agent_config = self.params.get("meal_planner_agent", {})
            
            # 2. Setup Logger
            log_file = self.agent_config.get("file_path", "meal_planner_agent.log")
            self.logger = setup_logger(name="MealPlannerPipeline", log_file_name=log_file)
            
            # 3. Model Configuration
            self.model_name = self.agent_config.get("model_name", "gemini-2.5-flash")
            
            # 4. Tools reference
            self.tools = tools
            self.pinecone = pinecone
            
            self.logger.info("MealPlannerPipeline initialized successfully.")
            
        except Exception as e:
            msg = f"Failed to initialize MealPlannerPipeline: {str(e)}"
            if hasattr(self, 'logger'):
                self.logger.critical(msg)
            else:
                print(f"CRITICAL: {msg}")
            raise AppException(msg, sys)

    def _create_recipe_finder_agent(self) -> Agent:
        """Creates an agent for finding recipes based on user nutritional information."""
        try:
            self.logger.info("Initializing Recipe Finder Agent")
            
            find_recipe_agent = Agent(
                name="RecipeFinderAgent",
                model=Gemini(
                    model=self.model_name,
                    retry_options=RETRY_CONFIG
                ),
                description="An agent for finding recipes based on the user nutritional information",
                instruction="""Find best recipes based on the user nutritional needs.
                
                Use the user's nutritional information: {user_nutritional_needs} 
                for breakfast, lunch, dinner, snacks, etc.
                
                Search for recipes that match their dietary requirements and health conditions.
                Return a structured list of recipes with nutritional breakdown.""",
                tools=[google_search, self.tools.nutrinix_tool, self.tools.usda_food_tool],
                output_key="recipe_find"
            )
            
            self.logger.info("Successfully initialized Recipe Finder Agent")
            return find_recipe_agent
            
        except Exception as e:
            self.logger.error("Error occurred while creating recipe finder agent: %s", e)
            raise AppException(e, sys)

    def _create_daily_meal_planner_agent(self) -> Agent:
        """Creates an agent for daily meal planning."""
        try:
            self.logger.info("Initializing Daily Meal Planner Agent")
            
            daily_meal_planner = Agent(
                name="DailyMealPlanner",
                model=Gemini(
                    model=self.model_name,
                    retry_options=RETRY_CONFIG
                ),
                description="An Agent to plan daily meals like breakfast, lunch, dinner and snacks",
                instruction="""You are an intelligent agent that plans users' daily meal plan for breakfast, 
                lunch, dinner and snacks.
                
                Current time: {current_time}
                Available recipes: {recipe_find}
                User ID: {user_id}
                
                Generate meal plans ensuring variety. If the user asks for a specific period like 
                "meal plan for lunch", generate for lunch. If no mention, use the current time 
                and analyze the time to give the user a perfect meal according to their nutritional needs.
                
                Create a detailed meal plan like "You should have oats for breakfast with all the ingredients, etc."
                
                If you don't have user nutritional info, use the pinecone_memory_tool to query the user 
                profile from the database.
                
                Save the meal plan data in the database using pinecone_memory_tool.""",
                tools=[self.tools.pinecone_memory_tool, self.tools.nutrinix_tool, 
                       self.tools.usda_food_tool, self.tools.spoonacular_tool],
                output_key="meal_plan"
            )
            
            self.logger.info("Successfully initialized Daily Meal Planner Agent")
            return daily_meal_planner
            
        except Exception as e:
            self.logger.error("Error occurred while creating daily meal planner agent: %s", e)
            raise AppException(e, sys)

    def _create_meal_generator_agent(self) -> Agent:
        """Creates an agent for generating meal preparation steps."""
        try:
            self.logger.info("Initializing Meal Generator Agent")
            
            generate_meal_agent = Agent(
                name="MealGeneratingAgent",
                model=Gemini(
                    model=self.model_name,
                    retry_options=RETRY_CONFIG
                ),
                description="An Agent for generating meals according to the users interests",
                instruction="""You are an intelligent agent who generates detailed meal preparation 
                instructions.
                
                Meal plan: {meal_plan}
                
                Generate cooking steps step-by-step with clear instructions so that even non-cooks 
                can follow along and cook successfully.
                
                If you don't have enough information, use the available tools for additional details.
                
                Save the meal preparation steps in the database using pinecone_memory_tool.""",
                tools=[self.tools.pinecone_memory_tool, google_search, 
                       self.tools.nutrinix_tool, self.tools.usda_food_tool],
                output_key="meal_preparations"
            )
            
            self.logger.info("Successfully initialized Meal Generator Agent")
            return generate_meal_agent
            
        except Exception as e:
            self.logger.error("Error occurred while creating meal generator agent: %s", e)
            raise AppException(e, sys)

    def _create_variety_agent(self) -> Agent:
        """Creates an agent for monitoring and suggesting meal variety."""
        try:
            self.logger.info("Initializing User Variety Agent")
            
            user_variety_agent = Agent(
                name="UserVarietyAgent",
                model=Gemini(
                    model=self.model_name,
                    retry_options=RETRY_CONFIG
                ),
                description="An Agent for variety and balance in nutrition",
                instruction="""You are an intelligent agent who monitors user profiles daily and 
                provides instructions for variety and nutritional balance.
                
                User ID: {user_id}
                Current meal plan: {meal_plan}
                
                Analyze the user's meal history from the database and suggest varieties and 
                additional nutrients that are required for the user based on their profile.
                
                Ensure the user gets balanced nutrition over time.""",
                tools=[self.tools.pinecone_memory_tool, self.tools.nutrinix_tool, 
                       self.tools.usda_food_tool, self.tools.spoonacular_tool, 
                       self.tools.open_food_tool],
                output_key="varieties_meal"
            )
            
            self.logger.info("Successfully initialized User Variety Agent")
            return user_variety_agent
            
        except Exception as e:
            self.logger.error("Error occurred while creating variety agent: %s", e)
            raise AppException(e, sys)

    def run_pipeline(self, user_id: str, user_input: str, 
                     user_nutritional_needs: str = None, 
                     session_id: str = "default") -> Any:
        """
        Executes the sequential meal planning chain and returns the final response(s).
        
        Args:
            user_id: Unique identifier for the user
            user_input: User's meal planning request
            user_nutritional_needs: Optional pre-fetched nutritional needs
            session_id: Session identifier for conversation tracking
        """
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
            self.logger.info("Executing Sequential Meal Planning Chain...")
            responses = asyncio.run(
                session_manager.run_session(
                    runner_instance=runner,
                    user_queries=user_input,
                    session_id=session_id,
                    context_variables={
                        "user_id": user_id,
                        "user_input": user_input,
                        "user_nutritional_needs": user_nutritional_needs or "Not provided - query from database",
                        "current_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                )
            )
            
            self.logger.info("Meal Planning Pipeline execution completed successfully.")
            return responses
            
        except Exception as e:
            self.logger.error(f"Error during meal planning pipeline execution: {e}")
            raise AppException(f"Meal Planning Failed: {e}", sys)


# ---------------- Example Usage ----------------
if __name__ == "__main__":
    try:
        pipeline = MealPlannerPipeline()
        mock_user_id = "test_user_meal_001"
        mock_input = (
            "I need a healthy lunch plan for today. "
            "I'm vegetarian and trying to maintain my weight."
        )
        
        result = pipeline.run_pipeline(
            user_id=mock_user_id,
            user_input=mock_input,
            session_id="test_meal_session_1"
        )
        
        print("\n\n✅ FINAL MEAL PLANNING RESPONSE:")
        print(result)
        
    except Exception as err:
        print(f"\n❌ SETUP FAILED: {err}")
