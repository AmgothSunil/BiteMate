import os
import sys
from pathlib import Path
from typing import List, Optional, Union, Generator

# Third-party imports
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai import types

# Internal imports
# Assuming these modules exist in your project structure
from src.bitemate.utils.params import load_params
from src.bitemate.core.logger import setup_logger
from src.bitemate.core.exception import AppException

# Define constants for clarity
DEFAULT_SESSION_ID = "default_session"
DEFAULT_USER_ID = "default_user"
CONFIG_REL_PATH = "src/bitemate/config/params.yaml"

class SessionManager:
    """
    Manages the lifecycle of GenAI sessions and query execution.

    This class handles configuration loading, session service initialization,
    and the execution of user queries against the Runner instance.
    """

    def __init__(self, config_path: Optional[str] = None, session_service = None):
        """
        Initializes the SessionManager with configuration and services.

        Args:
            config_path (Optional[str]): Custom path to the YAML config file. 
                                         If None, attempts to resolve relative to project root.
            session_service: Optional session service instance. If None, creates a new InMemorySessionService.
        """
        # Resolve configuration path dynamically to avoid file-not-found errors
        if config_path:
            self.config_path = Path(config_path)
        else:
            # Assuming this script is running from project root, or resolving relative to this file
            # Adjust .parent.parent calls depending on where this file sits relative to src/
            project_root = Path(os.getcwd()) 
            self.config_path = project_root / CONFIG_REL_PATH

        # Load parameters
        try:
            self.params = load_params(str(self.config_path))
            self.run_session_params = self.params.get("run_session_params", {})
        except Exception as e:
            # Fallback if config fails, but log critical error
            print(f"CRITICAL: Failed to load config at {self.config_path}. Error: {e}")
            self.run_session_params = {}

        # Extract configuration with defaults
        self.logs_file_path = self.run_session_params.get("file_path", "app.log")
        self.app_name = self.run_session_params.get("app_name", "agents")
        self.default_user_id = self.run_session_params.get("user_id", DEFAULT_USER_ID)

        # Initialize Logger
        self.logger = setup_logger(
            name="SessionManager",
            log_file_name=self.logs_file_path
        )

        # Initialize Session Service - use provided one or create new
        # This ensures runner and SessionManager use the same session_service instance
        if session_service is not None:
            self.session_service = session_service
        else:
            self.session_service = InMemorySessionService()
        
        self.logger.info("SessionManager initialized successfully.")

    async def _get_or_create_session(self, session_id: str, user_id: str):
        """
        Retrieves an existing session or creates a new one if it doesn't exist.

        Args:
            session_id (str): The unique identifier for the session.
            user_id (str): The user associated with the session.

        Returns:
            Session: The initialized session object.

        Raises:
            AppException: If session operations fail.
        """
        try:
            # Attempt to create a fresh session
            session = await self.session_service.create_session(
                app_name=self.app_name, 
                user_id=user_id, 
                session_id=session_id
            )
            self.logger.info(f"New session created. [SessionID: {session_id}, UserID: {user_id}]")
            return session

        except Exception as creation_error:
            # If creation fails (likely already exists), attempt retrieval
            self.logger.debug(f"Session creation skipped; attempting retrieval. Reason: {creation_error}")
            
            try:
                session = await self.session_service.get_session(
                    app_name=self.app_name, 
                    user_id=user_id, 
                    session_id=session_id
                )
                self.logger.info(f"Existing session retrieved. [SessionID: {session_id}]")
                return session
            except Exception as retrieval_error:
                # Log the exception stack trace and raise a custom application exception
                error_msg = f"Failed to initialize session {session_id} for user {user_id}."
                self.logger.exception(error_msg)
                raise AppException(f"{error_msg} Details: {retrieval_error}")

    async def run_session(
        self, 
        runner_instance: Runner, 
        user_queries: Union[List[str], str], 
        session_id: str = DEFAULT_SESSION_ID
    ) -> List[str]:
        """
        Executes a list of user queries against the provided runner within a specific session.

        Args:
            runner_instance (Runner): The agent runner instance to execute prompts.
            user_queries (list[str] | str): A single query string or a list of query strings.
            session_id (str): Unique identifier for the conversation session.

        Returns:
            List[str]: A list of response texts corresponding to the input queries.
        """
        
        # Normalize input to list
        if isinstance(user_queries, str):
            queries = [user_queries]
        else:
            queries = user_queries

        user_id = self.default_user_id
        responses: List[str] = []

        # 1. Initialize Session
        session = await self._get_or_create_session(session_id, user_id)

        # 2. Process Queries
        self.logger.info(f"Processing {len(queries)} queries for session {session_id}.")

        for index, query_text in enumerate(queries):
            try:
                query_content = types.Content(
                    role="user", 
                    parts=[types.Part(text=query_text)]
                )
                
                self.logger.debug(f"Streaming response for query {index+1}/{len(queries)}.")

                # Variable to hold the final accumulated text for this query
                final_response_text = None

                # Stream agent response
                async for event in runner_instance.run_async(
                    user_id=user_id, 
                    session_id=session.id, 
                    new_message=query_content
                ):
                    # Check for validity of content
                    if event.is_final_response() and event.content and event.content.parts:
                        text_part = event.content.parts[0].text
                        
                        # Validate text is not a string literal "None" or empty
                        if text_part and text_part != "None":
                            final_response_text = text_part
                            # We break the inner loop (stream) once we have the final answer
                            # If you need partial streaming updates, logic changes here.
                            break 
                
                if final_response_text:
                    responses.append(final_response_text)
                else:
                    self.logger.warning(f"Query {index+1} resulted in no valid text response.")
                    responses.append("") # Maintain index alignment

            except Exception as e:
                self.logger.error(f"Error processing query '{query_text[:30]}...': {str(e)}")
                raise AppException(f"Error during query execution: {e}")

        self.logger.info("Batch query execution completed.")
        return responses

# -------------------------------------------------------------------------
# Example Usage (usually inside a main block or a separate entrypoint file)
# -------------------------------------------------------------------------
# if __name__ == "__main__":
#     # This block prevents the code from running when imported by other modules
#     import asyncio

#     async def main():
#         # Mocking Runner for demonstration purposes as we don't have the instance here
#         # runner = Runner(...) 
#         print("✅ SessionManager defined. Initialize usage inside your main application flow.")

#     # asyncio.run(main())