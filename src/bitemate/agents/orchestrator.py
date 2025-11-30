"""
BiteMate Orchestrator - Unified Workflow

Single-input orchestrator that:
- Takes one user input
- Automatically detects profile info
- Generates 5+ meal options
- Saves to PostgreSQL
"""
import os
import sys
import asyncio
import datetime
from typing import Dict, Any
from dotenv import load_dotenv

# Google ADK Imports
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService

# Internal Imports
from src.bitemate.agents.user_profiler_agent import UserProfilingPipeline
from src.bitemate.agents.meal_planner_agent import MealPlannerPipeline
from src.bitemate.utils.run_sessions import SessionManager
from src.bitemate.utils.params import load_params
from src.bitemate.core.logger import setup_logger
from src.bitemate.core.exception import AppException

# Load environment
load_dotenv()
os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")

CONFIG_REL_PATH = "src/bitemate/config/params.yaml"


class BiteMateOrchestrator:
    """
    Unified orchestrator for BiteMate AI.
    Takes single user input → extracts profile if present → generates meal options.
    """
    
    def __init__(self, config_path: str = CONFIG_REL_PATH):
        """Initialize orchestrator with both pipelines and shared services."""
        try:
            self.params = load_params(config_path)
            self.logger = setup_logger(name="BiteMateOrchestrator", log_file_name="orchestrator.log")
            self.logger.info("Initializing BiteMate Orchestrator...")
            
            # Shared services (same instances for both pipelines)
            self.session_service = InMemorySessionService()
            self.memory_service = InMemoryMemoryService()
            self.session_manager = SessionManager(session_service=self.session_service)
            
            # Initialize pipelines
            self.user_profiler_pipeline = UserProfilingPipeline(config_path)
            self.meal_planner_pipeline = MealPlannerPipeline(config_path)
            
            # Runners (lazy initialization)
            self._user_profiler_runner = None
            self._meal_planner_runner = None
            
            self.logger.info("✅ BiteMate Orchestrator initialized successfully!")
            
        except Exception as e:
            msg = f"Failed to initialize BiteMateOrchestrator: {str(e)}"
            if hasattr(self, 'logger'):
                self.logger.critical(msg)
            raise AppException(msg, sys)
    
    def _get_user_profiler_runner(self) -> Runner:
        """Get or create user profiler runner (lazy)."""
        if self._user_profiler_runner is None:
            self.logger.info("Creating User Profiler Runner...")
            agent_chain = self.user_profiler_pipeline.create_sequential_agent()
            self._user_profiler_runner = Runner(
                app_name="agents",
                agent=agent_chain,
                session_service=self.session_service,
                memory_service=self.memory_service
            )
        return self._user_profiler_runner
    
    def _get_meal_planner_runner(self) -> Runner:
        """Get or create meal planner runner (lazy)."""
        if self._meal_planner_runner is None:
            self.logger.info("Creating Meal Planner Runner...")
            agent_chain = self.meal_planner_pipeline.create_sequential_agent()
            self._meal_planner_runner = Runner(
                app_name="agents",
                agent=agent_chain,
                session_service=self.session_service,
                memory_service=self.memory_service
            )
        return self._meal_planner_runner
    
    async def execute_unified_workflow(
        self,
        user_id: str,
        user_input: str,
        num_meals: int = 5
    ) -> Dict[str, Any]:
        """
        **UNIFIED WORKFLOW**: Single input handles everything.
        
        Automatically:
        1. Detects profile info → creates/updates profile if present
        2. Generates meal options based on request
        3. Saves to PostgreSQL
        
        Args:
            user_id: Unique user identifier
            user_input: Single user request (can include profile info + meal request)
            num_meals: Minimum number of meal options (default: 5)
        
        Returns:
            Dictionary with profile_updated flag and meal options
        """
        try:
            self.logger.info(f"Starting Unified Workflow for user: {user_id}")
            self.logger.info(f"Input: {user_input[:100]}...")
            
            profile_updated = False
            profile_response = None
            
            # Step 1: Auto-detect profile information
            profile_keywords = [
                "i'm", "i am", "years old", "kg", "cm", "tall", "weight",
                "diabetic", "diabetes", "vegetarian", "vegan", "allergy", "allergic",
                "prefer", "don't like", "hate", "love"
            ]
            
            has_profile_info = any(keyword in user_input.lower() for keyword in profile_keywords)
            
            if has_profile_info:
                self.logger.info("Profile info detected → Creating/updating profile...")
                try:
                    runner = self._get_user_profiler_runner()
                    profile_response = await self.session_manager.run_session(
                        runner_instance=runner,
                        user_queries=user_input,
                        session_id=f"{user_id}_profile",
                        context_variables={"user_id": user_id, "user_input": user_input}
                    )
                    profile_updated = True
                    self.logger.info("✅ Profile created/updated")
                except Exception as e:
                    self.logger.warning(f"Profile update failed, continuing: {e}")
            else:
                self.logger.info("No profile info detected → Proceeding to meal planning")
            
            # Step 2: Generate meal options
            self.logger.info(f"Generating meal options (minimum {num_meals})...")
            
            runner = self._get_meal_planner_runner()
            session_id = f"{user_id}_meal_{datetime.date.today().strftime('%Y%m%d')}"
            
            meal_responses = await self.session_manager.run_session(
                runner_instance=runner,
                user_queries=user_input,
                session_id=session_id,
                context_variables={
                    "user_id": user_id,
                    "user_input": user_input,
                    "current_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            )
            
            # Step 3: Auto-save to PostgreSQL (fallback)
            try:
                from src.bitemate.tools.bitemate_tools import save_generated_meal_plan
                
                save_result = save_generated_meal_plan(
                    user_id=user_id,
                    session_id=session_id,
                    plan_summary=f"Recipe Options - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    recipes_json={
                        "user_request": user_input,
                        "responses": meal_responses,
                        "timestamp": datetime.datetime.now().isoformat()
                    }
                )
                self.logger.info(f"✅ Saved to PostgreSQL: {save_result}")
            except Exception as save_error:
                self.logger.warning(f"PostgreSQL save failed: {save_error}")
            
            self.logger.info("✅ Unified Workflow completed successfully")
            
            return {
                "user_id": user_id,
                "profile_updated": profile_updated,
                "profile_response": profile_response,
                "meal_options": meal_responses,
                "num_meals_requested": num_meals,
                "status": "success"
            }
            
        except Exception as e:
            self.logger.error(f"Error in unified workflow: {e}")
            raise AppException(f"Unified Workflow Failed: {e}", sys)


# ==================== EXAMPLE USAGE ====================

async def example_usage():
    """Example: Single input with profile info + meal request."""
    print("\n" + "="*70)
    print("BITEMATE ORCHESTRATOR - UNIFIED WORKFLOW")
    print("="*70)
    
    orchestrator = BiteMateOrchestrator()
    
    # Example 1: User provides profile + meal request in one input
    user_input = """
    I'm a 30-year-old male, 75kg, 180cm tall. 
    I have type 2 diabetes and I'm vegetarian. 
    I want healthy lunch recipes.
    """
    
    try:
        result = await orchestrator.execute_unified_workflow(
            user_id="demo_user",
            user_input=user_input,
            num_meals=5
        )
        
        print(f"\n📊 RESULTS:")
        print(f"Profile Updated: {result['profile_updated']}")
        print(f"Meals Requested: {result['num_meals_requested']}")
        
        if result['profile_updated']:
            print(f"\n✅ PROFILE CREATED")
        
        print(f"\n🍽️ MEAL OPTIONS:")
        for i, meal in enumerate(result['meal_options'], 1):
            print(f"\n--- Option {i} ---")
            print(meal[:300] + "..." if len(meal) > 300 else meal)
        
        print("\n" + "="*70)
        print("✅ Workflow completed!")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    """
    Run the unified workflow example.
    Usage: uv run -m src.bitemate.agents.orchestrator
    """
    asyncio.run(example_usage())
