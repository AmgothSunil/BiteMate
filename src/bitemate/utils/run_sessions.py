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

    IMPORTANT CHANGE:
    ------------------
    Instead of returning ONLY the last text message (which was often
    just "I've saved this meal plan for you!"), we now:

    - Accumulate ALL meaningful text chunks for the query.
    - Return the concatenated text as a single string.

    This way, if the model first sends the full recipe + tips,
    then tools run, then it says "I've saved this meal plan for you!",
    your HTTP response will still contain the full recipe, not just
    the last tiny message.
    """
    print(f"\n ### Session: {session_name} | User: {user_id}")

    app_name = runner_instance.app_name

    if hasattr(runner_instance, "session_service"):
        session_service = runner_instance.session_service
    else:
        raise AppException("Runner instance is missing 'session_service'.", sys)

    # Create/Get Session
    try:
        session = await session_service.create_session(
            app_name=app_name, user_id=user_id, session_id=session_name
        )
    except Exception:
        session = await session_service.get_session(
            app_name=app_name, user_id=user_id, session_id=session_name
        )

    if not user_queries:
        print("No queries!")
        return "No queries provided."

    # Normalize to list
    if isinstance(user_queries, str):
        user_queries = [user_queries]

    final_response_text = ""  # we will return the merged text for the LAST query

    for query in user_queries:
        print(f"\nUser > {query}")
        query_content = types.Content(role="user", parts=[types.Part(text=query)])

        # Collect ALL text pieces for this single query
        collected_text_parts: list[str] = []

        # STREAM HANDLING 
        async for event in runner_instance.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=query_content,
        ):
            # Some ADK events may not have `.content`; guard for safety
            content = getattr(event, "content", None)
            if content and getattr(content, "parts", None):
                for part in content.parts:

                    # CASE A: It's a Function Call (Tool Use)
                    if getattr(part, "function_call", None):
                        func_name = part.function_call.name
                        print(f"   [⚙️ Tool Call]: {func_name}...")

                    # CASE B: It's a Function Response (Result from Tool)
                    elif getattr(part, "function_response", None):
                        print(f"   [✅ Tool Result]: Data received.")

                    # CASE C: It's actual Text (Chat)
                    elif getattr(part, "text", None):
                        text = (part.text or "").strip()
                        if text and text != "None":
                            # Log each message as it streams
                            role = (content.role or "model").capitalize()
                            print(f"\n{role} > {text}\n")

                            # Store it so we don't lose earlier responses
                            collected_text_parts.append(text)

        # After finishing the stream for this query,
        # join everything into a single response string.
        if collected_text_parts:
            final_response_text = "\n\n".join(collected_text_parts)
        else:
            final_response_text = "No text response generated."

    # If multiple user_queries are sent, we return the combined text
    # of the *last* one, which is usual for your API pattern.
    return final_response_text
