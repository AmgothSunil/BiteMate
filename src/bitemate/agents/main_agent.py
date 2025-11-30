import os
import sys
import asyncio
import datetime
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# --- Google ADK Imports ---
from google.adk.agents import SequentialAgent, Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService

# --- Internal Imports ---
from src.bitemate.agents.user_profiler_agent import UserProfilingPipeline
from src.bitemate.agents.meal_planner_agent import MealPlannerPipeline
from src.bitemate.utils.run_sessions import run_session
from src.bitemate.utils.params import load_params
from src.bitemate.core.logger import setup_logger
from src.bitemate.core.exception import AppException

# Load Environment
load_dotenv()

# Constants
CONFIG_REL_PATH = "src/bitemate/config/params.yaml"

class BiteMateOrchestrator:
    """
    The Master Controller for the BiteMate Application.
    
    This class composes agents from the User Profiling Pipeline and the 
    Meal Planning Pipeline into a single, cohesive Super-Agent.
    """

    def __init__(self, config_path: str = CONFIG_REL_PATH):
        try:
            # 1. Setup Logging
            self.logger = setup_logger(name="BiteMateOrchestrator", log_file_name="orchestrator.log")
            
            # 2. Initialize Sub-Pipelines (Factories)
            self.profiler_pipeline = UserProfilingPipeline(config_path)
            self.planner_pipeline = MealPlannerPipeline(config_path)
            
            # 3. Initialize Services
            self.session_service = InMemorySessionService()
            self.memory_service = InMemoryMemoryService()
            
            self.logger.info("BiteMateOrchestrator initialized.")

        except Exception as e:
            print(f"CRITICAL: Orchestrator failed to init. {e}")
            raise AppException(e, sys)

    def build_master_agent(self) -> Agent:
        """Constructs the final sequential workflow with all 7 agents."""
        try:
            # Phase 1: User Profiling & Nutrition
            agent_profiler = self.profiler_pipeline._create_profiler_agent()
            agent_calculator = self.profiler_pipeline._create_calculator_agent()

            # Phase 2: Meal Planning
            agent_variety = self.profiler_pipeline._create_variety_agent()
            agent_recipe_finder = self.profiler_pipeline._create_recipe_finder_agent()
            agent_meal_generator = self.planner_pipeline._create_meal_generator_agent()
            daily_meal_planner = self.planner_pipeline._create_daily_meal_planner_agent()

            # Phase 3: Persistence
            agent_updater = self.planner_pipeline._create_updater_agent()

            master_agent = SequentialAgent(
                name="BiteMateMasterFlow",
                description="Complete meal planning workflow from profile to daily meal plan.",
                sub_agents=[
                    agent_profiler, agent_calculator, agent_variety, agent_recipe_finder,
                    agent_meal_generator, daily_meal_planner, agent_updater,
                ]
            )
            
            return master_agent

        except Exception as e:
            self.logger.error(f"Error building master agent: {e}")
            raise AppException(e, sys)

    async def run_flow(self, user_input: str, user_id: str, session_id: str = "default"):
        """
        Executes the master workflow with dynamic user identification.
        
        Args:
            user_input: User's message/request
            user_id: Unique user identifier (persistent across sessions)
            session_id: Unique session identifier for this conversation
        
        Returns:
            str: Response from the sequential agent chain
        """
        try:
            final_agent = self.build_master_agent()

            runner = Runner(
                app_name="agents",
                agent=final_agent,
                session_service=self.session_service,
                memory_service=self.memory_service
            )

            self.logger.info(f"Executing for user {user_id}, session {session_id}...")
            
            response = await run_session(
                runner_instance=runner,
                user_queries=[user_input], 
                session_name=session_id,
                user_id=user_id,
            )
            
            return response

        except Exception as e:
            self.logger.error(f"Orchestration Failed: {e}")
            raise AppException(e, sys)


if __name__ == "__main__":
    TEST_USER_ID = "test_user_12345"
    TEST_SESSION_ID = f"session_{int(datetime.datetime.now().timestamp())}"
    TEST_INPUT = "Hi, I am a 30 year old male, 85kg, and I'm pre-diabetic. I need a lunch plan for today that is low carb but spicy."

    print(f"🚀 Starting BiteMate Orchestrator...")
    print(f"👤 User: {TEST_USER_ID}")
    print(f"💬 Input: {TEST_INPUT}\n")

    try:
        orchestrator = BiteMateOrchestrator()
        result = asyncio.run(orchestrator.run_flow(user_input=TEST_INPUT, user_id=TEST_USER_ID, session_id=TEST_SESSION_ID))
        
        print("\n==================================================")
        print("✅ FINAL AGENT RESPONSE")
        print("==================================================")
        print(result if isinstance(result, str) else "\n".join(result))
            
    except Exception as e:
        print(f"\n❌ Execution Failed: {e}")