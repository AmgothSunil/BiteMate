import sys
from google.adk.runners import Runner
from google.genai import types
from src.bitemate.core.exception import AppException

# Define constants
DEFAULT_USER_ID = "default_user"

async def run_session(
    runner_instance: Runner,
    user_queries: list[str] | str = None,
    session_name: str = "default",
    user_id: str = DEFAULT_USER_ID,
):
    """
    Execute agent runner and handle both TEXT responses and TOOL executions.
    """
    print(f"\n ### Session: {session_name} | User: {user_id}")

    app_name = runner_instance.app_name
    
    if hasattr(runner_instance, "session_service"):
        session_service = runner_instance.session_service
    else:
        raise AppException("Runner instance is missing 'session_service'.", sys)

    # Create/Get Session
    try:
        session = await session_service.create_session(app_name=app_name, user_id=user_id, session_id=session_name)
    except Exception:
        session = await session_service.get_session(app_name=app_name, user_id=user_id, session_id=session_name)

    if user_queries:
        if isinstance(user_queries, str):
            user_queries = [user_queries]

        for query in user_queries:
            print(f"\nUser > {query}")
            query_content = types.Content(role="user", parts=[types.Part(text=query)])

            last_text_response = "No text response generated."
            
            # --- IMPROVED STREAM HANDLING ---
            async for event in runner_instance.run_async(
                user_id=user_id,
                session_id=session.id, 
                new_message=query_content
            ):
                # 1. Check if the event has content
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        
                        # CASE A: It's a Function Call (Tool Use)
                        if part.function_call:
                            func_name = part.function_call.name
                            # Print a status update so you know it's working
                            print(f"   [⚙️ Tool Call]: {func_name}...")
                        
                        # CASE B: It's a Function Response (Result from Tool)
                        elif part.function_response:
                            print(f"   [✅ Tool Result]: Data received.")

                        # CASE C: It's actual Text (Chat)
                        elif part.text:
                            # Clean up the text
                            text = part.text.strip()
                            if text and text != "None":
                                print(f"\n{event.content.role.capitalize()} > {text}\n")
                                last_text_response = text
            
            return last_text_response
    else:
        print("No queries!")