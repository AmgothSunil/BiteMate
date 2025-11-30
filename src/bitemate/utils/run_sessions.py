import os
import sys
from pathlib import Path
from typing import List, Optional, Union, Generator

# Third-party imports
from google.adk.runners import Runner
from google.genai import types

# Internal imports
from src.bitemate.utils.params import load_params
from src.bitemate.core.logger import setup_logger
from src.bitemate.core.exception import AppException

# Define constants for clarity
DEFAULT_SESSION_ID = "default_session"
DEFAULT_USER_ID = "default_user"
CONFIG_REL_PATH = "src/bitemate/config/params.yaml"

async def run_session(
    runner_instance: Runner,
    user_queries: list[str] | str = None,
    session_name: str = "default",
    user_id: str = DEFAULT_USER_ID,  # Accept user_id as parameter
):
    """
    Execute agent runner with dynamic user identification.
    
    Args:
        runner_instance: Google ADK Runner instance
        user_queries: User input queries
        session_name: Unique session identifier for this conversation
        user_id: Unique user identifier (persistent across sessions)
    
    Returns:
        str: Response from the final agent in the sequential chain
    """
    print(f"\n ### Session: {session_name} | User: {user_id}")

    # Get app name from the Runner
    app_name = runner_instance.app_name
    
    # Use the session_service from the runner_instance
    if hasattr(runner_instance, "session_service"):
        session_service = runner_instance.session_service
    else:
        raise AppException("Runner instance is missing 'session_service'.", sys)

    # Attempt to create a new session or retrieve an existing one
    try:
        session = await session_service.create_session(
            app_name=app_name, 
            user_id=user_id,  # Use dynamic user_id
            session_id=session_name
        )
    except Exception:
        # If creation fails (e.g., session already exists), retrieve it
        session = await session_service.get_session(
            app_name=app_name, 
            user_id=user_id,  # Use dynamic user_id
            session_id=session_name
        )

    # Process queries if provided
    if user_queries:
        # Convert single query to list for uniform processing
        if isinstance(user_queries, str):
            user_queries = [user_queries]

        # Process each query in the list sequentially
        for query in user_queries:
            print(f"\nUser > {query}")

            # Convert the query string to the ADK Content format
            query_content = types.Content(role="user", parts=[types.Part(text=query)])

            # Stream the agent's response asynchronously
            # Collect all responses from the sequential agent chain
            last_response = None
            async for event in runner_instance.run_async(
                user_id=user_id,  # Use dynamic user_id
                session_id=session.id, 
                new_message=query_content
            ):
                # Check if the event contains valid content
                if event.content and event.content.parts:
                    # Filter out empty or "None" responses
                    part_text = event.content.parts[0].text
                    if part_text and part_text != "None":
                        print(f"\n{event.content.role.capitalize()} > {part_text}\n")
                        last_response = part_text  # Keep updating with latest response
            
            # Return the final response from the last agent in the chain
            return last_response
    else:
        print("No queries!")


print("✅ Helper functions defined.")