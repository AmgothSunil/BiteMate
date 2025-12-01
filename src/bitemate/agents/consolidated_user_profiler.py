# import sys
# import os
# from typing import Optional
# from dotenv import load_dotenv

# # --- Google ADK Imports ---
# from google.genai import types
# from google.adk.agents import Agent, SequentialAgent
# from google.adk.models.google_llm import Gemini

# # --- Internal Core Imports ---
# from src.bitemate.utils.params import load_params
# from src.bitemate.core.logger import setup_logger
# from src.bitemate.core.exception import AppException
# from src.bitemate.utils.prompt import PromptManager

# # --- Tool Imports ---
# from src.bitemate.tools.mcp_client import get_mcp_toolset

# prompt_manager = PromptManager()

# # Load Environment Variables
# load_dotenv()
# os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")

# # Constants
# CONFIG_REL_PATH = "src/bitemate/config/params.yaml"

# # Retry Configuration
# RETRY_CONFIG = types.HttpRetryOptions(
#     initial_delay=1,
#     attempts=3,
#     max_delay=30,
#     exp_base=2,
#     jitter=0.2,
#     http_status_codes=[429, 500, 503, 504]
# )

# class UserProfilingPipeline:
#     """
#     Consolidated User Profiling Pipeline.
    
#     Orchestrates the lifecycle of User Profiling using a Single Consolidated Agent
#     that handles Bio-Data Extraction, Nutrition Calculation, and Variety Checking.
#     """
    
#     def __init__(self, config_path: str = CONFIG_REL_PATH):
#         try:
#             # 1. Load Configuration
#             self.params = load_params(config_path)
#             self.agent_config = self.params.get("user_profiler_agent", {})
            
#             # 2. Setup Logger
#             log_file = self.agent_config.get("file_path", "user_profiling.log")
#             self.logger = setup_logger(name="UserProfilingPipeline", log_file_name=log_file)
            
#             # 3. Model Configuration
#             # Use a slightly stronger model (Flash or Pro) as it now handles 3 logic steps in one go.
#             self.model_name = self.agent_config.get("model_name", "gemini-1.5-flash")
            
#             # 4. Assign MCP Toolset
#             self.tools = get_mcp_toolset()
#             self.instructions = prompt_manager.load_prompt(
#                 "src/bitemate/prompts/user_profile_prompt.txt"
#             )
            
#             self.logger.info("UserProfilingPipeline initialized successfully.")
            
#         except Exception as e:
#             msg = f"Failed to initialize UserProfilingPipeline: {str(e)}"
#             if hasattr(self, 'logger'):
#                 self.logger.critical(msg)
#             else:
#                 print(f"CRITICAL: {msg}")
#             raise AppException(msg, sys)


#     def create_unified_agent(self) -> Agent:
#         """
#         Creates the single agent that does the work of the previous 3 agents.
#         """
#         try:
#             self.logger.info("Creating Unified User Profiling Agent...")
#             return Agent(
#                 name="UnifiedProfileManager",
#                 model=Gemini(model=self.model_name, retry_options=RETRY_CONFIG),
#                 description="Handles profile extraction, nutrition calculation, and variety checks.",
#                 instruction=self.instructions,
#                 tools=[self.tools], # Access to ALL tools needed for saving bio and saving macros
#                 output_key="profiling_summary"
#             )
#         except Exception as e:
#             self.logger.error(f"Error creating unified agent: {e}")
#             raise AppException(f"Agent Creation Failed: {e}", sys)

    