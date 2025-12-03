from __future__ import annotations

import sys
import traceback
from typing import Any, Optional, Sequence

from dotenv import load_dotenv

from google.genai import types as genai_types
from google.adk.agents import SequentialAgent, Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService

from src.bitemate.core.exception import AppException
from src.bitemate.core.logger import setup_logger
from src.bitemate.utils.params import load_params
from src.bitemate.utils.run_sessions import run_session
from src.bitemate.agents.router_agent import create_router_agent
from src.bitemate.agents.meal_generator import MealPlannerPipeline

# load .env for local/dev; in prod prefer a secrets manager
load_dotenv()

LOGGER = setup_logger(name="BiteMateOrchestrator", log_file_name="orchestrator.log")

CONFIG_REL_PATH = "src/bitemate/config/params.yaml"


class BiteMateOrchestrator:
    """
    Master orchestrator that:
      1. Uses a low-latency Router Agent to determine intent (UPDATE_PROFILE / GENERATE_PLAN / FULL_FLOW)
      2. Builds the proper execution agent(s) from MealPlannerPipeline
      3. Runs the selected agent(s) in a Runner with shared session & memory services

    Dependencies are injectable for testing:
      - meal_planner_pipeline: pipeline instance providing agent factories
      - session_service / memory_service: services to share context between runs
      - allowed_router_outputs: explicit set of permitted keywords
    """

    DEFAULT_ALLOWED = ("UPDATE_PROFILE", "GENERATE_PLAN", "FULL_FLOW")

    def __init__(
        self,
        config_path: str = CONFIG_REL_PATH,
        meal_planner_pipeline: Optional[MealPlannerPipeline] = None,
        session_service: Optional[Any] = None,
        memory_service: Optional[Any] = None,
        model_name: Optional[str] = None,
        retry_options: Optional[genai_types.HttpRetryOptions] = None,
        allowed_router_outputs: Optional[Sequence[str]] = None,
    ) -> None:
        try:
            LOGGER.info("Initializing BiteMateOrchestrator (config_path=%s)", config_path)
            self.params = load_params(config_path)
            orchestrator_agent_params = self.params.get("orchestrator_agent", {})

            # Logging target file from config if provided
            file_path = orchestrator_agent_params.get("file_path", "orchestrator.log")
            # Reconfigure logger file name if different than default (optional)
            # Note: setup_logger returns a logger; this call is idempotent in your setup
            self.logger = setup_logger(name="BiteMateOrchestrator", log_file_name=file_path)

            # Pipeline: allow injection for unit tests; otherwise create a default one
            self.meal_planner_pipeline = meal_planner_pipeline or MealPlannerPipeline(config_path=config_path)

            # Services for Runner and state sharing
            self.session_service = session_service or InMemorySessionService()
            self.memory_service = memory_service or InMemoryMemoryService()

            # Model selection for router (default falls back to params or provided model_name)
            self.model_name = model_name or orchestrator_agent_params.get("model_name", "gemini-2.0-flash")
            self.retry_options = retry_options  # pass to router factory if present

            self.allowed_router_outputs = set(allowed_router_outputs or self.DEFAULT_ALLOWED)

            LOGGER.info("Orchestrator initialized (router model=%s).", self.model_name)

        except Exception as exc:
            tb = traceback.format_exc()
            LOGGER.exception("Failed to initialize BiteMateOrchestrator: %s\n%s", exc, tb)
            raise AppException(f"Initialization Failed: {exc}", sys) from exc

    def _get_execution_agent(self, decision: str) -> Agent:
        """
        Build and return the execution Agent (or SequentialAgent) based on router decision.
        Raises AppException for unrecoverable errors during construction.
        """
        try:
            if decision == "UPDATE_PROFILE":
                self.logger.info("Router decision => UPDATE_PROFILE: creating profiler agent.")
                return self.meal_planner_pipeline.create_profiler_agent()

            if decision == "GENERATE_PLAN":
                self.logger.info("Router decision => GENERATE_PLAN: creating meal generator agent.")
                return self.meal_planner_pipeline.create_meal_generator_agent()

            if decision == "FULL_FLOW":
                self.logger.info("Router decision => FULL_FLOW: creating SequentialAgent (profile -> plan).")
                profiler = self.meal_planner_pipeline.create_profiler_agent()
                planner = self.meal_planner_pipeline.create_meal_generator_agent()
                return SequentialAgent(
                    name="FullWorkflow",
                    description="Profile then generate meal plan.",
                    sub_agents=[profiler, planner],
                )

            # Fallback: build a safe sequential flow
            self.logger.warning("Unknown decision in factory: %s. Falling back to FULL_FLOW.", decision)
            profiler = self.meal_planner_pipeline.create_profiler_agent()
            planner = self.meal_planner_pipeline.create_meal_generator_agent()
            return SequentialAgent(name="FallbackFlow", description="Fallback profile->plan flow", sub_agents=[profiler, planner])

        except Exception as exc:
            tb = traceback.format_exc()
            self.logger.exception("Error building execution agent: %s\n%s", exc, tb)
            raise AppException(f"Factory Build Failed: {exc}", sys) from exc

    @staticmethod
    def _normalize_router_result(router_result: Any) -> str:
        """
        Accepts the raw output from run_session and returns a normalized uppercase string.
        Handles common shapes: string, object with .text, list, etc.
        """
        if router_result is None:
            return ""

        # If run_session returns an object with text property (common), prefer it
        if hasattr(router_result, "text"):
            raw = str(getattr(router_result, "text") or "")
        else:
            raw = str(router_result)

        # Strip whitespace, backticks and make uppercase
        return raw.strip().replace("`", "").upper()

    async def run_flow(self, user_input: str, user_id: str, session_id: str = "default") -> Any:
        """
        Public async entrypoint to run a user request.

        Steps:
          1. Run Router Agent in a temporary session (to avoid polluting user chat).
          2. Validate router decision and build execution agent(s).
          3. Run the chosen agent(s) with shared session & memory.

        Returns:
            The result of run_session for the main agent run (shape depends on your run_session implementation).
        """
        try:
            self.logger.info("Running flow for user=%s, session=%s", user_id, session_id)

            # Build router agent with same retry options used elsewhere (optional)
            router_agent = create_router_agent(model_name=self.model_name, retry_options=self.retry_options)

            router_runner = Runner(
                app_name="agents",
                agent=router_agent,
                session_service=self.session_service,
                memory_service=self.memory_service,
            )

            # Execute routing in an isolated session name to keep routing internal
            router_session_name = f"{session_id}_router"
            router_result = await run_session(
                runner_instance=router_runner,
                user_queries=[user_input],
                session_name=router_session_name,
                user_id=user_id,
            )
            
            decision = self._normalize_router_result(router_result)
            self.logger.info("Router decision (raw): %s", decision)

            # Validate or fallback
            if decision not in self.allowed_router_outputs:
                self.logger.warning("Router produced unexpected decision '%s'. Allowed: %s. Defaulting to FULL_FLOW.", decision, self.allowed_router_outputs)
                decision = "FULL_FLOW"

            # Build the actual execution agent (profiler/planner/sequential)
            execution_agent = self._get_execution_agent(decision)

            main_runner = Runner(
                app_name="agents",
                agent=execution_agent,
                session_service=self.session_service,
                memory_service=self.memory_service,
            )

            # Run the selected agent(s) with the real session (this will be visible in user chat)
            result = await run_session(
                runner_instance=main_runner,
                user_queries=[user_input],
                session_name=session_id,
                user_id=user_id,
            )

            self.logger.info("Main flow execution complete for user=%s", user_id)
            return result

        except Exception as exc:
            tb = traceback.format_exc()
            self.logger.exception("Orchestration failed for user=%s: %s\n%s", user_id, exc, tb)
            raise AppException(f"Orchestration Failed: {exc}", sys) from exc
