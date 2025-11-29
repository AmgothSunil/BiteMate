"""
BiteMate Orchestrator Agent

This orchestrator manages the execution of both User Profiler and Meal Planner pipelines.
It coordinates the workflow: first ensuring user has a profile, then executing meal planning.

Architecture:
1. Initialize both pipelines (UserProfilingPipeline, MealPlannerPipeline)
2. Create Runners for each pipeline with shared session/memory services
3. Execute workflows based on user requests:
   - Profile creation/update: Run user profiler pipeline
   - Meal planning: Check profile exists → Run meal planner pipeline
   - Combined: Run both in sequence

Usage:
    orchestrator = BiteMateOrchestrator()
    
    # Create user profile
    response = await orchestrator.execute_user_profiling(
        user_id="user123",
        user_input="I'm 30 years old, 75kg, 180cm, diabetic, vegetarian..."
    )
    
    # Plan meals
    response = await orchestrator.execute_meal_planning(
        user_id="user123",
        user_input="I need a healthy lunch plan for today"
    )
"""
import os
import sys
import asyncio
import datetime
from typing import Optional, Dict, Any, List
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

# Constants
CONFIG_REL_PATH = "src/bitemate/config/params.yaml"


class BiteMateOrchestrator:
    """
    Orchestrator for managing BiteMate AI agent workflows.
    
    Responsibilities:
    - Initialize and manage both pipelines (User Profiler, Meal Planner)
    - Create and manage Runners with shared services
    - Execute workflows based on user requests
    - Coordinate data flow between pipelines
    """
    
    def __init__(self, config_path: str = CONFIG_REL_PATH):
        """
        Initialize the orchestrator with both pipelines and shared services.
        
        Args:
            config_path: Path to configuration YAML file
        """
        try:
            # 1. Load configuration
            self.params = load_params(config_path)
            
            # 2. Setup logger
            self.logger = setup_logger(
                name="BiteMateOrchestrator",
                log_file_name="orchestrator.log"
            )
            
            self.logger.info("Initializing BiteMate Orchestrator...")
            
            # 3. Initialize shared services (IMPORTANT: same instances for both pipelines)
            self.session_service = InMemorySessionService()
            self.memory_service = InMemoryMemoryService()
            self.session_manager = SessionManager(session_service=self.session_service)
            
            # 4. Initialize pipelines
            self.logger.info("Initializing User Profiling Pipeline...")
            self.user_profiler_pipeline = UserProfilingPipeline(config_path)
            
            self.logger.info("Initializing Meal Planner Pipeline...")
            self.meal_planner_pipeline = MealPlannerPipeline(config_path)
            
            # 5. Create runners (lazy initialization - created when needed)
            self._user_profiler_runner = None
            self._meal_planner_runner = None
            
            self.logger.info("✅ BiteMate Orchestrator initialized successfully!")
            
        except Exception as e:
            msg = f"Failed to initialize BiteMateOrchestrator: {str(e)}"
            if hasattr(self, 'logger'):
                self.logger.critical(msg)
            else:
                print(f"CRITICAL: {msg}")
            raise AppException(msg, sys)
    
    def _get_user_profiler_runner(self) -> Runner:
        """Get or create the user profiler runner."""
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
        """Get or create the meal planner runner."""
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
    
    async def execute_user_profiling(
        self,
        user_id: str,
        user_input: str,
        session_id: Optional[str] = None
    ) -> List[str]:
        """
        Execute the user profiling pipeline.
        
        This workflow:
        1. Extracts bio-data and preferences from user input
        2. Saves data to Pinecone vector database
        3. Calculates nutrition needs (BMR, TDEE, macros)
        4. Saves nutrition goals to database
        5. Returns confirmation message
        
        Args:
            user_id: Unique user identifier
            user_input: User's profile information (age, weight, height, conditions, preferences)
            session_id: Optional session ID (defaults to f"{user_id}_profile")
        
        Returns:
            List of response strings from the agent chain
        """
        try:
            session_id = session_id or f"{user_id}_profile"
            
            self.logger.info(f"Starting User Profiling for user: {user_id}")
            self.logger.info(f"Session ID: {session_id}")
            
            # Get runner
            runner = self._get_user_profiler_runner()
            
            # Prepare context variables for template substitution
            context_variables = {
                "user_id": user_id,
                "user_input": user_input
            }
            
            # Execute pipeline
            self.logger.info("Executing User Profiling Pipeline...")
            responses = await self.session_manager.run_session(
                runner_instance=runner,
                user_queries=user_input,
                session_id=session_id,
                context_variables=context_variables
            )
            
            self.logger.info("✅ User Profiling completed successfully")
            return responses
            
        except Exception as e:
            self.logger.error(f"Error in user profiling: {e}")
            raise AppException(f"User Profiling Failed: {e}", sys)
    
    async def execute_meal_planning(
        self,
        user_id: str,
        user_input: str,
        session_id: Optional[str] = None
    ) -> List[str]:
        """
        Execute the meal planning pipeline.
        
        This workflow:
        1. Recalls user profile from database
        2. Finds suitable recipes based on profile and request
        3. Creates full day meal plan (breakfast, lunch, dinner)
        4. Generates detailed cooking instructions
        5. Checks variety and provides final response
        
        Args:
            user_id: Unique user identifier
            user_input: User's meal request (e.g., "I need lunch for today")
            session_id: Optional session ID (defaults to f"{user_id}_meal_{date}")
        
        Returns:
            List of response strings from the agent chain
        """
        try:
            # Generate session ID with date if not provided
            if session_id is None:
                today = datetime.date.today().strftime("%Y%m%d")
                session_id = f"{user_id}_meal_{today}"
            
            self.logger.info(f"Starting Meal Planning for user: {user_id}")
            self.logger.info(f"Session ID: {session_id}")
            
            # Get runner
            runner = self._get_meal_planner_runner()
            
            # Prepare context variables
            context_variables = {
                "user_id": user_id,
                "user_input": user_input,
                "current_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # Execute pipeline
            self.logger.info("Executing Meal Planning Pipeline...")
            responses = await self.session_manager.run_session(
                runner_instance=runner,
                user_queries=user_input,
                session_id=session_id,
                context_variables=context_variables
            )
            
            # FALLBACK: Manually save to database since agents don't always call the tool
            try:
                from src.bitemate.tools.bitemate_tools import save_generated_meal_plan
                import json
                
                # Extract recipe data from responses (if possible)
                meal_summary = f"Recipe Options - {context_variables['current_time']}"
                recipes_data = {
                    "user_request": user_input,
                    "responses": responses,
                    "timestamp": context_variables['current_time']
                }
                
                self.logger.info("Saving meal plan to PostgreSQL (fallback)...")
                save_result = save_generated_meal_plan(
                    user_id=user_id,
                    session_id=session_id,
                    plan_summary=meal_summary,
                    recipes_json=recipes_data
                )
                self.logger.info(f"PostgreSQL save result: {save_result}")
                
            except Exception as save_error:
                self.logger.warning(f"Could not save to PostgreSQL: {save_error}")
            
            self.logger.info("✅ Meal Planning completed successfully")
            return responses
            
        except Exception as e:
            self.logger.error(f"Error in meal planning: {e}")
            raise AppException(f"Meal Planning Failed: {e}", sys)
    
    async def execute_complete_workflow(
        self,
        user_id: str,
        profile_input: str,
        meal_input: str
    ) -> Dict[str, Any]:
        """
        Execute complete workflow: create profile, then plan meals.
        
        This is useful for new users who need both profile creation and meal planning.
        
        Args:
            user_id: Unique user identifier
            profile_input: User profile information
            meal_input: Meal planning request
        
        Returns:
            Dictionary with both profile and meal planning responses
        """
        try:
            self.logger.info(f"Starting Complete Workflow for user: {user_id}")
            
            # Step 1: Create user profile
            self.logger.info("Step 1/2: Creating user profile...")
            profile_responses = await self.execute_user_profiling(
                user_id=user_id,
                user_input=profile_input
            )
            
            # Step 2: Plan meals
            self.logger.info("Step 2/2: Planning meals...")
            meal_responses = await self.execute_meal_planning(
                user_id=user_id,
                user_input=meal_input
            )
            
            self.logger.info("✅ Complete Workflow finished successfully")
            
            return {
                "user_id": user_id,
                "profile_response": profile_responses,
                "meal_plan_response": meal_responses,
                "status": "success"
            }
            
        except Exception as e:
            self.logger.error(f"Error in complete workflow: {e}")
            raise AppException(f"Complete Workflow Failed: {e}", sys)
    
    async def execute_unified_workflow(
        self,
        user_id: str,
        user_input: str,
        num_meals: int = 5
    ) -> Dict[str, Any]:
        """
        **UNIFIED WORKFLOW**: Single input for everything.
        
        This method intelligently:
        1. Checks if profile info is in the input → creates/updates profile if needed
        2. Plans meals based on request
        3. Returns at least `num_meals` meal options
        
        Perfect for: "I want a recipe for lunch" or "I'm 30M, diabetic, need dinner ideas"
        
        Args:
            user_id: Unique user identifier
            user_input: Single user request (may contain profile info + meal request)
            num_meals: Minimum number of meal options to generate (default: 5)
        
        Returns:
            Dictionary with profile_updated flag and meal options
        """
        try:
            self.logger.info(f"Starting Unified Workflow for user: {user_id}")
            self.logger.info(f"Input: {user_input[:100]}...")
            
            profile_updated = False
            profile_response = None
            
            # Step 1: Check if input contains profile information
            # Keywords that suggest profile info
            profile_keywords = [
                "i'm", "i am", "years old", "kg", "cm", "tall", "weight",
                "diabetic", "diabetes", "vegetarian", "vegan", "allergy", "allergic",
                "prefer", "don't like", "hate", "love"
            ]
            
            has_profile_info = any(keyword in user_input.lower() for keyword in profile_keywords)
            
            if has_profile_info:
                self.logger.info("Profile information detected in input. Creating/updating profile...")
                try:
                    profile_response = await self.execute_user_profiling(
                        user_id=user_id,
                        user_input=user_input
                    )
                    profile_updated = True
                    self.logger.info("✅ Profile created/updated successfully")
                except Exception as e:
                    self.logger.warning(f"Profile update failed, continuing with meal planning: {e}")
            else:
                self.logger.info("No profile info detected, proceeding directly to meal planning")
            
            # Step 2: Generate meal options
            self.logger.info(f"Generating meal options (minimum {num_meals})...")
            
            # Pass input directly - agents will handle generating multiple options
            meal_responses = await self.execute_meal_planning(
                user_id=user_id,
                user_input=user_input
            )
            
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

async def example_unified_simple_request():
    """Example: Simple meal request without profile info."""
    print("\n" + "="*70)
    print("EXAMPLE 1: SIMPLE MEAL REQUEST (No Profile Info)")
    print("="*70)
    
    orchestrator = BiteMateOrchestrator()
    
    # Simple request - no profile info
    user_input = "I want healthy lunch recipes"
    
    try:
        result = await orchestrator.execute_unified_workflow(
            user_id="user_simple",
            user_input=user_input,
            num_meals=5
        )
        
        print(f"\n📊 RESULTS:")
        print(f"Profile Updated: {result['profile_updated']}")
        print(f"Meals Requested: {result['num_meals_requested']}")
        print(f"\n🍽️ MEAL OPTIONS:")
        for i, meal in enumerate(result['meal_options'], 1):
            print(f"\n--- Meal Option {i} ---")
            print(meal[:300] + "..." if len(meal) > 300 else meal)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")


async def example_unified_with_profile():
    """Example: Request with profile info included."""
    print("\n" + "="*70)
    print("EXAMPLE 2: REQUEST WITH PROFILE INFO")
    print("="*70)
    
    orchestrator = BiteMateOrchestrator()
    
    # Request contains both profile and meal request
    user_input = """
    I'm a 30-year-old male, 75kg, 180cm tall. I have type 2 diabetes 
    and I'm vegetarian. I want healthy dinner recipes for today.
    """
    
    try:
        result = await orchestrator.execute_unified_workflow(
            user_id="user_with_profile",
            user_input=user_input,
            num_meals=5
        )
        
        print(f"\n📊 RESULTS:")
        print(f"Profile Updated: {result['profile_updated']}")
        print(f"Meals Requested: {result['num_meals_requested']}")
        
        if result['profile_updated']:
            print(f"\n✅ PROFILE CREATED:")
            print(result['profile_response'][0][:200] + "...")
        
        print(f"\n🍽️ MEAL OPTIONS:")
        for i, meal in enumerate(result['meal_options'], 1):
            print(f"\n--- Meal Option {i} ---")
            print(meal[:300] + "..." if len(meal) > 300 else meal)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")


# async def example_user_profiling():
#     """Example: Create a user profile."""
#     print("\n" + "="*70)
#     print("EXAMPLE 3: EXPLICIT USER PROFILING (OLD METHOD)")
#     print("="*70)
    
#     orchestrator = BiteMateOrchestrator()
    
#     user_input = """
#     I'm a 30-year-old male, weighing 75kg and 180cm tall.
#     I have type 2 diabetes and prefer vegetarian Indian food.
#     I want to lose weight and I exercise moderately 3-4 times per week.
#     I'm allergic to peanuts.
#     """
    
#     try:
#         responses = await orchestrator.execute_user_profiling(
#             user_id="demo_user_123",
#             user_input=user_input
#         )
        
#         print("\n📋 PROFILE CREATION RESPONSE:")
#         print("-" * 70)
#         for i, response in enumerate(responses, 1):
#             print(f"\nResponse {i}:")
#             print(response)
        
#     except Exception as e:
#         print(f"\n❌ Error: {e}")


# async def example_meal_planning():
#     """Example: Plan meals for a user."""
#     print("\n" + "="*70)
#     print("EXAMPLE 2: MEAL PLANNING")
#     print("="*70)
    
#     orchestrator = BiteMateOrchestrator()
    
#     meal_request = "I need a healthy meal plan for today with vegetarian Indian recipes."
    
#     try:
#         responses = await orchestrator.execute_meal_planning(
#             user_id="demo_user_123",
#             user_input=meal_request
#         )
        
#         print("\n🍽️ MEAL PLAN RESPONSE:")
#         print("-" * 70)
#         for i, response in enumerate(responses, 1):
#             print(f"\nResponse {i}:")
#             print(response)
        
#     except Exception as e:
#         print(f"\n❌ Error: {e}")


# async def example_complete_workflow():
#     """Example: Complete workflow for a new user."""
#     print("\n" + "="*70)
#     print("EXAMPLE 3: COMPLETE WORKFLOW (Profile + Meal Plan)")
#     print("="*70)
    
#     orchestrator = BiteMateOrchestrator()
    
#     profile_info = """
#     I'm a 25-year-old female, 60kg, 165cm tall.
#     I'm vegan and love Mediterranean cuisine.
#     I want to gain muscle and I'm very active (exercise 6 days/week).
#     """
    
#     meal_request = "Create a high-protein meal plan for today."
    
#     try:
#         result = await orchestrator.execute_complete_workflow(
#             user_id="new_user_456",
#             profile_input=profile_info,
#             meal_input=meal_request
#         )
        
#         print("\n📊 COMPLETE WORKFLOW RESULTS:")
#         print("-" * 70)
#         print(f"User ID: {result['user_id']}")
#         print(f"Status: {result['status']}")
        
#         print("\n1️⃣ Profile Response:")
#         for resp in result['profile_response']:
#             print(f"   {resp[:200]}...")  # Print first 200 chars
        
#         print("\n2️⃣ Meal Plan Response:")
#         for resp in result['meal_plan_response']:
#             print(f"   {resp[:200]}...")  # Print first 200 chars
        
#     except Exception as e:
#         print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    """
    Run examples to demonstrate orchestrator functionality.
    
    Usage:
        uv run python -m src.bitemate.agents.orchestrator
    """
    # print("\n" + "="*70)
    # print("BITEMATE ORCHESTRATOR - UNIFIED WORKFLOW EXAMPLES")
    # print("="*70)
    
    # NEW: Unified workflow examples (single input)
    asyncio.run(example_unified_simple_request())
    print("\n" + "="*70)
    
    # asyncio.run(example_unified_with_profile())
    # print("\n" + "="*70)
    
    # asyncio.run(example_complete_workflow())
    # print("\n" + "="*70)
    # print("\n✅ All examples completed!")
