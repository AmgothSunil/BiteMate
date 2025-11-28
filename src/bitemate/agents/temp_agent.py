from google.adk.agents import Agent, LlmAgent
from google.adk.tools import google_search
from google.adk.models.google_llm import Gemini
from google.genai import types
from google.adk.runners import Runner, InMemoryRunner
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService

import os
from dotenv import load_dotenv
load_dotenv()

os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")

# from src.bitemate.utils.run_sessions import run_session
from src.bitemate.agents.temp_run_session import SessionManager



import asyncio


retry_config = types.HttpRetryOptions(
    attempts=5,
    initial_delay=1,
    exp_base=7,
    http_status_codes=[429, 500, 503, 504]
)

personal_agent = Agent(
    name="Personal_Assistant",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=retry_config
    ),
    instruction="You are a personel assistant for users. Provide answers based on user queries",
    tools=[google_search]
)


memery_service = InMemoryMemoryService()
session_service = InMemorySessionService()

# Create SessionManager with the same session_service that will be used by the runner
session_manager = SessionManager("src/bitemate/config/params.yaml", session_service=session_service)

runner = Runner(
    app_name="agents",
    agent=personal_agent,
    session_service=session_service,
    memory_service=memery_service
)


def invoke(message: str):
    responses = asyncio.run(session_manager.run_session(runner_instance=runner, user_queries=message, session_id="default"))
    # Return the first response since we're passing a single query
    return responses[0] if responses else None

response = invoke("what is cybersecurity")

print(response)