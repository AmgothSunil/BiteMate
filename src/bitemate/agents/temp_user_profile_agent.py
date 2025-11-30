import sys
import os
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


class UserProfilingPipeline:
    """
    Orchestrates the lifecycle of User Profiling using Sequential Agents.
    This class ONLY defines the agent configuration - execution happens in the orchestrator.
    
    Agent Flow:
    1. UserProfiler: Extracts bio-data & saves to Pinecone → outputs extracted_profile_json
    2. NutritionCalculator: Calculates nutrition needs → outputs calculated_macros
    3. ProfileUpdater: Saves nutrition goals to Pinecone → provides confirmation
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
            self.model_name = self.agent_config.get("model_name", "gemini-2.5-flash")
            
            # 4. Define Tools per Agent
            # Profiler & Updater need save/recall tools
            self.profiling_tools = [
                save_user_preference,
                recall_user_profile,
            ]
            
            # Calculator needs research tools for nutrition data
            self.calculation_tools = [
                search_nutrition_info,
                search_usda_database,
                search_scientific_papers,
            ]
            
            self.logger.info("UserProfilingPipeline initialized successfully.")
            
        except Exception as e:
            msg = f"Failed to initialize UserProfilingPipeline: {str(e)}"
            if hasattr(self, 'logger'):
                self.logger.critical(msg)
            else:
                print(f"CRITICAL: {msg}")
            raise AppException(msg, sys)
    
    def _create_profiler_agent(self) -> Agent:
        """
        Agent 1: Extracts bio-data and preferences, saves to Pinecone, outputs JSON.
        Input: {user_input}
        Output: extracted_profile_json
        """
        instruction = prompt_manager.load_prompt(
            "src/bitemate/prompts/user_profiler_prompts/create_profiler_prompt.txt"
        )
        return Agent(
            name="UserProfiler",
            model=Gemini(model=self.model_name, retry_options=RETRY_CONFIG),
            description="Extracts bio-data and saves it to the vector database.",
            instruction=instruction,
            tools=self.profiling_tools,
            output_key="extracted_profile_json"
        )
    
    def _create_calculator_agent(self) -> Agent:
        """
        Agent 2: Calculates nutrition needs based on profile, suggests recipe types.
        Input: {extracted_profile_json}
        Output: calculated_macros
        """
        instruction = prompt_manager.load_prompt(
            "src/bitemate/prompts/user_profiler_prompts/create_calculator_prompt.txt"
        )
        return Agent(
            name="NutritionCalculator",
            model=Gemini(model=self.model_name, retry_options=RETRY_CONFIG),
            description="Calculates nutritional needs based on extracted profile.",
            instruction=instruction,
            tools=self.calculation_tools,
            output_key="calculated_macros"
        )
    
    def _create_updater_agent(self) -> Agent:
        """
        Agent 3: Saves nutrition goals to Pinecone and provides confirmation.
        Input: {calculated_macros}
        Output: None (final agent)
        """
        instruction = prompt_manager.load_prompt(
            "src/bitemate/prompts/user_profiler_prompts/create_updater_prompt.txt"
        )
        return Agent(
            name="ProfileUpdater",
            model=Gemini(model=self.model_name, retry_options=RETRY_CONFIG),
            description="Saves the final calculated goals back to memory.",
            instruction=instruction,
            tools=self.profiling_tools
        )
    
    def create_sequential_agent(self) -> SequentialAgent:
        """
        Creates and returns the complete sequential agent chain.
        This method is called by the orchestrator to build the pipeline.
        
        Returns:
            SequentialAgent: The configured sequential agent chain
        """
        try:
            self.logger.info("Building User Profiling Sequential Agent Chain...")
            
            # 1. Instantiate Agents
            profiler = self._create_profiler_agent()
            calculator = self._create_calculator_agent()
            updater = self._create_updater_agent()
            
            # 2. Define Sequential Chain
            root_agent = SequentialAgent(
                name="UserProfilingChain",
                sub_agents=[profiler, calculator, updater]
            )
            
            self.logger.info("User Profiling Sequential Agent Chain created successfully.")
            return root_agent
            
        except Exception as e:
            self.logger.error(f"Error creating sequential agent: {e}")
            raise AppException(f"Agent Creation Failed: {e}", sys)


# ---------------- Example Usage (for testing agent creation only) ----------------
if __name__ == "__main__":
    try:
        pipeline = UserProfilingPipeline()
        agent_chain = pipeline.create_sequential_agent()
        print(f"✅ User Profiling Agent Chain Created: {agent_chain.name}")
        print(f"   Sub-agents: {[agent.name for agent in agent_chain.sub_agents]}")
    except Exception as err:
        print(f"\n❌ SETUP FAILED: {err}")